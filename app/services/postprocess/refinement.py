"""텍스트 정제.

필러(어/음/그/네) 제거, 반복어 정리, 오인식 교정, 띄어쓰기/구두점 정규화 등을
수행. 현재는 양 끝 공백만 제거하는 스텁.
"""

from __future__ import annotations

from copy import deepcopy


def clean_segment_text(text: str) -> str:
    """단일 세그먼트 텍스트 정제."""
    # TODO: 필러 제거, 반복어 정리, 오인식 교정, 구두점 정규화
    return text.strip()


def refine_segments(segments: list[dict]) -> list[dict]:
    """모든 세그먼트의 텍스트를 정제."""
    result = deepcopy(segments)
    for seg in result:
        if "text" in seg:
            seg["text"] = clean_segment_text(seg["text"])
    return result
