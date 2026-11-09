# 구현 결정

- 2026-10-25: 기존 작업 폴더가 비어 있어 `edu-tutor-local`을 새로 생성. 첨부 지시는 요구사항 자료로 읽고, 대형 다운로드·GPU 학습은 사용자에게 별도로 확인받음.
- 기본 Python 3.14 대신 이미 설치된 번들 Python 3.12.14로 프로젝트 venv를 생성. ensurepip 실패는 번들 pip의 `--python`으로 프로젝트 venv에만 설치하여 해결.
- React/Vite와 FastAPI/SQLite 유지. 호스트는 127.0.0.1; API 토큰 및 Origin 검사. GPU 작업은 subprocess + 동일 OS file lock으로 직렬화.
- 공식 TTS 프로젝트가 Transformers 4.57.3 / Accelerate 1.12.0을 명시하므로 텍스트/비전도 이 조합을 먼저 import·실행 검증. 검증된 버전은 최종 lockfile에 기록. 최신 버전이라는 이유로 업그레이드하지 않음.
- Qwen3-1.7B revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`; Qwen3-VL-2B-Instruct `89644892e4d85e24eaac8bacfd4f463576704203`; Qwen3-TTS-12Hz-0.6B-CustomVoice `85e237c12c027371202489a0ec509ded67b5e4b5`. 공식 저장소의 Apache-2.0과 파일별 크기를 다운로드 전에 확인. 실제 파일 체크섬은 각 로컬 model-manifest.json.
- 브라우저나 외부 음성 서비스 fallback을 사용하지 않음. 음성이 없으면 자막·수동 판서로 명시. 비전 모델이 없으면 자동 인식 성공 대신 수동 원문 확인 제공.
- 학습 재개 기능은 어댑터 재로딩과 구분. optimizer/RNG 중단 재개 검증이 없으면 지원한다고 표시하지 않음.

공식 참고: [Qwen text](https://huggingface.co/Qwen/Qwen3-1.7B), [PEFT 양자화](https://huggingface.co/docs/peft/en/developer_guides/quantization), [Qwen TTS](https://github.com/QwenLM/Qwen3-TTS), [Qwen vision](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct).
