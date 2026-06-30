"""STT 전사 서비스 — Naver Clova Speech 연동.

흐름:
    enqueue_transcription(): 검증 → job 등록(processing) → 백그라운드에 Clova 호출 예약
    백그라운드 워커: Clova 동기 호출 → 응답 정규화 → text 후처리 → 결과 저장
    fetch_transcription_result(): in-memory store 조회

job 저장은 프로세스 내 dict (MVP). 재시작 시 유실되며, 운영 시 Redis/DB로 승격.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field

from fastapi import UploadFile

from app.services import audit_log
from app.services.clova_client import (
    ClovaConfigError,
    ClovaRequestError,
    transcribe_audio,
)
from app.services.postprocess import postprocess_segments

MAX_AUDIO_SIZE_BYTES = 2 * 1024 * 1024 * 1024  # 2GB (최대 1시간 분량 WAV 대응)
SUPPORTED_AUDIO_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/mp4",
        "audio/x-m4a",
        "audio/webm",
        "audio/ogg",
    }
)

STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


class TranscriberError(Exception):
    """전사 처리 중 발생한 일반 오류."""


class AudioFileRequiredError(TranscriberError):
    """오디오 파일이 누락되었거나 파일명이 비정상."""


class UnsupportedAudioFormatError(TranscriberError):
    """지원하지 않는 Content-Type."""

    def __init__(self, content_type: str | None) -> None:
        super().__init__(f"unsupported content type: {content_type}")
        self.content_type = content_type


class AudioFileTooLargeError(TranscriberError):
    """업로드 용량 제한 초과."""

    def __init__(self, max_bytes: int = MAX_AUDIO_SIZE_BYTES) -> None:
        super().__init__(f"audio file too large (max {max_bytes} bytes)")
        self.max_bytes = max_bytes


class TranscriptionFailedError(TranscriberError):
    """전사 작업 실패."""


class TranscriptionTimeoutError(TranscriberError):
    """전사 처리 타임아웃."""


class JobNotFoundError(TranscriberError):
    """존재하지 않는 job_id."""


class TranscriptionInProgressError(TranscriberError):
    """전사 작업 진행 중."""


@dataclass
class TranscribeJob:
    job_id: str
    status: str
    message: str | None = None


@dataclass
class TranscriptResult:
    job_id: str
    status: str
    text: str
    segments: list[dict] = field(default_factory=list)


@dataclass
class _JobRecord:
    status: str
    text: str = ""
    segments: list[dict] = field(default_factory=list)
    error: str | None = None
    filename: str | None = None


_JOBS: dict[str, _JobRecord] = {}
_JOBS_LOCK = threading.Lock()


def _store_job(job_id: str, record: _JobRecord) -> None:
    with _JOBS_LOCK:
        _JOBS[job_id] = record


def _get_job(job_id: str) -> _JobRecord | None:
    with _JOBS_LOCK:
        return _JOBS.get(job_id)


def _validate_upload(audio_file: UploadFile, content_length: int | None) -> None:
    if not audio_file.filename:
        raise AudioFileRequiredError("audio_file is required")
    if audio_file.content_type not in SUPPORTED_AUDIO_CONTENT_TYPES:
        raise UnsupportedAudioFormatError(audio_file.content_type)
    if content_length is not None and content_length > MAX_AUDIO_SIZE_BYTES:
        raise AudioFileTooLargeError()


def _run_transcription(
    job_id: str,
    audio_bytes: bytes,
    filename: str,
    content_type: str,
) -> None:
    """백그라운드에서 실행되는 Clova 호출 + 후처리."""
    try:
        clova_result = transcribe_audio(
            audio_bytes,
            filename=filename,
            content_type=content_type,
        )
        processed = postprocess_segments(
            clova_result.segments, skip_diarization=True
        )
        _store_job(
            job_id,
            _JobRecord(
                status=STATUS_COMPLETED,
                text=processed.text,
                segments=processed.segments,
                filename=filename,
            ),
        )
        audit_log.log_stt_result(
            job_id=job_id,
            status=STATUS_COMPLETED,
            text=processed.text,
            segments=processed.segments,
        )
    except (ClovaConfigError, ClovaRequestError) as exc:
        _store_job(
            job_id,
            _JobRecord(
                status=STATUS_FAILED,
                error=str(exc),
                filename=filename,
            ),
        )
        audit_log.log_stt_result(
            job_id=job_id, status=STATUS_FAILED, error=str(exc)
        )
    except Exception as exc:  # noqa: BLE001 — 백그라운드 실패는 모두 기록
        _store_job(
            job_id,
            _JobRecord(
                status=STATUS_FAILED,
                error=f"unexpected error: {exc}",
                filename=filename,
            ),
        )
        audit_log.log_stt_result(
            job_id=job_id, status=STATUS_FAILED, error=f"unexpected error: {exc}"
        )


def enqueue_transcription(
    audio_file: UploadFile,
    *,
    content_length: int | None = None,
    background_runner=None,
) -> TranscribeJob:
    """오디오 파일 검증 → job 생성 → 백그라운드 전사 예약.

    background_runner: callable(job_id, audio_bytes, filename, content_type) -> None
        FastAPI BackgroundTasks.add_task 어댑터. None이면 동기 실행(테스트용).
    """
    _validate_upload(audio_file, content_length)

    audio_bytes = audio_file.file.read()
    if len(audio_bytes) > MAX_AUDIO_SIZE_BYTES:
        raise AudioFileTooLargeError()

    job_id = uuid.uuid4().hex
    _store_job(
        job_id,
        _JobRecord(status=STATUS_PROCESSING, filename=audio_file.filename),
    )
    audit_log.log_stt_request(
        job_id=job_id,
        filename=audio_file.filename,
        content_type=audio_file.content_type,
        size_bytes=len(audio_bytes),
    )
    audit_log.log_stt_audio(
        job_id=job_id,
        filename=audio_file.filename,
        content_type=audio_file.content_type,
        audio_bytes=audio_bytes,
    )

    runner_args = (
        job_id,
        audio_bytes,
        audio_file.filename,
        audio_file.content_type or "application/octet-stream",
    )
    if background_runner is None:
        _run_transcription(*runner_args)
    else:
        background_runner(_run_transcription, *runner_args)

    return TranscribeJob(
        job_id=job_id,
        status=STATUS_PROCESSING,
        message=f"queued '{audio_file.filename}'",
    )


def fetch_transcription_result(job_id: str) -> TranscriptResult:
    """job_id로 전사 결과 조회."""
    record = _get_job(job_id)
    if record is None:
        raise JobNotFoundError("unknown job_id")
    if record.status == STATUS_PROCESSING:
        raise TranscriptionInProgressError("transcription is still in progress")
    if record.status == STATUS_FAILED:
        raise TranscriptionFailedError(record.error or "transcription failed")

    return TranscriptResult(
        job_id=job_id,
        status=record.status,
        text=record.text,
        segments=record.segments,
    )
