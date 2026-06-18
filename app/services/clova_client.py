"""Naver Clova Speech (Long Sentence) HTTP 클라이언트.

공식 엔드포인트: POST {INVOKE_URL}/recognizer/upload
요청: multipart - 'media' (오디오 파일) + 'params' (JSON 문자열)
응답: 전사 텍스트 + 화자분리된 segments (시간단위 ms)

환경변수:
    CLOVA_SPEECH_INVOKE_URL  - 도메인별 invoke URL
    CLOVA_SPEECH_API_KEY      - 시크릿 키
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import httpx


CLOVA_TIMEOUT_SECONDS = 3600.0  # 긴 음성(sync 최대 2시간) 처리 대비


class ClovaConfigError(RuntimeError):
    """Clova 환경변수 누락."""


class ClovaRequestError(RuntimeError):
    """Clova API 호출 실패."""


@dataclass
class ClovaTranscription:
    text: str
    segments: list[dict]
    raw: dict


def _load_config() -> tuple[str, str]:
    invoke_url = os.environ.get("CLOVA_SPEECH_INVOKE_URL")
    api_key = os.environ.get("CLOVA_SPEECH_API_KEY")
    if not invoke_url or not api_key:
        raise ClovaConfigError(
            "CLOVA_SPEECH_INVOKE_URL / CLOVA_SPEECH_API_KEY 환경변수가 필요합니다."
        )
    return invoke_url.rstrip("/"), api_key


def _normalize_segments(raw_segments: list[dict]) -> list[dict]:
    """Clova segment → 내부 표준 schema (start/end 초 단위, speaker 라벨)."""
    normalized: list[dict] = []
    for idx, seg in enumerate(raw_segments):
        start_ms = seg.get("start", 0)
        end_ms = seg.get("end", start_ms)
        speaker_obj = seg.get("speaker") or {}
        speaker_label = speaker_obj.get("label") or speaker_obj.get("name") or "1"
        normalized.append(
            {
                "index": idx,
                "timestamp": {
                    "start": round(start_ms / 1000.0, 3),
                    "end": round(end_ms / 1000.0, 3),
                },
                "text": seg.get("text", ""),
                "speaker": f"참석자{speaker_label}",
            }
        )
    return normalized


def transcribe_audio(
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    *,
    language: str = "ko-KR",
    enable_diarization: bool = True,
) -> ClovaTranscription:
    """Clova Speech Long Sentence 동기 호출.

    백그라운드 태스크에서 호출되므로 함수 자체는 blocking httpx 사용.
    """
    invoke_url, api_key = _load_config()

    params: dict = {
        "language": language,
        "completion": "sync",
    }
    if enable_diarization:
        params["diarization"] = {"enable": True}

    headers = {
        "X-CLOVASPEECH-API-KEY": api_key,
    }
    files = {
        "media": (filename, audio_bytes, content_type),
        "params": (None, json.dumps(params), "application/json"),
    }

    try:
        with httpx.Client(timeout=CLOVA_TIMEOUT_SECONDS) as client:
            resp = client.post(
                f"{invoke_url}/recognizer/upload",
                headers=headers,
                files=files,
            )
    except httpx.HTTPError as exc:
        raise ClovaRequestError(f"clova request failed: {exc}") from exc

    if resp.status_code >= 400:
        raise ClovaRequestError(
            f"clova returned {resp.status_code}: {resp.text[:500]}"
        )

    try:
        body = resp.json()
    except ValueError as exc:
        raise ClovaRequestError(f"clova returned non-json body: {exc}") from exc

    if body.get("result") and body["result"] not in ("COMPLETED", "OK"):
        raise ClovaRequestError(
            f"clova non-completed result: {body.get('result')} / {body.get('message')}"
        )

    raw_segments = body.get("segments") or []
    return ClovaTranscription(
        text=body.get("text", ""),
        segments=_normalize_segments(raw_segments),
        raw=body,
    )
