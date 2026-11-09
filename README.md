# AI 강의실

학생이 한국어로 개념을 묻거나 표 문제를 입력하면 캐릭터가 음성과 판서로 설명하는 로컬 학습 앱입니다. 지원하는 SQLite 문제에서는 원본 행, 조건 계산, 정렬 결과를 확인하고, 칠판의 행을 선택해 보충 설명을 들은 뒤 원래 위치로 돌아갈 수 있습니다.

2026년 11월 9일에 보관한 소스 버전은 **0.2.1 r3 repair final07**입니다. 마지막 실제 수업 검증에서 요구사항 16개 중 10개가 통과했습니다. 새 독립 질문에서 모델의 조건 오류로 설명을 제공하지 못한 사례가 있고, 준비된 모델에서도 첫 설명과 보충 설명에 각각 약 18초가 걸렸습니다. 제품 판정은 **부분 완성 · NOT_READY**, 사람의 교육·청취 검토는 **H_PENDING**입니다.

| 찾아볼 자료 | 위치 |
|---|---|
| 앱 설치·실행, Python API와 웹 강의실 | [앱 안내](edu-tutor-local/README.md) |
| 기능별 진행 상황, 측정값과 남은 문제 | [전체 진행 브리핑](edu-tutor-local/docs/PROGRESS_BRIEFING.md) · [작업 인계](edu-tutor-local/docs/CHATGPT_HANDOFF.md) |
| 배포용 검증 자료와 자작 테스트 수업 | [검증 자료 안내](evidence/README.md) |
| 최초 명세와 후속 요구사항 | [초기 개발 명세](edu_tutor_codex_pack/00_README_KO.md) · [후속 명세](edu-tutor-local/docs/source-pack-v02/) |
| 이전 소스 배포본과 학습 1회 기록 | [버전별 보관 자료](release-history/) |
| 포함된 라이브러리·폰트·캐릭터 고지 | [제3자 고지](edu-tutor-local/THIRD_PARTY_NOTICES.md) |

실제 강의실은 로컬 Python 환경, 설치한 모델, Windows Heami 음성을 사용합니다. 검증용 대사·WAV·화면은 저장소를 내려받아 [수업 갤러리](evidence/gallery/index.html)를 로컬 브라우저로 열어 확인할 수 있습니다.

운영 문서에 있는 절대경로·로컬 수업 URL·프로세스 번호·예산은 당시 검증 PC의 기록입니다. GitHub용 사본에는 앱 소스와 테스트, 실행 도구, 사전 빌드 웹 UI, 선별한 검증 자료를 담았습니다. 개인 업로드, 인증 정보, 운영 DB·장부, 모델 가중치·어댑터 및 가상환경은 원래 PC에서 관리합니다.
