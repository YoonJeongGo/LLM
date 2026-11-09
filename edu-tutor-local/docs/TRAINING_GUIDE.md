# 실제 학습과 검증

기반 모델은 Qwen3-1.7B. NF4 double quantization, LoRA r8/alpha16/q_proj/v_proj, batch1/accumulation8/max length512에서 시작한다. BF16은 실제 CUDA 지원을 확인해 사용한다. 자동 장기 학습이나 자동 어댑터 승격은 없다.

T1 tiny는 랜덤 Qwen3 소형 모델의 CPU LoRA 배선 검사이다. loss/gradient/adapter 변경/base 불변/저장 재로딩 logits를 확인하며 교육 성능 근거가 아니다.

T2 smoke는 5 optimizer step, demo는 최대50 step이다. run 폴더에 입력/데이터 해시/target token audit/제외 샘플/metrics/adapter/manifest를 기록한다. 새 프로세스가 같은 기반 모델+어댑터를 다시 읽는다. 단순 파일 존재를 재로딩 성공으로 계산하지 않는다.

시간 초과·OOM·취소·NaN은 별도 상태이며 미완료를 성공으로 기록하지 않는다. 어댑터 파일만으로는 독립 모델이 되지 않는다. 학습 loss 감소는 정확도 상승을 의미하지 않는다. 작은 평가에는 n/N과 실패·잘림을 함께 표시한다. 인간 설명 품질 평가는 별도이며 미실시 상태를 유지한다.

이 PC에서 smoke 5단계와 demo 50단계를 실제 완료했다. demo는 316 microbatch, 276.531초(별도 재로딩 포함), 최고 CUDA 할당 2,963,142,144바이트였다. 학습 가능한 어댑터 텐서 112개가 변했고 선택한 기반 가중치 검사는 불변이었다. 별도 재로딩의 160토큰 답변은 잘렸으며 COUNT/NULL 설명도 틀렸다. 기술적 재로딩 통과를 완성된 설명으로 계산하지 않는다.

고정 평가에서 기반 모델과 어댑터 모두 SQL 3/11 정답이며 12개 전체 응답 중 잘림은 0개에서 2개로 늘었다. 결과는 `runs/eval-comparison-v1/comparison.json`에 있다. 새로운 50단계 학습을 자동 반복하지 않는다. 이전 optimizer/RNG 상태에서 이어하기 기능은 제공하지 않는다. FP16 fallback 경로는 실제 장치 검증이 없고, 이번 실행은 BF16만 검증했다.

실행 지표는 `metrics.jsonl`의 실제 기록만 표시한다. 처리량은 처리한 샘플 수/실제 경과 시간이며 토큰/초와 다르다. CUDA 할당/최고 할당 메모리는 프로세스 텐서 메모리로 GPU 드라이버의 총 사용량과 같지 않다. 이전 run에 없는 지표를 나중에 만들어 채우지 않는다.
