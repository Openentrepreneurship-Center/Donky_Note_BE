"""STT 전사 텍스트를 프레임워크 자동 선택 + 요약 처리하는 서비스.

흐름:
    1차 LLM 호출 - 어떤 요약 프레임워크가 적합한지 판단 (operations / planning /
       solving / kpt / reporting 중 하나).
    2차 LLM 호출 - 선택된 프레임워크 프롬프트로 본문 요약.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from openai import OpenAI

from app.prompts import (
    FRAMEWORK_PROMPTS,
    ROUTER_SYSTEM_PROMPT,
    SUPPORTED_FRAMEWORKS,
)


DEFAULT_ROUTER_MODEL = os.getenv("OPENAI_ROUTER_MODEL", "gpt-4o-mini")
DEFAULT_SUMMARY_MODEL = os.getenv("OPENAI_SUMMARY_MODEL", "gpt-4o-mini")


class SummarizerError(Exception):
    """요약 처리 중 발생한 일반 오류."""


class FrameworkSelectionError(SummarizerError):
    """1차 호출 결과를 파싱하지 못했거나 알 수 없는 프레임워크가 반환된 경우."""


@dataclass
class SummarizeResult:
    framework: str
    reason: str
    summary: str
    confidence: float | None = None


def _client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SummarizerError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=api_key)


def _select_framework(client: OpenAI, text: str) -> tuple[str, str, float | None]:
    completion = client.chat.completions.create(
        model=DEFAULT_ROUTER_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    )
    raw = completion.choices[0].message.content or ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FrameworkSelectionError(f"router returned non-JSON: {raw!r}") from exc

    framework = (parsed.get("framework") or "").strip().lower()
    reason = (parsed.get("reason") or "").strip()
    if framework not in SUPPORTED_FRAMEWORKS:
        raise FrameworkSelectionError(f"unknown framework: {framework!r}")

    raw_conf = parsed.get("confidence")
    confidence: float | None
    try:
        confidence = float(raw_conf) if raw_conf is not None else None
    except (TypeError, ValueError):
        confidence = None
    if confidence is not None:
        confidence = max(0.0, min(1.0, confidence))

    return framework, reason, confidence


def _summarize_with_framework(
    client: OpenAI, framework: str, text: str, language: str
) -> str:
    system_prompt = FRAMEWORK_PROMPTS[framework]
    user_prompt = (
        f"Transcript language hint: {language}\n"
        f"Output language: {language}\n\n"
        "Transcript:\n"
        f"{text}"
    )
    completion = client.chat.completions.create(
        model=DEFAULT_SUMMARY_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return (completion.choices[0].message.content or "").strip()


def summarize_transcript(
    text: str,
    *,
    framework: str | None = None,
    language: str = "ko",
) -> SummarizeResult:
    client = _client()

    confidence: float | None
    if framework is not None:
        framework_normalized = framework.strip().lower()
        if framework_normalized not in SUPPORTED_FRAMEWORKS:
            raise FrameworkSelectionError(
                f"unknown framework: {framework!r}"
            )
        chosen = framework_normalized
        reason = "caller-specified framework"
        confidence = None
    else:
        chosen, reason, confidence = _select_framework(client, text)

    summary = _summarize_with_framework(client, chosen, text, language)
    return SummarizeResult(
        framework=chosen,
        reason=reason,
        summary=summary,
        confidence=confidence,
    )
