"""Update current handoff without changing the historical failure evidence."""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/student-latency/20261027/condition-recovery"


def main():
    result = json.loads((OUT / "result.json").read_text(encoding="utf-8"))
    if not result["status"].startswith("PASS"):
        raise SystemExit("Write the actual failure report; do not use the success wording")
    lesson = result["reprocessed"]["lesson"]
    timing = result["timing"]
    budget = result["current_budget"]
    prefix = f"""# 저장 실패 E의 조건식 집계 복구 — 실제 두 단계 재생 완료

2026-10-27. **이전 실패 이후 `SUM(열 IS NOT NULL)` 설명 경로를 구현했고, 저장 E를 새 텍스트 추론 없이 재처리해 판서·새 음성 두 단계를 실제 앱에서 완주했다.** 이전 E의 plan=null/TTS0은 당시 실패 기록으로 그대로 남아 있다. 최신 결과는 별도 수업 `{lesson['id']}`와 `runs/student-latency/20261027/condition-recovery/result.json`이다. 전체 제품은 여전히 **PARTIAL_PRODUCT_NOT_READY / NOT_READY / H_PENDING**이다. 설명 경로 복구가 모델 정확도·속도·전체 제품 완성의 증거는 아니다.

## 1. 실제로 고친 코드와 지원 범위

| 코드 | 변경과 역할 |
|---|---|
| `src/edu_tutor/problems/evidence.py` | SQLite `SUM(열 IS NOT NULL)`의 원본 행·셀을 1/0 입력에 연결. 독립 Python 계산·SQLite 행별 조건값·최종 집계 대조. 별칭 없는 출력 열 이름 정규화 차이는 검증된 SELECT 위치로 연결. |
| `src/edu_tutor/lessons/verified.py` | 동일 근거로 원본 표→조건값 표→최종 집계의 2단계 판서·대사 구성. 원시 자유 설명을 읽지 않으며 다른 조건식/복잡한 수업은 명시적으로 차단. |
| `src/edu_tutor/lessons/reprocessing.py`, `api/app.py` | 인증된 CPU 재처리 API. 저장 질문·문제·원답만 사용해 파생 답변/수업/감사 기록을 한 트랜잭션으로 추가. 원본 불변·요청 중복 방지·원본 변경 재검사. CPU 계산 중 취소 잠금을 점유하지 않음. |
| `web/src/App.tsx` | 일반 강의실의 ‘저장 답변으로 다시 검증’ 버튼. 검증된 새 수업으로만 전환하고 기존 학생 자동재생 경로 사용. 취소·이탈 뒤 늦은 응답 차단, 이전 실패 링크, 저장 조회 GET 전용 유지. |

이번 학생용 상세 설명 범위는 **SQLite 단일 표의 `SUM(열 IS NOT NULL)` 하나와 선택적인 `COUNT(*)`, WHERE/GROUP BY/HAVING 없는 수업**이다. 다른 조건식·CASE·조건식 DISTINCT·복합 피연산자·타 DBMS는 지원하지 않는다. 논리 계산으로 확인 가능한 일부 WHERE/그룹 쿼리도 이 두 단계 상세 판서 범위를 넘으면 음성을 차단한다. 조건식 집계의 선택행 보충질문도 현재 지원하지 않는다. 테이블명·사람 이름·질문 문자열·정답 5/3에 따른 제품 분기는 없다.

`SUM(조건식)`을 `COUNT(열)`로 바꾸지 않았다. 이번 비어 있지 않은 확정 입력에서만 의도와 맞는다고 판정하며, 빈 입력이면 SUM=NULL·COUNT=0을 유지한다. 빈 표의 제공 SQL 결과 설명은 `[0,NULL]`; ‘NULL 아닌 행 수’를 쓰라는 요청의 해당 SQL 후보는 의도 불일치로 차단한다.

## 2. 이전 실패 → 현재 실제 결과

질문은 이전 개발 검증 E의 저장 질문 그대로다. 새 질문이나 실제 학생 업로드가 아니다.

> SQLite 범위입니다. practice_checks 표에서 전체 행 수와 solved 값이 NULL이 아닌 행 수를 이 순서대로 한 행에 반환하는 SELECT문을 작성하고, 두 수가 다른 이유를 짧게 설명해 줘.

원본 learner/solved는 나래4, 우진NULL, 다온0, 세진7, 유림NULL이며 원시 SQL은 다음과 같다.

```sql
SELECT COUNT(*) AS total_rows, SUM(solved IS NOT NULL) AS solved_count FROM practice_checks
```

| 항목 | 이전 실패 E | 이번 별도 재처리 |
|---|---|---|
| 원시 SQL 실행 | [[5,3]] | 같은 원문·데이터로 [[5,3]] |
| 중간 계산 | SUM 조건식 미지원 | 4→1, NULL→0, 0→1, 7→1, NULL→0; 합계3 |
| 설명·판서 | plan=null, 검증 중단 | 검증된 2단계 계획·원본/조건값/결과 표 |
| 원시 COUNT 설명 오류 | 보존 | 원답 그대로 보존; 앱의 검증 설명으로 분리 |
| 실제 음성 | 0개 | 기존 캐시 없음 확인 후 승인 잔여2개 생성·재생 완료 |

첫 대사: **“전체 행 수는 NULL도 포함해 5입니다. 조건값은 NULL이면 0, 아니면 1입니다.”**

둘째 대사: **“1인 행은 3개이므로 조건값을 더한 결과는 3입니다.”**

잘못된 원시 문장 ‘COUNT(*)는 … solved 컬럼이 NULL이 아닌 행을 세어줍니다’는 역사 원문에 남아 있지만 이 수업의 대사·판서에는 사용하지 않았다. 이는 **앱의 SQL 실행·독립 계산 기반 설명**이며 모델이 원시 해설을 고쳤다는 뜻이 아니다.

## 3. 실제 앱·음성·화면 증거

일반 강의실에서 이전 실패 수업→재처리 버튼→새 수업 자동재생을 실행했다. 새 텍스트/플래너/OCR POST 없이 재처리1회·음성 POST2회만 실행했으며 자동 재시도·차단 우회가 없었다. 두 WAV 모두 종료 토큰 EOS·비무음·해시·대사 바인딩 검사를 통과하고 1.0x, seek 없이 자연 종료했다. s1 포인터는 원본 표, s2 포인터는 조건값 표 안에 있는지 실제 DOM 좌표로 확인했다. 문장별 발음·세밀한 입모양·교육 전달력은 사람이 확인하지 않았다.

| 항목 | 실제 기록 |
|---|---:|
| CPU 재처리 API 검증·계획 | {timing['api_verification_and_plan_seconds']:.3f}초 |
| 버튼→새 계획 수신 | {timing['reprocess_click_to_plan_seconds']:.3f}초 |
| 버튼→첫 설명 클립 재생 | {timing['reprocess_click_to_first_explanation_audio_seconds']:.3f}초 |
| 첫 클립 종료→둘째 재생 | {timing['s1_ended_to_s2_playing_seconds']:.3f}초 |
| s1 TTS 모델 로딩 / 합성 API / WAV 길이 | 17.016초 / 100.484초 / 18.56초 |
| s2 TTS 모델 로딩 / 합성 API / WAV 길이 | 3.609초 / 32.469초 / 5.52초 |
| 음성 작업 장부 청구 | 161.421초 + 47.625초 = 209.046초 |

서로 다른 시계·포함 범위를 단순 합산하지 않는다. 모델 로딩은 두 클립 모두 새 worker에 포함됐고, 두 번째가 빠르다는 이유로 상주 warm 모델이라고 부르지 않는다. 합성 API는 코드 생성·디코딩·완료 확인을 포함한 host 시간이다. 장부와 로딩/합성 차이는 프로세스·import·정리 등도 포함하지만 세부 분리는 이 기록만으로 확정하지 않는다. 첫 설명 수치는 안내음이 아닌 연결된 설명 클립의 `playing` 기준이며, 실제 첫 단어 시점은 청취 미검토다.

**속도 목표는 미달이다.** 다음 단계 선행 준비가 실제 실행됐지만 첫 음성 길이보다 둘째 준비가 길어 31.628초 공백이 남았다. 이전 질문과 입력·대사·로딩 조건이 달라 개선률을 계산하지 않는다. 새 질문 전체 응답 시간·사진 속도·모델 정확도 재평가는 하지 않았다. worker 상주·생성 스트리밍은 구현하지 않았다.

[원문·파생 답변·판서 상태·음성 메타·시간](../runs/student-latency/20261027/condition-recovery/result.json), [실제 브라우저 요청·이벤트·화면](../runs/student-latency/20261027/condition-recovery/actual.json), [기존 갤러리의 복구 사례](../runs/student-experience/20261027/index.html#E-condition-recovery-20261027), [저장 수업 재생](http://127.0.0.1:8000/?lesson={lesson['id']}). 갤러리는 사람이 검토할 자료이며 정적 판서와 WAV 자체를 실시간 동기화라고 부르지 않는다. 1440×1100 화면에서 긴 표 전체는 스크롤이 필요하며 full-page 캡처는 화면 밖 영역도 포함한다.

## 4. 검사 수준·전체 진행·남은 문제

- **프로그램/CPU:** 독립 SQLite 계약32개(원본·빈 표·NULL·0·음수·중복·이름/값 변경 및 미지원 경계), 추가 무별칭/대소문자/괄호6개 통과. 마지막 선택검사는 원본 포함7/7이다. 기존 영향120개 통과 뒤 최종 수정 영향30개 재검사, API7/7 통과. 중복 검사들을 합산해 새 문항 수·교육 정확도로 표시하지 않는다. 초기 API 기대 HTTP 코드 오류와 별칭 없는 집계 문제 발견 기록은 `cpu-api.xml`, 수정 후 결과는 `cpu-api-final.xml`로 보존했다.
- **웹 모의 검사:** 영향10/10, 원본 바인딩 보호 추가 뒤 재처리6/6, 최종 build 통과. 중복 포함이며 실제 모델 검증과 별도다. 초기 fixture 화면 전제 오류도 보존했다.
- **실제 실행:** 저장 E의 CPU 재처리와 새 TTS 두 단계가 이번에 완료됐다. 새로운 모델 응답·사진·조건식 보충질문은 검증하지 않았다.
- **학생 사용:** 저장 E를 복습할 수 있으나 첫 음성162.46초·공백31.63초로 실시간 사용 목표 미달. 원시 설명 능력, 좁은 지원 범위, 스크롤, 사람 청취·교육 검토가 남는다. 과거 전체 감사6/16은 이번에 재평가하거나 상향하지 않는다.

현재 핵심 장애는 **새 음성 준비 속도와 제한적인 설명 범위**다. 다음 CPU 수정 후보는 worker 단계 계측/상주 설계의 영향 분석, 조건식 집계 선택행 설명의 범위 명시와 연결, 실제 WAV의 사람 청취다. 현재 장비에서 목표 속도를 달성할 수 있는지는 미확인이다. 새 모델·음성 실험을 시작할 자동 승인량은 없다. 새 기능/관리UI/신경망 확장은 하지 않는다.

`NOT_READY` 해제에는 명시한 사용 범위의 새 질문→정확한 설명·판서·음성, 실제 지연 목표, 중간 질문·복귀·연속 사용을 같은 실행 경로에서 통과한 근거가 필요하다. `H_PENDING` 해제에는 사람이 실제 WAV와 화면을 보고 의미·발음·숫자 전달·학습 가능성을 검토한 기록이 필요하다. 자동 검사를 사람 판단으로 대신하지 않는다.

## 5. 예산과 보존

새 텍스트0, 새 음성2(성공2·실패0·캐시 재사용0), 사진/OCR/학습/다운로드/유료/외부 업로드0. 기존 승인 `20261027-new-text1-tts2`만 사용했으며 새로운 승인이나 시간을 추가하지 않았다. 범위 확인은 `authorization-scope.json`에 별도 기록했다.

현재 **128요청·4475.674/5400초**, 누적 시간 잔여 **924.326초**. 해당 승인 잔여는 **text0·TTS0·vision0·600.657초**다. 누적 음성21/21·사진6/6, 요청당300초·저장50GB/경고40GB/C여유50GB 조건 유지. 시간만 남았다고 새 실행이 허용되는 것은 아니다.

기존 실패 E의 파일·답변·수업과 기존 장부126요청은 보존 대상이며 새 파생 답변/수업/감사/음성 작업만 추가했다. 소스/상태/문서/갤러리는 작업 전 복사본을 보존했다. 최종 보존 감사는 `condition-recovery/preservation-final.json`을 확인한다. 최신 결과는 STATUS의 `conditional_aggregate_recovery`; `limited_new_lesson`은 이전 실패 기록이므로 그대로다.

최종 보존 감사 **PASS**: 기존 DB460행 모두 동일, 새5행만 추가, 기존 장부126건 동일, 정책 바이트·모델 파일 크기/수정시각·실행 당시 소스/번들 동일, 미완료 작업/예약0. 기존 WAV는 저장 메타데이터의 체크섬과 대조했고 과거 manifest의 원본9개는 이전 WAV/메타 해시와도 일치했다. 새 갤러리 사례는 1440/390px 가로 넘침0·링크12개·이미지5개·WAV2개 메타데이터 확인을 통과했다. 이는 로컬 자동·AI 화면검사이며 실제 사람의 청취/교육 검토가 아니다. `gallery-validation.json`과 `preservation-final.json`에 범위를 구분했다.

---

## 아래는 복구 이전 작업 기록 — 당시 실패·예산 수치 보존

"""
    (ROOT / "docs/PROGRESS_BRIEFING.md").write_text(prefix + (OUT / "before-PROGRESS_BRIEFING.md").read_text(encoding="utf-8"), encoding="utf-8")
    handoff = f"""# ChatGPT 전달용 — 그대로 복사

프로젝트 D:/LLM/edu-tutor-local. 2026-10-27 최신 작업은 저장 실패 E의 조건식 집계 설명 복구다. **SUM 조건식 미지원·plan=null·TTS0은 이전 실패 상태다. 지금은 원본 E를 새 텍스트 호출 없이 재검증해 2단계 판서와 새 TTS2개를 실제 앱에서 재생 완료했다.** 원래 실패 기록을 성공으로 바꾸지 않았다. 최신 docs/PROGRESS_BRIEFING.md, STATUS.json의 conditional_aggregate_recovery, runs/student-latency/20261027/condition-recovery/result.json을 먼저 읽어라. limited_new_lesson과 new-lesson/result.json은 보존된 이전 실패다.

변경: evidence.py가 SQLite 단일 열 IS NOT NULL을 행별1/0으로 계산하고 SQLite 행별 조건·독립집계·최종SQL을 대조한다. verified.py는 같은 근거로 원본표/조건값/집계결과와 두 대사를 구성한다. reprocessing.py + 인증 API /lessons/{{id}}/reprocess는 저장 원답만 사용하며 원본을 바꾸지 않고 새 파생답변/수업/감사를 원자 저장한다. 중복요청·원본변경·사진revision을 검사하고 CPU계산 중 취소 잠금을 점유하지 않는다. App.tsx는 일반 강의실 재검증 버튼→새 검증 수업→기존 학생자동재생 연결과 취소/늦은응답 보호를 넣었다. 저장 ?lesson= 검토는 GET전용이다.

지원 상세 수업은 SQLite 단일표 SUM(열 IS NOT NULL) 하나+선택 COUNT(*), WHERE/GROUP/HAVING 없음이다. CASE/임의조건식/조건식DISTINCT/타DBMS는 지원하지 않으며 조건식 집계 선택행 보충설명은 차단한다. 특정 표/사람/질문/정답에 맞춘 제품 분기는 없다. SUM을 COUNT로 무조건 바꾸지 않으며 빈 입력 SUM=NULL/COUNT=0을 검증했다. query_result 빈표는 [0,NULL], 비NULL 개수를 쓰라는 write_sql 후보는 빈표에서 의도불일치로 차단한다.

원문 질문: ‘SQLite 범위입니다. practice_checks 표에서 전체 행 수와 solved 값이 NULL이 아닌 행 수를 이 순서대로 한 행에 반환하는 SELECT문을 작성하고, 두 수가 다른 이유를 짧게 설명해 줘.’ 이전 개발용 입력 learner/solved는 나래4·우진NULL·다온0·세진7·유림NULL이다. 저장 원시 SQL SELECT COUNT(*) AS total_rows, SUM(solved IS NOT NULL) AS solved_count FROM practice_checks를 그대로 재사용했다. 조건값1,0,1,1,0→SUM3, 전체5, 실제SQL[[5,3]]이 일치한다.

원시 COUNT(*) 설명의 NULL 혼동은 그대로 보존했고 읽어주지 않았다. 앱 대사1 ‘전체 행 수는 NULL도 포함해 5입니다. 조건값은 NULL이면 0, 아니면 1입니다.’ 대사2 ‘1인 행은 3개이므로 조건값을 더한 결과는 3입니다.’ 검증된 새 수업ID {lesson['id']}. 원본 실패수업 c03a2b61607b471580296e98ec1a15eb와 별개다. raw 답변 교정이나 모델 정확도 향상으로 해석하지 마라.

실제 일반UI에서 재처리1회/TTS POST2회/새text0. 새WAV2개 EOS·비무음·체크섬·대사바인딩 통과, 1x·seek없이 모두자연종료. 실제표 원본→중간→최종5/3 연결, 포인터 s1원본표/s2조건값표 내부 확인. fullpage 화면은 스크롤 영역도 포함한다. 사람 청취·교육 검토는 하지 않았다.

시간: CPU API0.902초, 버튼→plan1.017초, 버튼→첫설명재생162.458초, s1끝→s2재생31.628초. s1로딩17.016/합성API100.484/WAV18.56초, s2로딩3.609/합성API32.469/WAV5.52초. 새음성 장부161.421+47.625=209.046초. 서로다른 시계/범위를 합산하지 마라. 두번째도 새worker로딩이며 warm상주가 아니다. 다음1단계 선행준비는 실제실행됐지만 공백은남았다. worker상주/생성스트리밍 미구현. 새질문전체지연/신규모델정확도/사진속도 재측정아님.

CPU 독립계약32+추가6을 별도시점 확인, 최종선택7/7. 기존영향120 뒤 최종변경영향30, API7/7. UI 영향10 뒤 최종재처리6, build통과. 중복이므로합산금지. 최초 실패/수정기록보존. 새모델을 호출하는 검사가 아니다.

기존 정책·카운터 초기화·추가승인 없음. 현재128요청·4475.674/5400초(누적잔여924.326), 승인20261027-new-text1-tts2의text0/TTS0/vision0/시간600.657초잔여. 누적음성21/21·사진6/6, 요청300초·기존저장제한유지. 이번text/OCR/학습/다운로드/유료/업로드0이며같은E에만기존잔여TTS2사용. 시간잔여를새호출승인으로해석하지마라.

전체 PARTIAL_PRODUCT_NOT_READY / NOT_READY / H_PENDING 유지. 가장 큰 남은 문제는 새음성지연·좁은설명범위·원시모델설명오류 및 사람검토다. 조건식 보충질문/복귀는 이번검증아님. 기존6/16전체기준을재평가/상향하지않았다. 모델/장비로목표속도가가능한지미확인. 저장수업복습은가능하나실시간개인튜터완성은아니다.

근거: condition-recovery/result.json, actual.json, cpu-saved-E-preview.json, quality-saved-replay.json, cpu-contract*.json/xml, cpu-api-final.xml, frontend-validation.json, preservation-final.json. 기존 갤러리 runs/student-experience/20261027/index.html#E-condition-recovery-20261027에서 원답/앱결과/판서/WAV/전후화면/사람검토대기 확인. 로컬앱 http://127.0.0.1:8000/?lesson={lesson['id']} 는 저장복습용이며토큰파일을UI에서불러온다. 원래실패·증거를삭제하거나새기능·신경망확장·전체앱재개발을하지마라.
"""
    (ROOT / "docs/CHATGPT_HANDOFF.md").write_text(handoff, encoding="utf-8")
    short = f"""# 최신 작업: 조건식 집계 복구 / 저장 E의 두 단계 실제 재생 완료

2026-10-27. 이전 실패 뒤 SUM(열 IS NOT NULL)의 행별1/0·독립합계·SQLite대조와 저장원답 CPU재처리 경로를 구현했다. 저장E는 원본5행→조건값[1,0,1,1,0]→[[5,3]]의2단계판서·새TTS2개를 일반UI에서실제완주했다. 새text0. 원시 COUNT 설명오류는그대로보존하고검증된앱대사로분리했다. 기존실패plan=null/TTS0은historical limited_new_lesson에보존, 새결과는conditional_aggregate_recovery이다.

실제 버튼→plan1.017초/첫설명162.458초/단계공백31.628초로속도미달. 전체PARTIAL_PRODUCT_NOT_READY/NOT_READY/H_PENDING유지. worker상주·생성스트리밍미구현, 조건식보충질문·사람검토미완료. 새모델정확도/새질문전체응답 개선주장없음.

현재128요청·4475.674/5400초(잔여924.326), 기존해당승인text0/TTS0/vision0/600.657초잔여. 음성21/21·사진6/6, 요청300초·저장제한불변. 새승인/학습/다운로드/유료/업로드0. 기존DB행·실패파일·장부126요청보존.

[최신 브리핑](docs/PROGRESS_BRIEFING.md), [ChatGPT 복사 인계](docs/CHATGPT_HANDOFF.md), [새 재처리 결과](runs/student-latency/20261027/condition-recovery/result.json), [갤러리 복구 사례](runs/student-experience/20261027/index.html#E-condition-recovery-20261027). 아래는복구이전인계원문이며그안의미지원/plan=null/TTS0은그때의실패다.

---

"""
    (ROOT / "HANDOFF.md").write_bytes(short.encode("utf-8")+(OUT / "before-HANDOFF.md").read_bytes())
    status_path = ROOT / "STATUS.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status.update(current_work="Saved E conditional SUM recovery implemented and real two-step speech/board playback completed. New text 0, TTS 2 from existing allowance. Latency target unmet; NOT_READY/H_PENDING retained.",
                  latest_verification="conditional_aggregate_recovery", updated_at=datetime.now(timezone.utc).isoformat())
    status["product_readiness"]["current_operating_counts"] = "conditional_aggregate_recovery.budget_after"
    status["product_readiness"]["readiness_change_after_conditional_recovery"] = False
    status["historical_field_scopes"]["tests"] = "Historical v0.1 snapshot. Later runs are dated in student_experience, limited_new_lesson and conditional_aggregate_recovery; overlapping runs are not summed."
    status["conditional_aggregate_recovery"] = {"at": result["at"], "result": result["status"],
        "source_failure": "runs/student-latency/20261027/new-lesson/result.json",
        "evidence": "runs/student-latency/20261027/condition-recovery/result.json",
        "actual_ui": "runs/student-latency/20261027/condition-recovery/actual.json",
        "gallery": "runs/student-experience/20261027/index.html#E-condition-recovery-20261027",
        "source_lesson_id": result["source"]["lesson"]["id"], "new_lesson_id": lesson["id"],
        "status_scope": "saved failed lesson recovery, not new model evaluation or product readiness",
        "original_failure_preserved": True, "raw_explanation_error_preserved": True,
        "new_calls": {"text": 0, "tts": 2, "vision": 0, "training": 0, "downloads": 0},
        "budget_after": budget, "timing": {k:v for k,v in timing.items() if k != "speech_jobs"},
        "human_review": "H_PENDING", "student_ready": False, "supported_scope": result["limits"][0],
        "conditional_row_followup": "unsupported", "model_quality_improvement": "NOT_MEASURED",
        "worker_resident": False, "generation_streaming": False,
        "validation": {"independent_cpu_initial": "32/32", "additional_projection_cases": 6,
            "final_projection_subset": "7/7 includes one original case", "existing_initial": "120/120",
            "final_existing_subset": "30/30", "api": "7/7", "ui_initial": "10/10",
            "ui_final_subset": "6/6", "build": "pass", "actual_speech_steps": "2/2",
            "note": "Overlapping runs are not summed; fixtures separate from actual E playback."}}
    evidence_path = "runs/student-latency/20261027/condition-recovery/result.json"
    if evidence_path not in status.setdefault("evidence", []):
        status["evidence"].append(evidence_path)
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"updated": ["STATUS.json", "HANDOFF.md", "docs/PROGRESS_BRIEFING.md", "docs/CHATGPT_HANDOFF.md"], "source_limited_failure_preserved": status["limited_new_lesson"] == json.loads((OUT / "before-STATUS.json").read_text(encoding="utf-8"))["limited_new_lesson"]}))


if __name__ == "__main__":
    main()
