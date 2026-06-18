"""요약 프레임워크 프롬프트 레지스트리.

각 프레임워크는 같은 폴더의 별도 모듈로 존재하며, 모듈은 다음 3개 상수를 노출한다:
    NAME: str               # 프레임워크 식별자
    DESCRIPTION: str        # 사람이 읽기 위한 짧은 설명
    SYSTEM_PROMPT: str      # 2차 호출 시 system 프롬프트
"""

from app.prompts import (
    kpt,
    operations,
    planning,
    reporting,
    solving,
)
from app.prompts.router import ROUTER_SYSTEM_PROMPT

_FRAMEWORK_MODULES = (
    operations,
    planning,
    solving,
    kpt,
    reporting,
)

FRAMEWORK_PROMPTS: dict[str, str] = {
    module.NAME: module.SYSTEM_PROMPT for module in _FRAMEWORK_MODULES
}
FRAMEWORK_DESCRIPTIONS: dict[str, str] = {
    module.NAME: module.DESCRIPTION for module in _FRAMEWORK_MODULES
}
SUPPORTED_FRAMEWORKS: tuple[str, ...] = tuple(FRAMEWORK_PROMPTS.keys())

__all__ = [
    "FRAMEWORK_PROMPTS",
    "FRAMEWORK_DESCRIPTIONS",
    "SUPPORTED_FRAMEWORKS",
    "ROUTER_SYSTEM_PROMPT",
]
