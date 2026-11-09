Qwen3-4B-Instruct-2507 후보 검토 — 2026-10-29

판정은 **기존 환경에서 비교 검토할 수 있는 후보, 아직 선택하지 않음**이다. 다운로드·설치·실제 모델 호출은 0회이며 성공한 SAPI·텍스트 상주 코드와 설정을 변경하지 않았다. 우선 기존 가중치 BF16 비교와 수정 데이터의 실험 2 결과로 추가 모델 필요성을 판단한다. 모델 크기나 제조사 벤치마크로 이 앱의 SQL 정확성·한국어 설명·속도가 개선된다고 단정하지 않는다.

공식 모델은 `Qwen/Qwen3-4B-Instruct-2507`, 확인한 main revision은 `cdbee75f17c01a7cc42f958dc650907174af0554`이다. 비사고형 Qwen3이며 별도 thinking 토큰을 생성하도록 설계된 모델이 아니다. Transformers 4.51.0 미만은 지원되지 않는다고 명시한다. [공식 모델 카드](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507), [확인한 commit](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/commit/cdbee75f17c01a7cc42f958dc650907174af0554)

라이선스는 Apache-2.0이며 공식 LICENSE를 확인했다. 향후 파일을 받을 경우 원문 LICENSE·README와 고정 revision·크기·체크섬을 manifest에 보존해야 한다. [공식 LICENSE](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/blob/main/LICENSE)

| 대조 항목 | 현재 로컬에서 읽어 확인한 값 | 판단 |
|---|---|---|
| Python | 프로젝트 .venv, 3.12.14 | 버전만으로 차단할 사유 없음 |
| torch | 2.9.1+cu128 | 기존 NVIDIA 경로 유지 가능성 |
| transformers | 4.57.3 | 모델 카드의 4.51.0 최소 범위 이상 |
| accelerate / peft | 1.12.0 / 0.18.1 | 이미 설치됨; 새 모델에 기존 LoRA를 붙여도 된다는 뜻은 아님 |
| bitsandbytes | 0.48.2, cuda128 DLL 존재 | Windows CUDA12.8 sm86 지원 범위와 일치 |
| tokenizer / safetensors | tokenizers0.22.2 / safetensors0.8.0 | 기존 BPE·safetensors 읽기 경로 사용 가능성 |
| GPU | RTX3060 Ti, 8192MiB, CC8.6, 드라이버610.88 | `nvidia-smi` 조회만 수행; 후보 메모리·커널 실행 검증 아님 |

bitsandbytes0.48.2의 공식 Windows x86-64 CUDA12.8–12.9 목록에 sm86이 포함되고 NF4의 최소 compute capability는6.0이다. 패키지·CUDA·드라이버 업그레이드를 선행조건으로 추가할 근거는 현재 없다. [해당 버전 설치 문서](https://huggingface.co/docs/bitsandbytes/v0.48.2/installation)

공식 저장소 표시 총크기는 **약8.06GB**이며 신규 다운로드12,000,000,000바이트 한도 안이다. 아래 세 shard의 정확한 크기 합계는 **8,044,982,000바이트**다. 이것은 원래 BF16 체크포인트의 디스크 크기이며 NF4 GPU 점유량이 아니다. 전체 파일의 정확한 바이트 합계·체크섬은 실제 다운로드를 결정한 뒤 공식 metadata로 다시 고정해야 한다. 이번에는 모델 파일 본문이 아니라 공식 웹 페이지와 LFS pointer 텍스트만 열람했다. [공식 전체 파일 목록](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/tree/cdbee75f17c01a7cc42f958dc650907174af0554)

| 파일 | 확인한 크기 |
|---|---:|
| model-00001-of-00003.safetensors | 3,957,900,840바이트 |
| model-00002-of-00003.safetensors | 3,987,450,520바이트 |
| model-00003-of-00003.safetensors | 99,630,640바이트 |
| tokenizer.json | 약11.4MB |
| vocab.json | 약2.78MB |
| merges.txt | 약1.67MB |
| model.safetensors.index.json | 약32.8KB |
| LICENSE / README.md | 약11.3KB / 8.17KB |
| config.json / generation_config.json | 727 / 238바이트 |
| tokenizer_config.json | 약9.38KB |
| .gitattributes | 약1.57KB, 실행에는 필요 없음 |

shard 크기는 각각 [pointer1](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/raw/main/model-00001-of-00003.safetensors), [pointer2](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/raw/main/model-00002-of-00003.safetensors), [pointer3](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/raw/main/model-00003-of-00003.safetensors)에서 확인했다. 최신 로컬 장부의 저장공간 추정은20,862,945,179바이트, 당시 C 여유79,525,019,648바이트·D 여유211,423,305,728바이트였다. 향후 실행 시에는 이 숫자를 재사용하지 말고 기존50GB 프로젝트 한도·C 여유50GB 검사와 scope 다운로드 장부를 다시 적용해야 한다. 기존 가중치 보존과 불필요한 이중 다운로드 캐시 회피가 필요하다.

8GB NF4 가능성은 **추정**이다. 모든4B 파라미터를 단순히4비트로 본 약2GB는 하한에 불과하다. 선형층만 NF4로 바꾸고 큰 embedding·일부 모듈은 고정밀로 남으면 가중치는 대략2.5GiB 수준부터 시작할 수 있다. CUDA context·workspace·activation·allocator 여유·디스플레이 사용량·로딩 순간 피크를 더해야 하므로 전체 실행3–6GiB 정도를 계획상의 범위로만 볼 수 있다. 실제 적재 가능성이나 안정성을 보증하는 수치는 아니다. 기존 NF4·double-quant·BF16 compute·SDPA 설정을 유지한 실측이 필요하다. [Transformers의 NF4 설명](https://huggingface.co/docs/transformers/v4.57.3/quantization/bitsandbytes)

config의36층·KV8개·head_dim128을 이용하면 batch1, BF16 KV cache의2048토큰 계산값은 `2×36×8×128×2048×2 = 301,989,888바이트`다. 모델 카드의262,144토큰을 이 장비에서 허용할 근거는 없다. 현재 앱의 입력+출력2048토큰 제한을 유지해야 한다. [공식 config](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/blob/main/config.json)

최소 교체 범위는 새 추론 엔진 도입이 아니라 다음 연결이다.

- 기존 `.local/models/text`를 덮어쓰지 않는 후보별 폴더·manifest와 명시적 선택/원복. 현재 `scripts/download_model.py`는 phase2 enabled이면 거절하며 모델 allowlist도1.7B 고정이다. 차단을 제거하고 실행하는 방식으로 진행하면 안 된다. 향후 필요가 확인되면 현재 승인 scope의 다운로드 byte/candidate 장부를 쓰는 제한 경로를 별도로 연결한다.
- `models/worker.py:load_text`, `models/runtime.py:model_status`, `models/text_session.py:_key`가 동일한 선택 manifest를 사용하도록 최소 수정. 현재 폴더와 runtime 표시 model_id가1.7B에 고정돼 있다. 캐시·상주 키에는 모델ID/실제경로/revision을 넣고 모델 전환 때 이전 owned worker를 닫아야 한다.
- 1.7B 어댑터를4B에 연결하지 않는다. 현재 학습 runner의1.7B 제한을 이번 추론 비교를 이유로 넓히지 않는다. 후보 검사는 base-only이며 기존 학습 기록과 어댑터는 보존한다.
- 새 tokenizer의 non-thinking template와 EOS를 확인한다. 공식 generation_config는 EOS `[151645,151643]`인데 현재 worker는 `tokenizer.eos_token_id` 한 개로 생성·완료를 판정한다. 종료 목록을 명시적으로 정규화하고 EOS/길이제한/취소를 구분하는 회귀가 필요하다. [공식 generation 설정](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/blob/main/generation_config.json)
- 현재 greedy 설정을 유지한 첫 비교와 공식 sampling 권고를 적용한 실험은 서로 다른 조건으로 기록한다. 출력 길이·template·quantization 차이를 숨기지 않는다. 신경망 시각화는 기본OFF를 유지하고 후보에 기존 구조 캐시를 잘못 표시하지 않는다. SAPI·판서 지문·기존 큐/인증/timeout/취소는 유지한다.

후보를 실제로 검증하기로 결정할 때 필요한 증거는 다음과 같다.

1. 원본35개 SQL·개념 문항과 의미 반례를 고정해 원시 모델의 SQL 값 일치, 의미 조건, 설명 오류를 따로 채점한다. 기준선20/35 값 일치를 교육 품질 통과로 바꾸지 않는다. 앱의 SQL 검증·교정 결과와 원시 모델 결과를 분리한다.
2. 실제8GB 장비에서 제한된 cold 적재와 warm 재사용의 PID·모델 인스턴스·로딩 횟수, peak allocated/reserved VRAM, 정상 EOS·OOM·종료 상태를 기록한다. 해당 환경에서 실패하면 자동 재시도하지 않는다.
3. 같은 질문·입출력 설정을 사용해 로딩·첫 토큰·생성·전체 응답을 나누고, 실제 수업에서는 첫 유효 음성·단계 공백·중간 질문 재설명도 확인한다. 큰 모델이라는 이유로 더 빠르다고 가정하지 않는다.
4. 취소·모델 전환·idle 종료·재시작 후 GPU lease가 남지 않는지 확인한다. 기존 음성·판서·손동작의 실제 수업 연결은 별도 통합 증거가 필요하다.
5. 정답 수나 자동 검사만으로 NOT_READY/H_PENDING을 해제하지 않는다. 한국어 설명의 교육적 적절성·이해 가능성·청취 품질은 실제 사람이 검토해야 한다.

이 문서는 공식 후보 검토의 저장 기록이며 다운로드 지시나 모델 선택 기록이 아니다.
