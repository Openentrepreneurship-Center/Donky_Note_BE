"""화자 분리 / 라벨링.

TODO: 실제 diarization 모델 또는 LLM 기반 화자 추정 연결.
현재는 모든 세그먼트를 단일 화자(`speaker_1`)로 표시하는 스텁.
"""

from __future__ import annotations

from copy import deepcopy


def diarize_segments(segments: list[dict]) -> list[dict]:
    """세그먼트에 화자 라벨(`speaker`)을 부여."""
    result = deepcopy(segments)
    for seg in result:
        seg.setdefault("speaker", "참석자1")
    return result
