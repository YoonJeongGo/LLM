# 실행·릴리스·재개 문서

## 사용자에게 제공할 실행 경로

실제로 구현한 CLI 이름과 README를 일치시킨다. 다음은 요구 인터페이스다.
- `python -m edu_tutor doctor`
- `python -m edu_tutor serve`
- `python -m edu_tutor baseline --config configs/local_8gb.yaml`
- `python -m edu_tutor data validate --dataset <경로>`
- `python -m edu_tutor train --smoke --config configs/local_8gb.yaml`
- `python -m edu_tutor train --profile demo --config configs/local_8gb.yaml`
- `python -m edu_tutor evaluate --run <run_id>`
- `python -m edu_tutor jobs list`
- `python -m edu_tutor jobs cancel --id <job_id>`

대규모 학습을 실행하는 명령은 명시적 config·budget을 요구한다.
학습은 웹 관리자와 CLI 모두 같은 validation/lease/job 코드를 사용한다.
serve를 실행할 때 자동 학습·모델 세 개 동시 다운로드가 시작되면 안 된다.

Windows PowerShell과 WSL/Linux의 검증된 실행 안내를 분리한다.
가능하면 `scripts/start.ps1`, `scripts/start.sh`, `scripts/check.ps1`, `scripts/check.sh`를 제공한다.
해당 OS를 실제 테스트하지 못했다면 unverified로 표시한다. 경로 공백·한글·가상환경 활성화 문제를 고려한다.
Windows에서 WSL을 자동 설치하거나 강제 재부팅하지 않는다.
설치 스크립트는 무엇을 설치할지 미리 표시하고 프로젝트 밖 전역 패키지를 바꾸지 않는다.

첫 실행은 ①환경 검사 ②모델 설치 상태 ③서버 기동 ④주소/관리 인증 안내로 진행한다.
브라우저를 못 열면 정상 localhost 주소를 표시한다. 실행되지 않은 주소를 정상 서비스처럼 보고하지 않는다.

## 문서 산출물

README.md: 초보자가 따라 할 설치/실행/종료/학습/오류 안내.
AGENTS.md: 기존 지침을 보존하고 이번 프로젝트의 핵심 규칙을 짧게 병합.
STATUS.json: 단계별 구현/검증/증거/차단 이유.
HANDOFF.md: 실제 현재 상태·마지막 성공 명령·다음 작업과 명령.
docs/ARCHITECTURE.md: 모듈/worker/GPU lease/데이터 흐름.
docs/DATA_GUIDE.md: source/권리/review/split/평가 누수 방지.
docs/TRAINING_GUIDE.md: 가중치·어댑터·실행과 학습·smoke와 본 학습 차이.
docs/OPERATIONS.md: 큐/모델 교체/취소/복구/저장 공간/백업.
docs/LIMITATIONS.md: 실측 성능·미검증 기능·사진/음성/작은 모델 한계.
docs/ACCEPTANCE.md: 테스트 매트릭스의 증거 링크.
docs/DECISIONS.md: 기술 선택·버전·fallback·범위 변경의 이유.
THIRD_PARTY_NOTICES.md: 사용하는 라이브러리·모델·자산의 라이선스와 출처.

README의 숫자나 스크린샷에 샘플 데이터가 있으면 샘플이라고 표시한다.
문서를 작성할 때 테스트를 하지 않았는데 “성공”이라는 기본 템플릿 문구를 남기지 않는다.

## 백업·배포

사용자 PC용 소스 release 묶음을 만든다. venv, node_modules, 대형 모델 가중치,
개인 대화·업로드·auth secret·임시 로그는 기본 제외한다. 필요한 dependency lockfile은 포함한다.
자료와 모델은 사용자가 선택하는 별도 백업 경로로 관리한다.
SQLite는 실행 중 DB 파일을 무작정 복사하지 말고 일관된 backup 절차를 구현한다.
다른 사용자의 PC에서 CUDA가 자동으로 정상 동작한다고 보장하지 않는다.
원격 push/공개 게시/패키지 출판은 요청되지 않았으므로 하지 않는다.

## HANDOFF에 반드시 남길 내용

- 프로젝트 위치와 Git 변경 요약(무단 commit/push를 완료 근거로 사용하지 않음).
- 읽어야 할 현재 지침과 결정 기록.
- 마지막 통과 단계와 실제 test artifact.
- 진행 중 단계, 파일별 다음 수정 사항.
- CPU/GPU/비전/TTS의 검증 여부와 환경 차이.
- 현재 blocker, 재시도 횟수와 원인.
- 사용자가 재개할 정확한 한 줄 지시와 바로 다음 실행 명령.

세션 재개 지시 예:
“STATUS.json과 HANDOFF.md를 읽고 원래 통합 명세를 유지한 채 미완료 단계부터 재개해라.
이미 검증한 코드를 무조건 다시 만들지 말고, 변경된 범위의 테스트를 먼저 확인해라.”

## 최종 보고 양식

프로젝트 상태: LOCAL_MVP_VERIFIED / IMPLEMENTED_RUNTIME_BLOCKED / PARTIAL.
실행 방법: 실제 작동한 명령과 환경.
구현 기능: 실제 API/UI 동작 기준.
검증 결과: T0/T1/T2/T3/H 별 pass/fail/not_run/blocked.
학습 결과: 기반 모델·어댑터·실제 step·저장 파일·전후 비교.
UI 결과: 실제 캡처 경로와 확인 항목.
미완료: 이유, 영향, 다음 조치. 없으면 없는 근거.

이 명세 팩을 작성한 AI가 수행한 파일 형식 검사는 앱의 실행/학습 검증과 무관하다.
개발 에이전트는 직접 구현한 결과만 근거로 보고해야 한다.
