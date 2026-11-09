# AI 강의실 — 검토용 부분 완성 버전

> GitHub 보관본 · 실제 수업 질문, 판서, 음성, 성공·실패 보고서는 [검증 자료](../evidence/README.md)에서 확인할 수 있습니다. 로컬 서버 상태와 실행 시각은 당시 검증 PC의 기록입니다.

현재 **NOT_READY / H_PENDING**입니다. 학생이 텍스트·사진을 보내고 캐릭터의 음성과 판서를 보는 경로는 연결했지만, 정확한 답변을 제공하는 범위와 사진 조건 확인, 응답 지연, 연속 사용에 실패가 남았습니다. 검증된 일부 SQLite 수업을 검토하는 용도로 사용할 수 있습니다. 독립적으로 공부하며 정답을 맡기는 제품으로 승인하지 않았습니다.

보관한 소스 버전은 `0.2.1`입니다. 실제 빌드는 [최신 상태](STATUS.json)의 실행 manifest와 파일 SHA로 구분합니다. 기존 Qwen3-1.7B/base/BF16 + Windows SAPI의 Microsoft Heami Desktop을 사용합니다. 학습1과 후보4B는 기본값으로 승격하지 않았습니다. 신경망 관측은 기본 OFF입니다.

- [전체 진행 브리핑](docs/PROGRESS_BRIEFING.md): 기능별 구현·실행·사람 검토, 실패, 16개 완료 기준.
- [현재 인계](HANDOFF.md), [ChatGPT 전달용](docs/CHATGPT_HANDOFF.md), [현재 실행](docs/ACTIVE_EXECUTION.md).
- 과거 0.2.0의 새8수업(r10)은 기술완료5/실패3, 유효 설명7/10입니다. 최종80을 기본/학습1로 각각 실행한 SQL 결과 일치는15/60·27/60이고, 당시 저장 답변을 앱 검증·계획 경로로 재처리한 결과는0/60·0/60이었습니다. 0.2.1에서 공개된 같은 답변의 개발 회귀는20/60·35/60계획이며 응답한 결과는모두일치했습니다. 새 독립 평가와 혼동하지 않습니다. 개념20개씩과 음성 교육 품질은 사람 검토 대기입니다. 서로 다른 분모·조건을 전체 정확도로 합치지 않습니다.
- 학생별 수업 한도를 명시적으로 시작하고 닫는 기능은 기존 총승인과 같은 장부를 사용합니다. 새 대화가 자동 충전되거나 실패 사용량이 환불되지 않습니다. r14 실제 수업 (검증 PC의 `runs/finish-v2/20261029/student-budget-proposal/integration-r3/r14-budget04/RUN_RESULT_KO.md`)에서는 선택한 0행과 NULL의 재설명, 원래 수업 복귀, SUM 45까지 완료했습니다. 전체 제품 완료를 뜻하지 않습니다.

0.2.1의 새 단일 표 출력·조건·다중정렬·조건집계 문법과 남겨 둔 제한은 [지원 범위](docs/SUPPORTED_SQL_V021.md)를 확인합니다. 모델 원시 답변과 앱이 검증한 계산·판서를 구분합니다.

## 2026-10-29 0.2.1 r3 실제 검증

새 독립 지원20개에서 앱 수업 계획19/20, 응답 SQL 구조·값19/19, 원시18/20입니다. 제한 문법의 단일 표 문제이며 자유 설명 정확도95%가 아닙니다. 같은 빌드 대표8수업·본 수업재생24개 연결을 확인했지만 NULL 비교 미충족·첫 설명 지연·단기 표시 불일치·완료 화면 재진입 autoplay와 사람 검토가 남았습니다. 요구사항 검증 통과율9/16=56.25%는 제품 완성률이 아닙니다.

현재 실제 질문·화면·대사·WAV 갤러리 (검증 PC의 `runs/v021-support/20261029/student/final-v021-r3-combined/gallery.html`) · 새 독립 평가 (검증 PC의 `runs/v021-support/20261029/independent-eval-r3/RESULT_KO.md`)

## 학생용 검토 흐름

현재 PC의 서버 주소는 [AI 강의실](http://127.0.0.1:8000)입니다. 서버가 켜져 있으면 중복 시작하지 않습니다. 최초 인증은 로컬 `.local/auth-token`을 직접 열어 화면에 입력합니다. 토큰을 채팅·사진·보고서에 공유하지 않습니다.

새 대화에서 현재 총 잔여 범위 안의 텍스트·음성·사진·시간 한도를 직접 정한 뒤 질문합니다. 사진은 원본과 인식 후보를 대조하고 중요한 글자·표·조건을 확인한 후 풀이를 요청합니다. 확정하지 않은 원문을 정확한 답변으로 간주하지 않습니다. 강의실에서는 선택한 행·셀을 포함해 질문할 수 있습니다. 오류로 중단되면 화면의 원인과 입력을 보존하며 무작정 반복하지 않습니다. 닫힌 수업도 저장된 정확한 음성 캐시와 기록을 읽을 수 있습니다.

## 설치와 배포 경계

이 PC에는 프로젝트 전용 Python3.12 가상환경과 필요한 모델이 이미 설치되어 있습니다. 소스 ZIP은 코드·설정 예시·사전 빌드한 웹 화면을 포함하며 인증키, 학생DB, 업로드, `.venv`, 모델 가중치, 실제 WAV와 `runs/`는 제외합니다. 따라서 소스 ZIP만으로 다른 PC의 실제 모델 수업이 즉시 실행되는 것은 아닙니다. ZIP 격리 검증도 기존 가상환경을 사용한 무모델 시작 검사이며 새 PC 설치 검증이 아닙니다.

새 환경의 설치 참고 명령은 아래와 같습니다. 이것은 설치 안내이며 현재 작업에서 다시 설치하거나 모델을 다운로드하지 않습니다. 운영체제·CUDA·한국어 SAPI 음성의 설치 상태가 다르면 별도 검증해야 합니다.

**검증한 BF16·Heami 선택은 이 PC의 로컬 정책입니다. 소스 ZIP에 `.local` 정책을 복사하지 않습니다.** 정책이 없는 새 환경의 코드 기본값은 NF4·Qwen TTS이므로 그것을 이번 검증 구성과 같다고 보고하면 안 됩니다. `configs/text-inference-bf16.example.json`은 선택 예시입니다. `configs/windows-sapi-provider.example.json`은 자리표시자가 있는 예시이며 그대로는 검증을 통과하지 않습니다. 새 PC에서는 기존 PowerShell7로 `scripts/speech_inventory.ps1 -OutputPath <새 보고 경로>`를 실행해 설치된 한국어 SAPI 음성·실행 파일·해시를 읽고 해당 환경의 값으로 채워야 합니다. 이 조회는 합성0회입니다. 활성 작업이 없는 상태에서 정책을 `.local`에 적용하고 인증된 `/api/models`와 `/api/capabilities`의 상태를 확인한 뒤, 별도 허용된 실제 실행으로 검증해야 합니다. 이 설정 절차가 새 실행 예산을 지급하지는 않습니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt --extra-index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
# 웹 소스를 바꾼 경우에만 web에서 npm ci, npm run build
```

## 보존과 검토 자료

`.local/tutor.sqlite3`는 대화·수업·작업 기록, `.local/audio`는 생성한 음성, `runs/phase2/current/resource-budget.json`은 누적 장부입니다. 과거 실패와 사용량을 지우거나 다른 이름의 승인으로 초기화하지 않습니다. 현재 승인 ID는 `finish-local-tutor-20261028-v1`이며 이번 작업 지시는 v0.2.1 지원 범위·정확성 개선입니다. 추가 학습 잔여는0이고 새 승인량을 만들지 않았습니다. 요청당300초, 프로젝트50GB, C여유50GB, 유료 호출·개인자료 외부 업로드 금지를 유지합니다.

현재 수업·음성·사진 증거는 `runs/v021-support/20261029`에 있습니다. 다음 `runs/finish-v2/20261029` 자료는 과거0.2.0 기록입니다. 대표8수업 갤러리 (검증 PC의 `runs/finish-v2/20261029/student/final03/report-binding-v2-20261029T054109464134Z/gallery.html`)와 최종 교육 비교 (검증 PC의 `runs/finish-v2/20261029/education/FINAL160_EDUCATION_RESULTS_KO.md`)는 로컬 증거 링크이며 소스 ZIP에는 포함되지 않습니다. 사람이 실제 설명·발음·자연스러움·선택 행 재설명을 검토해야 H_PENDING을 해제할 수 있습니다.

## 기본 설정 복귀 방법

현재는 base 모델이며 학습 adapter를 쓰지 않습니다. 아래 재현 절의 명시적 base 선택을 사용하면 adapter만 끌 수 있습니다. BF16을 과거 NF4로 되돌릴 경우 활성 작업과 소유 text worker가 종료된 상태에서 `.local/text-inference-policy.json`을 별도 백업 경로로 옮겨 정책 부재 상태로 복구합니다. 변경 전 기록은 `runs/finish-v2/20261029/bf16-default-selection-applied.json`입니다. 임의의 모델 파일이나 장부는 지우지 않습니다.

음성 설정의 이전 사본은 `runs/finish-v2/20261029/heami-first-new-lesson/speech-provider-before-promotion.json`, 검증한 Heami 사본은 같은 폴더의 `speech-provider-after-promotion.json`입니다. 활성 작업이 없는 상태에서 현재 `.local/speech-provider.json`을 먼저 백업하고 필요한 사본을 복원한 뒤 서버를 다시 시작합니다. 과거 Qwen TTS 세션은 native 실패가 해결되지 않았으므로 설정 복귀 자체를 합성 성공으로 해석하지 않습니다. 이번에는 롤백 실행을 하지 않았습니다.

## 현재 설치된 모델로 실행·학습 기록·평가를 재현하는 방법

최종평가 답변을 보고 모델·체크포인트·교육 프롬프트 선택을 바꾸지 않았다. 이후 별도 실제 학생 수업에서 발견한 집계 재설명 연결과 실패 시 칠판 보존 오류를 수정했다. 0.2.0 r14/r15에서 저장된 최종 원시 답변을 CPU 재처리한 결과는 당시 이전과 같았다. 이후 0.2.1의 변경과 새 평가 결과는 최신 브리핑을 따른다. **NOT_READY/H_PENDING**, 현재 학생 검토 구성은 기존 Qwen3-1.7B/base/BF16와 Microsoft Heami Desktop이다. 후보4B와 학습1 adapter는 기본값으로 승격하지 않았다. 아래 단계는 모델/엔진 다운로드·패키지 설치를 요구하지 않는다.

### 앱 실행과 현재 구성 확인

기존 프로젝트와 가상환경을 사용한다. 이미 서버가 켜져 있으면 같은 포트로 중복 실행하지 않는다.

```powershell
Set-Location -LiteralPath 'D:\LLM\edu-tutor-local'
pwsh -NoProfile -File .\scripts\start.ps1
```

주소는 `http://127.0.0.1:8000`이다. 로컬 인증은 `.local/auth-token`을 사용하며 토큰을 로그·채팅·화면 증거에 노출하지 않는다. 서버 시작은 새 모델 추론/음성/사진/학습/다운로드를 자동 시작하지 않는다. 실제 허용량은 관리자 예산과 현재 활성 scope 장부가 결정하며, 문서의 예전 숫자를 재사용하지 않는다.

실행 증거에서 확인할 구성은 모델 `Qwen/Qwen3-1.7B`, revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`, adapter `null`, 선택 정밀도 `bf16`, 실제 EOS `[151645,151643]`이다. BF16은 요청 설정이다. 실제 최종 비교에서 base parameter1,720,574,976개는 BF16이었지만 adapter 조건은 LoRA1,605,632개가 FP32여서 모든 parameter가 BF16인 것은 아니다.

### 실제 완료한 학습1의 재현 정보

- 데이터: 직접 작성한 절차 생성 SQLite 문제, train240/validation40/final80 가족 분리. 인간 검토 전이다. 최종80은 학습·선택·RAG·생성 prompt에 쓰지 않았다.
- 구성: `configs/finish_education.yaml`, NF4 QLoRA, r8/alpha16/dropout.05, q_proj/v_proj, lr1e-4, microbatch1/accum8, max512, 3epoch/90optimizerstep. config에 validation 경로도 있지만 runner가 train split만 학습 labels로 사용한다.
- 실제:720microbatch,112개 adapter tensor 변경, finite gradients, base weights 동결. 평균 train_loss1.4566875331931644는 학습 최적화 수치이며 설명 정확도가 아니다.
- 증거: `runs/train-f1cc05b37bb04d51ba326468f2fd74a1/training-result.json`, `target-token-audit.json`, `reload-result.json`, `manifest.json`.
- 학습 dataset fingerprint: `40e7b8502da07c570ded48fc495290569be099bb70c499a4bbfda15aed61ed65`.
- 별도 프로세스 reload는 성공했지만 `COUNT(값)`이 NULL행을 센다는 오답을 냈다. manifest의 passed는 실행 연결 검사이며 교육 품질 통과가 아니다.

현재 학습 시도 잔여는0이다. 실패한 학습2도 시도/예약을 차감했다. 아래는 새 GPU 실행이 없는 **준비 예시**이며 실제 학습 재실행 승인이 아니다. 과거 완료 run을 지우거나 새 이름으로 한도를 우회하지 않는다.

```powershell
New-Item -ItemType Directory -Path '.\runs\finish-v2\20261029\education\education-reproduction-prepared' -Force | Out-Null
.\.venv\Scripts\python.exe -X utf8 scripts/finish_education_live.py train --run education-reproduction-prepared --dataset-id finish-v2 --baseline-result runs/finish-v2/20261029/education/validation-base-v1/result.json
```

실제 과거 제출은 같은 train CLI의 `--run education-experiment-1 --dataset-id finish-v2 --baseline-result .../validation-base-v1/result.json --execute`였다. 제출 내용은 해당 폴더의 `submission.json`에 있다. 추가 실제 학습은 새 명시적 승인·예산이 있어야 하며, 이번 작업에서는 더 하지 않는다. 같은 학습을 재현해도 장치·패키지/연산 차이로 같은 가중치나 답변이 보장되지 않는다.

### 완료된 최종 평가 열람과 CPU 재채점

이미 최종80을 각2조건으로 실행했다. 두 run은 `education/final-base-bf16-v1`과 `education/final-adapter1-bf16-v1`이고, 선택 동결은 `selection-bf16-frozen-v1.json`이다. 모델·prompt·선택을 final 답변을 보고 바꾸지 않았다. 비교 조건은 동일1.7B/BF16/max256/greedy/RAG없음, adapter만 base 대 학습1이다. 실제 정확도를 새로 측정하려고 기존 최종80을 반복 생성하지 않는다. 향후 개선을 하면 새 독립 최종 세트가 필요하다.

아래는 **이미 저장된 답변의 CPU 재채점**이며 모델/음성 호출이 없다. 기존 결과와 소스가 같으면 기존 결과를 재사용하고, 다르면 덮어쓰지 않고 오류를 낸다. 생산 코드를 나중에 바꾼 뒤에는 과거 final-source-r10-v1 결과를 현재 것처럼 바꾸지 않는다.

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/finish_education_regrade.py runs/finish-v2/20261029/education/final-base-bf16-v1
.\.venv\Scripts\python.exe -X utf8 scripts/finish_education_counterexamples.py runs/finish-v2/20261029/education/final-base-bf16-v1
.\.venv\Scripts\python.exe -X utf8 scripts/finish_education_claims.py runs/finish-v2/20261029/education/final-base-bf16-v1
.\.venv\Scripts\python.exe -X utf8 scripts/finish_education_app_grade.py runs/finish-v2/20261029/education/final-base-bf16-v1 --version final-source-r10-v1
```

학습1 조건은 마지막 경로를 `final-adapter1-bf16-v1`로 바꾼다. SQL 고정표 결과일치·반례·명시 배열 모순·CPU 앱 검증/계획의 지원율·개념20개/H_PENDING을 분리한다. 앱 후처리는 새 RAG검색/모델 보정/실제 수업/TTS가 모두0이다. 평가실행 정확한 당시 명령은 `FINAL160_RUNBOOK_DRAFT_KO.md`, 원본 request/job/시간은 각 run의 batch01..20에 보존했다.

### 학습 adapter를 끄고 기존 모델로 복귀

현재 이미 base이므로 복귀 작업은 필요 없다. 이후 수동으로 adapter를 켰다면, 진행 작업을 종료한 뒤 관리자 모델 선택에서 **기본 모델**을 선택한다. 기록을 지우지 않는다. API의 명시적 base 선택은 `POST /api/adapters/select`에 `{"adapter_id":null}`이다. 임의 이전 history로 돌아가는 rollback과 달리 이 요청은 기반 모델을 직접 지정한다.

인증 토큰을 출력하지 않고 현재 상태를 읽는 예시는 다음과 같다.

```powershell
@'
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'scripts'))
from finish_education_live import Client
print(Client().call('/api/adapters'))
'@ | .\.venv\Scripts\python.exe -X utf8 -
```

기반 모델 복귀 자체가 필요할 때만 같은 Client로 `call('/api/adapters/select', {'adapter_id': None})`를 호출한다. 실행 중 작업이 있거나 GPU lease를 얻지 못하면 API가 거부한다. 모델·adapter 파일과 DB/WAV/이전 평가 기록은 삭제하지 않는다. 이는 기존 설치 모델의 선택 변경이며 새 다운로드나 새 추론을 실행하지 않는다. BF16 정책과 Heami 음성 선택은 별도 설정이며 그대로 확인한다.
