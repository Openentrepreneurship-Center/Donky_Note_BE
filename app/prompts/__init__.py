"""요약 프레임워크 프롬프트 레지스트리.

각 프레임워크는 같은 폴더의 별도 모듈로 존재하며, 모듈은 다음 상수를 노출한다:
    NAME: str               # 프레임워크 식별자
    NAME_KO: str            # 프레임워크 한글 이름 (UI 노출용)
    DESCRIPTION: str        # 라우터/내부용 짧은 설명
    LIST_DESCRIPTION: str   # 프레임워크 목록 API 노출용 설명
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

# 프레임워크 목록 API(GET /frameworks)용 메타데이터. _FRAMEWORK_MODULES 순서를 유지.
FRAMEWORK_CATALOG: tuple[dict[str, str], ...] = tuple(
    {
        "framework": module.NAME,
        "frameworkKo": module.NAME_KO,
        "description": module.LIST_DESCRIPTION,
    }
    for module in _FRAMEWORK_MODULES
)

__all__ = [
    "FRAMEWORK_PROMPTS",
    "FRAMEWORK_DESCRIPTIONS",
    "FRAMEWORK_CATALOG",
    "SUPPORTED_FRAMEWORKS",
    "ROUTER_SYSTEM_PROMPT",
]
