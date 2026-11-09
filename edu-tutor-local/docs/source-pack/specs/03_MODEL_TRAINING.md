# 로컬 모델·실제 추가 학습

## 모델 선택

기본 텍스트 모델은 `Qwen/Qwen3-1.7B`다. 이는 작은 실험 출발점이며 최신/최고 교육 모델이라는 뜻이 아니다.
후속 4B 이상 모델을 자동 다운로드하지 않는다. 모델 카드, 라이선스, revision, chat template을 기록한다.
학습에는 Transformers 공식 가중치를 사용하고 GGUF 추론 파일을 QLoRA 학습에 넣지 않는다.
기본 trust_remote_code=False, 모델·어댑터는 safetensors 우선. 불명확한 저장소 코드를 자동 실행하지 않는다.

LoRA/QLoRA는 기존 공개 모델에 추가한 작은 학습 부분을 수정하는 방식이다.
어댑터만 저장한 것을 독립적인 기반 모델을 새로 만들었다고 표현하지 않는다.
실제 사용 기반 모델과 revision이 다르면 어댑터 적용 전에 호환성을 검사한다.

## 학습 전 기준선

기반 모델만으로 한국어 설명·NULL·조건 부족·표 있는 SQL 문제를 실행한다.
입력·생성 옵션·출력·소요 시간·peak VRAM·끝난 이유를 저장한다.
Qwen3의 non-thinking 설정을 공식 template에 맞게 적용하고, 답변에는 공개 설명만 표시한다.
토큰 제한으로 잘린 답변을 정상 완성으로 채점하지 않는다.
구조화 출력은 모델 능력을 보장하지 않는다. JSON 검증과 재생성 제한은 강의 명세를 따른다.

## 초기 학습 설정

프로젝트 정책의 출발점이지 최적값·8GB 성공 보장값이 아니다.
- 4bit NF4, double quantization.
- compute dtype: 실제 BF16 지원 확인 시 BF16, 아니면 검증된 FP16 경로.
- prepare_model_for_kbit_training 후 PEFT 연결.
- r=8, alpha=16, dropout=0.05, target_modules=[q_proj, v_proj].
- batch size=1, gradient accumulation=8, learning rate=1e-4.
- max sequence length=512, packing=False, gradient checkpointing=True, use_cache=False.
- single GPU 명시. 추론용 device_map=auto로 CPU/offload 분산을 몰래 적용하지 않는다.
- 기본 seed=42. seed 고정을 다른 장치/라이브러리 버전의 비트 단위 재현 보장으로 설명하지 않는다.
- optimizer는 설치 환경에서 검증되는 표준 AdamW 경로를 우선하고 불필요한 추가 optimizer 의존성을 피한다.
- 5 optimizer step smoke를 먼저 수행한다. microbatch 5회와 optimizer step 5회를 혼동하지 않는다.

전체/학습 가능 파라미터 수, 실제 target module 이름, dtype, 입력 길이, device를 manifest에 기록한다.
원래 가중치의 requires_grad와 optimizer 파라미터 목록을 확인한다.
처음 LoRA 초기화에서 일부 행렬 gradient가 0인 것은 가능하므로, 모든 파라미터가
첫 step부터 비영 gradient여야 한다는 잘못된 테스트를 만들지 않는다.

## 응답 구간 마스킹 — 반드시 실제 토큰 검사

초기 데이터는 단일 질문-단일 답변으로 단순화한다. multi-turn을 지원하면 마지막 assistant 응답만
target으로 하고 이전 대화는 context로만 사용하는 규칙을 명시한다.

1. 고정한 revision의 tokenizer와 실제 chat template을 읽는다.
2. 추론 시 쓰는 generation prefix와 학습용 완성 대화의 assistant 시작 부분이 같은지 확인한다.
   Qwen3 non-thinking의 빈 think 블록이 들어갈 수 있음을 고려한다.
3. prefix 토큰과 전체 학습 토큰의 공통 앞부분을 **실제 토큰 ID로** 검증한 뒤 답변 시작 경계를 구한다.
   문자 길이나 별도로 tokenize한 문자열 길이를 무조건 믿지 않는다.
4. template이 prefix 안정성을 제공하지 않으면 공식 형식을 유지하는 canonical serializer를 만들고
   model-specific prefix+completion 경로를 fixture로 검증한다. 답변 내용이 중복되어도 위치가 정확해야 한다.
5. prompt/context 및 padding의 labels는 -100. 실제 답변과 정상 종료 `<|im_end|>`는 target에 남긴다.
   pad_token_id == eos_token_id인 설정에서 ID만으로 모두 가리면 실제 EOS가 사라질 수 있으므로
   유효 길이/attention mask로 padding을 구분한다.
6. causal LM 자체의 label shift를 사용하고 수동 shift를 중복 적용하지 않는다.
7. target token 0개, 정답 잘림, 모든 labels=-100 샘플은 학습 전에 실패시킨다.
8. input tokens, target mask, target만 decode한 문자열을 샘플별 검증 파일로 남긴다.

장문을 조용히 자르지 않는다. 초과 샘플은 제외/교육 단위로 분리하고 원래 ID와 사유를 기록한다.
max_length를 늘리려면 VRAM 검증과 설정 변경 내역이 필요하다.
loss mask 테스트와 실제 생성 template 테스트는 서로 별도다.

## GPU 없는 환경의 CPU 배선 테스트

실제 1.7B 가중치를 다운로드하지 않고 작은 랜덤 초기화 Qwen3Config 모델을 만든다.
예: vocab_size≤512, hidden_size=64, intermediate_size=128, layers=2,
attention_heads=4, key_value_heads=2, 짧은 sequence. 실제 설치 버전이 지원하는 필드로 구성한다.
이 모델은 **배선 검증용이지 학생에게 서비스할 교육 모델이 아니다.**

FP32 일반 LoRA로 finite loss, target masking, gradient, optimizer update, adapter save/load를 검사한다.
기반 모델 초기 state/config를 한 번 저장하고 어댑터 재로딩에도 정확히 같은 기반 가중치를 사용한다.
새 random base에 어댑터를 붙이고 출력 일치 테스트를 하면 안 된다.
trainable weights가 실제 변하는지, frozen base가 그대로인지 비교한다.
eval mode/dropout off 상태의 저장 전후 logits를 dtype에 맞는 tolerance로 비교한다.

tokenizer를 캐시/네트워크로 확보하면 실제 Qwen template도 CPU에서 테스트한다.
토크나이저조차 없으면 로컬 synthetic fixture로 공통 로직만 검사하고,
**실제 Qwen template 검증은 미실행**이라고 별도 표시한다.
CPU backend가 없다고 단정하는 설명 대신, CPU 배선 테스트에서 비양자화 LoRA를 쓰는 이유를
작은 의존성·빠른 확인·CUDA 통합과의 분리라고 설명한다.

## 실제 GPU 검증

text 모델 4bit load → 기준선 → 5 optimizer step → 저장 → worker 종료 →
새 프로세스에서 같은 기반 모델+어댑터 load → 응답 생성 순서로 확인한다.
CPU test pass를 이 증거로 대체할 수 없다.
실제 학습 후 가중치 비교는 어댑터 위주로 하고 frozen base는 파라미터 동결·optimizer 제외 및
선택한 모듈의 체크섬/값 비교를 기록한다. GPU 전체 모델 복사로 불필요한 OOM을 만들지 않는다.

smoke가 통과하면 정책 범위의 50 optimizer step 이하 데모 학습 1회까지 허용된다.
시간 제한으로 50 step에 못 미치면 실제 step을 표시한다.
NaN/inf, OOM, loss target 부재, 디스크 부족은 즉시 안전 중단·원인 기록.
훈련 worker는 앱 큐와 같은 GPU lease를 잡아 채팅/TTS/비전과 충돌하지 않도록 한다.

## 체크포인트와 재개

각 run에는 adapter safetensors/config, 기반 revision, tokenizer/template, 데이터 해시,
설정, 패키지 버전, 실제 완료 step, 평가 결과를 기록한다.
어댑터 가중치 저장과 학습 상태 체크포인트를 구분한다.
학습 이어하기를 지원하려면 optimizer, scheduler, global_step, RNG, 데이터 진행 상태를
현재 Trainer 방식으로 저장하고 실제 중단-재개 테스트를 수행한다.
재개 테스트가 없으면 “가중치에서 새 학습”과 “이전 학습 이어하기”를 같은 기능으로 표시하지 않는다.

관리자는 기반 모델/어댑터 사용을 선택하고 이전 버전으로 되돌릴 수 있어야 한다.
평가 나쁜 어댑터를 자동 기본값으로 승격하지 않는다. 모델 로더 교체 시 실행 중 작업과 경합을 막는다.
