"""Collect saved recovery evidence; no inference, speech or network calls."""
import hashlib
import json
import sqlite3
import wave
from datetime import datetime, timezone
from pathlib import Path

from edu_tutor.lessons.plans import scene_at
from edu_tutor.models.budget import status as budget_status
from student_experience_gallery import render_case, details, table, h

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/student-latency/20261027/condition-recovery"
GALLERY = ROOT / "runs/student-experience/20261027"
CASE = "E-condition-recovery-20261027"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect():
    actual = read(OUT / "actual.json")
    if not actual.get("completed_at"):
        raise SystemExit("Actual UI execution has not finished")
    with sqlite3.connect((ROOT / ".local/tutor.sqlite3").as_uri()+"?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        records = {name: [json.loads(r[0]) for r in db.execute(f"SELECT payload FROM {name}")]
                   for name in ("messages", "lessons", "jobs")}
    lesson_id = (actual.get("actual_lesson") or {}).get("id")
    lesson = next((r for r in records["lessons"] if r["id"] == lesson_id), None)
    message = next((r for r in records["messages"] if lesson and r["id"] == lesson["source_message_id"]), None)
    old_lesson = next(r for r in records["lessons"] if r["id"] == actual["source_lesson_id"])
    old_message = next(r for r in records["messages"] if r["id"] == actual["source_message_id"])
    source_question = next(r for r in records["messages"] if r["role"] == "user" and r["session_id"] == old_message["session_id"] and r.get("request_id") == old_message["request_id"])
    ledger = read(ROOT / "runs/phase2/current/resource-budget.json")
    before_ledger = read(OUT / "before-resource-budget.json")
    new_requests = ledger["requests"][len(before_ledger["requests"]):]
    jobs = [r for r in records["jobs"] if r["id"] in {q["job_id"] for q in new_requests}]
    audio, playback = {}, []
    for entry in (lesson or {}).get("audio_steps", []):
        ident = entry["audio_id"]
        meta_path = ROOT / ".local/audio" / (ident+".json")
        wav_path = meta_path.with_suffix(".wav")
        metadata = read(meta_path)
        with wave.open(str(wav_path), "rb") as wav:
            wav_format = {"sample_rate": wav.getframerate(), "channels": wav.getnchannels(),
                          "frames": wav.getnframes(), "duration_seconds": wav.getnframes()/wav.getframerate()}
        audio[ident] = {"audio_id": ident, "wav": str(wav_path), "json": str(meta_path),
            "wav_sha256": sha(wav_path), "metadata_checksum_matches_wav": sha(wav_path) == metadata["checksum"],
            "wav_format": wav_format, "metadata": metadata}
        events = [e for e in actual["events"] if e["type"] == "audio_playing" and e.get("step_id") == entry["step_id"]]
        if events:
            step = next(s for s in lesson["plan"]["steps"] if s["id"] == entry["step_id"])
            playback.append({"lesson_id": lesson_id, "step_id": entry["step_id"], "audio_id": ident,
                "speech": step["speech"], "event": events[0], "tts_clip_cache_hit": entry.get("cache_hit", False),
                "tts_load_regime": "model_loading_included" if metadata.get("model_load_count") else "already_loaded_in_worker_record",
                "tts_generation_metadata_is_historical_when_cached": entry.get("cache_hit", False)})
    def event(kind, step=None):
        return next((e for e in actual["events"] if e["type"] == kind and (step is None or e.get("step_id") == step)), None)
    def delta(start, end):
        return (end["at_ms"]-start["at_ms"])/1000 if start and end else None
    timing = {"scope": "saved failed E reprocessing, NOT new-question end-to-end latency; browser performance clock",
        "reprocess_click_to_plan_seconds": delta(event("saved_response_reprocess_submitted"), event("saved_response_reprocessed")),
        "reprocess_click_to_first_explanation_audio_seconds": delta(event("saved_response_reprocess_submitted"), event("audio_playing", "s1")),
        "s1_ended_to_s2_playing_seconds": delta(event("audio_ended", "s1"), event("audio_playing", "s2")),
        "api_verification_and_plan_seconds": (lesson or {}).get("reprocessing", {}).get("verification_and_plan_seconds"),
        "new_question_total": "NOT_RUN", "warm_resident_worker": "NOT_IMPLEMENTED", "generation_streaming": "NOT_IMPLEMENTED",
        "speech_jobs": [{"job_id": j["id"], "state": j["state"], "error": j.get("error"),
                         "budget_request": next(r for r in new_requests if r["job_id"] == j["id"]),
                         "result": j.get("result")} for j in jobs]}
    pointer_checks = []
    if lesson and lesson.get("plan"):
        for sample in actual["visual_samples"]:
            step_id = sample.get("audio", {}).get("step")
            step = next((s for s in lesson["plan"]["steps"] if s["id"] == step_id), None)
            if not step or not sample["name"].endswith("-playing"):
                continue
            target = next((e for e in sample["elements"] if e["id"] == step["gesture"]["target_element_id"]), None)
            point = sample.get("pointer_end")
            rect = target["rect"] if target else {}
            inside = bool(target and point and rect["left"] <= point["x"] <= rect["right"] and rect["top"] <= point["y"] <= rect["bottom"])
            pointer_checks.append({"sample": sample["name"], "step_id": step_id, "target_id": step["gesture"]["target_element_id"],
                "pointer_inside_target": inside, "audio_playing": sample["audio"]["paused"] is False,
                "rate": sample["audio"]["playbackRate"], "point": point, "target_rect": rect,
                "scope": "table element target, not per-syllable/per-cell alignment"})
    board_states = [{"step_id": s["id"], "speech": s["speech"], "gesture": s["gesture"],
                     "completed_scene": scene_at(lesson["plan"], index)} for index, s in enumerate((lesson or {}).get("plan", {}).get("steps", []))]
    result = {"at": datetime.now(timezone.utc).isoformat(), "status": actual["status"],
        "human_review": "H_PENDING", "product_readiness": "NOT_READY", "new_text_inference": 0,
        "source": {"question": source_question["content"], "lesson": old_lesson, "message": old_message},
        "reprocessed": {"lesson": lesson, "message": message}, "board_states": board_states,
        "timing": timing, "audio": list(audio.values()), "playback": playback, "pointer_checks": pointer_checks,
        "new_resource_requests": new_requests, "current_budget": budget_status(ROOT),
        "raw_explanation_notice": "Original COUNT(*) misconception is preserved. App uses SQL-checked derived speech, not a corrected model response.",
        "limits": ["SQLite single table SUM(column IS NOT NULL), optional COUNT(*), no WHERE/GROUP/HAVING in this two-step lesson path",
                   "Other predicates, CASE, DISTINCT predicate sums, arbitrary expressions and other DBMS are unsupported",
                   "No conditional-aggregate selected-row supplementary lesson is claimed",
                   "No human education/listening review; browser playback does not certify pronunciation or first spoken word",
                   "Full-page screenshots include scroll content; original/intermediate/final tables may require scrolling at 1100px viewport"]}
    write(OUT / "result.json", result)
    case = {"case": CASE, "execution_status": "completed" if actual["status"].startswith("PASS") else "failed",
        "started_at": actual["started_at"], "sanitized_source_archive": str(OUT / "actual.json"),
        "input": {"question": actual["question"], "table": old_message["problem"]["tables"][0],
                  "provenance": "이전 개발 검증 E의 저장 질문·표·SQL·원답을 재사용했습니다. 새 질문이나 실제 학생 업로드가 아닙니다."},
        "messages": [{"id": source_question["id"], "role": "user", "question_text": source_question["content"]}],
        "lessons": [lesson] if lesson else [], "playback": playback, "events": actual["events"],
        "tts_attempts": [{"job_id": j["id"], "state": j["state"], "error": j.get("error"),
                          "resource_requests": [r for r in new_requests if r["job_id"] == j["id"]],
                          "steps": [{"expected_audio_id": p["audio_id"]} for p in playback]} for j in jobs],
        "latencies": {"question_to_first_valid_explanation": [], "stage_gaps": [e for e in actual["events"] if e["type"] == "stage_gap"],
                      "saved_response_reprocessing": timing},
        "screenshots": [{"path": p, "sha256": sha(Path(p))} for p in actual["screenshots"]]}
    if message:
        case["messages"].append({"id": message["id"], "role": "assistant", "created_at": message["created_at"],
            "raw_model": {"response": message["raw_model_response"], "attempts": message["model_attempts"],
                          "generation_snapshot": message["generation_snapshot"], "historical_reused": True},
            "app_display": {"content": message["content"], "verification": message["verification"]},
            "original_problem": message["original_problem"], "working_problem": message["problem"],
            "evidence": message["evidence"], "sources": message.get("sources"), "source_note": message.get("source_note")})
    if actual.get("failure"):
        case["failure"] = actual["failure"]
    write(GALLERY / "cases" / (CASE+".json"), case)
    write(OUT / "audio-manifest.json", list(audio.values()))
    original_html = (OUT / "before-index.html").read_text(encoding="utf-8")
    rendered = render_case(ROOT, GALLERY, CASE, case, audio)
    notice = "<div class='notice'><strong>저장 실패 E 복구 · 새 모델 추론 없음</strong><p>원시 모델 설명의 오류는 보존하고 앱의 독립 계산에서 새 대사·판서를 구성했습니다. 아래 재처리 시간은 새 질문 전체 응답 시간이 아닙니다. 조건식 집계 보충질문·사람 청취는 미검증입니다.</p>"+details("재처리·음성 구간 및 범위", timing)+"</div>"
    rendered = rendered.replace("<h3>질문과 입력 출처</h3>", notice+"<h3>질문과 입력 출처</h3>", 1)
    rendered = rendered.replace("<h3>실행 화면 · 중간 질문 전후 포함</h3>", "<h3>실행 화면 · 기존 실패와 재처리 후 두 단계</h3>")
    marker = '<section class="separator">'
    if marker not in original_html:
        raise ValueError("Existing gallery insertion marker missing")
    (GALLERY / "index.html").write_text(original_html.replace(marker, rendered+marker, 1), encoding="utf-8")
    print(json.dumps({"status": result["status"], "lesson_id": lesson_id, "timing": {k:v for k,v in timing.items() if k!='speech_jobs'},
                      "audio_count": len(audio), "pointer_checks": pointer_checks, "budget": result["current_budget"]}, ensure_ascii=False))


if __name__ == "__main__":
    collect()
