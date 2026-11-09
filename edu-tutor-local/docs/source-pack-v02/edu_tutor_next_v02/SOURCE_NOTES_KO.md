# 근거와 범위

아래는 2026-10-26에 확인한 공식 문서다. 프로젝트 설치 버전과 문서 버전의 차이를 확인한다.
라이브러리 업그레이드 지시가 아니다. 이 문서가 사용자 앱의 실행 성공을 증명하지 않는다.

- Qwen3-1.7B 공식 모델 카드: 사전학습·후속학습을 거친 모델, non-thinking 및 대화 형식.
  https://huggingface.co/Qwen/Qwen3-1.7B
- PEFT LoRA: 기존 기반 가중치를 고정하고 학습 가능한 부분을 추가하는 방식.
  https://huggingface.co/docs/peft/en/package_reference/lora
- PyTorch 학습: loss, backward, optimizer.step의 역할.
  https://docs.pytorch.org/tutorials/beginner/basics/optimization_tutorial.html
- Transformers 생성 설정: max_new_tokens 및 종료 조건.
  https://huggingface.co/docs/transformers/en/main_classes/text_generation
- Codex 장기 작업: 계획·진행 기록·단계별 검증을 유지하는 개발 방식.
  https://developers.openai.com/blog/run-long-horizon-tasks-with-codex
- SQLite 집계: COUNT, SUM, AVG의 NULL 및 빈 입력 동작.
  https://www.sqlite.org/lang_aggfunc.html
- SQLite SELECT: 그룹, DISTINCT, 조인, 논리적 설명과 실제 실행의 구분.
  https://www.sqlite.org/lang_select.html
- Oracle 19c SQL 문장 분류: DDL/DML 설명의 DBMS 기준 확인.
  https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Types-of-SQL-Statements.html

SQL fixture는 위 개념을 시험하려고 새로 만든 예제이며 시험 기출 재현이 아니다.
출처 표기는 판서/해설을 만들기 위한 개념 확인용이지 사용자 제공 교재라고 주장하는 표시가 아니다.
검사기가 확인하는 것은 reference_sql과 직접 지정한 expected_rows의 일치다.
실제 모델이 이 문제를 맞혔거나 자연스럽게 가르쳤다는 의미가 아니다.
