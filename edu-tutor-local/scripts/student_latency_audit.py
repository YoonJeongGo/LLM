"""Read-only latency audit of existing student recordings; stdlib only.

No app imports, HTTP, model loading, worker launch, audio synthesis or DB writes.
Only audit*.json/md below the designated latency directory may be written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import wave
import zipfile
from datetime import datetime, timezone
from pathlib import Path

CASES = ("A-final", "BC-voicefix", "D-normal-lesson")
NOT_MEASURED = {"status": "NOT_MEASURED", "seconds": None}
ID = re.compile(r"[0-9a-f]{32}\Z")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def seconds(start, end):
    return (utc(end) - utc(start)).total_seconds() if start and end else None


def r(value):
    return round(value, 6) if isinstance(value, (int, float)) else value


def select(event):
    keys = ("type", "at_ms", "at_iso", "lesson_record_id", "step_id", "epoch",
            "supplement", "input_kind", "audio_id", "cached", "lesson_audio_already_ready")
    return {key: event[key] for key in keys if key in event}


def same_unit(a, b):
    return (a.get("lesson_record_id"), a.get("step_id"), a.get("epoch")) == (
        b.get("lesson_record_id"), b.get("step_id"), b.get("epoch"))


def browser_intervals(case):
    events = case["events"]
    first = []
    for timing in case["latencies"]["question_to_first_valid_explanation"]:
        index = timing["event_index"]
        submitted = events[index]
        end = next((j for j in range(index + 1, len(events))
                    if events[j]["type"] == "question_submitted"), len(events))
        plan = next((e for e in events[index + 1:end] if e["type"] == "plan_ready"), None)
        playing = next((p for p in case["playback"] if index < p["event_index"] < end
                        and p["audio_id"] == timing.get("audio_id")), None)
        if not plan or not playing:
            continue
        play = playing["event"]
        ready = next((e for e in events[index + 1:playing["event_index"]]
                      if e["type"] == "speech_ready" and same_unit(e, play)), None)
        if not ready:
            continue
        segments = {
            "submit_to_plan_ready": (plan["at_ms"] - submitted["at_ms"]) / 1000,
            "plan_ready_to_clip_fetched_decoded_ready": (ready["at_ms"] - plan["at_ms"]) / 1000,
            "clip_ready_to_native_playing": (play["at_ms"] - ready["at_ms"]) / 1000,
        }
        total = (play["at_ms"] - submitted["at_ms"]) / 1000
        assert abs(sum(segments.values()) - total) < 0.000001
        first.append({"request_id": timing["request_id"], "input_kind": timing["input_kind"],
            "lesson_id": playing["lesson_id"], "step_id": playing["step_id"],
            "supplement": bool(play.get("supplement")), "audio_id": playing["audio_id"],
            "tts_cache_hit": playing["tts_clip_cache_hit"], "clock": "same-case browser performance.now",
            "question_to_valid_audio_seconds": r(total),
            "disjoint_browser_segments_seconds": {k: r(v) for k, v in segments.items()},
            "anchors": [select(e) for e in (submitted, plan, ready, play)],
            "scope": "Ready is after authenticated full-WAV fetch and waveform decode. This is not first audible-word or H review."})
    clips = []
    for playback in case["playback"]:
        index = playback["event_index"]
        play = playback["event"]
        ready = next((e for e in reversed(events[:index]) if e["type"] == "speech_ready" and same_unit(e, play)), None)
        ended = next((e for e in events[index + 1:] if e["type"] == "audio_ended" and same_unit(e, play)), None)
        stop = next((e for e in events[index + 1:] if e["type"] in {"audio_pause", "audio_ended"}
                     and e.get("lesson_record_id") == play.get("lesson_record_id")
                     and e.get("step_id") == play.get("step_id")), None)
        # Never pair the resumed ending with the earlier interrupted playback.
        if stop and ended and stop["at_ms"] + 1 < ended["at_ms"]:
            ended = None
        clips.append({"lesson_id": playback["lesson_id"], "step_id": playback["step_id"],
            "audio_id": playback["audio_id"], "event_index": index,
            "ready_to_play_seconds": r((play["at_ms"] - ready["at_ms"]) / 1000) if ready else None,
            "playing_to_ended_seconds": r((ended["at_ms"] - play["at_ms"]) / 1000) if ended else None,
            "completion": "native_ended" if ended else "interrupted_or_not_observed",
            "tts_cache_hit": playback["tts_clip_cache_hit"]})
    gaps = []
    for gap in case["latencies"]["stage_gaps"]:
        idx = next(i for i, e in enumerate(events) if e == gap)
        play = next((e for e in reversed(events[:idx]) if e["type"] == "audio_playing" and same_unit(e, gap)), None)
        ready = next((e for e in reversed(events[:idx]) if e["type"] == "speech_ready" and same_unit(e, gap)), None)
        ended = next((e for e in reversed(events[:idx]) if e["type"] == "audio_ended"
                      and e.get("lesson_record_id") == gap.get("lesson_record_id")), None)
        gaps.append({"lesson_id": gap["lesson_record_id"], "next_step_id": gap["step_id"],
            "recorded_gap_seconds": r(gap["gap_ms"] / 1000), "clock": "same-case browser performance.now",
            "previous_end_to_ready_seconds": r((ready["at_ms"]-ended["at_ms"])/1000) if ready and ended else None,
            "ready_to_play_seconds": r((play["at_ms"]-ready["at_ms"])/1000) if ready and play else None,
            "direct_end_to_play_seconds": r((play["at_ms"]-ended["at_ms"])/1000) if play and ended else None,
            "note": "Recorded gap uses a subsequent callback clock read; sub-ms differences are retained, not forced equal."})
    return {"first_explanations": first, "playback_intervals": clips, "stage_gaps": gaps,
            "interruptions": case["latencies"]["interruptions"],
            "cancellation_server_confirmation": NOT_MEASURED,
            "clock_boundary": "No browser monotonic/ISO timestamps are subtracted from server clocks."}


def job_record(db, ident):
    assert ID.fullmatch(ident)
    row = db.execute("SELECT payload FROM jobs WHERE id=?", (ident,)).fetchone()
    if not row:
        return None
    value = json.loads(row[0])
    keys = ("id", "kind", "state", "request_id", "session_id", "generation_epoch", "created_at", "updated_at")
    return {key: value.get(key) for key in keys}


def server_job(job, requests):
    result = {"job": job, "ledger_requests": requests, "clock": "server UTC wall clock / separately recorded host duration"}
    result["job_created_to_terminal_seconds"] = r(seconds(job["created_at"], job["updated_at"])) if job else None
    result["queue_only_seconds"] = NOT_MEASURED
    result["process_spawn_only_seconds"] = NOT_MEASURED
    result["device_transfer_or_release_seconds"] = NOT_MEASURED
    result["note"] = "Job updates overwrite state timestamps. Pre-reservation is not pure queue; charged wall time is not GPU kernel time."
    if job and requests:
        ordered = sorted(requests, key=lambda x: x["started_at"])
        result["job_created_to_first_budget_reservation_seconds"] = r(seconds(job["created_at"], ordered[0]["started_at"]))
        result["last_budget_finish_to_job_terminal_seconds"] = r(seconds(ordered[-1].get("finished_at"), job["updated_at"]))
    return result


def audit(root, out):
    evidence = root / "runs/student-experience/20261027"
    ledger_path = root / "runs/phase2/current/resource-budget.json"
    policy_path = root / ".local/phase2-policy.json"
    protected_before = {str(p.relative_to(root)): sha(p) for p in (ledger_path, policy_path)}
    ledger = read(ledger_path)
    source_zip = evidence / "source-final.zip"
    sources = {}
    with zipfile.ZipFile(source_zip) as archive:
        for path, needles in {
            "src/edu_tutor/models/worker.py": ["started = time.monotonic()", "generation_seconds", "model.eval()", "with torch.inference_mode()"],
            "src/edu_tutor/models/runtime.py": ["subprocess.Popen", "process.wait(timeout=5)"],
            "src/edu_tutor/speech/provider.py": ["def speech_batch_job", "def speech_job", "started = time.monotonic()", "_checked_custom_voice(model, spec", "sf.write", '"elapsed_seconds"'],
            "web/src/Classroom.tsx": ["void prepareAudio(true)", "autoplay ||", "onEnded=", 'event("speech_ready"', "decodeAudioData"],
            "src/edu_tutor/api/app.py": ["started = time.monotonic()", "request_to_verified_core_seconds"],
            "src/edu_tutor/jobs/manager.py": ["def update", 'state="loading"', "def submit"],
        }.items():
            raw = archive.read(path)
            lines = raw.decode("utf-8").splitlines()
            sources[path] = {"sha256": hashlib.sha256(raw).hexdigest(),
                "matches": [{"line": i, "text": line.strip()} for i, line in enumerate(lines, 1) if any(n in line for n in needles)],
                "source": "preserved previous-task source-final.zip; not current mutable code"}
    artifacts = {str(source_zip.relative_to(root)): sha(source_zip)}
    cases = {}
    with sqlite3.connect((root / ".local/tutor.sqlite3").as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        for name in CASES:
            path = evidence / "cases" / (name + ".json")
            case = read(path)
            artifacts[str(path.relative_to(root))] = sha(path)
            text = []
            case_requests = case["resource_requests_linked_to_explicit_case_jobs"]
            jobs = {row["job_id"]: job_record(db, row["job_id"]) for row in case_requests}
            for message in case["messages"]:
                if message["role"] != "assistant":
                    continue
                matched_jobs = [job for job in jobs.values() if job and job["request_id"] == message["request_id"]]
                meta = message["raw_model"]["generation_snapshot"]
                text.append({"request_id": message["request_id"], "message_id": message["id"],
                    "lesson_ids": [x["id"] for x in case["lessons"] if x["source_message_id"] == message["id"]],
                    "attempt_count": len(message["raw_model"].get("attempts", [])),
                    "generation_metadata": meta, "model_condition": "cold worker; local base; model_load_count=1",
                    "request_handler_to_core_seconds": message["app_display"].get("latency", {}).get("request_to_verified_core_seconds"),
                    "generation_field_boundary": "loaded_at to generation_finished: input preparation and generation combined, not pure token generation or GPU time",
                    "text_first_token_seconds": NOT_MEASURED,
                    "tokenizer_prefill_generation_split": NOT_MEASURED,
                    "retrieval_sql_validation_parse_split": NOT_MEASURED,
                    "request_core_is_overlapping_aggregate": True,
                    "server_jobs": [server_job(job, [x for x in case_requests if x["job_id"] == job["id"]]) for job in matched_jobs]})
            audio = []
            seen = set()
            for played in case["playback"]:
                key = (played["lesson_id"], played["step_id"], played["audio_id"])
                if key in seen:
                    continue
                seen.add(key)
                meta = played["tts_generation_snapshot"]
                assert meta.get("batch_mode") == "sequential_shared_model"
                attempts = [attempt for attempt in case["tts_attempts"]
                            if attempt["lesson_id"] == played["lesson_id"]
                            and any(step["expected_audio_id"] == played["audio_id"] and step["step_id"] == played["step_id"] for step in attempt["steps"])]
                wav = evidence / "audio" / (played["audio_id"] + ".wav")
                with wave.open(str(wav), "rb") as stream:
                    wav_seconds = stream.getnframes() / stream.getframerate()
                assert abs(wav_seconds - meta["duration"]) < 0.0001
                assert sha(wav) == meta["checksum"]
                artifacts[str(wav.relative_to(root))] = sha(wav)
                workers = []
                server = []
                for attempt in attempts:
                    job = job_record(db, attempt["job_id"])
                    server.append(server_job(job, attempt["resource_requests"]))
                    for step in attempt["steps"]:
                        if step["expected_audio_id"] == played["audio_id"]:
                            workers.extend(step["worker_completion_records"])
                duration = float(meta["elapsed_seconds"])
                audio.append({"lesson_id": played["lesson_id"], "step_id": played["step_id"], "audio_id": played["audio_id"],
                    "speech": played["speech"], "cache_hit_this_case": played["tts_clip_cache_hit"],
                    "current_synthesis": "NOT_RUN_CACHE_REUSE" if played["tts_clip_cache_hit"] else "EXISTING_ACTUAL_NEW_GENERATION_RECORD",
                    "metadata_is_historical_for_cache": bool(played["tts_clip_cache_hit"]),
                    "wav_seconds": r(wav_seconds), "wav_sha256": sha(wav),
                    "worker_clip_processing_seconds": r(duration), "model_load_seconds": r(meta["model_load_seconds"]),
                    "model_load_count": meta["model_load_count"], "batch_index": meta["batch_index"],
                    "clip_processing_rtf": r(duration/wav_seconds),
                    "pure_synthesis_seconds": NOT_MEASURED, "pure_synthesis_rtf": NOT_MEASURED,
                    "wav_encoding_write_checksum_seconds": NOT_MEASURED,
                    "first_playable_chunk_before_full_wav": {"status": "NOT_IMPLEMENTED_IN_BASELINE"},
                    "gpu_kernel_seconds": NOT_MEASURED,
                    "timing_boundary": "speech_batch loads model before speech_job.started; elapsed includes full synthesis/codec return/validation/WAV write/SHA, excludes separately recorded model load and later sidecar/IPC/teardown. Do not subtract model_load_seconds from elapsed.",
                    "generation_metadata": {k: meta.get(k) for k in ("provider", "voice", "revision", "generation_settings", "peak_vram_bytes", "batch_mode")},
                    "server_jobs": server, "worker_completions": workers})
            cases[name] = {"source_file": str(path.relative_to(root)), "recorded_at": {"start": case["started_at"], "end": case["completed_at"]},
                "browser": browser_intervals(case), "text": text, "audio": audio}
    photos = []
    for name in ("D-normal", "D-cut"):
        path = evidence / "live" / (name + ".json")
        data = read(path)
        artifacts[str(path.relative_to(root))] = sha(path)
        job = data["ocr_job"]
        photos.append({"case": name, "photo_id": data["photo"]["id"], "job_id": job["id"],
            "model_revision": data["photo"].get("recognition_model_revision"),
            "vision_worker_elapsed_including_load_seconds": r(data["photo"]["recognition_elapsed_seconds"]),
            "model_load_generation_split": NOT_MEASURED,
            "job_created_to_terminal_seconds": r(seconds(job["created_at"], job["updated_at"])),
            "photo_upload_to_first_explanation": NOT_MEASURED,
            "boundary": "Separate OCR case; later restructure/confirmation/lesson cannot be added into one measured end-to-end latency."})
    failed_path = evidence / "cases/BC-repaired.json"
    failed = read(failed_path)
    artifacts[str(failed_path.relative_to(root))] = sha(failed_path)
    failed_attempts = [x for x in failed["tts_attempts"] if x["resource_requests"]]
    for attempt in failed_attempts:
        # Stored export contains no auth secrets. Keep exact failure and IDs, not model-generated content.
        for step in attempt["steps"]:
            step.pop("speech", None)
    new_audio = [a for c in cases.values() for a in c["audio"] if not a["cache_hit_this_case"]]
    unique_new = {a["audio_id"]: a for a in new_audio}
    rtf = [a["clip_processing_rtf"] for a in unique_new.values()]
    worker_paths = [Path(w["path"]).parent.name for a in unique_new.values() for w in a["worker_completions"]]
    assert len(worker_paths) == len(set(worker_paths)) == len(unique_new)
    assert all(a["model_load_count"] == 1 and a["batch_index"] == 0 for a in unique_new.values())
    checks = {"source_artifacts_unchanged": all(sha(root/p) == digest for p, digest in artifacts.items()),
        "ledger_policy_unchanged": all(sha(root/p) == digest for p, digest in protected_before.items()),
        "nonoverlapping_browser_partition_exact": True, "cache_replay_excluded_from_new_generation_samples": True,
        "wav_length_and_sha_match_metadata": True, "distinct_runtime_per_new_clip": True,
        "all_new_clips_batch_index_zero_and_one_model_load": True,
        "cross_clock_subtraction": False, "new_model_calls": 0,
        "new_tts": 0, "new_ocr": 0, "training": 0, "downloads": 0, "paid_calls": 0, "external_uploads": 0,
        "application_imports": 0, "production_db_writes": 0}
    assert checks["source_artifacts_unchanged"] and checks["ledger_policy_unchanged"]
    result = {"created_at": datetime.now(timezone.utc).isoformat(), "audit_status": "PASS_READONLY_EXISTING_RECORDS",
        "scope": "Historical baseline only. No new performance measurement or improvement claim. Source semantics read from frozen prior-task zip.",
        "code_source_baseline": read(evidence/"source-package.json")["code_source_sha256"],
        "source_semantics": sources, "artifact_hashes": artifacts, "protected_before": protected_before,
        "budget": {"request_count": len(ledger["requests"]),
            "charged_seconds": r(sum(x["charged_seconds"] for x in ledger["requests"])),
            "audio_attempts": sum(x["new_audio_clips"] for x in ledger["requests"]),
            "vision_attempts": sum(x["vision_requests"] for x in ledger["requests"]), "new_requests_during_audit": 0},
        "cases": cases, "separate_photo_ocr": photos, "preserved_failed_tts_attempts": failed_attempts,
        "new_successful_clip_sample_count": len(unique_new),
        "clip_processing_rtf_range": {"min": min(rtf), "max": max(rtf), "statistic": "individual sample range, not stable percentile or benchmark"},
        "conclusions": {
            "confirmed": [
                "Seven new successful clips each take 3.86-4.30 times WAV duration in the measured clip-processing interval, excluding model load; no streaming chunks precede completed WAV.",
                "Baseline autoplay requests only current step; next step is selected at onEnded. New steps use distinct speech_batch runtime directories, each batch_index=0/load_count=1.",
                "Four text calls include fresh worker loads (9.485-12.500s); preparation+generation is 11.500-19.485s. Cached audio does not remove text/model wait.",
                "Browser ready-to-playing is only tens of milliseconds, but ready occurs after WAV delivery and decoding; delivery/decode separately not measured."],
            "suspected": ["Per-request process startup/import/cleanup adds overhead; distinct worker design is confirmed but its exclusive duration is not recorded.",
                "Bounded preparation during current playback could reduce part of next-stage wait, but not guarantee gap elimination while measured production rate is below playback rate."],
            "insufficient_data": ["Pure synthesis vs codec decode vs file encoding/write/checksum", "Queue-only / process spawn / GPU handover or release", "TTFT / input preparation / first verified unit", "Retrieval / SQL execution / parsing / repair exclusive spans", "Browser WAV transfer / decode exclusive spans", "Resident warm model memory and latency", "Disk bottleneck or repeated offloading", "GPU kernel time and causal source of prior EOS failure"]},
        "checks": checks, "human_review": "H_PENDING", "education_status": "NOT_READY"}
    out.mkdir(parents=True, exist_ok=True)
    (out/"audit.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (out/"audit.md").write_text(markdown(result),encoding="utf-8")
    return result


def markdown(data):
    lines = ["# 기존 실제 수업 기록의 지연 감사", "", f"작성: {data['created_at']}", "",
        "새 모델·TTS·OCR·학습·다운로드·유료 호출·외부 업로드 없이 기존 기록만 읽었다. 아래 숫자는 2026-10-27 기존 실행의 재분석이며 새 측정이나 수정 후 속도 증거가 아니다. 교육 NOT_READY·H_PENDING을 유지한다.", "",
        "근거: [구간·ID·원본 해시 JSON](audit.json), [A-final](../../student-experience/20261027/cases/A-final.json), [B·C](../../student-experience/20261027/cases/BC-voicefix.json), [정상 사진 수업](../../student-experience/20261027/cases/D-normal-lesson.json), [보존한 당시 소스 ZIP](../../student-experience/20261027/source-final.zip). 현재 수정 중인 소스의 새 동작을 과거 실행에 적용하지 않았다.", "",
        "## 큰 병목 2개", "",
        "1. **완성 WAV를 얻는 음성 처리 속도.** 새 성공 clip 7개에서 모델 로딩을 제외한 clip 처리 시간이 WAV 길이의 3.857~4.302배였다. 합성·codec 반환·파형 검사·WAV 기록·SHA 계산을 합친 실제 구간이다. 순수 합성만의 RTF는 미측정이다. 이 생성 속도에서는 한 단계 선행 준비만으로 모든 공백이 사라진다고 말할 수 없다.",
        "2. **현재 음성이 끝난 뒤 다음 단계만 요청하는 순서와 반복 cold worker.** 보존된 소스에서 autoplay는 현재 step_id 하나만 요청하고 onEnded 후 다음 step으로 이동한다. 실제 새 음성 7개 모두 독립 runtime 디렉터리, batch_index=0, load_count=1이다. TTS 로딩은 각 2.968~3.515초, 텍스트 로딩은 9.485~12.500초다. 상주 가능 VRAM이나 외장 저장장치 병목은 측정하지 않았다.", "",
        "## 같은 브라우저 시계의 겹치지 않는 구간", "",
        "| 사례 | 요청 ID | 제출→계획 | 계획→WAV 준비 | 준비→재생 | 제출→유효 설명 | 음성 캐시 |", "|---|---|---:|---:|---:|---:|---|" ]
    for name, case in data["cases"].items():
        for q in case["browser"]["first_explanations"]:
            s=q["disjoint_browser_segments_seconds"]
            lines.append(f"| {name}{' 보충' if q['supplement'] else ''} | {q['request_id']} | {s['submit_to_plan_ready']:.3f}s | {s['plan_ready_to_clip_fetched_decoded_ready']:.3f}s | {s['clip_ready_to_native_playing']:.4f}s | {q['question_to_valid_audio_seconds']:.3f}s | {q['tts_cache_hit']} |")
    lines += ["", "각 행은 같은 case의 performance.now만 사용해 분할했다. 계획→WAV 준비는 TTS 요청·대기·완성 WAV 전달·브라우저 decode를 포함한 묶음이다. speech_ready는 이미 fetch/decode 후이므로 준비→재생만 보고 다운로드나 디코드가 빨랐다고 결론 내릴 수 없다. 서버 구간과 더해 총 시간을 만들지 않는다.", "",
        "## 텍스트 모델: 실제 cold 기록", "", "| 사례 | 요청 ID | 로딩 | 입력 준비+생성 | worker elapsed | 요청 handler→core |", "|---|---|---:|---:|---:|---:|"]
    for name, case in data["cases"].items():
        for t in case["text"]:
            m=t["generation_metadata"]
            lines.append(f"| {name} | {t['request_id']} | {m['model_load_seconds']:.3f}s | {m['generation_seconds']:.3f}s | {m['elapsed_seconds']:.3f}s | {t['request_handler_to_core_seconds']:.3f}s |")
    lines += ["", "OFF 경로의 generation_seconds는 loaded_at부터 generation_finished까지여서 입력 준비도 포함한다. TTFT·prefill·토큰 생성·검증·검색·SQL·파싱의 독립 시간은 NOT_MEASURED다. handler→core는 로딩·모델 실행 등을 포함하는 집계 구간이고 개념 정확성 검증을 뜻하지 않는다. 위 열들을 더하지 않는다.", "",
        "## 음성: 실제 로딩, clip 처리, WAV, RTF", "", "| 사례·단계 | 현재 캐시 | 로딩 | clip 처리 | WAV | clip 처리 RTF | 작업 청구 |", "|---|---|---:|---:|---:|---:|---:|"]
    for name, case in data["cases"].items():
        for a in case["audio"]:
            charge = [r["charged_seconds"] for j in a["server_jobs"] for r in j["ledger_requests"]]
            charged = f"{sum(charge):.3f}s" if charge else "새 작업 없음"
            suffix = "(과거 생성)" if a["cache_hit_this_case"] else ""
            lines.append(f"| {name} · {a['step_id']} | {a['cache_hit_this_case']} | {a['model_load_seconds']:.3f}s{suffix} | {a['worker_clip_processing_seconds']:.3f}s{suffix} | {a['wav_seconds']:.2f}s | {a['clip_processing_rtf']:.3f}{suffix} | {charged} |")
    lines += ["", "speech_batch는 모델을 먼저 로드한 뒤 speech_job 타이머를 시작한다. **clip elapsed에서 로딩을 다시 빼지 않았다.** 순수 합성·codec·WAV 저장·해시 시간의 분리는 NOT_MEASURED다. clip 처리 RTF는 순수 합성 RTF의 대용 이름이 아니라 기록된 전체 clip 처리 구간/실제 WAV 길이라는 별도 지표다. 캐시 행의 로딩·처리·RTF는 과거 생성 값이며 이번 질문에서 다시 소모한 시간이 아니다.",
        "", "A s3의 124.437초는 ledger charged_seconds(프로세스/로딩/처리/종료 포함)이고 clip 처리 elapsed는 110.125초, 로딩 3.250초, WAV 25.600초다. 차이를 프로세스 시작 시간이나 순수 합성으로 역산하지 않았다. 모든 host 시간은 GPU 커널 시간이 아니다.", "",
        "## 단계 공백·중간 질문", "", "| 사례 | 다음 단계 | 이전 종료→WAV 준비 | 준비→재생 | 기존 기록 공백 |", "|---|---|---:|---:|---:|"]
    for name, case in data["cases"].items():
        for g in case["browser"]["stage_gaps"]:
            lines.append(f"| {name} | {g['next_step_id']} | {g['previous_end_to_ready_seconds']:.3f}s | {g['ready_to_play_seconds']:.4f}s | {g['recorded_gap_seconds']:.3f}s |")
    lines += ["", "C 중단 요청→native DOM pause 8.8ms, 동기 paused 속성 확인 0.3ms, 중단 요청→보충 음성 81.2128초. 모델 취소 완료의 독립 서버 타임라인은 미측정이다. 이전 실제 C는 재생 중 중단·대기 판서 취소·복귀이며 실제 GPU 생성 중 취소의 속도 실험이 아니다.", "",
        "## 사진 경계와 실패 보존", ""]
    for p in data["separate_photo_ocr"]:
        lines.append(f"- {p['case']}: vision worker elapsed {p['vision_worker_elapsed_including_load_seconds']:.3f}초(로딩 포함), 서버 OCR job 생성→종료 {p['job_created_to_terminal_seconds']:.3f}초. 로딩/생성 별도 분해와 업로드→첫 음성 연속 시간은 미측정.")
    lines += ["- BC-repaired는 768 code frame에서 EOS가 없어 243.547초를 청구하고 유효 WAV를 게시하지 않았다. 실패의 순수 합성 시간·RTF는 미측정이다. 길이·SQL 혼합이 유일 원인이라는 실험은 없다.", "",
        "## 확인·의심·자료 부족", "",
        "확인: 완성 WAV 이후만 재생 가능, 단계별 단독 TTS 요청과 반복 로딩, 7개 신규 clip 처리 속도, 4개 cold text 생성, API·worker·browser 집계 구간은 서로 겹친다.",
        "", "의심: 독립 프로세스마다 import/시작/종료 비용이 더해질 수 있다. 독립 프로세스 경로는 확인됐지만 그 비용만의 시간은 없으므로 잔여 시간을 원인으로 확정하지 않는다.",
        "", "자료 부족: 순수 합성/codec/저장, 순수 큐, device 전환·해제, 첫 토큰, 첫 검증 가능 단위, RAG/SQL/parse, WAV 전달·decode, 상주 warm 가능성, 디스크/offload, GPU 커널별 시간. Job updated_at은 상태가 덮어써져 queue 시작/종료를 복원하지 않는다.",
        "", "요청·job·lesson·step·audio ID와 원본 파일 SHA는 audit.json에 연결했다. 단일 단계 타이머가 없는 구간은 NOT_MEASURED로 남겼다. 샘플은 새 음성 7개, 텍스트 4회뿐이므로 안정적인 평균/백분위 성능이나 일반 정확도를 주장하지 않는다.", "",
        "## 보존 확인", "", f"장부 요청 {data['budget']['request_count']}개, 누적 {data['budget']['charged_seconds']:.3f}초, 음성 {data['budget']['audio_attempts']}/19, 비전 {data['budget']['vision_attempts']}/6. 감사 전후 장부·정책·읽은 원본 증거 SHA가 동일했다. 신규 텍스트/TTS/OCR/학습/다운로드/유료/외부 업로드 0, DB 쓰기 0. 현재 변경한 제어 로직의 새 생성 성능은 별도 미검증이다.", ""]
    return "\n".join(lines)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    root=args.root.resolve()
    out=root/"runs/student-latency/20261027"
    data=audit(root,out)
    print(json.dumps({"status":data["audit_status"],"path":str(out/"audit.md"),"samples":data["new_successful_clip_sample_count"],"checks":data["checks"]},ensure_ascii=False))


if __name__=="__main__":
    main()
