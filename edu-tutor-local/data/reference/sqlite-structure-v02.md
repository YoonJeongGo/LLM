SQLite 구조와 행 데이터

DDL은 스키마를 정의·변경하는 명령의 분류입니다. CREATE TABLE은 표와 열을 정의하고, ALTER TABLE ADD COLUMN은 기존 표에 열을 추가합니다. DROP TABLE은 표를 제거합니다. INSERT INTO ... VALUES는 기존 표에 새 행을 넣습니다. 명단에 사람을 추가하는 것은 행 데이터 추가이고, 새 점수 칸을 정의하는 것은 구조 변경입니다. 다른 DBMS의 트랜잭션 규칙을 SQLite와 같다고 가정하지 않습니다.

공식 근거: https://www.sqlite.org/lang_createtable.html , https://www.sqlite.org/lang_altertable.html , https://www.sqlite.org/lang_insert.html
작성: 공식 문서를 대조해 직접 작성한 한국어 요약. AI 검토이며 사람의 교육·문장 검토는 미실시.
