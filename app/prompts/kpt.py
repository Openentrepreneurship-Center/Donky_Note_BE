"""KPT 프레임워크 — 회고 요약."""

from app.prompts.common import build_prompt

NAME = "kpt"
DESCRIPTION = (
    "KPT: 회고 회의. Keep(잘한 점)/Problem(문제점)/Try(개선 시도)로 지나간 "
    "활동을 돌아보는 형식에 적합."
)

OUTPUT_FORMAT = """\
[출력 형식]
1. 잘한 점 (Keep)
- 회의에서 긍정적/유지 의견으로 명시된 사항만 기재

2. 문제점 (Problem)
- 회의에서 부정적/문제로 언급된 사항만 기재

3. 개선 시도 (Try)
- 회의에서 명시적으로 "시도/개선해볼 것"으로 제안된 항목만 기재

4. 실행 액션
- [담당자] 구체적인 실행 항목 (Due: 날짜)
- 담당자 미언급: [미정], 기한 미언급: (Due: 미정)

[이 프레임워크 추가 규칙]
- 원문 톤을 임의로 긍정/완곡하게 바꾸지 말 것. 화자가 부정적으로 표현했다면 그대로 반영한다.
- 측정 수치/지표는 transcript에 명시된 값만 인용한다. 없는 KPI를 만들어내지 말 것.
- Keep/Problem/Try 분류는 화자가 명시했거나 맥락상 명백한 경우에만 부여한다.
  분류가 모호한 항목은 가장 가까운 섹션에 원문 표현을 그대로 인용해 기록한다.\
"""

SYSTEM_PROMPT = build_prompt(OUTPUT_FORMAT)
