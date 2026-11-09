"""One explicitly requested, authenticated SAPI verification; no auto retry.

Accepts an already verified lesson step. This tests a new voice synthesis, not
new-question model accuracy. Run once only after the integrated scope is active.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import uuid

ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = "finish-local-tutor-20261028-v1"
TERMINAL = {"succeeded", "failed", "cancelled", "blocked", "interrupted"}


def cancellation_status(requested, job_state, progress, remaining, published):
    stages = {event["stage"] for event in progress}
    if (requested and job_state == "cancelled" and "synth_queued" in stages
            and not stages.intersection({"synth_finished", "closed_completed"}) and not remaining and not published):
        return "CANCELLED_DURING_SYNTHESIS_WITH_OWNED_CHILD_EXIT"
    return "CANCELLATION_NOT_PROVEN"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--lesson-id", required=True)
    parser.add_argument("--step-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--cancel-after-queued", action="store_true")
    parser.add_argument("--require-text-resident", action="store_true")
    args = parser.parse_args()
    if not args.run or not args.name.replace("-", "").replace("_", "").isalnum():
        raise SystemExit("Explicit --run and a safe unique name are required")
    out = ROOT / "runs/finish-v2/20261029" / args.name
    out.mkdir(parents=True, exist_ok=False)
    target = out / "actual.json"
    token = (ROOT / ".local/auth-token").read_text(encoding="utf-8").strip()
    headers = {"Authorization": "Bearer " + token, "X-Execution-Allowance": AUTHORIZATION,
        "Content-Type": "application/json"}
    def api(path, body=None, *, raw=False):
        request = Request("http://127.0.0.1:8000/api" + path, headers=headers,
            data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None)
        with urlopen(request, timeout=15) as response:
            data = response.read()
        return data if raw else json.loads(data)
    state = {"started_at": datetime.now(timezone.utc).isoformat(), "scope": AUTHORIZATION,
        "purpose": "actual system voice from verified lesson; not new model answer or full-question latency",
        "new_text": 0, "new_vision": 0, "retry": False, "human_review": "H_PENDING",
        "cancel_requested": False, "network_observation": {"kind": "owned process connection sampling",
            "forced_network_disconnection": False, "limitation": "No observed connection is not proof of a blocked network environment.", "samples": []}}
    def save():
        target.write_text(json.dumps(state, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    save()
    try:
        budget = api("/resources/budget")
        allowance = budget.get("active_execution_allowance") or {}
        if allowance.get("id") != AUTHORIZATION or allowance.get("audio_remaining", 0) < 1:
            raise RuntimeError("Integrated active audio allowance is unavailable")
        if any(j["state"] not in TERMINAL for j in api("/jobs")):
            raise RuntimeError("Another job is active; root must serialize this verification")
        if args.require_text_resident:
            resident = api("/models").get("text_session") or {}
            if not resident.get("resident") or resident.get("active_request"):
                raise RuntimeError("This measurement requires an idle live text model before CPU voice")
            state["text_resident_before"] = resident
        lesson = api("/lessons/" + args.lesson_id)
        if not lesson.get("valid", True) or not lesson.get("speech_allowed") or not lesson.get("plan"):
            raise RuntimeError("Current verified lesson with speech permission is required")
        step = next(s for s in lesson["plan"]["steps"] if s["id"] == args.step_id)
        config = json.loads((ROOT / ".local/speech-provider.json").read_text(encoding="utf-8"))
        voice = "windows_sapi:" + config["windows_sapi"]["voice_id"]
        manifest_path = "/lessons/" + args.lesson_id + "/speech?" + urlencode({"step_id": args.step_id, "voice": voice})
        if api(manifest_path)["steps"]:
            raise RuntimeError("Exact WAV already exists; cache replay cannot replace new synthesis")
        state.update(budget_before=budget, lesson_id=args.lesson_id, step_id=args.step_id,
            display_text=step["speech"], board_step=step, binding=lesson["speech_binding_fingerprint"],
            voice=voice, request_id=uuid.uuid4().hex)
        before = set(ROOT.glob("runs/runtime-*"))
        started = time.perf_counter()
        response = api("/lessons/" + args.lesson_id + "/speech", {"voice": voice,
            "step_id": args.step_id, "request_id": state["request_id"]})
        state.update(job_id=response["job_id"], submitted=True)
        save()
        import psutil
        pids = {}
        progress = []
        while True:
            for folder in set(ROOT.glob("runs/runtime-*")) - before:
                for path in folder.glob("sapi-*-progress.jsonl"):
                    try:
                        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
                    except (OSError, ValueError):
                        continue
                    if not events or events[0].get("job_id") != state["job_id"]:
                        continue
                    progress = events
                    state["runtime_directory"] = str(folder.relative_to(ROOT))
                    ident = events[0]["process_id"]
                    try:
                        process = psutil.Process(ident)
                        pids.setdefault(ident, {"pid": ident, "create_time": process.create_time(),
                            "parent_pid": process.ppid(), "executable": process.exe()})
                        connections = [{"status": c.status, "local": list(c.laddr), "remote": list(c.raddr)}
                            for c in process.net_connections(kind="inet")]
                        state["network_observation"]["samples"].append({"elapsed_seconds": time.perf_counter()-started,
                            "pid": ident, "connections": connections})
                    except psutil.Error:
                        pass
            if args.cancel_after_queued and not state["cancel_requested"] and any(e["stage"] == "synth_queued" for e in progress):
                state["cancel_submit_elapsed_seconds"] = time.perf_counter()-started
                api("/jobs/" + state["job_id"] + "/cancel", {})
                state["cancel_requested"] = True
                save()
            job = api("/jobs/" + state["job_id"])
            if job["state"] in TERMINAL:
                break
            if time.perf_counter()-started > 315:
                api("/jobs/" + state["job_id"] + "/cancel", {})
                raise RuntimeError("Client deadline exceeded; cancelled once, no retry")
            time.sleep(.02)
        state.update(job=job, child_progress=progress, owned_processes=list(pids.values()),
            submit_to_terminal_seconds=time.perf_counter()-started, budget_after=api("/resources/budget"))
        if state.get("runtime_directory"):
            # Capture terminal stages too; a fast engine can finish between the
            # previous filesystem sample and the terminal API response.
            for path in (ROOT / state["runtime_directory"]).glob("sapi-*-progress.jsonl"):
                final_events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
                if final_events and final_events[0].get("job_id") == state["job_id"]:
                    progress = final_events
                    state["child_progress"] = progress
        alive = []
        for ident, info in pids.items():
            try:
                process = psutil.Process(ident)
                if process.create_time() == info["create_time"]:
                    try:
                        process.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        alive.append(ident)
            except psutil.NoSuchProcess:
                pass
        state["owned_children_remaining"] = alive
        if args.cancel_after_queued:
            state["cancel_to_terminal_seconds"] = (state["submit_to_terminal_seconds"] - state["cancel_submit_elapsed_seconds"]) if state["cancel_requested"] else None
            published = bool(api(manifest_path)["steps"])
            state["cancelled_clip_published"] = published
            state["status"] = cancellation_status(state["cancel_requested"], job["state"], progress, alive, published)
        else:
            clips = (job.get("result") or {}).get("steps", [])
            if job["state"] != "succeeded" or len(clips) != 1 or clips[0].get("cache_hit") or clips[0].get("provider") != "windows_sapi_local":
                raise RuntimeError("Actual SAPI synthesis did not complete; inspect job evidence")
            manifest = api(manifest_path)
            clip = manifest["steps"][0]
            data = api(clip["audio_url"].removeprefix("/api"), raw=True)
            if hashlib.sha256(data).hexdigest() != clip["checksum"] or alive:
                raise RuntimeError("Authenticated WAV integrity or owned-child exit failed")
            (out / "actual.wav").write_bytes(data)
            state.update(status="PASS_NEW_SAPI_WAV", synthesized_audio=clips[0], audio=clip, new_wave=True,
                cache_notice="synthesized_audio is the actual job result; audio is the later cache manifest read",
                submit_to_authenticated_wave_seconds=time.perf_counter()-started)
        if args.require_text_resident:
            after = api("/models").get("text_session") or {}
            before = state["text_resident_before"]
            state["text_resident_after"] = after
            preserved = after.get("resident") and all(after.get("session", {}).get(key) == before["session"].get(key)
                for key in ("worker_pid", "process_start_time", "instance_id", "model_instance_id", "model_python_id", "cumulative_model_load_count"))
            state["text_instance_preserved_during_cpu_voice"] = bool(preserved)
            if not preserved:
                raise RuntimeError("Voice attempt ended but the exact text model instance was not preserved")
        save()
        print(json.dumps({"status": state["status"], "job_id": state["job_id"], "artifact": str(target)}, ensure_ascii=False))
    except BaseException as exc:
        state.update(status="FAILED", error=f"{type(exc).__name__}: {exc}")
        save()
        raise


if __name__ == "__main__":
    main()
