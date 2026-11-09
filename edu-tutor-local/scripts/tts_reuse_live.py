"""Run exactly the approved cold and same-instance warm synthesis via local API."""
import json
import hashlib
import subprocess
import time
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/student-latency/20261027/tts-worker-reuse"
TOKEN = (ROOT / ".local/auth-token").read_text(encoding="utf-8").strip()


def api(path, body=None):
    request = urllib.request.Request("http://127.0.0.1:8000/api"+path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer "+TOKEN, "Content-Type": "application/json"},
        method="POST" if body is not None else "GET")
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def gpu():
    def command(args):
        done = subprocess.run(["nvidia-smi", *args], capture_output=True, timeout=15,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        # Windows process paths can be CP949 even when this harness uses -X utf8.
        # Keep decoding diagnostics from interrupting or obscuring generation.
        def decode(value):
            try:
                return value.decode("utf-8"), "utf-8"
            except UnicodeDecodeError:
                return value.decode("cp949", errors="replace"), "cp949-with-replacement"
        stdout, encoding = decode(done.stdout)
        stderr, error_encoding = decode(done.stderr)
        return {"exit": done.returncode, "stdout": stdout, "stderr": stderr,
                "stdout_encoding": encoding, "stderr_encoding": error_encoding}
    return {"at": datetime.now(timezone.utc).isoformat(),
        "device": command(["--query-gpu=name,driver_version,memory.total,memory.used,memory.free,utilization.gpu", "--format=csv,noheader,nounits"]),
        "processes": command(["--query-compute-apps=pid,process_name,used_gpu_memory", "--format=csv,noheader,nounits"]),
        "scope": "Read-only device-wide snapshot; WDDM may report per-process memory unavailable"}


def main():
    import sys
    if "--run" not in sys.argv:
        raise SystemExit("Explicit --run required")
    target = OUT / "actual.json"
    if target.exists():
        raise SystemExit("Prior actual attempt exists; never retry automatically")
    budget = api("/resources/budget")
    grant = budget.get("active_execution_allowance") or {}
    if grant.get("id") != "20261027-tts-worker-reuse-2calls" or grant.get("audio_remaining") != 2 or grant.get("text_remaining") != 0:
        raise SystemExit("Approved unused two-call scope not available")
    lesson_id = "83efe8cadf51497aa97afda5e40d17d4"
    lesson = api("/lessons/"+lesson_id)
    if not lesson.get("speech_allowed") or lesson["status"] != "verified_tool_plan":
        raise SystemExit("Saved verified source no longer valid")
    step = lesson["plan"]["steps"][0]
    ident = uuid.uuid4().hex
    record = {"started_at": datetime.now(timezone.utc).isoformat(), "comparison_id": ident,
        "scope": "Same saved verified Korean sentence; cold and same-model warm synthesis only; no browser lesson or human review",
        "source_lesson_id": lesson_id, "source_step_id": step["id"], "display_text": step["speech"],
        "binding": lesson["speech_binding_fingerprint"], "budget_before": budget,
        "session_before": api("/tts/session"), "gpu_before": gpu(), "phases": [],
        "new_text": 0, "new_vision": 0, "warmup_calls": 0, "retries": 0, "cache_bypass": True}
    def save():
        target.write_text(json.dumps(record, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    save()
    try:
        for phase in ("cold", "warm"):
            row = {"phase": phase, "request_id": uuid.uuid4().hex, "submitted_at": datetime.now(timezone.utc).isoformat()}
            record["phases"].append(row)
            save()
            started = time.monotonic()
            posted = api("/tts/reuse-benchmark", {"comparison_id": ident, "phase": phase,
                "lesson_id": lesson_id, "step_id": step["id"], "request_id": row["request_id"]})
            row["job_id"] = posted["job_id"]
            save()
            while True:
                job = api("/jobs/"+row["job_id"])
                if job["state"] in {"succeeded", "failed", "cancelled", "blocked", "interrupted"}:
                    break
                if time.monotonic()-started > 320:
                    api("/jobs/"+row["job_id"]+"/cancel", {})
                    raise RuntimeError("Job exceeded client wait boundary; cancelled, no retry")
                time.sleep(.5)
            row.update(job=job, client_submit_to_terminal_seconds=time.monotonic()-started,
                       completed_at=datetime.now(timezone.utc).isoformat(), budget_after=api("/resources/budget"),
                       session_after=api("/tts/session"))
            save()
            if job["state"] != "succeeded" or not job.get("result", {}).get("complete"):
                raise RuntimeError(phase+" synthesis failed: "+str(job.get("error")))
            audio = job["result"]["audio"]
            info = audio["session_info"]
            if audio.get("cache_hit") or not audio.get("wav_cache_bypassed") or audio["completion"]["finish_reason"] != "eos":
                raise RuntimeError("Actual synthesis/cache/EOS contract failed")
            if phase == "cold":
                if info["load_count_this_request"] != 1 or not row["session_after"]["resident"]:
                    raise RuntimeError("Cold did not leave one loaded model resident")
                first = audio
                if row["budget_after"]["active_execution_allowance"]["audio_remaining"] != 1:
                    raise RuntimeError("Second call no longer authorized")
            else:
                identity = ["worker_pid", "process_start_time", "worker_instance_id", "model_instance_id", "model_object_id"]
                checks = {name: info[name] == first["session_info"][name] for name in identity}
                checks.update(one_total_load=info["load_count_total"] == 1, warm_no_reload=info["load_count_this_request"] == 0,
                    same_text_hash=audio["text_hash"] == first["text_hash"], same_settings=audio["effective_tts_generation_settings"] == first["effective_tts_generation_settings"],
                    separate_files=audio["output_path"] != first["output_path"], released=not row["session_after"]["resident"])
                record["reuse_checks"] = checks
                if not all(checks.values()):
                    raise RuntimeError("Warm reuse/release checks failed")
        record["status"] = "PASS_ACTUAL_SAME_MODEL_TWO_SYNTHESIS_REUSE"
    except BaseException as exc:
        record["status"] = "FAILED_ACTUAL_REUSE_NO_RETRY"
        record["failure"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        record["completed_at"] = datetime.now(timezone.utc).isoformat()
        record["budget_after"] = api("/resources/budget")
        record["session_after"] = api("/tts/session")
        record["gpu_after"] = gpu()
        save()
        print(json.dumps({"status": record["status"], "failure": record.get("failure"), "comparison_id": ident,
            "phases": [{"phase": p["phase"], "state": p.get("job", {}).get("state"), "seconds": p.get("client_submit_to_terminal_seconds")} for p in record["phases"]],
            "budget": record["budget_after"], "resident_after": record["session_after"]["resident"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
