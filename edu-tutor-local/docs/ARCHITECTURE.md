# 구조

React → localhost 인증 API → SQLite/작업 관리자 → 격리 worker → 로컬 모델. API 프로세스는 대형 가중치를 적재하지 않는다. 텍스트·학습·음성·비전 worker가 같은 `.local/gpu.lock`을 사용한다. lock 메타데이터는 PID·시작 시간·heartbeat를 기록한다. 취소·timeout은 해당 Popen으로 생성한 자식만 대상으로 하며 다른 프로세스는 건드리지 않는다.

대화와 작업은 SQLite 트랜잭션으로 보존한다. 요청에는 session/request/epoch를 붙이며 오래된 스트림을 폐기한다. 서버 시작 시 미완료 job은 interrupted로 복구한다. 자료 검색은 승인된 문서의 한국어 문자 2~4gram TF-IDF. 출처는 실제 청크 ID로만 반환한다.

SQL은 일회성 DB subprocess에서 authorizer/query_only/progress/time/row 제한을 적용한다. 사진은 decode와 EXIF 회전을 거쳐 위치 메타데이터를 버린 PNG로 저장하고, 전사 후보를 사용자가 수정·확정해야 풀이할 수 있다.

강의는 JSON schema → 순수 scene reducer → HTML/SVG 판서로 렌더링한다. 생성 문자열을 HTML/JS로 실행하지 않는다. 음성은 local WAV와 실제 duration을 생성하고 인증된 fetch로 재생한다. 모델과 어댑터는 고정 revision·safetensors·local_files_only 경로를 사용한다.
