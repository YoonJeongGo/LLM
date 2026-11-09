"""Read-only live worker status. Artifact paths are server-issued and bounded."""
from __future__ import annotations

import json
import math
from pathlib import Path


def active_gpu_lease(local: Path):
    file = Path(local) / "gpu-lease.json"
    if not file.is_file():
        return {"active": False, "state": "not_acquired", "verification": "no_lease_metadata"}
    try:
        value = json.loads(file.read_text(encoding="utf-8"))
        result = {key: value.get(key) for key in ("job_id", "pid", "process_start", "device", "heartbeat", "state")}
        if result["state"] != "held":
            return {**result, "active": False, "verification": "released"}
        import psutil
        try:
            process = psutil.Process(int(result["pid"]))
            actual_start = process.create_time()
            recorded = result["process_start"]
            if recorded is None:
                return {**result, "active": None, "verification": "missing_process_start_identity"}
            matches = abs(float(recorded) - actual_start) < .01
            return {**result, "active": matches and process.is_running(),
                    "verification": "pid_and_start_verified" if matches else "stale_pid_reused"}
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return {**result, "active": False, "verification": "owner_exited"}
        except psutil.AccessDenied:
            return {**result, "active": None, "verification": "owner_identity_access_denied"}
    except (OSError, ValueError, TypeError, ImportError):
        return {"active": None, "verification": "lease_metadata_unavailable"}


def job_view(root: Path, job: dict):
    value = dict(job)
    if job.get("kind") != "training" or not job.get("artifact"):
        return value
    root = Path(root).resolve()
    runs = (root / "runs").resolve()
    folder = (root / job["artifact"]).resolve()
    if not runs.is_relative_to(root) or not folder.is_relative_to(runs) or folder == runs:
        return {**value, "metrics_error": "Invalid training artifact path"}
    phase_file = (folder / "phase.json").resolve()
    if phase_file.parent == folder and phase_file.is_file() and phase_file.stat().st_size <= 4096:
        try:
            phase = json.loads(phase_file.read_text(encoding="utf-8"))
            if phase.get("phase") in {"loading", "training", "saving", "saved", "reloading"}:
                value["worker_phase"] = phase["phase"]
                value["worker_reason"] = str(phase.get("reason", ""))[:300]
        except (ValueError, OSError, TypeError):
            pass
    metrics = (folder / "metrics.jsonl").resolve()
    if metrics.parent != folder or not metrics.is_file():
        return value
    allowed = {"timestamp", "step", "max_steps", "loss", "learning_rate", "grad_norm", "epoch", "elapsed_seconds",
               "current_vram_bytes", "peak_vram_bytes", "actual_microbatches", "samples_processed", "samples_per_second"}
    records = []
    try:
        with metrics.open("rb") as handle:
            size = metrics.stat().st_size
            handle.seek(max(0, size - 64 * 1024))
            lines = handle.read(64 * 1024).decode("utf-8", errors="replace").splitlines()
        for line in lines[-200:]:
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    continue
                clean = {}
                for key in allowed:
                    item = record.get(key)
                    if key == "timestamp" and isinstance(item, str):
                        clean[key] = item[:100]
                    elif isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item):
                        clean[key] = item
                if "step" in clean:
                    records.append(clean)
            except (ValueError, TypeError, OverflowError):
                continue  # Last writer line may be partial while training continues.
    except OSError:
        return value
    if records:
        latest = records[-1]
        value.update(metrics=records, latest_metrics=latest, metrics_source=str(metrics.relative_to(root)))
        if latest.get("max_steps", 0) > 0 and value["state"] not in {"failed", "cancelled", "interrupted", "blocked"}:
            value["progress"] = max(0, min(1, latest["step"] / latest["max_steps"]))
    return value
