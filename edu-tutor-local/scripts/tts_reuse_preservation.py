"""Read-only preservation audit after the bounded TTS comparison; no models."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/student-latency/20261027/tts-worker-reuse"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main():
    before = read(OUT / "before.json")
    old_status = read(OUT / "before-STATUS.json")
    current_status = read(ROOT / "STATUS.json")
    old_ledger = read(OUT / "before-resource-budget.json")
    ledger = read(ROOT / "runs/phase2/current/resource-budget.json")
    old_policy = read(OUT / "before-phase2-policy.json")
    policy = read(ROOT / ".local/phase2-policy.json")
    changed = [p for p, h in before["files"].items() if digest(ROOT / p) != h]
    # Historical evidence, WAVs, original E and its completed recovery stay exact.
    protected = [p for p in before["files"]
                 if (p.startswith("runs/") or p.startswith(".local/audio/"))
                 and p != "runs/phase2/current/resource-budget.json"]
    bad_protected = [p for p in changed if p in protected]
    db_changed, added = [], {}
    with sqlite3.connect((ROOT / ".local/tutor.sqlite3").as_uri() + "?mode=ro", uri=True) as db:
        for table, rows in before["database_row_hashes"].items():
            now = {r[0]: hashlib.sha256(json.dumps(r, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
                   for r in db.execute('SELECT * FROM "' + table + '"')}
            db_changed.extend(table + ":" + key for key, value in rows.items() if now.get(key) != value)
            added[table] = [key for key in now if key not in rows]
        jobs = [json.loads(r[0]) for r in db.execute("SELECT payload FROM jobs")]
    model_changed = []
    for path, original in before["model_file_metadata"].items():
        p = ROOT / path
        if not p.is_file() or {"bytes": p.stat().st_size, "mtime_ns": p.stat().st_mtime_ns} != original:
            model_changed.append(path)
    untouched_limits = {key: policy.get(key) == value for key, value in old_policy.items()
                        if key not in {"new_audio_clips", "active_execution_allowance", "execution_allowance_history"}}
    source_at_run = read(OUT / "actual-source-snapshot.json")
    modified_after_attempt = [p for p, h in source_at_run["files"].items() if digest(ROOT / p) != h]
    checks = {
        "old_database_rows_unchanged": not db_changed,
        "old_evidence_and_audio_unchanged": not bad_protected,
        "model_files_size_mtime_unchanged": not model_changed,
        "old_128_budget_rows_exact": ledger["requests"][:128] == old_ledger["requests"],
        "original_E_recovery_status_exact": current_status["conditional_aggregate_recovery"] == old_status["conditional_aggregate_recovery"],
        "original_E_failure_status_exact": current_status["limited_new_lesson"] == old_status["limited_new_lesson"],
        "readiness_audit_not_regraded": current_status["product_readiness"] == old_status["product_readiness"],
        "limits_not_reset": all(untouched_limits.values()),
        "old_grant_preserved_in_history": old_policy["active_execution_allowance"] in policy["execution_allowance_history"],
        "global_audio_only_raised_by_two": policy["new_audio_clips"] == old_policy["new_audio_clips"] + 2,
        "no_active_jobs": not any(j["state"] not in {"succeeded", "failed", "cancelled", "blocked", "interrupted"} for j in jobs),
        "no_reserved_budget_rows": not any(r["status"] == "reserved" for r in ledger["requests"]),
    }
    result = {"at": datetime.now(timezone.utc).isoformat(), "checks": checks,
        "all_passed": all(checks.values()),
        "baseline_file_count": len(before["files"]), "protected_file_count": len(protected),
        "original_database_rows": sum(len(rows) for rows in before["database_row_hashes"].values()),
        "changed_original_database_rows": db_changed, "added_database_rows": added,
        "changed_protected_files": bad_protected, "changed_model_file_metadata": model_changed,
        "changed_baseline_files": changed, "new_budget_rows": ledger["requests"][128:],
        "modified_after_actual_attempt": modified_after_attempt,
        "actual_attempt_source_archive": "source-at-failed-run.zip",
        "post_attempt_validation_boundary": "Any later edits are CPU-validated only; the failed real attempt is never relabeled.",
        "limits_checks": untouched_limits}
    (OUT / "preservation-final.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"all_passed": result["all_passed"], "checks": checks,
        "changed_original_database_rows": db_changed, "changed_protected_files": bad_protected,
        "added_database_rows": added, "modified_after_actual_attempt": modified_after_attempt}, ensure_ascii=False))
    if not result["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
