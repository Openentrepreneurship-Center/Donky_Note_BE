# DonkeyNote STT & Summarize API

회의/강의 오디오를 **화자분리 STT로 전사**한 뒤, 회의 성격에 맞는 **프레임워크를 LLM이 자동 선택해 요약**해주는 FastAPI 백엔드입니다.

## 기술 스택

- **API**: FastAPI 0.115 + uvicorn (Python 3.12)
- **STT**: Naver Clova Speech (Long Sentence, 화자분리)
- **요약**: OpenAI `gpt-4o-mini` (라우터 + 요약 2단계 호출)
- **감사 로그**: AWS S3 (boto3, best-effort)

## 처리 흐름

```
[전사]  POST /stt/transcribe  → job_id 발급 (비동기, 즉시 응답)
        GET  /stt/results/{job_id} → 폴링 (처리 중이면 409)
            └ Clova 호출 → segment 정규화 → 후처리(diarize→refine→assemble)

[요약]  POST /summarize  (전사 segments 또는 text 전달)
        1차 LLM(라우터): 회의 유형 분류 → 프레임워크 1개 선택 + confidence
        2차 LLM: 선택된 프레임워크 프롬프트로 Markdown 요약
```

요약 프레임워크 5종: `operations`(실행 점검) · `planning`(기획) · `solving`(문제 해결) · `kpt`(회고) · `reporting`(보고). `framework`를 직접 지정하면 라우터 단계를 건너뜁니다. 지원 목록은 `GET /frameworks`로 조회할 수 있습니다.

## 디렉터리 구조

```
app/
├── main.py              # FastAPI 라우트, 에러 코드 매핑, 예외 핸들러
├── schemas.py           # Pydantic 요청/응답 모델
├── prompts/             # 라우터 + 5개 프레임워크 system 프롬프트
└── services/
    ├── transcriber.py   # job 관리 + 백그라운드 전사 워커
    ├── clova_client.py  # Clova Speech HTTP 클라이언트
    ├── summarizer.py    # 2단계 LLM 요약
    ├── audit_log.py     # S3 감사 로그
    └── postprocess/     # diarize → refine → assemble 파이프라인
```

## 프레임워크 추가하기

새 요약 프레임워크(`xxx`)를 추가할 때:

1. **`app/prompts/xxx.py` 생성** — 기존 모듈과 동일하게 아래 상수를 노출:
   - `NAME` (식별자) · `NAME_KO` (한글명) · `DESCRIPTION` (라우터/내부용) · `LIST_DESCRIPTION` (`/frameworks` 노출용) · `SYSTEM_PROMPT`
2. **`app/prompts/__init__.py`의 `_FRAMEWORK_MODULES`에 모듈 등록** ← 실질적인 "명단"은 이 한 곳.

이 둘만 하면 `FRAMEWORK_CATALOG`(→ `GET /frameworks`), `FRAMEWORK_PROMPTS`,
`FRAMEWORK_DESCRIPTIONS`, `SUPPORTED_FRAMEWORKS`가 모두 자동 반영됩니다.

> 자동 분류(라우터)가 새 프레임워크를 **선택**하게 하려면 `app/prompts/router.py`의
> 후보 목록·시그널·few-shot 예시도 직접 추가해야 합니다. 이걸 안 하면 `/frameworks`
> 목록에는 떠도 라우터는 못 고르고, `framework`로 강제 지정해야만 사용됩니다.

## 로컬 실행

```bash
pip install -r requirements.txt
cp .env.example .env   # 값 채우기
uvicorn app.main:app --reload
```

- API 문서: <http://localhost:8000/docs>
- 헬스체크: `GET /health`

## Docker

```bash
docker build -t donkey-note .
docker run -p 8000:8000 --env-file .env donkey-note
```

## 환경변수

`.env.example` 참고. Clova(STT)와 OpenAI(요약) 키는 필수, AWS S3 감사 로그는 선택입니다.

## 참고

- 전사 job은 현재 프로세스 내 메모리(dict)에 저장됩니다 — 재시작 시 유실되며, 운영 환경에서는 Redis/DB로 승격해야 합니다.
- `postprocess`의 diarization/refinement는 스텁 상태입니다. 실사용 경로에서는 Clova가 화자분리를 담당합니다.
