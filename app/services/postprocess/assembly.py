"""세그먼트 → 본문 조립.

화자 라벨이 있으면 `speaker_1: ...` 형태로 prefix를 붙이고, 동일 화자가
연속되는 줄에서는 prefix를 생략한다.
"""

from __future__ import annotations


def assemble_transcript(segments: list[dict]) -> str:
    lines: list[str] = []
    last_speaker: str | None = None
    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        speaker = seg.get("speaker")
        if speaker and speaker != last_speaker:
            lines.append(f"{speaker}: {text}")
            last_speaker = speaker
        else:
            lines.append(text)
    return "\n".join(lines)
