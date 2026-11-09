# 실행 증거와 판정

검증 환경은 Windows 11, Python 3.12.14, RTX 3060 Ti 8GB, Torch 2.9.1+cu128다. 각 경로는 프로젝트 루트 기준이다. `runs/`와 브라우저 캡처는 이 PC에 보존하며 개인 데이터 제외 소스 ZIP에는 넣지 않는다. 최종 단계 상태는 `STATUS.json`을 따른다.

T0는 CPU/계약, T1은 작은 CPU 모델의 실제 학습, T2는 실제 GPU/모델, T3는 브라우저·API·실제 모델 연결이다. UI fixture 검사와 실제 모델 검사를 구분했다. H 인간 교육·청취 검토는 수행하지 않았다.

| ID | 검사 | 실행 증거와 범위 |
|---|---|---|
| A01 | 환경 검사 unknown/no-GPU | `runs/environment/doctor.json`, `tests/test_doctor.py`, `runs/training-tests/doctor-evaluation-junit.xml`; 미설치·CPU-only·timeout 구분 |
| A02 | GPU 소유/취소/복구 | `tests/unit/test_backend.py`, `tests/test_training_runner.py`; 중복 API 인스턴스·PID 시작시간·stale·중단 후 늦은 쓰기 차단 |
| A03 | 채팅/중지/한국어 IME | `web/test-results/ui-report.json`; fixture임을 명시, 이전 epoch 배제 |
| A04 | 실제 텍스트 | `runs/20261025T145843Z-baseline-f4e79d/baseline.json`, `runs/integration-live/20261025T152154Z-text-e52cb0/actual-chat.json`; 생성 성공과 오답을 함께 보존 |
| A05 | 실제 마스킹/EOS/길이 | `runs/data-audit-tokenizer/target-token-audit.json`; Qwen 실제 template 45/45, 최대 170토큰 |
| A06 | CPU tiny LoRA | `runs/tiny-lora-t1/manifest.json`; 3 optimizer step, adapter 8개 변경, 기반 불변, reload logits 최대 차이 0 |
| A07 | GPU smoke | `runs/train-1562b36c2366497e88ffe22e70eacc65/manifest.json`; 실제 5단계와 새 프로세스 로딩. 재로딩 출력 잘림·설명 오류는 품질 실패 |
| A08 | family/권리/중복 | `tests/test_training_data.py`, `runs/data-audit-tokenizer/data-audit.json`; 모든 의미적 유사성에 대한 인간 검토는 미실시 |
| A09 | RAG/출처/삭제 | `tests/unit/test_backend.py`, `web/test-results-live/live-report.json`; 실제 업로드·검토·검색·삭제 |
| A10 | SQL 채점/격리 | `tests/unit/test_backend.py`; 중복행·NULL·순서·차단 쿼리·시간/행 제한 |
| A11 | 같은 조건 전후 비교 | `runs/eval-comparison-v1/comparison.json`; 12문항 동일, SQL 3/11→3/11, 잘림 0→2 |
| A12 | 관리자/모델 선택 | `tests/test_admin.py`, `web/test-results-live/training-live-evidence.json`; 실제 학습 로그 표시, 선택/rollback 계약. 자동 승격 없음 |
| A13 | 강의 스키마/reducer | `tests/unit/test_backend.py`, `web/test-results-unit/unit-report.json`; schema 통과가 내용 정답을 의미하지 않음 |
| A14 | 판서/손/화면 크기 | `web/test-results/ui-report.json`; 1440/1280/390 및 확대. 원본 SVG·정적 PNG 교체, 실제 획순 아님 |
| A15 | 한국어 로컬 TTS | `runs/integration-live/20261025T152435Z-media-825a59/report.json`; 실제 24kHz WAV 7.84초/9.12초, checksum·무음 검사 |
| A16 | 실제 음성 동기화 | `web/test-results-t3/`; 실제 audio currentTime 기반 재생·일시정지·재개·배속, 세부 최신 결과 파일 참조 |
| A17 | 사진 확정 게이트 | `tests/unit/test_backend.py`, `web/test-results-live/live-report.json`; 미확정 409, 편집 revision·확정 이력 |
| A18 | 실제 사진 인식 | `runs/integration-live/20261025T152435Z-media-825a59/vision-clear.json`, `vision-table.json`, `vision-cut.json`; 3종 실행. 오인식과 구조 추출 한계 존재 |
| A19 | 인증/업로드/출력 보안 | `tests/unit/test_backend.py`, `tests/test_admin.py`, UI fixture; token/Origin/Host/크기/경로/실제 이미지 decode, 출력 문자열 비실행 |
| A20 | 설치/재시작/보존 | `scripts/start.ps1` 실제 실행, `runs/environment/startup-doctor.json`, `runs/integration-live/20261025T154339Z-inflight-recovery-6980ea/report.json`; 진행 중 실제 채팅 interrupted, 기존 대화/학습 기록 보존, 자식 종료·GPU OS 잠금 재획득 확인 |

실제 50단계 demo는 `runs/train-bf0e7bcb6e3f44b29b77fee6f0e586c1/manifest.json`에 있다. 316 microbatch, 재로딩 포함 276.531초, 최고 CUDA 할당 2,963,142,144바이트다. 학습 가중치 변화와 교육 성능 향상은 별개다.

`runs/integration-live/quality-observations.json`은 실제 결과의 한계를 정리한다. RAG를 사용한 COUNT 질문에서도 존재하지 않는 열을 참조한 SQL을 만들었고, 강의도 그 오류를 반복했다. 사진의 일반 정확도·교육 전문성·음성 자연스러움·다른 PC 호환성을 검증했다고 주장하지 않는다.

최종 Python 전체 검사는 **119 passed, 2 warnings, 38.83초, exit 0**이다. `runs/final-tests/junit.xml`과 `runs/final-tests-output.log`를 보존했다. 경고는 TestClient의 httpx 사용 중단 예고와 tiny PEFT의 config 경고다. `pip check`도 의존성 충돌이 없었다.

프런트엔드 단위 12/12, fixture UI 11/11, 실제 API UI 4/4, 실제 모델·음성/S2 2/2, 실제 학습 취소/S3 1/1을 통과했다. 관리자 실제 데이터/긴 ID/390px·200% 글씨 확인은 `web/test-results-admin/evidence.json`에 있다. 마지막 모델/설정 진입 시 상태 갱신 변경은 빌드로 확인했으며 그 작은 변경 후 브라우저 전체 검사를 다시 수행하지 않았다.

S2의 실제 증거는 `web/test-results-t3/s2-evidence.json`이다. 한 번의 중간 질문, 실제 재설명 계획, 추가 WAV 13.84초, 원강의 ID/단계/진행률 복귀를 확인했다. 실제 중단은 clear 이후 draw 이전이므로 빈 판서 복원이며, 내용이 있는 표 복원은 fixture 증거다. 총 실제 TTS 생성은 3클립으로 제한했다.

S3의 `web/test-results-s3/s3-evidence.json`은 추가 smoke 1회를 취소 시험으로 사용했다. 첫 지표 이후 취소하여 실제 2단계에서 멈췄고, 동시 질문은 409로 거절되며 입력이 저장되지 않았다. 어댑터는 보존했지만 별도 재로딩은 취소로 미실시, optimizer 이어하기는 미지원이다. 실제 sample/s와 CUDA 할당량도 이 run에서 기록했다. 50단계 demo를 다시 실행하지 않았다.

잘린 사진의 원문을 변조하지 않고 누락 조건 형식 검사를 추가했다. `runs/backend-t0/captured-cut-postprocess.json`은 저장된 실제 모델 출력의 T0 후처리 검사다. `runs/integration-live/20261025T153836Z-restart-check-5ee78c/cut-guard-live.json`은 확정된 복제 사진에도 실제 API가 409를 반환하는 증거다. 새로운 비전 성공으로 계산하지 않는다.

최종 분류는 **LOCAL_MVP_VERIFIED(로컬 기능 동작 범위)**, 교육 실사용 준비는 **NOT_READY**다. H는 미검토다. 실제 hardware OOM을 고의 발생시키지 않았고 FP16/다른 GPU/다른 OS도 미검증이다. 실패와 이전 실행 기록을 삭제하지 않았다.
