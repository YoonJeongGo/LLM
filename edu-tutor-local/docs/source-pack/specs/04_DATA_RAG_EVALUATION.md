# 데이터·자료 검색·평가

## 세 종류의 데이터 구분

1. **교육자료 corpus**: 답할 때 참고하는 원문·출처·페이지. 검색 인덱스 생성은 가중치 학습이 아니다.
2. **추가 학습 dataset**: 검토된 좋은 질문/답변 또는 명확히 표시한 데모. 가중치 변경에 사용.
3. **독립 평가 dataset**: 학습 데이터·프롬프트 예시·검색 인덱스의 정답집과 분리.

`problem_family_id`로 분할하고 이름/숫자만 다른 문제군이 split을 넘나들지 않게 한다.
데이터를 수정하면 version/hash를 새로 생성한다. 동일 family는 한 split에만 존재한다.
모델 사전학습 데이터에 무엇이 있었는지 완전히 확인했다고 주장하지 않는다.

## 새로 작성하는 데모

기본키, 외래키, NULL, COUNT, WHERE/HAVING, 기본 JOIN, GROUP BY 등 소규모 예제로 시작한다.
기출 문장·유료 교재·강사 말투를 기억에서 그대로 복원하지 않는다.
train≥24, validation≥8, test≥12는 기능 점검을 위한 최소 규모일 뿐 성능의 통계적 보장 기준이 아니다.
문제 종류별 다양성을 유지한다. 수량 기준 때문에 잘못된 정답을 급히 넣지 않는다.

형식은 `schemas/qa_record.schema.json`을 따른다. 직접 작성한 자료도 source와 created_by를 남긴다.
AI 생성 예제에는 `review_status=generated_unreviewed`, `demo_only=true`를 기본으로 한다.
SQL 실행으로 확인한 부분은 `machine_verified` 검증 기록을 별도 추가할 수 있지만,
교육 설명 전체가 인간 검토된 것으로 승격하지 않는다.

데모 학습은 명시적 demo profile에서 미검토 생성 예제를 사용할 수 있다.
운영 학습 profile은 사람이 승인한 자료만 포함한다. 관리자 승인 action과 시간을 감사 로그에 남긴다.
학생 대화·개인정보·오답은 자동으로 학습셋에 들어가지 않는다.

필수 검사: 필드·역할 순서·중복·family 분리·source·권리 메모·token 길이·응답 target·NULL 표현.
NULL은 문자열 "NULL"이 아닌 null로 저장하고 UI에서 NULL로 표현한다.

## 검색(RAG)

기본 입력은 TXT/MD 및 텍스트가 들어 있는 PDF. PDF는 페이지별 텍스트 추출 후
사람이 미리보기를 확인한다. 스캔 PDF/복잡한 표는 자동 정확 인식이라고 하지 말고
사진 인식/수동 확인 경로로 보낸다.

첫 검색 엔진은 한국어 문자 n-gram TF-IDF + SQL 키워드 보정을 사용해 CPU에서 실행한다.
예: TfidfVectorizer의 char 2~4그램. 구현·데이터에 맞춰 확인하며 검색 성능 보장은 하지 않는다.
임베딩 GPU 모델/벡터 DB는 필수로 추가하지 않는다. 추후 provider 교체 인터페이스만 명확히 둔다.

청크에는 document_id, chunk_id, source_title, page/line, text, rights, subject, version을 저장한다.
검색한 실제 청크 ID만 답변 출처로 연결한다. 모델이 임의 생성한 source ID는 reject한다.
해당 문서 삭제 시 청크·인덱스·사용되지 않는 캐시를 삭제하고 재검색 테스트를 한다.
질문 데이터는 사용자 승인 없이 외부 임베딩/검색 API로 보내지 않는다.

검색 문서 안의 "이전 지시 무시" 등은 자료의 문자 내용일 뿐 시스템 명령이 아니다.
추출 문서가 모델의 도구 권한이나 파일 쓰기 대상을 정할 수 없게 한다.
자료가 없거나 관련성이 낮으면 그 상태를 답변에 표시한다. 출처가 있다고 내용이 무조건 맞는 것도 아니다.

## SQL 자동 검증 계약

초기 실행 검증의 공식 dialect는 `sqlite`로 한정한다. 이것은 Oracle을 구현했다는 뜻이 아니다.
Oracle 전용 SQL은 Oracle 실행 환경이 없으면 `not_executed`로 표시한다.
단순 SQLite 결과를 Oracle 정답으로 포장하지 않는다.

각 실행 평가 예제에는 fixture.tables의 스키마/행, reference SQL 또는 expected columns/rows,
row_order 설정, 숫자 비교 정책을 명시한다. 예제 JSON을 참고한다.
신뢰한 fixture로 일회성 DB를 준비한 뒤 실제 모델 SQL은 SELECT 계열의 읽기 전용으로 제한한다.

모델 SQL 추출 규칙은 버전 있는 구조 `{sql, explanation}`을 우선 사용한다.
파싱이 실패하면 코딩 블록 `sql` 하나만 존재하는 응답에서만 추출한다.
여러 SQL 블록/여러 문장/정체 불명의 내용이면 ambiguous_parse로 처리한다.
정규식만으로 임의 SQL을 안전하다고 판단하지 않는다.

별도 subprocess에서 다음을 함께 적용한다.
- 임시/일회성 DB, 사용자 DB 연결 금지.
- SQLite authorizer 및 query_only 설정으로 DML/DDL/ATTACH/확장 로딩 등 금지.
- 위험 함수/PRAGMA/파일 접근을 허용하지 않음; 단일 읽기 전용 문장만 실행.
- progress handler/시간/행 수/출력 크기 제한, 무한 recursive query 방지.
- 실패는 오류로 기록하고 실제 DB나 OS를 조작하지 않음.

ORDER BY가 없으면 결과는 중복 수를 보존하는 multiset으로 비교한다.
단순 set 비교로 중복 행 오류를 놓치지 않는다. ORDER BY가 있으면 명시된 행 순서를 비교한다.
컬럼 순서는 명세대로 비교한다. float 허용 오차는 평가 예제에서 정하고,
모든 숫자를 임의 문자열 변환해서 같다고 만들지 않는다.

## 학습 전후 평가

항상 표시할 문구:
“소규모 데모 평가입니다. 파이프라인 검증용이며, 전체 교육 성능이나 일반화 성능을 보장하지 않습니다.”

같은 문제·동일 생성 조건·동일 revision·동일 RAG 자료 조건으로 baseline vs adapter를 비교한다.
기본 학습 비교는 RAG off. RAG 유무 효과는 별도 실험으로 분리한다.
평가 정답/해설을 RAG corpus에 넣지 않는다. 의도한 오픈북 평가는 그 사실과 corpus를 기록한다.
평가셋을 보고 설정을 반복 조정했다면 test 독립성이 깨졌음을 표시하고 새 holdout을 둔다.

자동 지표: schema success, SQL parse/execution/result match, 필요한 조건 누락 시 확인 요청,
source ID 유효성, 끊김/timeout, latency/VRAM. 자동 규칙의 한계를 함께 기록한다.
사람 지표: 설명 정확성, 중간 과정 충분성, 쉬운 용어 풀이, 잘못된 확신, 학생의 오해 교정.
사람 평가를 실행하지 않았으면 점수를 지어내지 말고 `not_reviewed`로 둔다.
모델 자신이 매긴 점수를 인간 평가로 표시하지 않는다.
정답률은 n/N을 함께 보여주고, loss 감소를 정답률 증가로 설명하지 않는다.
