# 텍스트 부분 기록 비용과 변경 범위

이 기록은 실제 학생 속도 측정 이전의 구현·격리 SQLite 검사다. 모델·음성·사진 생성은 없다.

`JobManager`는 요청별로 60,000자 이내 원시 prefix 하나와 정제된 prefix 하나만 보유한다. 첫 부분 답변은 즉시 저장하고, 이후 250ms 또는 4,096자 증가 때 저장한다. 중간에 모델 출력이 멎어도 소유 timer가 마지막 prefix를 저장한다. GET/SSE는 같은 epoch의 메모리 prefix를 읽어 화면 전달과 영구 기록 주기를 분리한다. 최종 답변, 취소 요청, 오류, 종료 상태는 기록을 먼저 완료한다. 인증·원문 revision·SQL 검증·모델 작업 장부는 지연하지 않는다. 비정상 종료의 미확정 prefix는 일부 유실될 수 있으나, 해당 작업은 기존 복구 경로에서 interrupted가 된다. 성공 결과로 복구하지 않는다.

terminal 상태는 늦은 완료로 바꿀 수 없다. timer identity/owner/epoch를 검사하고 큐에서 늦게 도착한 prefix를 거부한다. 부분 저장 오류는 생성 취소와 영구 진단으로 남으며 성공을 허용하지 않는다. 취소 자체는 저장 오류 진단을 남기며 정상적으로 접수할 수 있다. 저장소가 계속 쓰기 불가능하면 최종 상태도 영구 저장됐다고 주장할 수 없다.

250ms는 저장 예약 간격이다. SQLite 잠금 대기와 운영체제 스케줄링까지 포함한 영구 기록 지연의 절대 상한이 아니다. 최종 assistant 메시지와 최종 job 상태는 기존처럼 별도 트랜잭션이다. 두 번째 저장만 실패하는 경계의 원자성까지 새로 해결했다고 주장하지 않는다.

## 격리 CPU 측정

- `cpu-baseline.json`: 기존 매-prefix get+put 64회, 총4.146초. 128연결, commit2.809초, close1.131초.
- `cpu-coalesced.json`: 새 경로 64prefix 화면조회+최종 flush, 총0.151초. 5연결, 2쓰기. 전체 원시 결과 보존을 검사했다.

각1회 소표본이고 측정 경계가 다르다. SQLite 연결·commit 비용이 큰 근거이며 모델 속도나 학생 대기 시간의 개선율이 아니다. 당시 C: 기본 임시 테스트 폴더 접근 오류11건은 `cpu-after.xml`에 보존했고, 새 D: 임시 폴더를 쓴 관련 검사11건은 통과했다. 최종 통합 CPU 검사는 별도다.

## 계측 해석

`storage_timing`은 부모 프로세스 `perf_counter`의 합계/최대/횟수를 사용한다. JSON 인코딩·디코딩, 연결·설정·읽기·쓰기·commit·rollback·close, JobManager 잠금 대기, C: 여유 검사, 프로젝트 변경 가능 영역 전체 스캔을 구분한다. SQLite 내부 busy/lock 대기는 실행/commit 안에 포함되고 별도로 식별하지 않는다. timer의 context를 공유하여 소유 작업에 합산한다. snapshot은 최종 job 상태 쓰기 직전이다. 따라서 자기 자신의 마지막 job write/commit, 그 뒤 HTTP/SSE 최종 전달까지 포함한 총 시간이 아니다. 브라우저 시계 및 worker 모델 시간과 단순 합산하지 않는다.

resident `transport_timing`은 reader 수신, 유한 큐 대기, 소비자 yield/resume을 별도로 기록한다. 소비자 시간과 DB 시간은 겹친다. worker의 TextIteratorStreamer는 보존한다. SQL 검증 시간은 기존 generation/request trace와 함께 보되, 계측하지 않은 비용을 임의로 모델 생성 비용이라고 부르지 않는다.

`storage-check-profile.json`의 한 번의 전체 스캔은17.308초였고, 이후 구성요소 읽기에서는 runs0.759초/.local0.695초였다. 운영체제 파일 캐시·동시 CPU 검사의 영향이 달라 동일 조건 개선 비교가 아니다. 이 작업에서는 전체 스캔 검사를 줄이거나 저장량·볼륨·예약 한도를 약화하지 않았다.
