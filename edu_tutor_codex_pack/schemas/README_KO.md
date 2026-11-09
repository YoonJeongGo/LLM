# JSON 계약 사용법

JSON Schema는 형식·타입·허용 명령을 검사하기 위한 출발점이다. 실제 앱에서는 Pydantic/TypeScript 타입과
일치시키고, 필요한 수정은 schema_version 변경·migration·예제·테스트를 함께 갱신한다.

스키마만으로 모든 의미를 검증할 수는 없다. 다음은 별도 검사해야 한다.
- table 행 너비가 columns 수와 같은지.
- step ID와 생성 element ID가 중복되지 않는지.
- highlight/arrow/gesture가 현재 board에 존재하는 element를 가리키는지.
- 행·열 highlight index가 실제 범위 안인지.
- source_refs가 실제 검색한 document/chunk를 가리키는지.
- confirmed_image일 때 원문 확정 기록이 있는지.
- SQL 기대 결과와 실제 실행 결과가 일치하는지.
- 데이터 messages의 역할 순서와 train/validation/test의 family 분리.
- schema pass를 설명의 참/거짓 검증으로 혼동하지 않는지.

examples는 `demo_fixture`다. 개발 과정의 렌더러 검사에는 쓸 수 있지만 실제 모델 답변으로 위장하면 안 된다.
