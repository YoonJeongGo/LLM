"""Register the approved finish-local-tutor scope once, preserving all history."""
from pathlib import Path
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from filelock import FileLock
from edu_tutor.models.budget import status, _execution_allowance, _save

IDENT = "finish-local-tutor-20261028-v1"
REVISION = "finish-local-tutor-20261028-v2"
CAPS = {"gpu_seconds": 28800, "text_requests": 800, "new_audio_clips": 120,
    "vision_requests": 30, "training_experiments": 2,
    "training_per_experiment": {"max_seconds": 7200, "max_optimizer_steps": 600, "max_epochs": 3},
    "download_bytes": 12000000000, "new_text_candidates": 1, "new_tts_candidates": 1}


def register(root):
    root = Path(root).resolve()
    source = root / "docs/source-pack/finish-v2/MASTER_KO.txt"
    if hashlib.sha256(source.read_bytes()).hexdigest() != "7821885b3819413d73a0b1c43420246ebbd3322c490fa21306e8b03ecc544640":
        raise ValueError("Instruction checksum differs; do not infer a replacement authorization")
    with sqlite3.connect((root/".local/tutor.sqlite3").as_uri()+"?mode=ro", uri=True) as db:
        jobs = [json.loads(r[0]) for r in db.execute("SELECT payload FROM jobs")]
    if any(j["state"] not in {"succeeded", "failed", "cancelled", "blocked", "interrupted"} for j in jobs):
        raise ValueError("Active jobs exist; do not change policy")
    policy_path = root / ".local/phase2-policy.json"
    ledger_path = root / "runs/phase2/current/resource-budget.json"
    out = root / "runs/finish-v2/20261028"
    out.mkdir(parents=True, exist_ok=True)
    with FileLock(str(root / ".local/phase2-budget.lock")):
        limits = json.loads(policy_path.read_text(encoding="utf-8"))
        ledger_raw = ledger_path.read_bytes()
        rows = json.loads(ledger_raw)["requests"]
        existing = limits.get("active_execution_allowance") or {}
        if existing.get("id") == IDENT:
            _execution_allowance(limits, rows)
            if existing["limits"] != CAPS:
                raise ValueError("Existing same-scope caps differ; do not replenish or override")
            return {"status": "ALREADY_ACTIVE_NO_CHANGES", "id": IDENT}
        if any(x.get("id") == IDENT for x in limits.get("execution_allowance_history", [])):
            raise ValueError("Same ID exists in history; resume that saved grant explicitly, never register again")
        if any(row["status"] == "reserved" for row in rows):
            raise ValueError("Unfinished reservations exist; inspect before changing active scope")
        baseline = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        grant = {"id": IDENT, "directive_revision": REVISION,
            "baseline_request_count": len(rows), "baseline_requests_sha256": hashlib.sha256(baseline).hexdigest(),
            "limits": CAPS, "runtime_scope": "finish_local_tutor", "accounting": "scope_only_preserve_lifetime",
            "source": source.relative_to(root).as_posix(), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "explicit_request_scope_required": True,
            "note": "One finish-local-tutor authorization; same ID never refills. Historical unused grants do not transfer."}
        record = {"at": datetime.now(timezone.utc).isoformat(), "authorization": grant,
            "previous_active_grant_preserved": existing, "old_scope_time_not_transferred": True,
            "old_lifetime_used": {"requests": len(rows), "seconds": sum(x["charged_seconds"] for x in rows),
                "audio": sum(x["new_audio_clips"] for x in rows), "vision": sum(x["vision_requests"] for x in rows)},
            "policy_before_sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest(),
            "ledger_unchanged_sha256": hashlib.sha256(ledger_raw).hexdigest()}
        if existing:
            limits.setdefault("execution_allowance_history", []).append(existing)
        limits.update(active_execution_allowance=grant, no_new_training=False, no_new_model_download=False)
        _save(out / "authorization.json", record)
        _save(policy_path, limits)
        assert ledger_path.read_bytes() == ledger_raw
    return status(root)


if __name__ == "__main__":
    print(json.dumps(register(Path(__file__).resolve().parents[1]), ensure_ascii=False, indent=2))
