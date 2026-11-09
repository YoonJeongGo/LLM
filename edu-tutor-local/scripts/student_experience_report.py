"""Collect completed browser cases and their explicitly referenced new records.

No model calls or network access. SQLite is opened read-only. Original live
records, old failures, model files and the resource ledger are never modified.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import wave


EXPECTED = ("A-final", "BC-voicefix", "D-normal-lesson", "D-cut-review")
TERMINAL = {"failed", "completed_selected_scope", "completed", "passed", "succeeded", "blocked", "cancelled", "not_run"}
TABLES = ("sessions", "messages", "lessons")
ID = re.compile(r"^[0-9a-f]{32}$")
AUDIO_ID = re.compile(r"^[0-9a-f]{64}$")
PRIVATE_KEYS = {"authorization", "auth", "auth_token", "token", "access_token", "refresh_token",
                "api_key", "apikey", "password", "secret", "client_secret", "cookie", "set_cookie",
                "input_token_ids", "output_token_ids", "token_ids", "tokens", "last_generated_tokens",
                "observed_eos_token_id"}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def redact(value):
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items() if key.lower().replace("-", "_") not in PRIVATE_KEYS}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact(value), ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def iso(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError):
        return None


def explicit_ids(record):
    """Never enumerate all messages merely because a session happens to exist."""
    found = {table: set() for table in TABLES}
    jobs = set()

    def add(table, value):
        if isinstance(value, str) and ID.fullmatch(value): found[table].add(value)

    def nested(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "session_id": add("sessions", item)
                elif key in {"message_id", "source_message_id"}: add("messages", item)
                elif key in {"lesson_id", "lesson_record_id"}: add("lessons", item)
                elif key == "job_id" and isinstance(item, str) and ID.fullmatch(item): jobs.add(item)
                if isinstance(item, (dict, list)): nested(item)
        elif isinstance(value, list):
            for item in value: nested(item)

    for response in record.get("responses", []):
        path = response.get("path", "").split("?")[0]
        value = response.get("value")
        nested(value)
        if path == "/api/sessions" and response.get("method") == "POST" and isinstance(value, dict):
            add("sessions", value.get("id"))
        if re.fullmatch(r"/api/sessions/[0-9a-f]{32}/messages", path):
            add("sessions", path.split("/")[3])
            if isinstance(value, list):
                for message in value:
                    if isinstance(message, dict) and message.get("role") in {"user", "assistant"}: add("messages", message.get("id"))
        if path == "/api/lessons" or re.fullmatch(r"/api/lessons/[0-9a-f]{32}(?:/.*)?", path):
            if isinstance(value, dict) and "plan" in value: add("lessons", value.get("id"))
            match = re.match(r"/api/lessons/([0-9a-f]{32})", path)
            if match: add("lessons", match.group(1))
        match = re.fullmatch(r"/api/jobs/([0-9a-f]{32})", path)
        if match: jobs.add(match.group(1))
    return found, jobs


def metadata_regime(meta):
    if not isinstance(meta, dict): return "NOT_MEASURED"
    count = meta.get("model_load_count")
    if count == 0: return "already_loaded_in_worker_record"
    if isinstance(count, (int, float)) and count > 0: return "model_loading_included"
    return "load_state_not_recorded"


def message_export(message):
    shared = {key: message.get(key) for key in ("id", "session_id", "role", "request_id", "created_at", "generation_epoch")}
    if message.get("role") == "user":
        return {**shared, "question_text": message.get("content"), "question_fields": {
            key: value for key, value in message.items() if key not in shared and key != "content"}}
    return {**shared,
        "raw_model": {"response": message.get("raw_model_response"), "attempts": message.get("model_attempts"),
                      "generation_snapshot": message.get("generation_snapshot"),
                      "load_regime": metadata_regime(message.get("generation_snapshot"))},
        "app_display": {key: message.get(key) for key in ("content", "provenance", "verification", "verification_mode", "latency")},
        "original_problem": message.get("original_problem"), "working_problem": message.get("problem"),
        "evidence": message.get("evidence"), "hypothesis": message.get("hypothesis"),
        "lesson_context": message.get("lesson_context"), "sources": message.get("sources"),
        "source_note": message.get("source_note")}


def snapshot_records(db, ids, baseline):
    records, excluded, missing = {}, {}, {}
    for table in TABLES:
        previous = set(baseline["tables"][table]["ids"])
        excluded[table] = sorted(ids[table] & previous)
        records[table], missing[table] = [], []
        for ident in sorted(ids[table] - previous):
            row = db.execute(f"SELECT payload FROM {table} WHERE id=?", (ident,)).fetchone()
            if row is None: missing[table].append(ident)
            else: records[table].append(json.loads(row[0]))
    return records, excluded, missing


def clip_at(record, lessons, event, audio_id):
    """Prefer the response observed before playback over a later DB snapshot."""
    candidates = []
    for response in record.get("responses", []):
        event_time, response_time = iso(event.get("at_iso")), iso(response.get("at"))
        if event_time and response_time and response_time > event_time: continue
        value = response.get("value")
        if not isinstance(value, dict): continue
        for key in ("audio_steps", "clips", "audio", "steps"):
            entries = value.get(key)
            if isinstance(entries, list):
                candidates.extend(item for item in entries if isinstance(item, dict) and item.get("audio_id") == audio_id)
    if candidates: return candidates[-1], "captured_api_response_before_playback"
    lesson = lessons.get(event.get("lesson_record_id") or event.get("lesson_id"), {})
    entries = [item for item in lesson.get("audio_steps", []) if item.get("audio_id") == audio_id]
    return (entries[-1], "current_lesson_snapshot") if entries else ({}, "not_found")


def lesson_at(record, lessons, event):
    ident = event.get("lesson_record_id") or event.get("lesson_id")
    candidates = []
    for response in record.get("responses", []):
        event_time, response_time = iso(event.get("at_iso")), iso(response.get("at"))
        if event_time and response_time and response_time > event_time: continue
        value = response.get("value")
        if isinstance(value, dict) and value.get("id") == ident and value.get("plan"):
            candidates.append(value)
    return (candidates[-1], "captured_api_response_before_playback") if candidates else (lessons.get(ident, {}), "current_lesson_snapshot")


def copy_audio(root, folder, ident):
    if not isinstance(ident, str) or not AUDIO_ID.fullmatch(ident):
        return {"audio_id": ident, "status": "INVALID_ID"}
    source = root / ".local/audio" / (ident+".wav")
    metadata_path = source.with_suffix(".json")
    if not source.is_file() or not metadata_path.is_file():
        return {"audio_id": ident, "status": "MISSING_WAV_OR_JSON"}
    original_sha = digest(source)
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / source.name
    collision = dest.exists() and digest(dest) != original_sha
    if collision: dest = folder / (ident+"-"+original_sha[:12]+".wav")
    if not dest.exists(): shutil.copy2(source, dest)
    metadata = read(metadata_path)
    sanitized = (json.dumps(redact(metadata), ensure_ascii=False, indent=2)+"\n").encode("utf-8")
    sanitized_sha = hashlib.sha256(sanitized).hexdigest()
    dest_json = dest.with_suffix(".json")
    if dest_json.exists() and digest(dest_json) != sanitized_sha:
        dest_json = folder / (ident+"-"+sanitized_sha[:12]+".json")
    if not dest_json.exists(): dest_json.write_bytes(sanitized)
    with wave.open(str(source), "rb") as stream:
        wav = {"frames": stream.getnframes(), "sample_rate": stream.getframerate(),
               "channels": stream.getnchannels(), "sample_width_bytes": stream.getsampwidth(),
               "duration_seconds": stream.getnframes()/stream.getframerate()}
    return {"audio_id": ident, "status": "COPIED", "wav": str(dest), "json": str(dest_json),
        "source_wav": str(source), "wav_sha256": original_sha, "copy_wav_sha256": digest(dest),
        "original_json_sha256": digest(metadata_path), "sanitized_json_sha256": sanitized_sha,
        "json_copy_scope": "Credential fields and token-ID arrays omitted; token counts/completion reason retained.",
        "wav_format": wav, "metadata_checksum_matches_wav": metadata.get("checksum") == original_sha,
        "metadata_duration_matches_wav": abs(metadata.get("duration", 0)-wav["duration_seconds"]) < 1/wav["sample_rate"]+1e-6,
        "preserved_existing_different_copy": collision,
        "generation_metadata": metadata,
        "source_wav_mtime_utc": datetime.fromtimestamp(source.stat().st_mtime, timezone.utc).isoformat()}


def playback_records(root, record, lesson_map, audio_folder, audio_exports):
    events = record.get("events", [])
    ready, played = {}, []
    for index, event in enumerate(events):
        key = (event.get("lesson_record_id") or event.get("lesson_id"), event.get("step_id"), event.get("epoch"))
        if event.get("type") == "speech_ready": ready[key] = event
        if event.get("type") != "audio_playing": continue
        prepared = ready.get(key, {})
        audio_id = event.get("audio_id") or prepared.get("audio_id")
        lesson, plan_source = lesson_at(record, lesson_map, event)
        step = next((item for item in (lesson.get("plan") or {}).get("steps", []) if item.get("id") == key[1]), {})
        if not audio_id:
            options = [item for item in lesson.get("audio_steps", []) if item.get("step_id") == key[1]]
            if len(options) == 1: audio_id = options[0].get("audio_id")
        if audio_id not in audio_exports: audio_exports[audio_id] = copy_audio(root, audio_folder, audio_id)
        exported = audio_exports[audio_id]
        clip, clip_source = clip_at(record, lesson_map, event, audio_id)
        speech = step.get("speech", "")
        valid = bool(speech.strip() and lesson.get("speech_allowed") and exported.get("status") == "COPIED"
                     and not re.fullmatch(r"(?:처리|음성 준비|답변 준비)\s*중(?:입니다)?[.… ]*|잠시 기다려 주세요[.… ]*", speech.strip()))
        reused = clip.get("cache_hit")
        meta = exported.get("generation_metadata", {})
        played.append({"event_index": index, "event": event, "audio_id": audio_id,
            "lesson_id": key[0], "step_id": key[1], "speech": speech,
            "playback_plan_source": plan_source,
            "valid_explanation_by_record_linkage": valid,
            "semantic_accuracy_and_listening_review": "H_PENDING",
            "ui_existing_lesson_clip": prepared.get("cached"),
            "tts_clip_cache_hit": reused, "clip_metadata_source": clip_source,
            "tts_load_regime": "no_new_load_for_cached_clip" if reused is True else metadata_regime(clip or meta),
            "tts_generation_metadata_is_historical_when_cached": reused is True,
            "tts_generation_snapshot": clip or meta,
            "cache_note": "UI cached reflects lesson clip availability, not provider cache. A cached clip's sidecar load_count describes its earlier creation."})
    return played


def tts_attempts(root, record, lesson_map, ledger):
    # _spec only hashes text/settings and reads the local pinned manifest. It
    # never loads a model, initializes a store or starts a worker.
    sys.path.insert(0, str(root / "src"))
    from edu_tutor.speech.provider import _spec
    attempts = []
    for response in record.get("responses", []):
        match = re.fullmatch(r"/api/lessons/([0-9a-f]{32})/speech", response.get("path", ""))
        if not match or response.get("method") != "POST": continue
        ident = match.group(1)
        request, value = response.get("request") or {}, response.get("value") or {}
        job_id = value.get("job_id")
        if not job_id: continue
        lesson, plan_source = lesson_at(record, lesson_map, {"lesson_record_id": ident, "at_iso": response.get("at")})
        steps = (lesson.get("plan") or {}).get("steps", [])
        if request.get("step_id"): steps = [step for step in steps if step["id"] == request["step_id"]]
        attempt = {"job_id": job_id, "lesson_id": ident, "request_at": response.get("at"),
            "voice": request.get("voice", "Sohee"), "plan_source": plan_source,
            "resource_requests": [row for row in ledger["requests"] if row.get("job_id") == job_id], "steps": []}
        attempt["actual_model_reservation_recorded"] = bool(attempt["resource_requests"])
        for step in steps:
            key, spec = _spec(step["speech"], root, attempt["voice"])
            completion = []
            for path in (root / "runs").glob("runtime-*/completion-"+key+".json"):
                changed = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
                start, end = iso(record.get("started_at")), iso(record.get("completed_at"))
                if (start and changed < start) or (end and changed > end): continue
                completion.append({"path": str(path), "sha256": digest(path), "completion": read(path),
                    "linkage": "exact content/settings audio key and case time window; runtime file has no job_id"})
            attempt["steps"].append({"step_id": step["id"], "speech": step["speech"],
                "expected_audio_id": key, "generation_settings": {k: v for k, v in spec.items() if k not in {"text", "display_text"}},
                "worker_completion_records": completion,
                "published_wav_exists_now": (root / ".local/audio" / (key+".wav")).is_file()})
        attempts.append(attempt)
    return attempts


def latencies(record, played, messages):
    events = record.get("events", [])
    valid = [item for item in played if item["valid_explanation_by_record_linkage"]]
    question_rows, interruption_rows = [], []
    for index, event in enumerate(events):
        if event.get("type") == "question_submitted":
            next_index = next((i for i in range(index+1, len(events)) if events[i].get("type") == "question_submitted"), len(events))
            supplement = event.get("input_kind") == "followup"
            audio = next((p for p in valid if index < p["event_index"] < next_index and bool(p["event"].get("supplement")) == supplement), None)
            requests = [r for r in record.get("responses", []) if r.get("method") == "POST"
                and (re.fullmatch(r"/api/sessions/[0-9a-f]{32}/messages", r.get("path", ""))
                     or re.fullmatch(r"/api/photos/[0-9a-f]{32}/solve", r.get("path", "")))
                and iso(r.get("at")) and iso(event.get("at_iso")) and iso(r["at"]) >= iso(event["at_iso"])
                and (next_index == len(events) or not iso(events[next_index].get("at_iso"))
                     or iso(r["at"]) < iso(events[next_index]["at_iso"]))]
            request = requests[0].get("request", {}) if requests else {}
            request_id = (requests[0].get("value") or {}).get("request_id") if requests else None
            answer = next((m for m in messages if m.get("role") == "assistant" and m.get("request_id") == request_id), {})
            user = next((m for m in messages if m.get("role") == "user" and m.get("request_id") == request_id), {})
            question_rows.append({"event_index": index, "input_kind": event.get("input_kind", "unknown"),
                "submission_event": event, "question_text": request.get("content") or user.get("content"), "request_id": request_id,
                "status": "MEASURED" if audio else "NO_VALID_EXPLANATION_AUDIO_RECORDED",
                "first_valid_explanation_ms": audio["event"]["at_ms"]-event["at_ms"] if audio else None,
                "audio_id": audio.get("audio_id") if audio else None,
                "text_model_load_regime": metadata_regime(answer.get("generation_snapshot")),
                "text_model_generation": answer.get("generation_snapshot"),
                "tts_load_regime": audio.get("tts_load_regime") if audio else None,
                "clock": "same case browser performance.now()", "notice_audio_excluded": True,
                "onset_measurement": "browser onPlaying for the linked explanation clip; first audible word or pronunciation not human-verified"})
        if event.get("type") == "interruption_submitted":
            limit = next((i for i in range(index+1, len(events)) if events[i].get("type") == "interruption_submitted"), len(events))
            stop = next((e for e in events[index+1:limit] if e.get("type") == "interruption_stopped"
                         and e.get("lesson_record_id") == event.get("lesson_record_id")), None)
            pause = next((e for e in events[index+1:limit] if e.get("type") == "audio_pause"
                          and e.get("lesson_record_id") == event.get("lesson_record_id")
                          and e.get("audio_epoch", event.get("epoch")) == event.get("epoch")), None)
            supplemental = next((p for p in valid if index < p["event_index"] < limit and p["event"].get("supplement") is True), None)
            measured_stop = pause or stop
            interruption_rows.append({"submission_event": event, "synchronous_stopped_event": stop, "native_pause_event": pause,
                "old_audio_stopped_ms": measured_stop["at_ms"]-event["at_ms"] if measured_stop else None,
                "old_audio_stop_evidence": "native_DOM_pause_event" if pause else "synchronous_paused_property_only" if stop else "NOT_RECORDED",
                "synchronous_paused_property_ms": stop["at_ms"]-event["at_ms"] if stop else None,
                "native_pause_event_ms": pause["at_ms"]-event["at_ms"] if pause else None,
                "old_audio_paused_confirmed": stop.get("audio_paused") if stop else None,
                "supplement_started_ms": supplemental["event"]["at_ms"]-event["at_ms"] if supplemental else None,
                "supplement_audio_id": supplemental.get("audio_id") if supplemental else None,
                "supplement_status": "MEASURED" if supplemental else "NOT_RECORDED",
                "clock": "same case browser performance.now()"})
    return {"question_to_first_valid_explanation": question_rows, "interruptions": interruption_rows,
        "stage_gaps": [e for e in events if e.get("type") == "stage_gap"],
        "stage_gap_status": "MEASURED" if any(e.get("type") == "stage_gap" for e in events) else "NO_STAGE_TRANSITION_RECORDED",
        "return_events": [e for e in events if any(word in e.get("type", "") for word in ("return", "resume", "complete"))],
        "photo_boundary": "Photo followup-case question latency starts at confirmed question submission. Do not add separate OCR/correction runs or subtract monotonic clocks across cases.",
        "quality_boundary": "Playback linkage excludes generic waiting notices; content correctness and listening quality require separate review."}


def collect(root, folder):
    baseline = read(folder / "preservation-start.json")
    ledger = read(root / "runs/phase2/current/resource-budget.json")
    artifacts, skipped, cases, audio_exports = [], [], {}, {}
    with sqlite3.connect((root / ".local/tutor.sqlite3").as_uri()+"?mode=ro", uri=True, timeout=15) as db:
        db.execute("PRAGMA query_only=ON"); db.execute("BEGIN")
        for path in sorted((folder / "live").glob("*.json")):
            if not re.fullmatch(r"[A-Za-z0-9_-]+", path.stem):
                skipped.append({"path": str(path), "reason": "unexpected_case_filename"}); continue
            try:
                raw = path.read_bytes()
                source_sha = hashlib.sha256(raw).hexdigest()
                record = json.loads(raw)
            except (OSError, ValueError) as exc:
                skipped.append({"path": str(path), "reason": "incomplete_or_unreadable_json", "detail": str(exc)}); continue
            if not isinstance(record, dict) or record.get("status") not in TERMINAL:
                skipped.append({"path": str(path), "reason": "no_terminal_status_yet"}); continue
            archive = folder / "case-history" / (path.stem+"-"+source_sha[:16]+".json")
            if not archive.exists(): write(archive, {"source_sha256": source_sha, "source_path": str(path), "record": record})
            artifacts.append({"path": str(archive), "sha256": digest(archive), "scope": "sanitized terminal source snapshot; retained across retries"})
            ids, job_ids = explicit_ids(record)
            records, excluded, missing = snapshot_records(db, ids, baseline)
            lessons = {item["id"]: item for item in records["lessons"]}
            played = playback_records(root, record, lessons, folder / "audio", audio_exports)
            snapshots = []
            for name in record.get("screenshots", []):
                screenshot = Path(name)
                snapshots.append({"path": str(screenshot), "exists": screenshot.is_file(),
                    "sha256": digest(screenshot) if screenshot.is_file() else None})
            result = {"case": path.stem, "execution_status": record["status"], "source": str(path),
                "source_sha256": source_sha, "sanitized_source_archive": str(archive), "started_at": record.get("started_at"), "completed_at": record.get("completed_at"),
                "failure": record.get("failure"), "errors": record.get("errors", []),
                "classification": ({"BC": "preserved_initial_BC_failure", "A": "preserved_initial_A_failure",
                    "A-fixed": "preserved_intermediate_A_extraction_failure",
                    "BC-repaired": "preserved_intermediate_BC_tts_failure"}.get(path.stem, "preserved_failed_case")
                    if record["status"] == "failed" else "current_case_record"),
                "input": record.get("input"), "followup": record.get("followup"),
                "new_explicit_record_ids": {key: [item["id"] for item in value] for key, value in records.items()},
                "excluded_preexisting_record_ids": excluded, "missing_referenced_new_records": missing,
                "sessions": records["sessions"], "messages": [message_export(item) for item in records["messages"]],
                "lessons": records["lessons"], "events": record.get("events", []), "playback": played,
                "tts_attempts": tts_attempts(root, record, lessons, ledger),
                "latencies": latencies(record, played, records["messages"]), "screenshots": snapshots,
                "resource_requests_linked_to_explicit_case_jobs": [row for row in ledger["requests"] if row.get("job_id") in job_ids],
                "photo_evidence": {key: record[key] for key in ("photo", "photo_fields", "ocr_job", "photo_submission_at", "solve_enabled", "fresh_photo_lesson_status", "correction_provenance") if key in record},
                "additional_harness_findings": {key: value for key, value in record.items() if key not in {
                    "responses", "events", "screenshots", "input", "mode", "started_at", "completed_at", "status", "failure", "errors", "scope", "final_text", "budget_before", "final_budget"}},
                "human_education_review": "H_PENDING", "human_listening_review": "H_PENDING",
                "not_a_new_accuracy_benchmark": True}
            destination = folder / "cases" / path.name
            write(destination, result)
            cases[path.stem] = {"execution_status": record["status"], "report": str(destination),
                "report_sha256": digest(destination), "source_sha256": result["source_sha256"],
                "failure": result["failure"], "new_ids": result["new_explicit_record_ids"],
                "played_audio_count": len(played), "latencies": result["latencies"],
                "classification": result["classification"], "human_review": "H_PENDING"}
            artifacts.append({"path": str(destination), "sha256": digest(destination)})
    for name in EXPECTED:
        if name not in cases: cases[name] = {"execution_status": "NOT_RUN_OR_NOT_FINALIZED", "human_review": "H_PENDING"}
    actual_audio = [value for key, value in audio_exports.items() if key is not None]
    for item in actual_audio:
        for key in ("wav", "json"):
            if key in item: artifacts.append({"path": item[key], "sha256": digest(Path(item[key]))})
    manifest = {"collected_at": datetime.now(timezone.utc).isoformat(), "collector": str(Path(__file__).resolve()),
        "collector_sha256": digest(Path(__file__)), "scope": "Completed live JSON plus explicitly referenced new session/message/lesson IDs; no whole-DB export.",
        "cases": cases, "skipped_in_progress": skipped, "audio": actual_audio, "artifacts": artifacts,
        "latest_education_evaluation": str(folder / "quality-audit.md"),
        "not_a_new_accuracy_benchmark": True, "human_education_review": "H_PENDING", "human_listening_review": "H_PENDING",
        "limitations": ["Database and file snapshots can advance while other verification runs; rerun when complete.",
            "No inference, audio generation, training, downloads or external uploads are performed by this collector.",
            "Original WAV bytes are copied; JSON copies omit credentials and token-ID arrays with both original/export hashes retained.",
            "Existing failure BC stays separate from BC-repaired; a completed harness status is not educational readiness.",
            "Browser audio_playing proves a browser playback event, not that a human heard or approved the audio.",
            "UI cached and provider cache_hit have different meanings. Historical sidecar loading times are not new latency for cached playback.",
            "Question-to-voice times include the measured UI path; loading regime is recorded from actual model metadata, not inferred from speed."]}
    write(folder / "manifest.json", manifest)
    lines = ["# 학생 수업 실행 증거", "", "이 파일은 실행 기록 수집 요약입니다. 새 정확도 벤치마크가 아니며 교육·음성 인간 검토는 **H_PENDING**입니다.", "",
        f"수집 시각: {manifest['collected_at']}", "", "| 사례 | 실행 상태 | 실제 재생 이벤트 | 질문 → 첫 유효 설명 음성 |", "|---|---|---:|---|"]
    for name, item in cases.items():
        measured = item.get("latencies", {}).get("question_to_first_valid_explanation", [])
        timing = "; ".join(f"{row['input_kind']}: {row['first_valid_explanation_ms']/1000:.3f}초" if row["first_valid_explanation_ms"] is not None else f"{row['input_kind']}: 유효 음성 미기록" for row in measured) or "NOT_MEASURED"
        label = f"[{name}]({Path(item['report']).as_posix()})" if item.get("report") else name
        lines.append(f"| {label} | {item['execution_status']} | {item.get('played_audio_count', 0)} | {timing} |")
    lines += ["", "원시 모델 답변, 앱 검증 답변, 수치 evidence, 판서 계획, 음성 메타데이터를 각 사례 JSON에서 분리했습니다. 기존 BC 실패는 BC-repaired 결과와 별도로 보존합니다.", "",
        "중간 질문 정지·보충 시작 시간, 단계 공백과 전후 판서/화면은 각 사례의 latencies/events/screenshots에서 확인할 수 있습니다. 사진 인식과 교정이 다른 실행이라면 시간을 합쳐 실제 업로드부터의 지연처럼 표시하지 않습니다.", "",
        "WAV는 audio 폴더에 원본 바이트로 복사했고 JSON은 인증값·토큰 ID 배열을 제외했습니다. UI의 cached 표시와 실제 TTS cache_hit을 구분했으며, 재사용 음성의 모델 로딩 시간은 과거 생성 기록입니다.", "",
        f"이전 최신 교육 평가 54문항/68호출 및 비교 조건: [품질 감사]({(folder/'quality-audit.md').as_posix()}).", "",
        "완료 상태 없는 JSON은 수집하지 않았으며 manifest.json의 skipped_in_progress에 남겼습니다. 최종 실증이 끝나면 같은 수집기를 다시 실행해야 합니다."]
    (folder / "SUMMARY.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from student_experience_gallery import generate_gallery
    gallery = generate_gallery(root, folder)
    manifest["gallery"] = {"path": str(gallery), "sha256": digest(gallery),
                           "scope": "Static offline HTML; local images/audio; no JavaScript or external resources."}
    write(folder / "manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--folder", type=Path, default=Path("runs/student-experience/20261027"))
    args = parser.parse_args()
    root = args.root.resolve(); folder = (root / args.folder).resolve()
    if not folder.is_relative_to(root / "runs/student-experience"):
        raise ValueError("Reports must remain inside the student-experience artifact directory.")
    result = collect(root, folder)
    print(json.dumps({"cases": {name: value["execution_status"] for name, value in result["cases"].items()},
        "audio_files": len(result["audio"]), "skipped": result["skipped_in_progress"],
        "manifest": str(folder / "manifest.json")}, ensure_ascii=False))
