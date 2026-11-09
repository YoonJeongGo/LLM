# 제삼자 구성요소

- Qwen3-1.7B, Qwen3-VL-2B-Instruct, Qwen3-TTS-12Hz-0.6B-CustomVoice: Qwen 공식 공개 모델, Apache-2.0. revision과 파일 목록은 `runs/downloads/*-inventory.json`; 다운로드 완료 체크섬은 `.local/models/*/model-manifest.json`.
- Transformers, PEFT, Accelerate: Hugging Face, Apache-2.0.
- PyTorch: PyTorch contributors, BSD-style license. CUDA wheel에 포함된 제삼자 고지는 해당 배포본을 따른다.
- FastAPI, React, React DOM, Scheduler, Vite, TypeScript, Ajv, KaTeX: 각 프로젝트의 설치 배포본 고지를 따른다. 아래 UI 구성요소의 MIT 원문은 release에 함께 포함한다.
- Lucide React 0.468.0: ISC. 설치 LICENSE의 Feather 유래 부분에 대한 Cole Bemis/MIT 저작권 문구도 원문 그대로 보존한다.
- NumPy, SciPy, scikit-learn, Pydantic, Pillow, pypdf 등: 설치 배포본의 LICENSE/METADATA를 따른다. 실제 설치 버전은 requirements-lock.txt 및 web/package-lock.json.
- 기본 아바타/UI와 데모 교육 데이터는 이 프로젝트에서 생성. 데모 데이터는 인간 내용 검토 전이다.
- SQLGlot 30.12.0: MIT, 제한된 SQL 구문 트리 분석에 사용. [설치본 원문](docs/licenses/sqlglot-LICENSE.txt), [공식 문서](https://sqlglot.com/sqlglot). SQL 실행 안전 경계는 기존 격리 SQLite 검사기다.

모델 가중치·사용자 업로드를 소스 release에 재포장하지 않는다. 외부 캐릭터 자산은 권리 확인 후 사용한다.

## 사전 빌드 UI에 동봉하는 원문

`web/dist`에 포함된 브라우저 UI 및 생성 도구의 관련 고지다. 설치된 로컬 패키지에서 아래 원문을 그대로 복사했으며, 패키지 버전·출처 경로·SHA256은 [라이선스 목록](docs/licenses/license-inventory.json)에 기록했다. 각 배포본의 저작권과 허가·면책 조항을 유지한다.

| 구성요소 | 확인한 설치 버전 | 원문 |
|---|---|---|
| React | 19.3.1 | [MIT](docs/licenses/react-LICENSE.txt) |
| React DOM | 19.3.1 | [MIT](docs/licenses/react-dom-LICENSE.txt) |
| Scheduler | 0.28.0 | [MIT](docs/licenses/scheduler-LICENSE.txt) |
| Lucide React | 0.468.0 | [ISC 및 기존 저작권 고지](docs/licenses/lucide-react-LICENSE.txt) |
| KaTeX | 0.16.47 | [MIT](docs/licenses/katex-LICENSE.txt) |
| Ajv | 8.20.0 | [MIT](docs/licenses/ajv-LICENSE.txt) |
| Vite | 6.4.5 | [Vite 및 배포본의 포함 의존성 고지](docs/licenses/vite-LICENSE.txt) |

Vite 고지는 빌드 도구 및 생성된 module-preload 지원 코드의 출처를 보존한다. Vite LICENSE에 나열된 모든 도구 의존성이 브라우저 bundle에 포함된다는 뜻은 아니다. KaTeX의 배포 CSS·폰트도 설치 패키지의 고지와 함께 보존한다. 전체 Python 환경·Node 개발 의존성·모델 가중치는 이 소스 패키지에 포함하지 않는다.

기본 아바타의 기존 CC0-1.0 선언과 구현 출처는 [아바타 자산 고지](docs/licenses/PROJECT_AVATAR.md) 및 [원본 manifest](web/src/avatar-manifest.json)를 참고한다. 이 선언은 전체 앱 소스나 외부 교체 PNG에 적용되지 않는다.
