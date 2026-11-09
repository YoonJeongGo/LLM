"""Explicit authenticated cold/warm API pair; no retries or hidden warmups.

This creates two new model-only answers to isolate worker latency. It does not
claim educational verification, first spoken explanation latency, or listening QA.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCOPE = "finish-local-tutor-20261028-v1"
TERMINAL = {"succeeded", "failed", "cancelled", "blocked", "interrupted"}
QUESTIONS = [
    "SQLite에서 DDL은 어떤 역할을 하나요? CREATE TABLE 예를 포함하여 한국어 두 문장 이내로 설명해 주세요.",
    "SQLite에서 COUNT(*)와 COUNT(열)의 차이를 NULL을 포함해 한국어 두 문장 이내로 설명해 주세요.",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    if not args.run or not args.name.replace("-", "").replace("_", "").isalnum():
        raise SystemExit("Explicit --run and unique safe name required")
    out = ROOT / "runs/finish-v2/20261029" / args.name
    out.mkdir(parents=True, exist_ok=False)
    token = (ROOT / ".local/auth-token").read_text(encoding="utf-8").strip()
    headers = {"Authorization": "Bearer " + token, "X-Execution-Allowance": SCOPE, "Content-Type": "application/json"}
    def api(path, body=None):
        request = Request("http://127.0.0.1:8000/api" + path, headers=headers,
            data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None)
        with urlopen(request, timeout=15) as response:
            return json.load(response)
    def lease():
        path = ROOT / ".local/gpu-lease.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    state = {"started_at": datetime.now(timezone.utc).isoformat(), "scope": SCOPE,
        "purpose": "two fresh model-only API calls proving actual text instance reuse", "adapter": "base",
        "new_audio": 0, "new_vision": 0, "automatic_retry": False, "hidden_warmup": False,
        "human_review": "H_PENDING", "educational_accuracy": "not evaluated by this latency comparison",
        "whole_question_to_voice_latency": "not measured", "requests": []}
    def save():
        (out / "actual.json").write_text(json.dumps(state, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    save()
    try:
        budget = api("/resources/budget")
        grant = budget.get("active_execution_allowance") or {}
        if grant.get("id") != SCOPE or grant.get("text_remaining", 0) < 2 or grant.get("seconds_remaining", 0) < 12:
            raise RuntimeError("Active allowance is insufficient for exactly two attempted text calls")
        if any(job["state"] not in TERMINAL for job in api("/jobs")):
            raise RuntimeError("Another model job is active")
        before = api("/models")
        residency = before.get("text_session") or {}
        if residency.get("policy", {}).get("mode") != "session" or residency.get("resident"):
            raise RuntimeError("Pair requires enabled session mode and no preloaded text instance")
        state.update(budget_before=budget, model_before=before, gpu_lease_before=lease())
        save()
        first_identity = None
        for index, question in enumerate(QUESTIONS):
            current = api("/models").get("text_session") or {}
            if index and (not current.get("resident") or current.get("session", {}).get("instance_id") != first_identity["instance_id"]):
                raise RuntimeError("Warm owner is unavailable; a replacement cold call is forbidden")
            session = api("/sessions", {"title": "실제 상주 비교 · " + ("cold" if not index else "warm")})
            record = {"phase": "cold" if not index else "warm", "question": question, "session_id": session["id"],
                "request_id": uuid.uuid4().hex, "verification_mode": "model_only", "cache": "no text answer cache used"}
            state["requests"].append(record)
            save()
            started = time.perf_counter()
            submitted = api("/sessions/" + session["id"] + "/messages", {"content": question,
                "request_id": record["request_id"], "adapter": "base", "use_rag": False, "verification_mode": "model_only"})
            record.update(job_id=submitted["job_id"], submitted=True)
            save()
            first_partial = None
            while True:
                job = api("/jobs/" + record["job_id"])
                if first_partial is None and job.get("raw_partial_text"):
                    first_partial = time.perf_counter()-started
                if job["state"] in TERMINAL:
                    break
                if time.perf_counter()-started > 310:
                    api("/jobs/" + record["job_id"] + "/cancel", {})
                    raise RuntimeError("Client deadline reached; cancelled once, no retry")
                time.sleep(.1)
            record.update(submit_to_terminal_seconds=time.perf_counter()-started, first_polled_partial_seconds=first_partial,
                partial_timing_notice="100ms polling and API overhead; not exact first-token generation timing", job=job)
            if job["state"] != "succeeded":
                raise RuntimeError("Actual text attempt failed; second request is not retried")
            messages = api("/sessions/" + session["id"] + "/messages")
            answer = next(m for m in messages if m["id"] == job["result"]["message_id"])
            snapshot = answer.get("generation_snapshot") or {}
            model = api("/models")
            resident = model.get("text_session") or {}
            record.update(answer=answer, model_after=model, gpu_lease_after=lease())
            identity = {key: snapshot.get(key) for key in ("worker_pid", "process_start_time", "instance_id",
                "model_instance_id", "model_python_id", "cumulative_model_load_count", "request_model_load_count")}
            record["actual_identity"] = identity
            if len(answer.get("model_attempts", [])) != 1 or not resident.get("resident") or not all(identity.get(key) is not None for key in identity):
                raise RuntimeError("Missing real runtime identity or unexpected additional generation")
            if identity["cumulative_model_load_count"] != 1 or identity["request_model_load_count"] != (1 if not index else 0):
                raise RuntimeError("Actual model load counters do not establish cold then warm")
            if not index:
                first_identity = identity
            elif any(identity[key] != first_identity[key] for key in identity if key != "request_model_load_count"):
                raise RuntimeError("Second answer came from a different worker/model; warm success is not established")
            import psutil
            process = psutil.Process(identity["worker_pid"])
            if abs(process.create_time()-identity["process_start_time"]) > .01:
                raise RuntimeError("Current process birth differs from recorded owner")
            record["actual_process"] = {"pid": process.pid, "create_time": process.create_time(),
                "rss_bytes": process.memory_info().rss, "executable": process.exe()}
            runtime_folder = ROOT / "runs" / ("text-session-" + identity["instance_id"])
            requests = []
            for file in runtime_folder.glob("request-*/request.json"):
                saved = json.loads(file.read_text(encoding="utf-8"))
                if saved.get("job_id") == record["job_id"]:
                    requests.append(saved)
            request_ids = {entry["request_id"] for entry in requests}
            events = [json.loads(line) for line in (runtime_folder / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]
            record.update(runtime_directory=str(runtime_folder.relative_to(ROOT)), request_records=requests,
                worker_events=[event for event in events if event.get("request_id") in request_ids],
                runtime_session=json.loads((runtime_folder / "session.json").read_text(encoding="utf-8")))
            save()
        state.update(status="PASS_REAL_API_COLD_WARM_MODEL_REUSE", budget_after=api("/resources/budget"),
            cancellation="CPU ownership/cancellation tests only; no third generation was requested",
            residency_retained="idle timeout remains 60s; subsequent CPU voice requires separate explicit coordinated run")
        save()
        print(json.dumps({"status": state["status"], "artifact": str(out / "actual.json"),
            "identity": first_identity, "seconds": [r["submit_to_terminal_seconds"] for r in state["requests"]]}, ensure_ascii=False))
    except BaseException as exc:
        state.update(status="FAILED", error=f"{type(exc).__name__}: {exc}")
        save()
        raise


if __name__ == "__main__":
    main()
