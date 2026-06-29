from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile

load_dotenv()
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas import (
    ErrorResponse,
    FrameworkInfo,
    SummarizeRequest,
    SummarizeResponse,
    TranscribeResponse,
    TranscriptResultResponse,
)
import uuid

from app.prompts import FRAMEWORK_CATALOG
from app.services import audit_log
from app.services.postprocess import assemble_transcript
from app.services.summarizer import (
    FrameworkSelectionError,
    SummarizerError,
    summarize_transcript,
)
from app.services.transcriber import (
    AudioFileRequiredError,
    AudioFileTooLargeError,
    JobNotFoundError,
    MAX_AUDIO_SIZE_BYTES,
    TranscriptionFailedError,
    TranscriptionInProgressError,
    TranscriptionTimeoutError,
    UnsupportedAudioFormatError,
    enqueue_transcription,
    fetch_transcription_result,
)

app = FastAPI(
    title="DonkeyNote STT & Summarize API",
    version="0.2.0",
    description=(
        "화자분리 STT 전사 + 5개 프레임워크 자동 요약 API.\n\n"
        "흐름: `POST /stt/transcribe` → `job_id` 받기 → `GET /stt/results/{job_id}` 폴링 "
        "→ 결과 segments를 그대로 `POST /summarize`에 전달.\n\n"
        "요약 프레임워크: operations / planning / solving / kpt / reporting"
    ),
    openapi_tags=[
        {"name": "health", "description": "헬스체크"},
        {"name": "stt", "description": "오디오 전사 (화자분리 포함)"},
        {"name": "summarize", "description": "전사 결과 자동 요약"},
        {"name": "frameworks", "description": "지원 요약 프레임워크 목록"},
    ],
)

ERROR_CODE_INVALID_REQUEST = "INVALID_REQUEST"
ERROR_CODE_AUDIO_FILE_REQUIRED = "AUDIO_FILE_REQUIRED"
ERROR_CODE_UNSUPPORTED_AUDIO_FORMAT = "UNSUPPORTED_AUDIO_FORMAT"
ERROR_CODE_AUDIO_FILE_TOO_LARGE = "AUDIO_FILE_TOO_LARGE"
ERROR_CODE_JOB_NOT_FOUND = "JOB_NOT_FOUND"
ERROR_CODE_TRANSCRIPTION_IN_PROGRESS = "TRANSCRIPTION_IN_PROGRESS"
ERROR_CODE_TRANSCRIPTION_FAILED = "TRANSCRIPTION_FAILED"
ERROR_CODE_TRANSCRIPTION_TIMEOUT = "TRANSCRIPTION_TIMEOUT"
ERROR_CODE_INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
ERROR_CODE_SUMMARY_INPUT_REQUIRED = "SUMMARY_INPUT_REQUIRED"
ERROR_CODE_UNSUPPORTED_FRAMEWORK = "UNSUPPORTED_FRAMEWORK"
ERROR_CODE_SUMMARY_FAILED = "SUMMARY_FAILED"


def raise_api_error(
    status_code: int, code: str, message: str, details: list[dict] | None = None
) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "details": details},
    )


@app.get("/health", tags=["health"], summary="헬스체크")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/frameworks",
    response_model=list[FrameworkInfo],
    tags=["frameworks"],
    summary="지원 요약 프레임워크 목록",
)
def list_frameworks() -> list[FrameworkInfo]:
    """요약 시 사용할 수 있는 프레임워크 목록을 반환.

    각 항목의 `framework` 값을 `POST /summarize`의 framework 필드로 강제 지정할 수 있다.
    """
    return [FrameworkInfo(**item) for item in FRAMEWORK_CATALOG]


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            code=ERROR_CODE_INVALID_REQUEST,
            message="request validation failed",
            details=exc.errors(),
        ).model_dump(),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        payload = ErrorResponse(
            code=exc.detail.get("code", ERROR_CODE_INTERNAL_SERVER_ERROR),
            message=exc.detail.get("message", "request failed"),
            details=exc.detail.get("details"),
        )
    else:
        payload = ErrorResponse(
            code=ERROR_CODE_INTERNAL_SERVER_ERROR,
            message=str(exc.detail),
            details=None,
        )
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump())


@app.post(
    "/stt/transcribe",
    response_model=TranscribeResponse,
    tags=["stt"],
    summary="오디오 업로드 + 전사 비동기 시작",
    responses={
        400: {"model": ErrorResponse, "description": "AUDIO_FILE_REQUIRED"},
        413: {"model": ErrorResponse, "description": "AUDIO_FILE_TOO_LARGE"},
        415: {"model": ErrorResponse, "description": "UNSUPPORTED_AUDIO_FORMAT"},
        500: {"model": ErrorResponse, "description": "TRANSCRIPTION_FAILED"},
        504: {"model": ErrorResponse, "description": "TRANSCRIPTION_TIMEOUT"},
    },
)
async def request_transcription(
    request: Request,
    background_tasks: BackgroundTasks,
    audio_file: UploadFile = File(...),
) -> TranscribeResponse:
    """STT 전사 요청을 받는 엔드포인트."""
    raw_length = request.headers.get("content-length")
    content_length = int(raw_length) if raw_length and raw_length.isdigit() else None

    try:
        job = enqueue_transcription(
            audio_file,
            content_length=content_length,
            background_runner=background_tasks.add_task,
        )
    except AudioFileRequiredError as exc:
        raise_api_error(400, ERROR_CODE_AUDIO_FILE_REQUIRED, str(exc))
    except UnsupportedAudioFormatError as exc:
        raise_api_error(415, ERROR_CODE_UNSUPPORTED_AUDIO_FORMAT, str(exc))
    except AudioFileTooLargeError:
        raise_api_error(
            413,
            ERROR_CODE_AUDIO_FILE_TOO_LARGE,
            f"audio file too large (max {MAX_AUDIO_SIZE_BYTES} bytes)",
        )
    except TranscriptionFailedError as exc:
        raise_api_error(500, ERROR_CODE_TRANSCRIPTION_FAILED, str(exc))
    except TranscriptionTimeoutError as exc:
        raise_api_error(504, ERROR_CODE_TRANSCRIPTION_TIMEOUT, str(exc))

    return TranscribeResponse(
        job_id=job.job_id,
        status=job.status,
        message=job.message,
    )


@app.post(
    "/summarize",
    response_model=SummarizeResponse,
    tags=["summarize"],
    summary="전사 결과 자동 프레임워크 요약",
    responses={
        400: {
            "model": ErrorResponse,
            "description": "SUMMARY_INPUT_REQUIRED / UNSUPPORTED_FRAMEWORK",
        },
        500: {"model": ErrorResponse, "description": "SUMMARY_FAILED"},
    },
)
def summarize(payload: SummarizeRequest) -> SummarizeResponse:
    """STT 전사 텍스트를 받아 적합한 프레임워크로 자동 요약.

    segments 우선. 없으면 text fallback. 둘 다 없으면 400.
    """
    request_id = uuid.uuid4().hex
    seg_dicts: list[dict] | None = None

    if payload.segments:
        seg_dicts = [
            {"text": s.text, "speaker": s.speaker}
            for s in payload.segments
            if s.text and s.text.strip()
        ]
        if not seg_dicts:
            audit_log.log_summarize_request(
                request_id=request_id,
                segments=[],
                text=None,
                framework=payload.framework,
                language=payload.language,
            )
            raise_api_error(
                400, ERROR_CODE_SUMMARY_INPUT_REQUIRED, "segments are empty"
            )
        transcript_text = assemble_transcript(seg_dicts)
    elif payload.text and payload.text.strip():
        transcript_text = payload.text
    else:
        raise_api_error(
            400,
            ERROR_CODE_SUMMARY_INPUT_REQUIRED,
            "either segments or text is required",
        )

    audit_log.log_summarize_request(
        request_id=request_id,
        segments=seg_dicts,
        text=payload.text if seg_dicts is None else None,
        framework=payload.framework,
        language=payload.language,
    )

    try:
        result = summarize_transcript(
            transcript_text,
            framework=payload.framework,
            language=payload.language or "ko",
        )
    except FrameworkSelectionError as exc:
        audit_log.log_summarize_response(
            request_id=request_id,
            framework=None,
            reason=None,
            summary=None,
            confidence=None,
            error=str(exc),
        )
        raise_api_error(400, ERROR_CODE_UNSUPPORTED_FRAMEWORK, str(exc))
    except SummarizerError as exc:
        audit_log.log_summarize_response(
            request_id=request_id,
            framework=None,
            reason=None,
            summary=None,
            confidence=None,
            error=str(exc),
        )
        raise_api_error(500, ERROR_CODE_SUMMARY_FAILED, str(exc))

    audit_log.log_summarize_response(
        request_id=request_id,
        framework=result.framework,
        reason=result.reason,
        summary=result.summary,
        confidence=result.confidence,
    )

    return SummarizeResponse(
        framework=result.framework,
        reason=result.reason,
        summary=result.summary,
        confidence=result.confidence,
    )


@app.get(
    "/stt/results/{job_id}",
    response_model=TranscriptResultResponse,
    tags=["stt"],
    summary="전사 결과 조회 (폴링)",
    responses={
        404: {"model": ErrorResponse, "description": "JOB_NOT_FOUND"},
        409: {"model": ErrorResponse, "description": "TRANSCRIPTION_IN_PROGRESS"},
        500: {"model": ErrorResponse, "description": "TRANSCRIPTION_FAILED"},
    },
)
def get_transcription_result(job_id: str) -> TranscriptResultResponse:
    """전사 결과 조회."""
    try:
        result = fetch_transcription_result(job_id)
    except TranscriptionInProgressError as exc:
        raise_api_error(409, ERROR_CODE_TRANSCRIPTION_IN_PROGRESS, str(exc))
    except TranscriptionFailedError as exc:
        raise_api_error(
            500,
            ERROR_CODE_TRANSCRIPTION_FAILED,
            str(exc),
            details=[{"reason": "asr engine error"}],
        )
    except JobNotFoundError as exc:
        raise_api_error(404, ERROR_CODE_JOB_NOT_FOUND, str(exc))

    return TranscriptResultResponse(
        job_id=result.job_id,
        status=result.status,
        text=result.text,
        segments=result.segments,
    )
