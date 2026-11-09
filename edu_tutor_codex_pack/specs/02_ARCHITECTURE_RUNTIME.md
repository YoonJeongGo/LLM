# 기술 구성·환경·작업 관리

## 기본 구현 경로

새 프로젝트 기준:
- Python 3.11 우선: FastAPI, Pydantic, SQLite, PyTorch, Transformers, PEFT, Accelerate, bitsandbytes.
- 학습은 Transformers.Trainer + 직접 검증한 data collator. TRL은 이번 경로에서 제외한다.
- 웹 화면은 React + TypeScript + Vite. 판서는 SVG/HTML, 수식은 KaTeX 등 검증된 렌더러.
- Python 테스트 pytest, 웹 단위 Vitest, 브라우저 E2E Playwright.
- 학습 로그는 JSONL + TensorBoard. TensorBoard 공개 네트워크 노출 금지.
- 저장은 로컬 SQLite와 파일. Redis/Postgres/Docker는 필수 구성으로 추가하지 않는다.
- Gradio와 React 관리자 화면을 중복 구현하지 않는다. 복잡한 강의 타임라인 때문에 React를 선택한다.
  기존 앱이 이미 다른 스택으로 정상 작동하면 기능 충족 여부를 확인해 유지하고 변경 근거를 기록한다.

패키지 버전은 실제 설치·import·스모크 테스트 후 lockfile에 고정한다.
서로 다른 모델 런타임의 요구 버전이 충돌하면 text/train, vision, TTS 가상환경을 분리하고
작업 프로세스 인터페이스로 연결한다. 검증하지 않은 버전 번호를 “검증됨”이라고 적지 않는다.
FlashAttention, torch.compile, vLLM, 다중 GPU는 필수로 만들지 않는다.

## 권장 폴더

```
src/edu_tutor/
  api/             # HTTP·스트리밍·인증
  jobs/            # 작업 상태·GPU lease·worker 관리
  models/          # 텍스트 로더·추론·메타데이터
  training/        # 데이터·마스킹·LoRA·학습·재로딩
  retrieval/       # 문서 청크·인덱스·출처
  evaluation/      # SQL sandbox·정답 비교·보고
  lessons/         # 강의 schema·계획·장면 reducer
  speech/          # TTS provider·발음 사전·캐시
  vision/          # 사진 전사·검토 흐름
  storage/         # DB·안전한 파일 IO
  cli.py
web/src/           # 대화/강의실/관리자 UI
configs/
tests/{unit,integration,gpu}/
web/tests/
scripts/
docs/
.local/            # DB·uploads·models·indexes·assets; git 제외
runs/              # 실행별 설정·로그·검증 증거; git 제외
```

GPU를 사용하지 않는 API 프로세스와 모델 worker를 분리한다. API는 메모리를 가득 채운 작업 때문에
상태 조회·취소 요청에 응답하지 못하는 구조가 되어서는 안 된다. worker와 통신하는 payload를 검사한다.
훈련·추론·TTS·비전은 명시적인 작업 종류와 설정만 허용한다. 사용자 임의 명령 문자열은 받지 않는다.

## doctor

모델 다운로드 없이 JSON과 쉬운 요약을 출력한다.
실제 OS/WSL, Python, 로컬/원격 여부의 확인 근거, GPU 가시성, torch CUDA, BF16 지원,
VRAM total/free, RAM total/free, 지정 저장 경로의 디스크 공간, 의존성 버전을 기록한다.
네트워크 검사 실패는 런타임 실패와 구분하고, 알 수 없는 값은 null + reason으로 기록한다.
WSL에서는 Windows 호스트 드라이버를 사용한다. 일반 Linux GPU 디스플레이 드라이버를
WSL에 임의 설치하지 않는다. 기존 native Windows 경로가 검증되면 유지한다.

## GPU 직렬화 — 핵심

전용 VRAM 8GB에는 큰 모델을 무조건 동시에 올리지 않는다.
전 앱의 GPU lease를 OS file lock과 DB 작업 레코드로 관리하고 CLI도 동일 규칙을 사용한다.
lease에는 job_id, PID, 프로세스 시작 식별자, device, heartbeat를 남긴다.
PID 번호만 보고 남의 프로세스를 종료하지 않는다. stale lease 복구는 생존 여부를 확인한 뒤 수행한다.

작업 상태:
queued → loading → running → saving → succeeded
추가 terminal: failed / cancelled / interrupted / blocked.
취소는 cancel_requested를 기록하고 worker가 안전한 시점에 반응한다.
브라우저 새로고침은 작업 성공·실패로 간주하지 않는다. 서버 재시작 후 고아 작업은 interrupted로 복구한다.

텍스트 모델 → 음성 모델 → 비전 모델 전환 때 이전 worker의 참조·메모리 정리를 확인한다.
`empty_cache()` 호출만으로 모델이 GPU에서 사라졌다고 판단하지 않는다.
필요하면 소유한 worker를 정상 종료하고 다음 worker를 실행한다.
CPU로 내리는 경우 RAM 잔량도 확인하고, 메모리를 계속 누적하지 않는다.
사용 중인 학습 작업이 있으면 채팅은 대기/거절 상태를 명확하게 표시한다.

## 요청과 취소

모든 생성에 session_id, request_id, generation_epoch를 붙인다.
사용자가 중단/새 질문/새 강의를 시작하면 epoch를 갱신한다.
기존 스트리밍·오디오·판서 이벤트가 늦게 도착해도 이전 epoch면 UI가 폐기한다.
작업 재시도에는 idempotency key를 사용해 중복 학습 시작·중복 산출물 등록을 막는다.

## 실행 제한

기본 컨텍스트 2048 tokens부터 검증하고 GPU 여유가 확인될 때만 확장한다.
총 입력/출력 토큰 예산을 검사한다. 예산을 넘으면 무작위 잘림 대신 사용자에게 알리거나
인용 자료 개수·이전 대화를 명시적으로 줄인다. 강의 계획은 단계별 생성으로 긴 JSON을 피한다.
기본 동시 GPU 작업 1개. 서버 host는 127.0.0.1. 다른 네트워크 노출은 자동 활성화하지 않는다.

## 핵심 API 계약

OpenAPI로 계약을 남기고 web 클라이언트 타입과 일치시킨다.
- 상태/설정: health, capabilities, doctor, models, adapters
- 대화: sessions, messages, generation events, cancel
- 자료: documents, ingest, review, search, delete
- 학습: datasets validate, train jobs, cancel, artifacts, promote/rollback
- 평가: evaluations, compare, rubric results
- 강의: lesson create/read, speech prepare, play state, interrupt/reexplain
- 사진: upload, transcribe, edit, confirm

큰 파일은 제한된 multipart 업로드로 받고 임의 로컬 경로·임의 외부 URL fetch는 제공하지 않는다.
파일 읽기와 삭제는 서버가 발급한 ID를 경로에 매핑한다.
