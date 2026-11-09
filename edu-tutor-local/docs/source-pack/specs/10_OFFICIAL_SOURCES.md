# 공식 자료 — 2026-10-25 확인 기준

아래는 기술 선택의 참고 자료다. 이 문서 자체가 설치 버전 호환성이나 사용자 GPU에서의
동작을 증명하지 않는다. 구현 시 실제 버전·모델 revision·문서를 다시 확인하고 결과를 기록한다.
요구사항의 예산·데이터 수·UI 구조는 프로젝트 설계 선택이며 공식 최소 요구량이 아니다.

## Codex 작업 구조

- OpenAI, Run long horizon tasks with Codex:
  https://developers.openai.com/blog/run-long-horizon-tasks-with-codex
  단계 계획, 검증과 작업 기록의 참고. 한 세션 무조건 완료를 보장하지 않음.
- OpenAI, Using PLANS.md for multi-hour problem solving:
  https://developers.openai.com/cookbook/articles/codex_exec_plans
  지속적인 실행 계획 파일과 복구 가능한 진행 기록.
- OpenAI, Custom instructions with AGENTS.md:
  https://developers.openai.com/codex/guides/agents-md
  프로젝트 지침 파일과 기존 지침 확인. URL은 현재 문서로 리디렉션될 수 있음.

## 텍스트 모델·학습

- Qwen/Qwen3-1.7B 공식 모델 카드:
  https://huggingface.co/Qwen/Qwen3-1.7B
  기본 공개 모델, 라이선스·template·non-thinking 동작 확인.
- Hugging Face PEFT, Quantization:
  https://huggingface.co/docs/peft/en/developer_guides/quantization
  양자화 모델 준비와 PEFT 학습 연결.
- Hugging Face PEFT, LoRA:
  https://huggingface.co/docs/peft/en/package_reference/lora
  LoRA 설정과 적용 대상의 참고.
- PyTorch, How to use TensorBoard:
  https://docs.pytorch.org/tutorials/recipes/recipes/tensorboard_with_pytorch.html
  실제 학습 로그와 지표 시각화.

## 실행 환경과 UI

- NVIDIA, CUDA on WSL User Guide:
  https://docs.nvidia.com/cuda/wsl-user-guide/index.html
  Windows 호스트 드라이버와 WSL의 관계. 일반 Linux 드라이버를 WSL에 임의 설치하지 않음.
- FastAPI, WebSockets:
  https://fastapi.tiangolo.com/advanced/websockets/
  실시간 요청/응답 채널 구현 참고.
- FastAPI, Testing WebSockets:
  https://fastapi.tiangolo.com/advanced/testing-websockets/
  연결·이벤트 테스트 참고.

## 음성·이미지

- Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice 공식 모델 카드:
  https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice
  한국어 지원, preset voice·API·라이선스 확인. 특정 PC 지연을 공식 홍보 수치로 대체하지 않음.
- Qwen/Qwen3-VL-2B-Instruct 공식 모델 카드:
  https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct
  processor·모델 클래스·라이선스 확인. 모든 사진/수식을 정확히 읽는다는 보장이 아님.

## 구현 시 자료 확인 원칙

가능하면 공식 문서와 공식 모델 저장소만 기술 판단의 근거로 삼는다.
설치 네트워크가 없으면 로컬 docs/lockfile/캐시와 실제 import 검증을 사용하고,
온라인 확인이 안 된 내용은 unverified로 표시한다. 가짜 URL·가짜 버전 검증을 만들지 않는다.
공식 예제의 default 값도 8GB GPU와 현재 의존성에서 적합한지 별도로 시험한다.
