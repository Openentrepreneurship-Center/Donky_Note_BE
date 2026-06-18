"""S3 감사 로그 — STT/요약 요청·응답을 best-effort로 적재.

설계 원칙:
    - 로그 업로드 실패는 서비스 흐름을 막지 않는다 (조용히 실패 + stderr).
    - 키 구조는 날짜·이벤트·식별자로 분리해 콘솔에서 사람이 따라가기 쉽게.
    - 외부에 노출되는 입출력만 저장한다 (Clova raw 응답·내부 디버깅 데이터는 제외).

키 구조:
    {prefix}/{YYYY-MM-DD}/stt/{job_id}/request.json
    {prefix}/{YYYY-MM-DD}/stt/{job_id}/result.json
    {prefix}/{YYYY-MM-DD}/summarize/{request_id}/request.json
    {prefix}/{YYYY-MM-DD}/summarize/{request_id}/response.json

환경변수:
    AWS_S3_LOG_BUCKET       - 필수. 로그 적재 버킷 이름
    AWS_REGION              - 필수. 버킷 리전 (예: ap-northeast-2)
    AWS_S3_LOG_PREFIX       - 선택. 키 prefix (기본 'donkey-note')
    AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY - 선택. IAM Role 쓰면 생략 가능
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

DEFAULT_PREFIX = "donkey-note"


@lru_cache(maxsize=1)
def _s3_client():
    region = os.environ.get("AWS_REGION")
    if not region:
        return None
    try:
        return boto3.client("s3", region_name=region)
    except (BotoCoreError, ClientError) as exc:
        print(f"[audit_log] S3 client init failed: {exc}", file=sys.stderr)
        return None


def _bucket() -> str | None:
    return os.environ.get("AWS_S3_LOG_BUCKET")


def _prefix() -> str:
    return os.environ.get("AWS_S3_LOG_PREFIX", DEFAULT_PREFIX).strip("/")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _put_json(key: str, payload: dict[str, Any]) -> None:
    bucket = _bucket()
    client = _s3_client()
    if not bucket or client is None:
        # 환경변수 미설정 → 감사 로그 비활성화. 서비스에는 영향 없음.
        return

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="application/json; charset=utf-8",
        )
    except (BotoCoreError, ClientError) as exc:
        # best-effort: 절대 호출자에게 전파하지 않음.
        print(f"[audit_log] put_object failed for {key}: {exc}", file=sys.stderr)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- STT ----------------------------------------------------------------

def log_stt_request(
    *,
    job_id: str,
    filename: str,
    content_type: str | None,
    size_bytes: int,
) -> None:
    key = f"{_prefix()}/{_today()}/stt/{job_id}/request.json"
    _put_json(
        key,
        {
            "event": "stt.request",
            "timestamp": _now_iso(),
            "job_id": job_id,
            "filename": filename,
            "content_type": content_type,
            "size_bytes": size_bytes,
        },
    )


def log_stt_result(
    *,
    job_id: str,
    status: str,
    text: str | None = None,
    segments: list[dict] | None = None,
    error: str | None = None,
) -> None:
    key = f"{_prefix()}/{_today()}/stt/{job_id}/result.json"
    _put_json(
        key,
        {
            "event": "stt.result",
            "timestamp": _now_iso(),
            "job_id": job_id,
            "status": status,
            "text": text,
            "segments": segments,
            "error": error,
        },
    )


# --- Summarize ---------------------------------------------------------

def log_summarize_request(
    *,
    request_id: str,
    segments: list[dict] | None,
    text: str | None,
    framework: str | None,
    language: str | None,
) -> None:
    key = f"{_prefix()}/{_today()}/summarize/{request_id}/request.json"
    _put_json(
        key,
        {
            "event": "summarize.request",
            "timestamp": _now_iso(),
            "request_id": request_id,
            "segments": segments,
            "text": text,
            "framework": framework,
            "language": language,
        },
    )


def log_summarize_response(
    *,
    request_id: str,
    framework: str | None,
    reason: str | None,
    summary: str | None,
    confidence: float | None,
    error: str | None = None,
) -> None:
    key = f"{_prefix()}/{_today()}/summarize/{request_id}/response.json"
    _put_json(
        key,
        {
            "event": "summarize.response",
            "timestamp": _now_iso(),
            "request_id": request_id,
            "framework": framework,
            "reason": reason,
            "summary": summary,
            "confidence": confidence,
            "error": error,
        },
    )
