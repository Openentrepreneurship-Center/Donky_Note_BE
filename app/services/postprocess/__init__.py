"""전사 결과 후처리 파이프라인.

흐름:
    raw segments → diarize → refine → assemble → PostprocessedTranscript
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.postprocess.assembly import assemble_transcript
from app.services.postprocess.diarization import diarize_segments
from app.services.postprocess.refinement import clean_segment_text, refine_segments


class PostprocessorError(Exception):
    """후처리 중 발생한 일반 오류."""


@dataclass
class PostprocessedTranscript:
    text: str
    segments: list[dict]


def postprocess_segments(
    segments: list[dict], *, skip_diarization: bool = False
) -> PostprocessedTranscript:
    """전체 후처리 파이프라인: (diarization →) 텍스트 정제 → 본문 조립.

    skip_diarization=True: 입력 segment에 이미 speaker가 부여돼 있을 때
    내부 diarize 단계를 건너뜀 (예: Clova Speech 결과).
    """
    staged = segments if skip_diarization else diarize_segments(segments)
    refined = refine_segments(staged)
    text = assemble_transcript(refined)
    return PostprocessedTranscript(text=text, segments=refined)


__all__ = [
    "PostprocessedTranscript",
    "PostprocessorError",
    "assemble_transcript",
    "clean_segment_text",
    "diarize_segments",
    "postprocess_segments",
    "refine_segments",
]
