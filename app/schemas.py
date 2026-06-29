from pydantic import BaseModel, ConfigDict, Field


class TranscribeRequest(BaseModel):
    """STT 전사 요청 본문 (필드는 이후 실제 연동에 맞게 조정)."""

    source: str | None = Field(
        default=None,
        description="오디오 URL 또는 내부 스토리지 식별자",
    )
    language: str | None = Field(default="ko", description="언어 코드")


class TranscribeResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "0b857cc2428147c3a7d38e7ac032b711",
                "status": "processing",
                "message": "queued 'sample.m4a'",
            }
        }
    )

    job_id: str = Field(..., description="32자 hex (UUID4)")
    status: str = Field(..., description="항상 'processing' — 백그라운드에서 STT 처리 진행 중")
    message: str | None = None


class FrameworkInfo(BaseModel):
    """요약 프레임워크 1개의 공개 메타데이터."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "framework": "operations",
                "frameworkKo": "운영 관리",
                "description": "지속 가능한 정기 업무 및 서비스 유지보수를 위한 프로세스 관리 프레임워크",
            }
        }
    )

    framework: str = Field(..., description="프레임워크 식별자 (요약 API의 framework 값)")
    frameworkKo: str = Field(..., description="프레임워크 한글 이름 (UI 노출용)")
    description: str = Field(..., description="프레임워크 설명")


class SegmentTimestamp(BaseModel):
    start: float = Field(..., description="음성파일 내 발화 시작 시각(초, 파일 시작점 기준 경과)")
    end: float = Field(..., description="음성파일 내 발화 종료 시각(초, 파일 시작점 기준 경과)")


class TranscriptSegment(BaseModel):
    index: int = Field(..., description="세그먼트 순번 (0부터)")
    text: str = Field(..., description="해당 구간 발화 텍스트 (refinement 적용 후)")
    speaker: str | None = Field(
        default=None,
        description="화자 라벨 ('참석자1', '참석자2' …). 화자분리 결과를 정규화한 값.",
    )
    timestamp: SegmentTimestamp | None = Field(
        default=None,
        description="음성파일 내 해당 발화의 시간 구간(초). start/end.",
    )


class TranscriptResultResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "0b857cc2428147c3a7d38e7ac032b711",
                "status": "completed",
                "text": "참석자1: 이번 주까지 베타 배포해야 합니다\n참석자2: GPU 서버 늦어지는 게 블로커네요",
                "segments": [
                    {
                        "index": 0,
                        "text": "이번 주까지 베타 배포해야 합니다",
                        "speaker": "참석자1",
                        "timestamp": {"start": 0.0, "end": 3.42},
                    },
                    {
                        "index": 1,
                        "text": "GPU 서버 늦어지는 게 블로커네요",
                        "speaker": "참석자2",
                        "timestamp": {"start": 3.91, "end": 7.05},
                    },
                ],
            }
        }
    )

    job_id: str
    status: str = Field(..., description="'completed' (결과 있음). 진행 중/실패는 별도 에러 코드로 응답.")
    text: str = Field(..., description="화자 prefix가 포함된 본문 (동일 화자 연속 줄은 prefix 생략).")
    segments: list[TranscriptSegment] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "TRANSCRIPTION_IN_PROGRESS",
                "message": "transcription is still in progress",
                "details": None,
            }
        }
    )

    code: str = Field(..., description="클라이언트 분기용 에러 식별자")
    message: str = Field(..., description="사람이 읽는 에러 메시지")
    details: list[dict] | None = Field(default=None, description="추가 상세 정보. 없으면 null.")


class SummarizeSegment(BaseModel):
    """요약 입력용 세그먼트. /stt/results의 segments에서 text/speaker만 추린 형태."""

    text: str = Field(..., min_length=1)
    speaker: str | None = None


class SummarizeRequest(BaseModel):
    """STT 전사 결과를 받아 자동 프레임워크 요약을 요청.

    segments 또는 text 중 하나는 필수. 둘 다 주면 segments 우선.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "segments": [
                    {"text": "이번 주까지 베타 배포해야 합니다", "speaker": "참석자1"},
                    {"text": "GPU 서버 늦어지는 게 블로커네요", "speaker": "참석자2"},
                ],
                "framework": None,
                "language": "ko",
            }
        }
    )

    segments: list[SummarizeSegment] | None = Field(
        default=None,
        description="화자 분리된 세그먼트 배열. 화자 정보가 라우터/요약 품질에 도움이 되므로 권장.",
    )
    text: str | None = Field(
        default=None,
        min_length=1,
        description="(legacy) 한 덩어리 transcript. segments가 없을 때만 사용.",
    )
    framework: str | None = Field(
        default=None,
        description=(
            "명시적으로 프레임워크를 강제할 때 사용. 미지정 시 라우터 LLM이 자동 선택. "
            "허용 값: operations / planning / solving / kpt / reporting"
        ),
    )
    language: str | None = Field(default="ko", description="요약 출력 언어 (기본 'ko')")


class SummarizeResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "framework": "operations",
                "reason": "베타 출시 일정에 대해 담당자별 진행 상태와 블로커를 점검하는 실행 회의.",
                "summary": (
                    "## 1. 핵심 논의\n"
                    "- 베타 출시 일정 조율\n\n"
                    "## 2. 결정 사항\n"
                    "- 다음 주 화요일 베타 데모 진행\n\n"
                    "## 3. 액션 아이템\n"
                    "- [참석자1] STT 후처리 모듈 PR 작성 (Due: 5/12)\n"
                    "- [참석자2] GPU 서버 증설 협의 (Due: 미정)\n\n"
                    "## 4. 블로커 / 이슈\n"
                    "- GPU 서버 입고 지연\n\n"
                    "## 5. 다음 일정\n"
                    "- 5/12 베타 데모"
                ),
                "confidence": 0.9,
            }
        }
    )

    framework: str = Field(..., description="선택된 요약 프레임워크 식별자")
    reason: str = Field(..., description="해당 프레임워크가 선택된 이유 (한국어 1~2문장)")
    summary: str = Field(..., description="프레임워크에 맞춘 요약 본문(Markdown)")
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="라우터 LLM의 분류 신뢰도(0.0~1.0). 사용자가 framework를 강제 지정한 경우 null.",
    )
