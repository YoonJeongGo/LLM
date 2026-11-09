# 계측 기록기 수정 — 실제 학생 속도와 별도인 CPU 검증

최종06 N01 actual은57,279,441바이트였고, 기존 기록기는 응답마다 이 전체 객체를 주 스레드에서 JSON.stringify하고 writeFileSync했다. 실제 파일 복사 fixture2회에서 직렬화115.8/119.7ms, 동기 쓰기273.0/276.0ms, 예약된 event-loop callback 대기389.1/421.1ms를 측정했다. 이 결과는 logger의 주 스레드 차단을 재현하며, 실제 브라우저/API 자체 지연을 측정한 값은 아니다.

수정 범위는 기존 journeys.mjs 연결부, evidence_writer.mjs, evidence_writer_worker.mjs, 기존 collector의 새 모드 commit 검증이다. 제품 runtime·모델·정책·장부는 수정하지 않았다.

- 측정 중에는 전체 결과의 직렬화/전체 파일 저장을 하지 않는다. 추가 request/response/event/음성 이벤트/화면 표본 등은 append-only journal에 원문과 순서대로 보존한다. 보충 객체의 중첩 상태와 최종 긴 이벤트 prefix도 보존한다.
- worker가 실제 JSON 직렬화·쓰기·fsync를 수행한다. 주 스레드는 새 항목과 현재 필요한 소규모 상태만 structured clone한다. 이 비용이0이라는 뜻은 아니다.
- 최대1개의 checkpoint 메시지가 in-flight이며, busy일 때 최신 상태 참조와 dirty revision만 보유한다. 새 응답 배열을 무한한 별도 쓰기 큐로 복제하지 않는다. flush는 해당 revision의 내구성 있는 journal 기록 ACK를 기다린다.
- 초기 상태와 화면 capture 경계는 flush한다. 정상 종료와 실패는 기존 owned-job 취소·학생 예산 닫기·브라우저 종료를 먼저 수행한 뒤, worker에 축적된 전체 결과를 딱1회 임시 파일에 쓰고 rename한다.
- 실제 JSON 게시와 receipt는 원자적 두 파일 연산이 아니다. 새 recording_mode에 한해 collector는 actual SHA/크기·최종 journal marker·별도 writer receipt·소유 경로가 모두 일치해야 완료로 받아들인다. 기록 완료 gate가 없거나 다르면 INCOMPLETE_WRITER_COMMIT으로 거부한다. 기존 actual의 판정 경로는 바꾸지 않았다.
- journal만 남은 경우 미완료다. 자동 재시도나 기존 attempt 덮어쓰기는 없다. hard kill 또는 I/O 실패까지 완전한 최종 파일을 보장하는 것은 아니며, 마지막 ACK까지의 journal을 보존하고 성공으로 오인하지 않는다.

CPU 검증:

1. 신규 writer fixture6개 PASS: 원문/순서·연속100개 변경 coalescing·긴 event prefix 교체·보충 객체 중첩 변경·최종 deep equality·실패 기록·기존 attempt 보호·배열 축소 거부·receipt 실패시 미완료·정확한 harness cleanup 순서. finalization 시작에서 오류가 나도 worker 종료를 보장한다.
2. 기존 exact-route 검사20개 PASS, 반복 보충 orchestration6개 PASS. 기록기 오류시 새 작업을 막으면서 GET 및 소유 작업 취소가 가능한 경계도 확인했다.
3. collector commit/cache17개 + subtest2개 PASS. receipt 누락/불일치/부분 marker/다른 hash/다른 경로를 완료로 받지 않는다. 실제 worker fixture의 게시 후 receipt 실패도 거부했다.
4. 같은57MB 상태에서 신규 응답2개를 추가한 fixture: checkpoint 호출0.015/0.020ms, writer pump 뒤에 예약한 callback 대기1.198/1.585ms, 내구성 있는 checkpoint 완료55.057/62.033ms. fullsave는 측정 구간 후780.193ms,1회였다. 최종 JSON의 deep equality, 원본 SHA 불변, collector commit 검증 모두 통과했다.

기존 자료는 student/final06-harness-preserved에 보존했다. journeys SHA는 실제 final06 freeze와 같았다. collector의 원문은 이 변경만 역적용하여 exact frozen SHA 일치를 확인한 **사후 재구성**이며, 사전 백업이라고 표현하지 않는다.

이 수정 뒤 실제 생성/브라우저 수업은 아직 실행하지 않았다. final06→final07은 logger 조건도 달라지므로 관측 지연의 차이를 제품 개선율로 단정할 수 없다. 새 실제 측정은 수정된 기록기와 UI의 동일 최종 빌드에서 별도로 수행해야 한다. H_PENDING/NOT_READY는 유지한다.
