"""요약 프롬프트 평가 하네스.

로컬(수정 중인) app.prompts + summarizer 로직을 그대로 사용해 transcript를 요약하고
결과를 출력한다. 운영 컨테이너를 건드리지 않고 같은 도커 이미지로 일회용 실행하기 위함.

사용:
    python tools/eval_summary.py <case파일> [framework]
    # framework 생략/auto → 라우터 자동 선택, 그 외 → 강제 지정

환경변수: OPENAI_API_KEY (필수), OPENAI_ROUTER_MODEL / OPENAI_SUMMARY_MODEL (선택)
"""

from __future__ import annotations

import sys

from app.services.summarizer import summarize_transcript


def main() -> None:
    case_path = sys.argv[1] if len(sys.argv) > 1 else "case.txt"
    arg_fw = sys.argv[2] if len(sys.argv) > 2 else "auto"
    framework = None if arg_fw == "auto" else arg_fw

    text = open(case_path, encoding="utf-8").read()
    result = summarize_transcript(text, framework=framework, language="ko")

    print(f"=== framework  : {result.framework}")
    print(f"=== reason     : {result.reason}")
    print(f"=== confidence : {result.confidence}")
    print("=== summary ====================================")
    print(result.summary)


if __name__ == "__main__":
    main()
