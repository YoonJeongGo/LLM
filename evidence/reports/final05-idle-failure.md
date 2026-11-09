# final05 cold 지연·예정 warm 실패 — 파일 전용 진단

결론: 예정 warm은 실제로 같은 모델을 재사용하지 못하고 **새 cold로 실행된 뒤 첫 delta 이전에 요청 deadline으로 실패**했다. 새 실행은 하지 않았고 원본 actual·작업·worker 로그·장부 한 행을 읽었다. 같은 모델 재사용 성공이나 속도 개선으로 보고할 수 없다.

| 구간 | J01 cold | 'warm' 이름으로 제출한 다음 요청 |
|---|---:|---:|
| 실제 worker PID | 17072 | 23104 (새 worker) |
| 모델 인스턴스 | [local-id] | [local-id] |
| 요청 model load | 1 | 1 |
| 같은 worker의 import 구간 | 20.373665초 | 61.400779초 |
| 같은 worker의 load 시작→ready | 45.596028초 | 148.868787초 |
| 모델 생성 완료 기록 | 41.921초 | 없음 |
| delta 수 | 54 | 0 |
| 종료 | 설명 재생까지 도달 | 요청 deadline 실패, 실제 종료 확인 |
| 첫 유효 설명 | 부모 수집 결과128.0633초, 기존 음성 캐시 | 없음 |

cold의 metadata model_load45.657초와 event 구간45.596초는 측정 경계가 다르다. cold의 부모 resident 요청108.7034초에는 import가 들어가지만 모델 metadata elapsed87.985초에는 앞 import가 빠진다. cold의 저장 공간 검사3.5218초, preflight3.5593초, 부분 저장 snapshot32/54 delta, DB commit5.5788초·close3.2600초·consumer yield4.4361초도 관측됐다. 서로 겹치는 구간을 더해 전체 지연 비율로 만들지 않는다.

## 다음 요청에서 확인된 경로

1. 시작 전 GET snapshot에는 PID17072/session20500d5336914166b41b69f8c8b6d4d9/model831f…가 resident였다. 마지막 이전 모델 완료는13:00:46.904877Z다.
2. 다음 chat job71f1284b…는13:01:19.310208Z에 생성됐다. 이 작업의 `project_mutable_storage_scan` 계측만52.177779초다. 모델 실행 예약은 그 후13:02:12.859820Z에 기록됐다. 저장 공간 검사 시간은 모델 예산 차감에 들어가지 않지만 같은 요청의300초 벽시계 기한은 소비한다.
3. 이전 session.json에는 reason=`idle_expired`, exit_code0, 실제 worker 종료 확인이 있다. old events.jsonl에는 closed 이벤트가 없어 **정확한 idle 만료 시각은 기록되지 않았다**. 이전 완료 후60초 기준과52초 검사 구간은 만료 순서와 일치하지만 이 자료로 특정 expiry 순간을 만들어 쓰지 않는다.
4. 다음 요청은 새 sessionc130c996679245e1b313bfbce37f49b2/PID23104에서 protocol request0b6ae125…로 실행됐다. import61.400779초 후 load→ready148.868787초를 썼고 worker 상대시각210.963663초에 model_ready가 기록됐다.
5. 그 뒤 delta·최종 metadata·done 기록 없이 `Text session request reached its reserved deadline`로 failed가 됐다. stderr 마지막에는 `Text session reached its bounded lifetime/request deadline`가 있다. 세션 종료 사유는 `request_failed_or_cancelled`, exit_code0/실제 worker 종료 확인이다. native access violation이 재현됐다는 증거는 없다. 모델 준비 완료 이후 첫 텍스트 조각 전에 기한에 도달했으며, 그 구간의 내부 커널/스케줄링 원인은 측정되지 않았다.

코드상 runtime은 큐/검사 시작 전에 요청 deadline을 잡고, 검사 이후 남은 시간만 worker에 넘긴다. text_session은 내부에서 정리6초를 확보한다. 따라서 모델 사용 예산이 남아 있어도 개별 요청은 먼저 deadline에 도달할 수 있다. max session600초나 정책을 늘리지 않았다.

## 실패·정리·예산 시각 구분

- chat job failed 업데이트:13:06:15.305579Z. 생성→실패 약295.995초.
- 모델 예약:13:02:12.859820Z→완료13:06:15.210760Z. `failed_or_cancelled`, text1·audio0, 차감242.344초.
- 학생 cap은 정리 직전에도 active였고 모델 시간57.656초가 남아 있었다.13:06:19.594957Z는 자동 만료가 아니라 실패 정리 후 명시적인 close 기록이다.
- 이후 승인 범위 잔여는 text291·audio47·vision22·14668.082초이며 기존 장부를 바꾸지 않았다. 더 실행해 성공을 찾지 않는다.

## 확정하지 않은 원인

저장 공간 검사52초와 새 worker import61초·로드149초가 실제로 길어진 것은 계측으로 확인된다. 하지만 무엇이 이들을 느리게 했는지는 아직 미확정이다. 부모가 보존한13:07 호스트 snapshot의 CPU53.5%, 가용 메모리9.27GB/34GB 및 GPU 약2GB/8GB는 **worker 종료 후 상태**다. 이 값이나 함께 실행 중인 다른 사용자 앱만으로 당시 지연 원인을 단정할 수 없다. 다른 앱을 종료하거나 패키지·드라이버·엔진을 바꾸지 않았다.

증거는 `anomaly-evidence.json`에 각 actual/session/events/stderr의 원본 경로·SHA, 마지막 진행 단계, 장부 한 행과 cap 상태를 연결했다. 제품·동결 하네스 수정, 모델/음성 생성, API/운영 DB 접근은 없었다. NOT_READY/H_PENDING 유지.
