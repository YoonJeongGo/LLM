"""Static local evidence gallery. Reads exports only; no DB, models or network."""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
from pathlib import Path
from urllib.parse import quote

LATEST = ("A-final", "BC-voicefix", "D-normal-lesson", "D-cut-review")
FAILURES = ("A-fixed", "A", "BC", "BC-repaired")
LABELS = {"A-final": "A · DDL 개념과 실행 예시", "A-fixed": "중간 A · SQL 예시 추출 경계",
          "BC-voicefix": "B·C · 새 표 수업과 중간 질문",
          "D-normal-lesson": "D · 정상 테스트 사진의 수업", "D-cut-review": "D · 조건이 잘린 사진",
          "A": "초기 A · 정의·예시 처리", "BC": "초기 B·C · 수업 중단 흐름",
          "BC-repaired": "중간 B·C · 음성 종료 검증 실패"}
CSS = """
:root{color-scheme:light;--ink:#1b2938;--muted:#526475;--line:#d8e0e8;--paper:#fff;--bg:#f2f5f8;--accent:#175a72}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.7 "Malgun Gothic","맑은 고딕",system-ui,sans-serif}
main{max-width:1180px;margin:auto;padding:36px 24px 80px}h1{font-size:2rem;line-height:1.35;margin:0 0 12px}
h2{font-size:1.45rem;margin:0}h3{font-size:1.1rem;margin:28px 0 10px}h4{font-size:1rem;margin:14px 0 8px}
p{margin:8px 0}a{color:#15566e;text-underline-offset:3px}nav{display:flex;gap:10px 20px;flex-wrap:wrap;margin:22px 0}
.card{background:var(--paper);border:1px solid var(--line);border-radius:14px;margin:22px 0;padding:24px}
.subcard{border:1px solid var(--line);border-radius:10px;padding:16px;margin:14px 0}
.head{display:flex;justify-content:space-between;gap:14px;align-items:start;flex-wrap:wrap}.meta,.small{color:var(--muted);font-size:.88rem}
.badge{display:inline-block;border:1px solid #b6ccd5;border-radius:20px;padding:3px 10px;font-size:.8rem;white-space:nowrap;background:#edf6f8}
.pending{background:#fff6df;border-color:#ddbd68;color:#624512}.failed{background:#fff0ee;border-color:#d9aaa2;color:#842c20}
.notice{padding:14px 18px;background:#fff6df;border-left:4px solid #bd841b;border-radius:5px;margin:16px 0}
.danger{background:#fff0ee;border-left-color:#bb5041}.callout{padding:13px 16px;background:#edf5f9;border-left:4px solid #427b91;margin:12px 0}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8fa;border:1px solid #e1e6eb;border-radius:8px;padding:14px;margin:10px 0;font:14px/1.7 Consolas,"Malgun Gothic",monospace}
code{overflow-wrap:anywhere}.scroll{overflow-x:auto;margin:12px 0}table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{padding:10px 12px;border:1px solid var(--line);text-align:left;vertical-align:top}th{background:#edf2f6;font-weight:650}
td{overflow-wrap:anywhere}details{border:1px solid var(--line);border-radius:9px;margin:14px 0;padding:12px 16px}
summary{cursor:pointer;font-weight:650;overflow-wrap:anywhere}details>div{margin-top:14px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.grid>*{min-width:0}
figure{margin:10px 0}img{display:block;width:100%;height:auto;border:1px solid var(--line);border-radius:8px;background:#fff}
figcaption{font-size:.85rem;color:var(--muted);overflow-wrap:anywhere;margin:7px 0}audio{width:100%;margin:10px 0}
.links{display:flex;flex-wrap:wrap;gap:8px 18px}.step-title{color:var(--accent);font-weight:700}.separator{margin-top:40px}
.review-form label{display:block;margin:12px 0;font-weight:600}.review-form input,.review-form textarea,.review-form select{display:block;width:100%;max-width:100%;font:inherit;padding:8px;border:1px solid #9aacba;border-radius:5px;background:white;color:var(--ink)}
.review-form textarea{min-height:90px;resize:vertical}.review-form input[readonly]{background:#f0f3f6}.review-actions{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
button,.file-label{font:inherit;padding:8px 12px;cursor:pointer;border:1px solid #6e8e9e;border-radius:6px;background:#edf6f8;color:var(--ink)}button:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible{outline:3px solid #297e9c;outline-offset:2px}
.review-feedback{min-height:1.5em}.board-preview{padding:10px;border:1px solid var(--line);border-radius:8px;background:#fafcfb}.review-target{font-size:.8rem;overflow-wrap:anywhere}.marked-cell{background:#fff0b4;font-weight:700}.review-form small{font-weight:400}
@media(max-width:700px){main{padding:22px 12px 48px}.card{padding:17px}.grid{grid-template-columns:1fr}h1{font-size:1.6rem}th,td{padding:8px}pre{font-size:13px}}
@media print{body{background:#fff}main{max-width:none;padding:0}.card{break-inside:avoid}audio,nav{display:none}details{display:block}a{color:#000}}
"""


def h(value):
    return html.escape("—" if value is None else str(value), quote=True)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def pre(value):
    if not isinstance(value, str): value = json.dumps(value, ensure_ascii=False, indent=2)
    return "<pre>"+h(value)+"</pre>"


def details(label, value):
    return "<details><summary>"+h(label)+"</summary>"+pre(value)+"</details>"


def local_href(root, folder, value):
    if not isinstance(value, str) or value.startswith(("\\\\", "//")) or "://" in value:
        return None
    path = Path(value)
    if not path.is_absolute(): path = folder / path
    path = path.resolve()
    if not path.is_relative_to(root) or not path.is_file(): return None
    return quote(os.path.relpath(path, folder).replace("\\", "/"), safe="/._-")


def link(root, folder, value, label):
    url = local_href(root, folder, value)
    return f'<a href="{h(url)}">{h(label)}</a>' if url else f'<span class="meta">{h(label)} · 파일 없음</span>'


def number(value, unit="seconds"):
    if not isinstance(value, (int, float)): return "미기록"
    return f"{value/1000:.3f}초" if unit == "seconds" else f"{value:.3f}ms"


def table(columns, rows, caption=None, marked=None):
    cols = [c.get("label") or c.get("name", "") if isinstance(c, dict) else c for c in columns]
    if not cols: return ""
    title = f'<p class="small">{h(caption)}</p>' if caption else ""
    head = "".join(f'<th scope="col">{h(c)}</th>' for c in cols)
    body = "".join("<tr>"+"".join(f'<td class="{"marked-cell" if (ri,ci) in (marked or set()) else ""}">{h("NULL" if v is None else v)}</td>' for ci,v in enumerate(row))+"</tr>" for ri,row in enumerate(rows))
    if not rows: body = f'<tr><td colspan="{len(cols)}">행 없음</td></tr>'
    return title+f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def load_label(value):
    return {"model_loading_included": "모델 로딩 포함", "already_loaded_in_worker_record": "이미 로딩된 모델 기록",
            "no_new_load_for_cached_clip": "음성 캐시 재사용", "NOT_MEASURED": "미측정",
            "load_state_not_recorded": "로딩 상태 미기록"}.get(value, value or "미기록")


def latency_section(case):
    data = case.get("latencies", {})
    rows = []
    for row in data.get("question_to_first_valid_explanation", []):
        rows.append([{"text": "텍스트", "photo": "확정 사진 질문", "followup": "추가 질문"}.get(row.get("input_kind"), row.get("input_kind")),
                     number(row.get("first_valid_explanation_ms")), load_label(row.get("text_model_load_regime")),
                     load_label(row.get("tts_load_regime"))])
    result = "<h3>학생이 체감한 시간</h3>"+table(["입력", "질문 → 설명 클립 재생 시작", "텍스트 모델", "음성"], rows)
    for index, row in enumerate(data.get("interruptions", []), 1):
        result += table(["중간 질문", "정지 확인", "동기 paused 속성", "보충 설명 시작"], [[index,
            number(row.get("old_audio_stopped_ms"), "ms")+" · "+("DOM pause 이벤트" if row.get("old_audio_stop_evidence") == "native_DOM_pause_event" else "속성 확인만 / DOM 미기록"),
            number(row.get("synchronous_paused_property_ms"), "ms"), number(row.get("supplement_started_ms"))]])
    gaps = data.get("stage_gaps", [])
    result += "<p class='small'>단계 사이 공백: "+(", ".join(number(row.get("gap_ms")) for row in gaps) if gaps else "전환 계측 기록 없음")+".</p>"
    result += "<p class='small'>안내음은 제외했습니다. 시간은 연결된 설명 클립의 브라우저 재생 이벤트 기준이며, 사람이 들은 첫 단어 시점과 발음 품질은 미검토입니다. 사진의 별도 OCR·교정 시간을 다른 실행과 합산하지 않습니다.</p>"
    return result


def board_actions(step):
    parts = []
    highlights = {a.get("target_element_id"):a for a in step.get("board_actions", []) if a.get("type")=="highlight"}
    for action in step.get("board_actions", []):
        kind = action.get("type")
        if kind == "table":
            highlight = highlights.get(action.get("element_id"), {})
            marked = set()
            for ri,row in enumerate(action.get("rows", [])):
                for ci,_ in enumerate(row):
                    ids = action.get("cell_ids", [])
                    cell = ids[ri][ci] if ri < len(ids) and ci < len(ids[ri]) else None
                    if ri in highlight.get("row_indices", []) or ci in highlight.get("column_indices", []) or cell in highlight.get("cell_ids", []): marked.add((ri,ci))
            parts.append(table(action.get("columns", []), action.get("rows", []), action.get("caption"), marked))
        elif kind == "code":
            parts.append(pre(action.get("code", "")))
        elif kind == "text":
            parts.append('<div class="callout">'+h(action.get("text", ""))+"</div>")
        elif kind in {"equation", "diagram"}:
            parts.append(pre(action))
        elif kind == "highlight":
            parts.append("<p class='small'>강조 대상: "+h(action.get("target_element_id"))+" · "+h({k:v for k,v in action.items() if k in {"row_indices","column_indices","cell_ids"}})+"</p>")
        elif kind != "clear":
            parts.append(pre(action))
    return "".join(parts)


def completed_step_board(lesson, step_id):
    """Static end-of-step content, preserving earlier elements until explicit clear.

    This is not the application's timed renderer or a synchronized replay.
    """
    elements, highlights = {}, {}
    for step in (lesson.get("plan") or {}).get("steps", []):
        for action in step.get("board_actions", []):
            kind = action.get("type")
            if kind == "clear":
                if action.get("target") == "all": elements.clear(); highlights.clear()
                else: elements.pop(action.get("target"), None); highlights.pop(action.get("target"), None)
            elif kind == "highlight": highlights[action.get("target_element_id")] = action
            else: elements[action.get("element_id", str(len(elements)))] = action
        if step.get("id") == step_id:
            return board_actions({"board_actions":[*elements.values(), *highlights.values()]})
    return "<p>대응하는 원래 단계 계획이 없습니다. 원본 JSON을 확인하세요.</p>"


def review_form(case, lesson_id=None, step_id=None, audio_id=None, checksum=None, duration=None, element_id=None):
    name = case.get("case", "unknown")
    context = {"run_id":name, "case_id":name, "case_started_at":case.get("started_at"),
        "lesson_id":lesson_id, "step_id":step_id, "audio_id":audio_id, "audio_sha256":checksum,
        "duration_seconds":duration}
    context["target_id"] = hashlib.sha256(json.dumps(context,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    status_options = "".join(f'<option>{h(value)}</option>' for value in ("미검토","통과","수정 필요","판단 어려움"))
    issue_options = "".join(f'<option>{h(value)}</option>' for value in ("미지정","사실 오류","조건 누락","불필요한 설명","한국어 발음","SQL/수식 읽기","판서 불일치","가리키는 행 오류","대화 맥락 상실"))
    offset = '<button type="button" data-read-offset>현재 원본 음성 위치 읽기</button>' if audio_id else '<p class="small">조건 차단 사례에는 음성과 위치가 없습니다.</p>'
    return f'''<details class="review-entry"><summary>이 {'음성·판서' if audio_id else '조건 차단'} 검토 기록</summary>
<form class="review-form" data-review-target="{h(json.dumps(context,ensure_ascii=False))}" data-audio-element="{h(element_id or '')}">
<p class="review-target">run_id/case: {h(name)} · lesson: {h(lesson_id)} · step: {h(step_id)}<br>audio: {h(audio_id)}<br>SHA256: {h(checksum)}</p>
<p class="small">run_id는 저장된 사례 실행 이름입니다. 개별 자기 기록이며 전체 교육 승인이 아닙니다. 개인정보·인증키를 입력하지 마세요.</p>
<label>검토자<input name="reviewer" maxlength="120" required autocomplete="off"></label><div class="grid"><label>검토 날짜<input name="review_date" type="date" required></label><label>검토 시각<input name="review_time" type="time" required></label></div>
<div class="review-actions">{offset}</div><label>음성 위치(초)<input name="audio_offset_seconds" type="number" readonly step="0.001" min="0"></label>
<label>실제로 들은 발화<textarea name="heard_utterance" maxlength="2000" placeholder="음성을 듣고 직접 적으세요. 계획 대사는 자동 복사하지 않습니다."></textarea></label>
<div class="grid"><label>문제 종류<select name="issue_kind">{issue_options}</select></label><label>개별 검토 상태<select name="review_status">{status_options}</select></label></div>
<label>의견<textarea name="comment" maxlength="4000"></textarea></label><button type="submit">검토 기록 저장</button><p class="review-feedback small" role="status" aria-live="polite"></p>
</form></details>'''


def app_replay_links(case):
    lessons = {x["id"]:x for x in case.get("lessons", []) if x.get("plan")}
    observed = []
    for item in case.get("playback", []):
        if item.get("lesson_id") in lessons and item["lesson_id"] not in observed: observed.append(item["lesson_id"])
    if not observed: return ""
    supplement = next((p["lesson_id"] for p in case.get("playback", []) if p.get("event", {}).get("supplement")), None)
    main = next((p["lesson_id"] for p in case.get("playback", []) if not p.get("event", {}).get("supplement")), None)
    values=[]
    for ident in observed:
        if ident == supplement: continue
        suffix = "&supplement="+supplement if ident == main and supplement else ""
        label = "로컬 앱에서 저장 수업·보충 설명·복귀 재생" if suffix else "로컬 앱에서 저장 수업 재생"
        values.append(f'<a class="app-replay-link" href="http://127.0.0.1:8000/?lesson={h(ident+suffix)}">{h(label)}</a>')
    return '<p class="links">'+"".join(values)+'</p><p class="small">실행 중인 로컬 앱과 인증이 필요합니다. 저장 자료 재생 링크이며 새 질문을 생성하지 않습니다.</p>'


def voice_section(root, folder, case, audio):
    output = "<h3>실제 재생된 음성</h3>"
    if not case.get("playback"): return output+"<p>유효한 설명 음성의 재생 기록이 없습니다.</p>"
    seen=set()
    for item in case["playback"]:
        ident = item.get("audio_id")
        key=(item.get("lesson_id"),item.get("step_id"),ident)
        if key in seen: continue
        seen.add(key)
        clip = audio.get(ident, {})
        url = local_href(root, folder, clip.get("wav"))
        cache = item.get("tts_clip_cache_hit")
        reserved = any(attempt.get("resource_requests") and any(s.get("expected_audio_id") == ident for s in attempt.get("steps", []))
                       for attempt in case.get("tts_attempts", []))
        label = "기존 생성 음성 재사용 · 새 TTS 아님" if cache is True else "이번 실행의 새 TTS 요청과 연결됨" if reserved else "새 생성 여부의 연결 근거 확인 필요"
        output += '<section class="subcard"><div class="head"><strong>'+h(item.get("step_id"))+" · "+h("보충 설명" if item.get("event", {}).get("supplement") else "수업 설명")+'</strong><span class="badge">'+h(label)+"</span></div>"
        element_id="clip-"+hashlib.sha256((str(case.get("case"))+repr(key)).encode()).hexdigest()[:20]
        lesson = next((x for x in case.get("lessons", []) if x.get("id")==item.get("lesson_id")), {})
        output += '<p class="small">원래 해당 단계의 완료 판서와 WAV를 나란히 제공합니다. 이 정적 판서는 음성과 자동 동기화되지 않습니다.</p><div class="grid"><section><h4>실제 생성 대사·WAV</h4><p>'+h(item.get("speech", ""))+"</p>"
        if url: output += f'<audio id="{h(element_id)}" controls preload="none" aria-label="{h(item.get("step_id"))} 설명 음성"><source src="{h(url)}" type="audio/wav">음성 파일 링크를 사용하세요.</audio>'
        else: output += '<p class="notice danger">대응 WAV를 찾지 못했습니다.</p>'
        duration = clip.get("wav_format", {}).get("duration_seconds")
        output += '<p class="small">WAV 길이: '+h(f"{duration:.2f}초" if isinstance(duration, (int,float)) else "미기록")+" · 인간 청취 검토 대기</p>"
        output += '<div class="links">'+link(root, folder, clip.get("wav"), "WAV 파일")+link(root, folder, clip.get("json"), "음성 메타데이터")+"</div>"
        output += '</section><section class="board-preview"><h4>해당 단계의 원래 완료 판서</h4>'+completed_step_board(lesson,item.get("step_id"))+"</section></div>"
        if url: output += review_form(case,item.get("lesson_id"),item.get("step_id"),ident,clip.get("wav_sha256"),duration,element_id)
        message=next((m for m in case.get("messages",[]) if m.get("id")==lesson.get("source_message_id")),{})
        output += details("이 단계의 원래 모델·자료·실행 검증 사용 기록", {
            "text_model_and_adapter":(message.get("raw_model") or {}).get("generation_snapshot"),
            "retrieved_sources":message.get("sources"), "source_note":message.get("source_note"),
            "lesson_generation":lesson.get("generation"), "reference_evidence":lesson.get("reference_evidence"),
            "plan_verification":(lesson.get("plan") or {}).get("verification"),
            "original_problem":lesson.get("original_problem"), "human_review":"H_PENDING"})
        output += details("캐시·로딩·파일 해시 근거", {"provider_cache_hit": cache, "ui_existing_lesson_clip": item.get("ui_existing_lesson_clip"),
            "load_regime": item.get("tts_load_regime"), "wav_sha256": clip.get("wav_sha256"),
            "metadata_checksum_matches_wav": clip.get("metadata_checksum_matches_wav"),
            "historical_generation_metadata_when_cached": item.get("tts_generation_metadata_is_historical_when_cached")})+"</section>"
    return output


def render_case(root, folder, name, case, audio):
    title = LABELS.get(name, name)
    if case is None:
        return f'<section class="card" id="{h(name)}"><div class="head"><h2>{h(title)}</h2><span class="badge pending">종료 기록 대기 / NOT_RUN</span></div><p>진행 중이거나 최종 수집 전입니다. 이전 실행을 이 결과로 대신 표시하지 않습니다.</p></section>'
    status = case.get("execution_status")
    badge = "실패 기록 보존" if status == "failed" else "실행 기록 완료 · 교육 합격 아님"
    output = f'<section class="card" id="{h(name)}"><div class="head"><h2>{h(title)}</h2><span class="badge {"failed" if status=="failed" else ""}">{badge}</span></div>'
    output += '<p class="meta">'+h(case.get("started_at"))+" · "+h(name)+"</p>"
    output += '<div class="links">'+link(root, folder, str(folder/"cases"/(name+".json")), "사례 JSON")+link(root, folder, case.get("sanitized_source_archive"), "실행 원본 snapshot")+"</div>"
    output += app_replay_links(case)
    if case.get("failure"): output += '<div class="notice danger"><strong>남은 실패</strong><p>'+h(case["failure"])+"</p></div>"
    if case.get("errors"): output += details("기록된 오류", case["errors"])
    inputs = case.get("input") or {}
    output += "<h3>질문과 입력 출처</h3>"
    output += "<p class='small'>"+h(inputs.get("provenance") or "이번 개발 검증 기록 · 실제 사용자 업로드로 간주하지 않음")+"</p>"
    messages = sorted(case.get("messages", []), key=lambda m:(m.get("created_at") or "",m.get("id") or ""))
    questions = [m for m in messages if m.get("role") == "user"]
    for index, item in enumerate(questions, 1): output += f"<h4>질문 {index}</h4>"+pre(item.get("question_text"))
    if not questions: output += pre(inputs)
    if inputs.get("table"):
        t = inputs["table"]; output += table(t.get("columns", []),t.get("rows", []),"직접 작성한 개발 검증용 입력 표")
    if inputs.get("sql"): output += pre(inputs["sql"])
    if inputs.get("expected_rows") is not None: output += details("개발 검증용 독립 기대값 · 모델 답변 아님",inputs["expected_rows"])
    output += latency_section(case)
    for index, message in enumerate([m for m in messages if m.get("role") == "assistant"], 1):
        raw = message.get("raw_model", {})
        display = message.get("app_display", {})
        output += f"<h3>응답 {index} · 모델과 앱 결과 분리</h3><div class='grid'><section><h4>원시 모델 답변 · 검증 판정 아님</h4>"+pre(raw.get("response"))+"</section><section><h4>학생에게 표시한 앱 답변</h4>"+pre(display.get("content"))+"</section></div>"
        output += "<p class='small'>원래 모델 답변과 자료 인용·도구 실행 결과를 같은 성능으로 집계하지 않습니다. 글자 불일치만으로 모델의 의미 오류를 판정하지 않습니다.</p>"
        evidence = message.get("evidence") or {}
        if evidence.get("result"):
            value = evidence["result"]; output += table(value.get("columns", []),value.get("rows", []),"저장된 계산 evidence의 결과")
        output += details("원본 문제·수치 근거·모델 시도", {"original_problem":message.get("original_problem"),
            "working_problem":message.get("working_problem"),"evidence":evidence,"model":raw,"app_verification":display.get("verification")})
    output += voice_section(root, folder, case, audio)
    if name=="D-cut-review": output += review_form(case)
    output += "<h3>수업 단계 대사와 판서</h3>"
    for lesson in sorted(case.get("lessons", []), key=lambda x:(x.get("created_at") or "",x.get("id") or "")):
        plan = lesson.get("plan") or {}
        output += "<p class='small'>수업 "+h(lesson.get("id"))+" · "+h(lesson.get("status"))+"</p>"
        if not plan: output += '<p class="notice">계획이 차단되었거나 준비되지 않았습니다.</p>'; continue
        output += details("검증 범위와 자료 출처", {"verification":plan.get("verification"),"reference_evidence":lesson.get("reference_evidence"),"generation":lesson.get("generation")})
        for step in plan.get("steps", []):
            observed = [p for p in case.get("playback", []) if p.get("lesson_id")==lesson.get("id") and p.get("step_id")==step.get("id")]
            output += "<details><summary>"+h(step.get("id"))+" · "+h(step.get("title"))+" · "+("재생 이벤트 있음" if observed else "계획만 있음 / 재생 미기록")+"</summary><div>"
            output += "<p class='step-title'>계획 대사</p>"+pre(step.get("speech"))+board_actions(step)+"</div></details>"
    if case.get("photo_evidence"): output += details("사진 OCR·누락 조건·확정 기록",case["photo_evidence"])
    output += details("모든 음성 준비 시도 · EOS 실패와 실제 예산 포함",case.get("tts_attempts", []))
    screenshots = case.get("screenshots", [])
    if screenshots:
        output += "<h3>실행 화면 · 중간 질문 전후 포함</h3><div class='grid'>"
        for shot in screenshots:
            url = local_href(root, folder, shot.get("path"))
            if url:
                label = Path(shot["path"]).name
                output += f'<figure><a href="{h(url)}"><img src="{h(url)}" loading="lazy" alt="{h(label)} 실행 화면"></a><figcaption>{h(label)}<br>SHA-256 {h(shot.get("sha256"))}</figcaption></figure>'
        output += "</div>"
    output += details("판서·캐릭터·재생 이벤트 원문",case.get("events", []))
    return output+"</section>"


def generate_gallery(root, folder):
    manifest_path = folder / "manifest.json"
    manifest = read(manifest_path) if manifest_path.exists() else {}
    audio = {item.get("audio_id"):item for item in manifest.get("audio", [])}
    cases = {}
    for path in sorted((folder/"cases").glob("*.json")):
        try: cases[path.stem] = read(path)
        except (OSError, ValueError): continue
    current = "".join(render_case(root,folder,name,cases.get(name),audio) for name in LATEST)
    old = "".join(render_case(root,folder,name,cases[name],audio) for name in FAILURES if name in cases)
    extra = "".join(render_case(root,folder,name,value,audio) for name,value in cases.items() if name not in LATEST+FAILURES)
    nav = "".join(f'<a href="#{h(name)}">{h(LABELS[name])}</a>' for name in LATEST)
    links = link(root,folder,str(manifest_path),"전체 manifest")+" · "+link(root,folder,str(folder/"quality-audit.md"),"이전 최신 교육 평가 54문항·68호출")+" · "+link(root,folder,str(folder/"preservation-final.json"),"최종 보존 감사")
    links += " · "+link(root,folder,str(root/"docs/STUDENT_EXPERIENCE.md"),"수정·검증 최종 보고")
    links += " · "+link(root,folder,str(folder/"final-cpu-summary.json"),"CPU 검사 범위")
    readonly_reports = sorted((folder/"ui-readonly").glob("*/report.json"))
    if readonly_reports:
        links += " · "+link(root,folder,str(readonly_reports[-1]),"최근 저장 수업 재생·화면 검사")
    script=(root/"scripts/student_review_ui.js").read_text(encoding="utf-8")
    script_hash=base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    document = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'sha256-{script_hash}'; style-src 'unsafe-inline'; img-src 'self' file:; media-src 'self' file:; connect-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'">
<title>학생 수업 실행 증거</title><style>{CSS}</style></head><body><main>
<header><p class="meta">로컬 실행 증거 · 외부 전송 없는 검토 페이지</p><h1>학생 수업 실행 증거</h1>
<p>질문, 실제 모델 답변, 앱의 계산 근거, 칠판과 재생 음성을 함께 확인합니다.</p>
<div class="notice"><strong>인간 교육·청취 검토 대기 · H_PENDING</strong><p>“짧은 준비 후 설명” 목표는 아직 달성하지 못했습니다. 측정 시간을 그대로 보존하며, 캐시 음성 재사용과 이번 실행의 새 TTS를 구분합니다. 이 기록은 새 정확도 벤치마크가 아닙니다.</p></div>
<p class="small">수집 시각: {h(manifest.get("collected_at"))}. 완료되지 않은 사례는 대기로 표시합니다. 사람의 직접 청취·교육 품질 판정을 수행한 것으로 보고하지 않습니다.</p>
<p class="links">{links}</p><nav aria-label="최신 사례 바로가기">{nav}</nav></header>
<section class="card" id="human-review"><h2>사람이 직접 검토하기</h2><p>아래 사례에서 실제 WAV를 듣고 원래 판서를 대조한 뒤 <strong>이 음성·판서 검토 기록</strong>을 여세요. 실제 들은 발화와 판단은 직접 적습니다. 저장 수업 재생은 새 질문 생성 속도의 증거가 아닙니다.</p>
<p class="notice"><strong>H_PENDING 유지</strong> · 통과 기록도 해당 사례의 자기 기록입니다. 전체 과목·시스템의 교육 승인을 자동으로 만들지 않습니다.</p>
<p class="small">명시적으로 저장한 기록만 이 브라우저 저장소에 보관합니다. file:// 저장소는 브라우저·파일 위치에 따라 유지되지 않을 수 있으므로 JSON 내보내기로 보존하세요. 가져오기는 기존 기록에 추가하며 중복 ID도 덮어쓰지 않습니다. 서버 API·외부 전송은 없습니다.</p>
<div class="review-actions"><button id="review-export" type="button">검토 JSON 내보내기</button><label class="file-label">검토 JSON 가져오기<input id="review-import" type="file" accept="application/json,.json"></label></div>
<p id="review-notice" role="status" aria-live="polite" class="small"></p><details><summary>이 브라우저의 개별 검토 기록 <span id="review-count">0</span>개</summary><div id="review-records"></div></details>
<noscript><p class="notice">검토 기록 기능에는 이 페이지에 포함된 로컬 스크립트가 필요합니다. 원본 WAV·판서·JSON은 아래에서 확인할 수 있습니다.</p></noscript></section>
{current}<section class="separator"><h2>이전 실패와 변경 전 기록</h2><p>후속 실행으로 덮어쓰지 않고 별도로 보존했습니다.</p>
<details><summary>초기 A·B·C 실패 펼쳐 보기</summary><div>{old or "<p>수집된 기록 없음</p>"}</div></details>
<details><summary>사진 인식 등 보조 실행 기록</summary><div>{extra or "<p>수집된 기록 없음</p>"}</div></details></section>
<footer class="small"><p>오디오 재생은 브라우저의 기본 컨트롤을 사용합니다. 증거는 프로젝트의 로컬 파일이며 저장 수업 재생 링크만 127.0.0.1 앱을 엽니다. 원시 모델 출력은 자료 인용·실행 검증·인간 검토 상태와 구분합니다.</p></footer>
</main><script>{script}</script></body></html>"""
    target = folder/"index.html"
    target.write_text(document, encoding="utf-8")
    return target


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument("--folder",type=Path,default=Path("runs/student-experience/20261027"))
    args=parser.parse_args(); root=args.root.resolve(); folder=(root/args.folder).resolve()
    if not folder.is_relative_to(root/"runs/student-experience"): raise ValueError("Gallery must remain in student-experience artifacts.")
    print(generate_gallery(root,folder))
