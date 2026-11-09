# 신경망 관측 인수 기록 · 2026-10-26

기존 `D:\LLM\edu-tutor-local`에 관리자 **신경망 보기**를 추가했다. 주소는 **http://127.0.0.1:8000/#neural**. [사용 안내](NEURAL_VIEW.md)의 순서대로 질문을 입력하고 **질문 보내고 관찰**을 누른다. 새 의존성·모델 다운로드·GPU 학습·외부 전송은 추가하지 않았다. 기존 교육 정확성 **NOT_READY**, 사람 검토 미실시는 유지한다.

## 확인한 내용

실제 Qwen3-1.7B revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e` 객체의 config·named_modules·설치 forward를 대조했다. **28 Transformer 블록, 숨김 차원 2048, 관측 모듈 31개**가 일치한다. 기존 어댑터 실행에서도 `PeftModelForCausalLM`의 실제 `base_model.model` 경로를 확인했다. NF4/BF16/SDPA 설정을 유지했다. 그래프는 검증된 블록 수준 요약이며 내부 residual·attention·MLP 경로는 소스 설명이다. 전체 뉴런·attention·가중치 또는 완전한 계산 그래프를 계측한 것이 아니다.

실제 입력/생성 token ID, 요청/epoch 연결, prefill/decode, 호출 순서·shape·dtype·device, 작은 상세 표본을 수신했다. 상세는 `model.layers.0`과 `model.layers.27`의 마지막 유효 토큰 앞 32개 성분을 16 step 간격으로 읽었다. 질문 A/B의 첫 표본은 두 선택 층에서 달랐다. 모든 질문·모든 층이 항상 달라야 한다고 판정하지 않았다. host hook 시간만 측정하며 GPU 커널 완료 시간은 null이다.

기본 경량은 4 step마다 블록 메타데이터를 기록하고 누적 호출 수는 모두 유지한다. 128토큰 실행에서 실제 관측 모듈 호출 **3,968회**, 개별 기록 **992회**, 의도적 집계 생략 **2,976회**였다. 토큰 128개는 모두 실제 최종 ID와 일치했다. 최종 완료 실행들의 worker 유실·backend 버퍼 밀림은 0이었다. 초기 매 step 기록 방식의 backend 밀림 2,094건은 원본 증거에 남아 있다. 제한 버퍼는 더 긴/느린 환경에서 일부 일반 호출을 생략할 수 있다.

## 실제 GPU 질문과 기록

최대 새 토큰 128, 실제 추론 **8/8회 사용**, 추가 GPU 학습 **0회**. GPU 실행은 기존 프로세스·lease·누적 예산을 사용했다. 다음 JSON에는 실제 요청 원문·설정·run/job ID·SSE 이벤트·시각·worker 결과가 있다. 수락 검사용 합성 질문과 증거를 명시해 보관했으며 제품의 일반 질문은 기본 영구 저장하지 않는다.

질문 A: “토큰과 Transformer 층이 각각 무엇인지 한국어로 세 문장으로 설명해 주세요.”

질문 B: “SQL에서 WHERE와 HAVING의 차이를 짧은 예시와 함께 한국어로 설명해 주세요.”

질문 C: “Transformer의 임베딩, attention, MLP, 정규화, residual, 출력 토큰 선택을 각각 번호를 붙여 자세히 설명해 주세요.”

| 순서 | 질문 / 설정 | 실제 run ID | 증거 |
|---|---|---|---|
| 1 | A / 초기 OFF | `51a23e11c9674d4295011e8eb1fec75f` | [off-1](../runs/neural/current/gpu/off-1.json) |
| 2 | A / 초기 매 step 경량 | `de99cf81404440c088f7d300befbf055` | [light-1](../runs/neural/current/gpu/light-1.json) |
| 3 | A / 최종 OFF | `76099ff897214fbaa6d3e7c32b4d6c4b` | [off-2](../runs/neural/current/gpu/off-2.json) |
| 4 | A / 최종 4 step 경량 | `98bb103c061a428cbe52e363f75145a8` | [light-2](../runs/neural/current/gpu/light-2.json) |
| 5 | A / 상세 + 실제 Chrome | `8ef8f8f7dcaf4ae8a436371d29d4ef02` | [detail-a](../runs/neural/current/gpu/detail-a.json) |
| 6 | B / 상세 | `418a4696805c4de5934c53a310739147` | [detail-b](../runs/neural/current/gpu/detail-b.json) |
| 7 | C / OFF·ON·연결 종료·재접속·취소 | `a0f7ef82947e402995debb78ef103677` | [cancel-reconnect](../runs/neural/current/gpu/cancel-reconnect.json) |
| 8 | A / 기존 50-step 어댑터 + Chrome | `0323d008ee724abd9007167ccd683745` | [adapter](../runs/neural/current/gpu/adapter.json) |

7번은 실제 124토큰에서 취소했고 worker의 최종 훅 수 0·취소 결과·원문 제거 저장을 확인했다. 계측 OFF/연결 단절 중에는 토큰 이벤트가 없으므로 이 요청의 수신 토큰 전체 일치는 판정하지 않았다. 다른 7회는 128토큰 한도에서 끝난 **부분 출력**이다. 프로세스 성공을 답변 완성이나 교육 정답으로 표현하지 않으며 UI에 종료 이유를 표시한다. 이번 검증은 교육 정확성 재평가가 아니다.

## 같은 조건의 성능

| 조건 | 생성 시간 | 처리량 | 모델 로딩 | 첫 토큰 host 구간 | 이후 생성 |
|---|---:|---:|---:|---:|---:|
| 최종 OFF | 5.751 s | 22.257 token/s | 6.349 s | 0.378 s | 5.373 s |
| 최종 경량 | 6.160 s | 20.778 token/s | 6.341 s | 0.361 s | 5.799 s |

최종 생성 시간 증가 **7.12%**, 동일 입력·최종 출력 token ID 일치. PyTorch peak allocated VRAM은 둘 다 **1,972,855,808 bytes**, 증가 **0 bytes**였다. 별도 상세 A는 생성 6.246초/20.494 token/s이며 같은 모델·질문에서 작은 표본과 실제 브라우저가 함께 동작한 결과다. 이는 독립적인 반복 상세 성능 벤치마크가 아니다.

최초 매 step 기록은 11.734초→13.375초(**+13.98%**)로 10% 목표를 넘었다. 기록 빈도를 낮추고 비기록 step의 metadata 조립을 생략한 뒤 최종 쌍을 재측정했다. 초기 소스는 `runs/neural/current/source-before-aggregation/`, 원래 결과는 그대로 보존했다. 두 구현의 측정값을 평균내지 않았다. 초기와 최종 사이 시스템 부하·캐시 상태도 달라, 절대 시간 차이 전체를 최적화 효과로 단정하지 않는다.

각 요청은 독립 cold worker이며 모델 로딩·준비·generate를 분리했다. 첫 토큰은 기존 stopping callback이 streamer 뒤 처음 실행되는 지점까지 QPC host 시간이다. 최초 prefill·초기 CUDA 준비가 포함되며, **워밍업만의 독립 시간은 미측정**이고 별도 워밍업 추론은 실행하지 않았다. 이후 생성 구간을 따로 기록했다. GPU 커널 시간이 아니며 한 최종 입력 쌍으로 모든 상황의 10% 이하를 보장하지 않는다. [전체 수치](../runs/neural/current/gpu-summary.json)

## UI·재생·보안과 회귀

- Python 전체 **299/299 통과**, 128.53초. 기존 Starlette deprecation 및 CPU tiny PEFT 경고 2개를 보존했다. 전체 검사에 포함된 무작위 극소형 CPU LoRA 배선 검사는 실제 GPU 학습과 다르다. [로그](../runs/neural/current/full-tests.log), [JUnit](../runs/neural/current/full-tests.xml)
- 웹 단위 **26/26**, 최종 신규 Chrome fixture **7/7**, 기존 UI 흐름 **16/16** 통과. 기존 UI 재실행과 당시 신경망 5개를 합친 보고서는 21개이며 최신 신경망 7개와 중복 합산하지 않는다. 390/1440px·390px 200% 글자 크기에서 페이지 가로 넘침을 확인했다. [프런트엔드 증거](../web/test-results-neural/frontend-summary.json)
- 5번 실제 Chrome에서 LIVE 카운터 증가와 실제 32개 성분, 종료 후 STATIC 전환을 확인했다. [원본 LIVE 화면](../runs/neural/current/browser/actual-live-1440.png), [증거](../runs/neural/current/browser/evidence.json)
- 그 화면에서 발견된 미완성 토큰의 `U+FFFD` 대체 문자 일시 표시를 수정했다. 본문은 기존 streamer 출력만 사용한다. 원본 화면은 보존했고 최종 8번 실제 Chrome에서는 미완성 문자가 본문에 없고 이벤트가 갱신됨을 확인했다. [최종 LIVE 화면](../runs/neural/current/browser-adapter/actual-live-1440.png), [실제 브라우저 기록](../runs/neural/current/browser-adapter/evidence.json)
- 실제 5번 기록을 원문 포함/제외로 각각 명시 저장해 0.25x/1x REPLAY·일시정지·원문 제외 시 표본/토큰 없음 검증. 모델 추가 요청 0회. 최초 검증기의 20초 대기가 원래 로딩 구간을 0.25배로 재생하는 시간을 못 기다린 실패는 `replay-browser/initial-timeout-evidence.json`에 보존했다. 검증 대기를 수정한 재실행 통과는 [재생 기록](../runs/neural/current/replay-browser/evidence.json), [실제 기록의 구조·값 화면](../runs/neural/current/replay-browser/actual-record-structure-and-values.png).
- 실제 API 무인증 state/SSE 및 query-token은 401, 잘못된 Origin은 403, Host는 400. 마지막 상태는 active jobs 0·STATIC·resident false. [인증·최종 상태](../runs/neural/current/actual-final-api.json)
- 실제 유휴 API 재시작 후 이전 run은 404, 구조는 cached·resident false이며 LIVE가 되지 않았다. [재시작 확인](../runs/neural/current/restart-after-first-pair.json)
- CPU에서 표본 수치·padding·단일 토큰 prefill·cache 유무·입출력/가중치 불변·중복 훅·fail-open·느린 수신/저장·epoch/순번·원문 제거·할당 상한을 검사했다. 실제 GPU를 끄고 강제 하드웨어 오류를 만든 검증은 하지 않았다. 새 GUI에서 기존 수업의 음성·사진을 다시 생성하지 않고 기존 회귀 조건과 저장 자료를 보존했다.

## 학습·보존·운영 한계

학습 화면은 기존 `Bounds.on_log`/metrics를 읽는다. 기존 50 optimizer step·316 microbatch 표시와 현재 작업 없음은 실제 기록으로 확인했다. 미래 승인 학습의 갱신 연결과 CPU 합성 이벤트는 구현·검증했으나 **실시간 GPU 학습 시각화는 NOT RUN**이다. 과거 층별 활성값·gradient·가중치 변화를 재구성하지 않는다. 전역 grad_norm의 기록 위치와 AMP/clipping 의미는 사용 안내에 명시했다.

시작 당시 sessions 68·messages 141·jobs 110·photos 7·lessons 18 및 나머지 테이블의 기존 행이 모두 그대로다. 기존 v0.1/v0.2 배포 ZIP SHA256도 동일하다. 기본 어댑터 선택은 null(기반 모델), 기존 미승격 어댑터는 보존했다. [보존 검사](../runs/neural/current/preservation-final.json)

검증 후 보수적 프로젝트 귀속 용량은 약 **20.603 GB**, C 여유 약 **98.8 GB**로 50GB 한도/40GB 경고/C 여유50GB 정책을 유지한다. 실제 데이터 경로는 D 드라이브이며 F 드라이브를 가정하거나 데이터를 옮기지 않았다. 새 기록과 검증 자료도 전체 용량에 포함했다. 예산은 기존 누적 **3073.675/5400초**, 남음 약 **2326.325초**이며 이번 자동 검증의 8회 한도는 소진됐다. 새 자동 GPU 검사를 임의로 추가하지 않는다. [저장공간](../runs/neural/current/storage-final.json)

관측을 끄려면 **관측 끄기**, 화면만 멈추려면 **화면만 일시정지**, 계산을 중단하려면 **모델 작업 취소**를 사용한다. 관측 오류 시 훅을 정리하고 기존 채팅/강의실로 돌아간다. 모델 오류 자체를 성공으로 바꾸지는 않는다. 제한/불변/시각화 검증은 교육·청취 품질 보증이 아니며 기존 NOT_READY 판단은 유지한다.
