"""Write the bounded no-generation outcome; retain the earlier handoff verbatim."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/student-latency/20261027'
LIVE = 'live-cache/2026-10-27T07-52-16-683Z'

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def main():
    assert read(OUT / 'preservation-after.json')['status'] == 'PASS'
    assert read(OUT / LIVE / 'report.json')['status'] == 'PASS_ACTUAL_STORED_WAV_REPLAY_NOT_NEW_GENERATION'
    assert read(OUT / 'frontend-terminal-race/report.json')['stats']['unexpected'] == 0
    report = '''# 지연 원인 개선 — 신규 생성 없이 완료한 범위

2026-10-27 · D:/LLM/edu-tutor-local. 기존 STATUS/HANDOFF/v0.2 결과와 원본 증거를 확인하고 필요한 프로그램 수정 후 검증했다. **교육 NOT_READY, 인간 검토 H_PENDING**을 유지한다. 새 질문이 짧은 준비 후 수업으로 이어진다는 목표는 아직 달성했다고 판단하지 않는다.

## 결과와 측정의 구분

저장된 유효 WAV의 재생·다음 단계 준비·중단·복귀는 실제 앱에서 확인했다. 새 질문의 모델 응답, 새 음성 합성 속도, 모델 상주 효과는 이번에 측정하지 않았다. 새 텍스트 추론·TTS·사진 OCR·학습·모델 다운로드·유료 호출·외부 업로드는 모두 0회다. 음성 한도를 우회하는 브라우저/CPU TTS도 사용하지 않았다.

기존 SQL 3/11 이후의 최신 수치 평가는 2026-10-26의 54문항/68모델 호출이다. 이번 작업은 그 정확도 평가를 갱신하지 않았다. 원시 모델과 RAG/SQL 도구를 연결한 앱의 결과를 구분한 [앞선 교육 보고서](../../student-experience/20261027/quality-audit.md)를 그대로 유지한다.

## 확인한 지연 원인

다음은 **이전 실제 실행 기록의 재분석**이다. [구간별 감사](audit.md)와 [원본 ID·해시 JSON](audit.json)을 확인할 수 있다.

| 구간 | 확인한 값 | 해석/한계 |
|---|---:|---|
| 텍스트 모델 로딩 | 9.485~12.500초, 4회 | 요청마다 새 worker의 cold 로딩. warm 상주 실행은 미측정 |
| 음성 모델 로딩 | 2.968~3.515초, 새 성공 7개 | 각 독립 worker에서 반복 로딩 |
| 로딩 제외 음성 clip 처리 | 실제 WAV 길이의 3.857~4.302배 | 합성·codec·파형검사·WAV 저장·SHA를 포함. 순수 합성 RTF 아님 |
| A 질문→수업계획→음성 준비→재생 | 33.605 + 67.883 + 0.0324 = 101.520초 | 같은 브라우저 시계의 겹치지 않는 구간 |
| 기존 A/B 단계 공백 | 32.055~128.696초 | 이전 음성 종료 후 다음 한 단계의 생성·준비를 시작 |

가장 큰 병목은 완성 WAV를 얻는 처리 시간과 다음 준비를 종료 후에 시작하는 순서다. 로딩도 기여하지만 전체 지연을 로딩 하나로 설명하지 않는다. 설치된 TTS는 전체 code를 생성·decode한 WAV를 반환하며 `non_streaming_mode=false`만으로 실제 오디오 스트리밍이 되지 않는다. 텍스트 eval/inference mode와 KV cache 설정은 이미 사용 중이다. 설정을 무작정 바꾸거나 신경망 관측을 켜지 않았다.

독립 프로세스 시작/import/종료 비용은 의심 요인이지만 별도 타이머가 없어 잔여 시간을 그 비용으로 역산하지 않았다. 과거 TTFT/prefill, RAG/SQL/파싱, 순수 합성/codec/저장, 순수 queue, GPU 커널 시간, 디스크 병목은 NOT_MEASURED다. 서버·worker·브라우저의 시계를 더하지 않는다. 기존 clip elapsed에서 이미 밖에서 끝난 모델 로딩을 다시 빼지 않았다.

새 음성 메타데이터에는 향후 실행을 위한 host 단조 시계 구간과 실제 상속 TTS 설정을 추가했다. 이번 실제 새 생성 검증은 NOT_RUN이며 GPU 커널 측정이 아니다. 상위 talker의 do_sample=false와 달리 기존 subtalker는 pinned 설정의 sampling=true를 상속하므로 전체 TTS를 완전한 greedy/deterministic 엔진이라고 부르지 않는다.

## 수정한 프로그램 동작

- 정확한 대사·발음사전·화자·모델 revision/설정·EOS·WAV SHA/PCM/길이가 맞는 캐시를 읽기 전용으로 재사용한다. 수업에 아직 연결되지 않은 기존 전역 캐시도 사용할 수 있다. 실제 저장 33단계 조사에서 27개 유효, 6개 미존재였다. 미존재를 새 생성 성공으로 취급하지 않는다.
- 명시적 `?lesson=<ID>` 검토 링크는 저장 재생 모드다. 인증된 GET만 사용하고 누락/손상 시 멈춘다. **일반 학생 수업 복원은 기존 질문·생성 기능을 유지한다.** 이번 실행 도구는 모든 비GET API/외부 요청을 별도로 차단했다.
- 현재 음성 재생 중 다음 **한 단계의 기존 WAV만** 준비한다. 소비 직전에 현재 화면 plan, 서버 수업 지문, 음성 지문을 다시 비교한다. 수정된 판서와 옛 음성이 섞이면 재생을 중단한다. 검증한 WAV 바이트를 그대로 응답해 파일 교체 경합도 막는다.
- pause/질문/단계 이동/화면 종료/수업 변경 시 대기 음성과 보충 설명 GET을 취소한다. 늦은 결과와 늦은 autoplay를 차단한다. 원본 복귀 버튼은 원본 GET을 기다리기 전에 현재 음성을 멈춘다. 수동 재생과 연속 재생의 복귀 정책을 따로 보존한다.
- 입 모양용 파형 decode는 재생의 필수 선행 작업에서 분리했다. manifest·WAV fetch·파형 decode·playing·ended 시간은 같은 브라우저 시계로 기록한다.
- 회귀 검사에서 발견한 빠른 작업 완료 경합도 수정했다. 첫 메시지 조회 뒤 job이 완료돼 polling이 시작되지 않는 경우 최종 메시지를 다시 읽는다. 이미 취소/전환된 요청은 화면에 반영하지 않는다.

주요 코드: `src/edu_tutor/speech/provider.py`, `src/edu_tutor/api/app.py`, `web/src/speechCache.ts`, `web/src/Classroom.tsx`, `web/src/App.tsx`. 인간 검토 화면은 기존 `scripts/student_experience_gallery.py`와 새 `scripts/student_review_ui.js`를 사용한다. 신경망 기능 확장, 모델 상주, 새 합성의 선행 생성, 엔진/정밀도 변경은 이번에 구현하지 않았다.

## 실제 기존 WAV 재생 결과

[실제 실행 JSON](live-cache/2026-10-27T07-52-16-683Z/report.json) · [요약/화면](live-cache/2026-10-27T07-52-16-683Z/SUMMARY.md) · [실행 버전 경계](live-cache/2026-10-27T07-52-16-683Z/provenance.json)

| 저장 재생 사례 | 재생 버튼→첫 playing | 실제 단계 공백 |
|---|---:|---:|
| A DDL, 3단계 | 0.1648초 | 0.0570 / 0.0679초 |
| B 새로 작성했던 6행 검증 표, 4단계 | 0.1126초 | 0.0496 / 0.0543 / 0.0598초 |
| 저장 C 보충 설명, 1단계 | 0.1263초 | C 종료→B 복귀 재생 0.1124초 |
| D 정상 테스트 사진의 기존 수업, 1단계 | 0.0843초 | 단일 단계 |

새 질문 제출 시간이 아니다. 모델 로딩 cold/warm 비교는 해당하지 않는다. 브라우저는 격리 컨텍스트였지만 사전 WAV SHA 읽기 때문에 OS 파일 캐시가 warm일 수 있다. 같은 조건의 수정 전 캐시 재생 대조 실험도 없으므로 101초가 0.16초로 개선됐다는 배율을 주장하지 않는다. **수정 후 새 질문→첫 유효 설명과 새 합성 단계 공백은 NOT_MEASURED**다.

A3/B4/C1/D1의 기존 9개 WAV를 모두 1배속 자연 종료로 재생했다. 테스트 도구의 가속/강제 seek는 없고, 앱이 동일 B의 저장 위치로 복귀할 때만 seek했다. B의 내용 있는 원본 표에서 1행 attended=1을 선택했고, 저장 C가 9.84초 자연 종료된 뒤 같은 셀·0.465038초 위치로 돌아와 나머지 수업을 완주했다. 복귀 전후 포인터의 선택 셀 중심 거리 0px를 확인했다.

저장 보충 요청→동기 paused 확인은 0.3ms, native pause 이벤트는 4.2ms였다. 새 중간 질문 추론의 응답 시간이 아니다. 원본 질문·표·대사·판서 HTML·음성 ID/메타데이터·전후 PNG·media/lesson 이벤트는 JSON에 있다. API 84회는 모두 GET, 비GET/외부 시도와 페이지 오류는 0이었다. 사진은 기존에 만든 합성 개발 이미지이며 실제 학생 업로드가 아니다. 조건이 잘린 사진은 기존 차단 기록을 검토 화면에 보존했으며 새 OCR은 하지 않았다.

이 실제 재생은 `index-Do71JGmN.js` 시점이다. 그 뒤 채팅 완료 경합만 고친 최종 빌드는 `index-DwuDoYF8.js`다. Classroom/speechCache는 그 사이 바꾸지 않았다. 실제 실행 당시 번들 SHA와 전체 소스 snapshot은 미채집이며, 최종 소스 해시를 당시 실행에 소급하지 않는다.

## 검증과 보존

| 증거 층위 | 결과 | 범위 |
|---|---|---|
| 선택 전체 CPU 회귀 | 474 통과, 30 NOT_RUN | 최종 수업 지문 projection 수정 전. 실제 신경망/학습/토크나이저 제외 |
| 후속 백엔드 영향 검사 | 40 통과, demo 별칭 보완 후 핵심 2 재검사 통과 | 앞의 474와 겹치므로 합산하지 않음 |
| 프런트 단위/빌드 | 43 통과, 최종 빌드 성공 | 채팅 완료 경합은 이후 영향 UI로 검증 |
| 확장 화면 검사 | 38 중 37 통과, 1 실패 보존 | 신규 캐시/경합 12개 통과. 기존 채팅 최종 표시 경합 발견 |
| 채팅 수정 후 영향 검사 | 관련 7 통과 + 결정적 경계 1 통과 | 첫 결정적 fixture의 설정 탭 준비 실패도 보존. 준비만 고친 뒤 1개 재검사. 전체 39개 재실행으로 표시하지 않음 |
| 인간 검토 UI 제어 | 36 통과 | 원본 WAV 표본/기록 저장·내보내기/가져오기/390px·글자2배. 자동 입력은 실제 인간 검토 아님 |
| 실제 기존 WAV | A/B/C/D 통과 | 1배속 재생·중단·선택 셀·복귀. 신규 모델 품질 검사 아님 |
| 사람 교육·발음·청취 판단 | H_PENDING | 사람 검토 미수행 |

[CPU 결과](final-cpu-summary.json), [최종 프런트 검증](frontend-validation-final.json), [검토 UI](review-ui-qa.json). 기존 Starlette TestClient 경고와 프런트 500kB chunk 경고가 남아 있다. 검사 실패를 삭제하거나 전체 검사 개수를 합산하지 않았다.

[보존 검사](preservation-after.json): 기존 DB 454행 전체의 canonical SHA가 동일하다. 기존 증거·정책 등 723파일 중 허용한 갤러리 index.html만 변경했고 원본 index를 백업했다. 장부 파일도 byte SHA가 동일하다. 모델 파일의 크기·수정시각은 동일하며 이번에 전체 가중치를 다시 해시하지는 않았다.

장부 **125요청, 4176.331/5400초, 음성19/19, 사진6/6, 예약0** 유지. 남은 1223.669초가 음성/OCR 추가 승인은 아니다. 요청300초, 단일 GPU 큐, 인증, 저장50GB/경고40GB/C여유50GB 정책을 그대로 유지했다. [읽기 전용 저장 조사](storage.json)는 보수적 약20.74GB, C여유86GB 수준으로 한도 이내다. 정리·삭제는 하지 않았다.

## 사람이 검토하는 방법

[기존 증거 갤러리](../../student-experience/20261027/index.html)를 열고 A/B·C/정상·잘린 테스트 사진을 선택한다. 실제 WAV와 같은 단계의 누적 완료 판서를 확인한다. 정적 판서는 자동 동기화되지 않는다는 안내가 있다. 실제 캐릭터/판서 진행은 저장 수업 링크에서 확인한다.

검토자·날짜/시각·audio_offset·실제로 들은 발화·문제 종류·의견·상태를 직접 기록한다. 기대 대사를 들은 발화로 자동 채우지 않는다. 기본은 미검토이며 개별 통과/수정필요/불확실 기록이 H_PENDING을 자동 승격하지 않는다. 명시 저장은 브라우저 localStorage에만 남고 JSON 내보내기로 보존한다. 가져오기는 기존 기록을 덮어쓰지 않는다. 서버/외부로 전송하지 않는다. [검토 절차와 한계](review-implementation.md).

## 남은 문제와 다음 최소 검증안 — 이번 실행 안 함

새 질문의 큰 모델·합성 지연은 남아 있다. 로딩 제외 clip RTF가 약4이므로 한 단계 선행 생성만으로 목표 공백2초 이하가 보장되지 않는다. warm 상주 가능 VRAM, 오디오 streaming, 정확한 합성/codec 비용은 실제 실행 없이 성능 개선으로 주장하지 않는다.

모델 교육 능력도 그대로다. 이전 raw B는 WHERE를 값 설정처럼 설명했고, raw C는 선택 행 근거 대신 일반 SQL 설명으로 벗어났으며, D에는 NULL 관련 모호한 설명이 있었다. 앱의 SQL 검증/행 근거 연결 결과를 모델 단독 정확도 개선으로 계산하지 않는다. C의 긴 정적 판서는 스크롤이 필요하며 전반적 가독성·발음·교육 적절성은 사람이 판단해야 한다.

추후 승인을 받는다면 **새 텍스트 추론 최대1회와 짧은 새 TTS 최대2개**, OCR0회로 첫 유효 설명·새 host 구간·두 단계 공백을 한 번 측정하는 최소안이 가능하다. 최대3작업×300초=900초의 실패 포함 상한을 기존 잔여1223.669초 안에서 계획하며, 음성 추가2회는 별도 승인 기록이 필요하다. 모델/대사 조건을 고정해 기록하되 이 작은 측정만으로 상주/선행 생성의 A/B 효과를 주장하지 않는다. 원인 수정 없는 실패 재시도, 학습, 새 모델 다운로드, 유료 호출, 외부 업로드는 포함하지 않는다. 이번에는 이 승인 요청이나 실행을 시작하지 않았다.

최종 코드·검사·설정·빌드 목록은 [source-final.json](source-final.json), 비밀·DB·모델·WAV를 제외한 소스 보존본은 [source-final.zip](source-final.zip)에 둔다. 기존 source-final.zip과 모든 성공/실패 기록은 그대로 남겼다.
'''
    (OUT / 'REPORT.md').write_text(report, encoding='utf-8')
    handoff = '''# ChatGPT 전달용 — 그대로 복사

작업 경로는 D:/LLM/edu-tutor-local이다. STATUS.json, HANDOFF.md, docs/STUDENT_EXPERIENCE.md, docs/PROGRESS_BRIEFING.md와 runs/student-latency/20261027/REPORT.md를 먼저 읽어라.

2026-10-27 지연 후속 작업의 신규 생성 없는 범위를 완료했다. 정확한 기존 음성 캐시 조회, 다음 한 단계 WAV 선행 준비, 화면 판서/서버/음성 지문 일치, 늦은 GET/음성 취소, 수동·연속 재생 상태를 구분한 보충 설명 복귀, 빠른 채팅 완료 시 최종 답변 누락을 수정했다. 기존 갤러리에 사람이 실제 WAV를 듣고 audio_offset/발화/오류를 기록·내보내는 기능을 추가했다. 일반 학생 수업 기능은 유지하고 ?lesson 검토 링크만 GET-only 저장 재생으로 분리했다.

기존 기록 분석상 text cold 로딩9.485~12.500초, TTS 로딩2.968~3.515초, 새 성공7개 clip 처리RTF3.857~4.302(로딩 제외, 순수합성 아님)이다. 과거 A 새 질문 첫 음성101.520초는 33.605초 계획+67.883초 음성준비+0.0324초 재생으로 분해된다. 새 질문/새 합성 지연은 이번 수정 후 NOT_MEASURED다.

기존 실제 WAV 9개를 1배속으로 A/B/저장C/D 재생했다. 재생 버튼→playing A0.1648초/B0.1126초/D0.0843초, 저장C0.1263초. A/B 단계공백0.0496~0.0679초. B 선택행 attended=1과0.465038초 위치로 복귀했다. 저장C 요청→native pause4.2ms다. 이는 OS캐시가warm일 수 있는 기존 음성 재생이며 신규 질문 응답 개선으로 비교하지 마라. 실제 실행은 index-Do71JGmN.js였고 번들SHA/전체snapshot은 미채집; 이후 채팅 완료 경합만 고친 최종빌드는 index-DwuDoYF8.js다.

선택CPU474통과/30NOT_RUN 후 backend projection 영향40+핵심2통과, 단위43통과, UI38중37통과에서 채팅경합1건발견·보존 후 관련7개와 결정적1개통과, 검토UI36통과다. 중복 합산하거나 전체 최신39개가 모두 재실행됐다고 쓰지 마라. 사람 교육/발음/청취 검토는 H_PENDING, 교육 NOT_READY다. raw모델의 WHERE·행 맥락·NULL 설명 문제는 남아 있고 앱SQL검증을 모델자체 개선으로 보고하지 마라.

DB454행/기존723파일은 갤러리index 허용변경 외 보존됐다. 장부125요청·4176.331/5400초·음성19/19·사진6/6·예약0 유지. 이번 text/TTS/OCR/학습/다운로드/유료/외부업로드0이다. 잔여시간은 추가음성/OCR 승인이 아니다. 기존 인증·직렬GPU큐·요청300초·저장제한을 유지하라. 신경망 시각화 확장을 재개하지 마라.

다음은 사람이 기존 수업을 실제로 듣고 검토하거나, 별도 승인 후 새 text최대1회/TTS최대2개/OCR0으로 새 host 구간과 첫 설명·단계 공백을 측정하는 최소안이다. 최대900초를 기존잔여1223.669초 안에서 계획하고 실패원인 수정 없이 반복하지 마라. 이번에는 추가승인/추론을 실행하지 않았다. 새 모델/학습/유료/외부전송은 범위에 없다.
'''
    (ROOT / 'docs/CHATGPT_HANDOFF.md').write_text(handoff, encoding='utf-8')
    prefix = '''# 2026-10-27 지연 후속 작업 — 신규 생성 없는 범위 완료

현재 결론은 **교육 NOT_READY / H_PENDING**이다. 저장된 수업의 캐시·재생·취소·복귀를 수정하고 실제 기존 WAV를 검증했다. 새 질문/새 합성 속도 개선은 이번에 측정하지 않았다.

최신 결과: [지연 종합 보고](runs/student-latency/20261027/REPORT.md), [진행 브리핑](docs/PROGRESS_BRIEFING.md), [복사 인계문](docs/CHATGPT_HANDOFF.md). 장부125요청·4176.331초·음성19/19·사진6/6 유지, 신규 text/TTS/OCR/학습/다운로드/유료/업로드0. 기존 학생 기능과 이전 신경망 증거를 보존했다. 아래는 앞선 학생 수업 검증 인계 원문이다.

---

'''
    (ROOT / 'HANDOFF.md').write_bytes(prefix.encode('utf-8') + (OUT / 'before-HANDOFF.md').read_bytes())
    student_prefix = '''# 2026-10-27 후속: 지연 원인과 생성 없는 개선

**저장 재생 경로의 프로그램 개선을 완료했다. 새 질문/새 음성 성능과 사람 교육·청취 품질은 미검증이며 NOT_READY / H_PENDING이다.** [최신 종합 보고](../runs/student-latency/20261027/REPORT.md)에 병목·변경·실패·검증 시점·보존·최소 후속안을 구분했다.

실제 기존 WAV A/B/C/D를1배속으로 재생했다. A/B 단계공백0.0496~0.0679초, 저장C 요청→native pause4.2ms, 같은 B행/음성위치 복귀를 확인했다. 이 값은 새 질문 첫음성101.520초와 조건이 다르므로 속도개선 배율로 비교하지 않는다. [실제 재생 근거](../runs/student-latency/20261027/live-cache/2026-10-27T07-52-16-683Z/report.json)와 [기존 WAV 인간 검토 갤러리](../runs/student-experience/20261027/index.html)를 확인한다. 새 생성0, 장부·원본 증거 유지. 아래 이전 보고서는 당시 조건과 결과를 그대로 보존했다.

---

'''
    (ROOT / 'docs/STUDENT_EXPERIENCE.md').write_bytes(student_prefix.encode('utf-8') + (OUT / 'before-STUDENT_EXPERIENCE.md').read_bytes())
    (ROOT / 'docs/PROGRESS_BRIEFING.md').write_text('''# 전체 진행 브리핑 — 2026-10-27

이번 신규 생성 없는 수정·검증 범위는 완료했다. 학생이 새 질문을 보내 짧은 준비 후 정확한 수업을 듣는 최종 목표는 아직 NOT_READY다. 사람 검토는 H_PENDING이다.

| 구분 | 현재 상태 |
|---|---|
| 이미 실제 확인한 기능 | 이전 A개념/B원본→중간→결과/C행질문·복귀/D정상·잘린 개발사진 처리 기록 보존 |
| 이번 완료 | 엄격한 캐시 조회, 다음 한 단계 기존 WAV 준비, 화면판서/서버/음성 지문 비교, 늦은결과 취소, 수동/연속복귀, 빠른 채팅완료 답변표시 경합 수정, 기존 갤러리 인간검토 기록 |
| 이번 실제 재생 | 기존9개WAV 1x, A/B단계공백0.0496~0.0679초, 저장C native정지4.2ms, B같은셀/0.465038초복귀 |
| 남는 학생 문제 | 새질문 모델로딩·완성WAV생성 지연, raw WHERE/행맥락/NULL 설명 결함, 긴판서의 스크롤·가독성 및 발음 검토 필요 |
| 미검증 | 새질문/새합성 수정후지연, 실제 streaming/상주warm효과, 인간 교육·청취 판단 |
| 보존/예산 | DB454행, 기존723파일 중 index만허용변경.125요청/4176.331초/음성19/사진6/예약0. 신규text/TTS/OCR/학습/다운로드/유료/업로드0 |

선택CPU474통과(후속projection전), 후속영향40+2, 단위43, UI38중37통과에서 발견한채팅경합수정후관련7+결정적1통과, 검토UI36통과다. 서로겹치는검사를합산하지 않는다. 실제기존WAV는채팅최종수정전번들이므로 [버전경계](../runs/student-latency/20261027/live-cache/2026-10-27T07-52-16-683Z/provenance.json)를 함께 본다.

[전체 보고와 근거](../runs/student-latency/20261027/REPORT.md) · [복사 인계문](CHATGPT_HANDOFF.md). 수정중이거나 실행중인 모델 작업은 없다. 추가 실행은 이번에 시작하지 않았다.
''', encoding='utf-8')
    status = read(ROOT / 'STATUS.json')
    status['current_work'] = 'No-generation latency repairs completed within verified scope; fresh-question latency NOT_MEASURED; education NOT_READY/H_PENDING.'
    status['latest_verification'] = 'latency_followup'
    status['latency_followup'].update(status='COMPLETED_NO_GENERATION_SCOPE', report='runs/student-latency/20261027/REPORT.md',
        preservation='runs/student-latency/20261027/preservation-after.json', actual_cached_replay=f'runs/student-latency/20261027/{LIVE}/report.json',
        actual_replay_bundle='index-Do71JGmN.js', actual_bundle_sha256='NOT_CAPTURED', final_bundle='index-DwuDoYF8.js',
        tests={'selected_cpu_before_final_projection':474,'not_run':30,'projection_affected':40,'projection_alias_recheck':2,
               'frontend_unit':43,'extended_ui_before_chat_fix':{'passed':37,'failed':1},'chat_fix_affected_passed':7,'deterministic_chat_recheck_passed':1,'review_ui_passed':36},
        fresh_question_latency_after_change='NOT_MEASURED', new_synthesis_latency_after_change='NOT_MEASURED',
        budget={'requests':125,'charged_seconds':4176.331,'total_seconds':5400,'audio_used':19,'audio_cap':19,'vision_used':6,'vision_cap':6,'reserved':0},
        runtime_url='http://127.0.0.1:8000', runtime_pid_snapshot=43532,
        next_minimal_plan_not_authorized_or_run={'text':1,'tts':2,'ocr':0,'worst_case_seconds':900,'requires_separate_audio_authorization':True})
    (ROOT / 'STATUS.json').write_text(json.dumps(status, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Updated REPORT and all five requested state/handoff documents.')

if __name__ == '__main__':
    main()
