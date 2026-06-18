"""Reporting 프레임워크 — 보고/공유 중심 요약."""

from app.prompts.common import build_prompt

NAME = "reporting"
DESCRIPTION = (
    "Reporting: 보고/공유 중심. 상태 보고, 결과 발표, 수치 공유, KPI 등 "
    "정보 전달이 주된 목적인 자리에 적합."
)

OUTPUT_FORMAT = """\
[출력 형식]
1. 진행 내용
- 현재까지 완료된 작업 및 진행 상황 (회의에서 보고된 내용만)

2. 주요 성과
- transcript에 언급된 수치/결과만 인용. 정량 표현이 없으면 정성 표현 그대로 기재.

3. 이슈 / 리스크
- 회의에서 발생/언급된 이슈와 리스크만 기재. 임의로 예측한 리스크 추가 금지.

4. 요청 사항
- 의사결정권자 또는 타 팀에 요청한 사항 (회의에서 명시된 것만)

5. 향후 계획
- 다음 단계 및 일정 (회의에서 언급된 것만)

[이 프레임워크 추가 규칙]
- 수치는 transcript에 명시된 값만 인용한다. 추정치/예상치를 만들어내지 말 것.
- 리스크는 회의에서 언급된 것만 기재한다. AI가 예측한 리스크 추가 금지.\
"""

SYSTEM_PROMPT = build_prompt(OUTPUT_FORMAT)
