# 최종07 실제 실행 — 완료 기록 확인, 응답 속도 목표 미달

수정된 증분 기록기와 캐시 조회 경로를 적용한 최종07에서 J01 cold/warm 통제2회, N01 초기/보충2질문, J08 의도적 취소/새 질문2회를 실행했다. **브라우저 attempt4개, 텍스트 제출6회(의도적 취소1회 포함), 설명 음성에 도달한 질문5개, 새 음성0개**다. N01은 기존에 실행한 개발 회귀2질문만이며 final06의 N02·반복 질문·새 음성5개를 이 분모에 합치지 않는다.

4개 actual 모두 새 recording_mode의 actual SHA/크기, writer receipt, 마지막 journal commit marker, 소유 경로가 일치했다. 전체 JSON 저장은 각1회·in-flight 최대1개이며 완료 gate가 확인된 기록만 collector로 내보냈다. 원시 actual·실패 기록·최종06 reports는 수정하지 않았다.

| 질문/행동 | 실제 텍스트 상태 | 첫 음성 | 버튼→첫 native 설명(초) | 추가 질문→native 정지(초) |
|---|---|---|---:|---:|
| J01 cold 통제 | load1 | 캐시 |35.2515|해당 없음|
| J01 warm 통제 | 같은 PID/모델·load0 | 캐시 |17.8266|해당 없음|
| N01 초기 | load1 | 캐시 |34.7406|해당 없음|
| N01 보충 | 초기와 같은 PID/모델·load0 | 캐시 |17.8638|0.0134|
| J08 의도적 취소 | preflight 중 취소·새 모델 미시작 | 없음 |의도적 취소|음성 재생 전이므로 해당 없음|
| J08 취소 뒤 새 질문 | load1 | 캐시 |30.9126|해당 없음|

N01 보충은 interruption 버튼부터 측정했다. 그 뒤 question_submitted부터17.8596초, POST부터17.8546초로 시작점을 구분했다. 다른 질문도 버튼/POST 차이는 개별 데이터에 보존했다. 첫 유효 UI 텍스트는 모든 질문에서 **NOT_MEASURED**이며 첫 delta를 대신 쓰지 않는다. native playing·음성 bytes/지문 linkage는 자동 확인이며 사람이 실제 발음을 들었다는 뜻은 아니다.

| 실행 | 저장 검사(초) | 모델 load 기록(초) | 모델 생성(초) | 실제 PID / 요청 load |
|---|---:|---:|---:|---|
| J01 cold |3.5524|10.328|11.547|39084 /1|
| J01 warm |3.5071|0|10.812|39084 /0|
| N01 초기 |3.6127|9.968|13.813|24660 /1|
| N01 보충 |3.3368|0|10.890|24660 /0|
| J08 새 질문 |4.1253|12.312|5.047|14392 /1|

각 구간은 시작점과 포함 범위가 다르다. generation·parent consumer·DB·reader queue를 더해 전체 지연 또는 원인 비율로 만들지 않는다. worker import/load→ready·첫 delta·metadata·DB commit/close 상세는 collected/data.json과 REPORT_KO.md에 있다. warm 두 질문의 **생성 자체가10초를 넘었으므로** 캐시 GET/기록기만 고쳐 실시간10초 목표를 충족했다고 말할 수 없다. 저장 검사3.3~4.1초도 남아 있다.

재사용은 실제 PID·출생시각·session·model instance·Python 객체 모두 동일함과 request load0/누적load1로 확인했다. J01 session bad037ca…/model8d8a355e…, N01 session4f8dc397…/modelae39c102…다. 두 warm 요청의 activity ACK는 직전 request·현재 job·nonce·instance·PID에 정확히 결합된다. J08의 새 질문은 PID14392의 새 로딩이며 warm으로 분류하지 않는다. 정상 수업 오디오가 계속 재생돼도 idle60 이후 텍스트 worker를 영구 유지하는 기능은 없다.

N01 보충9단계가 자연 종료되고 원래 표·선택 셀·재생 위치로 복귀했다. 보충 native 첫재생→마지막 ended205.2151초, 마지막 ended→원수업 audio_playing2.0881초다. **이 복귀 공백은2초를 조금 넘는다.** 같은 수업 내부 단계 사이 공백10개는 최대1.362초이며, J08의2개는 최대0.1809초였다. 통제 J01은 첫 음성 직후 중지하므로 전체 단계 공백을 검증한 것이 아니다.

J08에서는 running/progress0의 텍스트 작업을 취소했고 서버는 `Request cancelled during preflight; no model worker started`로 종료했다. 취소 POST→서버 terminal4.4055초는 음성 정지 또는 UI 렌더 시간과 다르다. 이후 새 질문의 수업이 정상 종료하고, 취소 응답의 늦은 추가 없음·완료 재진입 자동재생 없음이 확인됐다. 이번 최종07에는 새 Heami 합성/대기 작업이 없어 그 취소 분기를 이번 실제 실행에서 재현했다고 주장하지 않는다. 관련 CPU 회귀와 final04의 실제 취소 기록은 별도 근거다.

모든 첫 음성은 캐시다. final06에서 새로 생성한 후속 단계 음성5개는 당시 기록으로 남았으며, 이번 최종07의 새 합성 속도/새 음성 품질 검사로 바꾸어 쓰지 않는다. 사진/group의 저장 자료 재생과 controlled restart는 별도 GET 검사이며 새 모델·OCR 실행 결과가 아니다.

final06→final07은 기록기·UI 경로·실행 환경 조건이 달라졌으므로 관측 차이를 제품 속도 개선율로 단정하지 않는다. 이 기록기는 journal I/O와 일부 structured clone 비용이 남으며 무계측 일반 학생 환경과 동일하다고 가정하지 않는다. 정확한 설명 요구 충족은 별도 내용 판정 보고서를 참조한다. 사람 교육·청취 검토는 **H_PENDING**, 제품은 **NOT_READY**를 유지한다.

최종 collector:

- control: student/repair-control-final07/report-20261030T144127941874Z
- N01 subset: student/repair-development-final07/report-20261030T144127911336Z
- J08: student/repair-cancel-final07/report-20261030T144127912846Z
