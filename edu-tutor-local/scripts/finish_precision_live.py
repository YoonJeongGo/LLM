"""Bounded precision screening. Default preparation performs no API/model calls.

Two batches, two identical prompts each, no retries or hidden warmup. Run with
--execute only after the coordinator's explicit GPU GO and server restart.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from finish_education_live import (Client, ROOT, SCOPE, TERMINAL, await_job,
                                   digest, result_of, save, stamp, submit_once)

PROPOSAL = Path("runs/finish-v2/20261029/precision-proposal")
SOURCES = ("src/edu_tutor/models/worker.py", "src/edu_tutor/models/evaluate.py",
           "src/edu_tutor/models/runtime.py", "src/edu_tutor/api/admin.py",
           "src/edu_tutor/models/budget.py", "src/edu_tutor/models/registry.py",
           "src/edu_tutor/jobs/manager.py", "scripts/finish_precision_live.py",
           ".local/models/text/model-manifest.json", ".local/models/text/config.json")
TIMING_NOTICE = ("generation_seconds measures model.generate plus CUDA synchronization, "
                 "excluding tensor-to-list conversion and text decoding. Older student/evaluation "
                 "timers had different boundaries. This is raw-model screening, not student "
                 "question-to-explanation latency or educational accuracy.")


def inputs(root=ROOT):
    protocol = json.loads((root / PROPOSAL / "protocol.json").read_text(encoding="utf-8"))
    if (protocol["precision_order"] != ["nf4", "bf16"] or protocol["max_new_tokens"] != 128
            or protocol["adapter"] != "base" or protocol["attempted_text_generations_max"] != 4):
        raise ValueError("Protocol differs from the reviewed four-generation screening")
    bodies = []
    for precision in protocol["precision_order"]:
        bodies.append({"adapter": "base", "precision": precision, "max_new_tokens": 128,
                       "items": [{"id": precision + "-" + phase,
                                  "messages": protocol["same_messages_in_each_item"]}
                                 for phase in protocol["items_per_precision"]]})
    if any(len(body["items"]) != 2 for body in bodies):
        raise ValueError("Exactly two generations per precision are allowed")
    return protocol, bodies


def source_hashes(root):
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in SOURCES}


def gpu_snapshot():
    query = "name,memory.total,memory.used,memory.free,utilization.gpu,pstate,clocks.sm,clocks.mem,power.draw,temperature.gpu"
    try:
        process = subprocess.run(["nvidia-smi", "--query-gpu=" + query, "--format=csv"],
                                 capture_output=True, text=True, timeout=10,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return {"at": stamp(), "returncode": process.returncode,
                "stdout": process.stdout, "stderr": process.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"at": stamp(), "unavailable": str(exc)}


def preflight(client, protocol, needed):
    budget = client.preflight("text", needed)
    if budget.get("accounting_scope") != SCOPE:
        raise RuntimeError("Explicit scope accounting is not effective")
    if budget["active_execution_allowance"].get("seconds_remaining", 0) <= 12:
        raise RuntimeError("Insufficient scoped time after the existing cleanup reserve")
    model = client.call("/api/models")
    speech = client.call("/api/tts/session")
    if model.get("resident") or speech.get("resident"):
        raise RuntimeError("Resident text/TTS worker must be closed by its owner before this screening")
    if (not model.get("ready") or model.get("model_id") != protocol["model_id"]
            or model.get("revision") != protocol["base_revision"]):
        raise RuntimeError("Installed base model identity/readiness differs")
    schema = client.call("/api/openapi.json")
    precision = schema.get("components", {}).get("schemas", {}).get("TextBatchInput", {}).get("properties", {}).get("precision", {})
    if set(precision.get("enum", [])) != {"nf4", "bf16"} or precision.get("default") != "nf4":
        raise RuntimeError("Server has not loaded the reviewed precision API")
    return {"budget": budget, "model": model, "tts_session": speech, "gpu": gpu_snapshot()}


def check_result(job, raw, body, protocol):
    """Require actual identity and reuse evidence, retaining failures as failures."""
    if job.get("state") != "succeeded" or raw.get("status") != "completed":
        raise RuntimeError("Batch failed/incomplete; no retry or next precision is allowed")
    rows = raw.get("items", [])
    if [row.get("id") for row in rows] != [item["id"] for item in body["items"]]:
        raise RuntimeError("Actual result IDs/count differ")
    if [row.get("model_load_count") for row in rows] != [1, 0]:
        raise RuntimeError("Cold/warm load counts must be 1 then 0")
    if any(not rows[0].get(key) or rows[0][key] != rows[1].get(key)
           for key in ("worker_pid", "model_object_id")):
        raise RuntimeError("Warm result did not prove identical worker/model instance")
    summaries = []
    for index, row in enumerate(rows):
        actual = row.get("inference", {})
        precision = body["precision"]
        if (row.get("precision") != precision or actual.get("requested_precision") != precision
                or actual.get("actual_is_loaded_in_4bit") is not (precision == "nf4")
                or actual.get("actual_parameter_devices") != ["cuda:0"]
                or actual.get("load_dtype") != "torch.bfloat16"
                or actual.get("unique_parameter_storage_bytes", 0) <= 0):
            raise RuntimeError("Requested and actual device/precision/storage contradict")
        if precision == "bf16" and set(actual.get("actual_parameter_dtypes_elements", {})) != {"torch.bfloat16"}:
            raise RuntimeError("BF16 parameters include another dtype; record before interpreting")
        if (row.get("revision") != protocol["base_revision"] or row.get("max_new_tokens") != 128
                or row.get("output_tokens", 0) <= 0 or row.get("finish_reason") not in {"eos", "length"}):
            raise RuntimeError("Actual base/revision/token limit/output is invalid")
        phases = row.get("phase_timing", {})
        seconds = phases.get("generation_seconds", 0)
        if seconds <= 0 or row.get("latency_seconds") != seconds:
            raise RuntimeError("Generation timing is missing or inconsistent")
        if index and (row.get("model_load_seconds") != 0
                      or any(phases.get(key) != 0 for key in ("runtime_import_seconds", "loader_import_seconds", "load_excluding_loader_import_seconds"))):
            raise RuntimeError("Warm result reports new imports/load")
        summaries.append({"id": row["id"], "precision": precision,
                          "phase": "cold_first_generation" if index == 0 else "warm_second_generation",
                          "worker_pid": row["worker_pid"], "model_object_id": row["model_object_id"],
                          "input_tokens": row.get("input_tokens"), "output_tokens": row["output_tokens"],
                          "finish_reason": row["finish_reason"], "phase_timing": phases,
                          "generation_tokens_per_second": row["output_tokens"] / seconds,
                          "memory": row.get("memory"), "inference": actual,
                          "raw_text": row.get("text", "")})
    return summaries


def run(name, *, execute=False, root=ROOT, client_factory=Client):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", name):
        raise ValueError("Use a simple unique run name")
    root = Path(root)
    folder = root / "runs/finish-v2/20261029" / name
    if folder.exists():
        raise ValueError("Evidence directory already exists; no automatic rerun/overwrite")
    protocol, bodies = inputs(root)
    folder.mkdir(parents=True)
    report = {"status": "prepared", "created_at": stamp(), "protocol": protocol,
              "prompt_sha256": digest(protocol["same_messages_in_each_item"]),
              "timing_notice": TIMING_NOTICE, "batches": [], "human_review": "H_PENDING",
              "product_readiness": "NOT_READY", "model_calls_submitted": 0,
              "generation_attempts_requested_upper_bound": 0,
              "attempt_count_notice": "Acknowledged submissions are not confirmed generations. An ambiguous POST can have started work; the preserved server budget ledger is authoritative."}
    save(folder / "protocol.json", protocol)
    for body in bodies:
        save(folder / (body["precision"] + "-request.json"), body)
    save(folder / "result.json", report)
    if not execute:
        return report
    client = client_factory(root)
    owned_jobs = []
    started = time.perf_counter()
    try:
        report.update(status="running", started_at=stamp(), source_hashes=source_hashes(root),
                      packages={key: importlib.metadata.version(key) for key in
                                ("torch", "transformers", "bitsandbytes", "accelerate")})
        for index, body in enumerate(bodies):
            if source_hashes(root) != report["source_hashes"]:
                raise RuntimeError("Source changed between precision batches; stop without another call")
            state = preflight(client, protocol, 4 if index == 0 else 2)
            batch = folder / body["precision"]
            batch.mkdir()
            save(batch / "before.json", state)
            # Persist the possible attempt before POST; a lost response must not
            # appear to authorize another uncounted pair of generations.
            report["generation_attempts_requested_upper_bound"] += 2
            save(folder / "result.json", report)
            journal = submit_once(client, batch, protocol["endpoint"], body, "evaluation", execute=True)
            owned_jobs.append(journal["job_id"])
            report["model_calls_submitted"] += 2
            save(folder / "result.json", report)
            job = await_job(client, batch, journal, 315)
            raw = result_of(job, root)
            save(batch / "raw-result.json", raw)
            after = {"budget": client.call("/api/resources/budget"), "gpu": gpu_snapshot()}
            save(batch / "after.json", after)
            entry = {"precision": body["precision"], "job_id": journal["job_id"],
                     "job_state": job["state"], "artifact": job.get("artifact"),
                     "worker_exit_evidence": ("API succeeded requires _run_worker done event, waited process exit=0; code-enforced, not a separate OS exit observation"
                                              if job["state"] == "succeeded" else "Successful exit not confirmed; inspect preserved failure"),
                     "before": state["budget"], "after": after["budget"]}
            report["batches"].append(entry)
            entry["items"] = check_result(job, raw, body, protocol)
            save(folder / "result.json", report)
        report["status"] = "completed_screening_only"
    except BaseException as exc:
        report.update(status="stopped_preserved_no_retry", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        report.update(finished_at=stamp(), client_elapsed_seconds=time.perf_counter() - started)
        try:
            jobs = client.call("/api/jobs")
            for job in jobs:
                if job["id"] in owned_jobs and job["state"] not in TERMINAL:
                    cancelled = client.call("/api/jobs/" + job["id"] + "/cancel", {})
                    save(folder / ("cancel-" + job["id"] + ".json"), cancelled)
            report["final_budget"] = client.call("/api/resources/budget")
        except Exception as exc:
            report["cleanup_observation_error"] = str(exc)
        save(folder / "result.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--execute", action="store_true")
    arguments = parser.parse_args()
    result = run(arguments.name, execute=arguments.execute)
    print(json.dumps({"status": result["status"], "model_calls_submitted": result["model_calls_submitted"],
                      "batches": len(result["batches"])}, ensure_ascii=False))
