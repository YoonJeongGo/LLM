"""Read-only DB/file audit; write only a new student-experience report.

Run again after live verification quiesces. Concurrent DB and ledger activity is
reported as a bounded snapshot, not an atomic cross-system transaction.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3


TABLES = {"sessions", "messages", "jobs", "documents", "chunks", "photos", "lessons",
          "datasets", "audit", "evaluation_reviews"}
FORBIDDEN_KINDS = {"train", "training", "download", "model_download", "download_model"}
BUDGET_PATH = "runs/phase2/current/resource-budget.json"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def file_checks(root, manifest, *, skip_budget=False):
    rows = []
    for name, expected in manifest.items():
        path = root / name
        budget = name.replace("\\", "/") == BUDGET_PATH
        if budget and skip_budget:
            rows.append({"path": name, "check": "authorized_append_only_ledger_checked_separately",
                         "baseline_sha256": expected})
            continue
        try:
            current = sha(path)
            rows.append({"path": name, "baseline_sha256": expected,
                         "current_sha256": current, "unchanged": current == expected})
        except OSError as exc:
            rows.append({"path": name, "baseline_sha256": expected, "unchanged": False,
                         "error": str(exc)})
    return rows


def source_markers(root):
    expected = {
        "src/edu_tutor/models/runtime.py": ["HF_HUB_OFFLINE=\"1\"", "TRANSFORMERS_OFFLINE=\"1\"", "HF_HUB_DISABLE_TELEMETRY=\"1\""],
        "src/edu_tutor/models/worker.py": ["local_files_only=True", "is_trainable=False"],
        "src/edu_tutor/models/vision_runtime.py": ["local_files_only=True", "trust_remote_code=False"],
        "src/edu_tutor/speech/provider.py": ["local_files_only=True"],
        "src/edu_tutor/training/runner.py": ["if policy(project).get(\"enabled\")"],
        "src/edu_tutor/api/admin.py": ["if policy(root).get(\"enabled\")"],
    }
    result = {}
    for rel, markers in expected.items():
        path = root / rel
        lines = path.read_text(encoding="utf-8").splitlines()
        result[rel] = {"sha256": sha(path), "markers": {
            marker: [i for i, line in enumerate(lines, 1) if marker in line] for marker in markers}}
    return result


def model_metadata(root, baseline_time):
    folder = root / ".local/models"
    result = {"root": str(folder), "files": 0, "bytes": 0,
              "modified_since_baseline": [], "errors": [], "skipped_links": [],
              "scope": "Filesystem modification metadata only; no pre-task full model-content manifest exists here."}
    for directory, dirs, files in os.walk(folder, followlinks=False):
        retained = []
        for name in dirs:
            path = Path(directory, name)
            if path.is_symlink() or path.is_junction():
                result["skipped_links"].append(str(path.relative_to(root)))
            else:
                retained.append(name)
        dirs[:] = retained
        for name in files:
            path = Path(directory, name)
            try:
                stat = path.stat(follow_symlinks=False)
                result["files"] += 1
                result["bytes"] += stat.st_size
                if stat.st_mtime >= baseline_time.timestamp():
                    result["modified_since_baseline"].append({"path": str(path.relative_to(root)),
                        "bytes": stat.st_size, "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                        "classification": "mutable_load_metadata_written_by_models_worker" if path.name == "runtime-structure.json"
                            else "model_or_cache_file_modification_requires_review"})
            except OSError as exc:
                result["errors"].append({"path": str(path.relative_to(root)), "error": str(exc)})
    return result


def audit(root, out):
    started = datetime.now(timezone.utc).isoformat()
    folder = root / "runs/student-experience/20261027"
    baseline_path = folder / "preservation-start.json"
    authorization_path = folder / "additional-authorization.json"
    baseline = read(baseline_path)
    authorization = read(authorization_path)
    checks, new_jobs, new_audit = {}, [], []
    # Never instantiate Store: its constructor performs schema/WAL writes.
    uri = (root / ".local/tutor.sqlite3").as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=15) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        for table, expected in baseline["tables"].items():
            if table not in TABLES:
                raise ValueError("Unexpected baseline table: " + table)
            rows = db.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
            old_ids = set(expected["ids"])
            original = [row for row in rows if row[0] in old_ids]
            added = [row for row in rows if row[0] not in old_ids]
            # Use exactly the serialization used by the starting snapshot.
            digest = hashlib.sha256(json.dumps(original, ensure_ascii=False).encode()).hexdigest()
            missing = sorted(old_ids - {row[0] for row in original})
            unchanged = digest == expected["sha256"] and not missing
            checks[table] = {"baseline_count": expected["count"], "current_count": len(rows),
                "original_count_present": len(original), "missing_original_ids": missing,
                "original_ids_preserved": not missing, "baseline_original_sha256": expected["sha256"],
                "current_original_sha256": digest, "original_rows_byte_identical": unchanged,
                "new_count": len(added), "new_ids": [row[0] for row in added],
                "classification": "originals_unchanged_with_appended_records" if unchanged and added else
                    "originals_unchanged" if unchanged else "original_content_or_ID_change_requires_review"}
            if table == "jobs":
                new_jobs = [json.loads(row[-1]) for row in added]
            if table == "audit":
                new_audit = [json.loads(row[-1]) for row in added]
        db_snapshot_end = datetime.now(timezone.utc).isoformat()
    frozen = file_checks(root, baseline["frozen_neural_files"])
    evidence = file_checks(root, baseline["evidence_hashes"], skip_budget=True)
    # The producer atomically replaces the complete JSON. Reading it does not
    # create a lock file or mutate the producer's resource ledger.
    ledger = read(root / BUDGET_PATH)
    policy = read(root / ".local/phase2-policy.json")
    before_requests = authorization["baseline_requests"]
    before_count = authorization["baseline_request_count"]
    prefix = ledger["requests"][:before_count]
    prefix_same = canonical(prefix) == canonical(before_requests)
    new_requests = ledger["requests"][before_count:]
    expected_budget_hash = baseline["evidence_hashes"].get(BUDGET_PATH.replace("/", "\\"))
    changed_policy = {key: {"before": authorization["policy_before"].get(key), "after": value}
                      for key, value in authorization["policy_after"].items()
                      if authorization["policy_before"].get(key) != value}
    totals = {"gpu_seconds": sum(row["charged_seconds"] for row in ledger["requests"]),
              "new_audio_clips": sum(row["new_audio_clips"] for row in ledger["requests"]),
              "vision_requests": sum(row["vision_requests"] for row in ledger["requests"])}
    ledger_checks = {
        "authorization_record": str(authorization_path.relative_to(root)),
        "authorization_record_sha256": sha(authorization_path),
        "authorization_record_authority": authorization["authority"],
        "baseline_ledger_hash_matches_start": expected_budget_hash == authorization["baseline_ledger_sha256"],
        "baseline_request_count_consistent": before_count == len(before_requests) == baseline["budget"]["requests"],
        "baseline_request_prefix_exact_json": prefix_same,
        "prefix_sha256": hashlib.sha256(canonical(prefix).encode()).hexdigest(),
        "expected_prefix_sha256": hashlib.sha256(canonical(before_requests).encode()).hexdigest(),
        "prefix_comparison": "Exact canonical JSON including numeric representation, all fields, order and IDs; no dropped fields.",
        "new_requests": new_requests, "new_request_count": len(new_requests),
        "request_ids_unique": len({row["id"] for row in ledger["requests"]}) == len(ledger["requests"]),
        "policy_changed_keys": changed_policy,
        "authorized_policy_changes_only": set(changed_policy) <= {"new_audio_clips", "vision_requests"},
        "authorized_cap_arithmetic_matches": (
            authorization["policy_after"]["new_audio_clips"] == authorization["baseline_audio_attempts"] + authorization["additional_caps"]["new_audio_clips"]
            and authorization["policy_after"]["vision_requests"] == authorization["baseline_vision_attempts"] + authorization["additional_caps"]["vision_requests"]),
        "policy_matches_authorized_after": canonical(policy) == canonical(authorization["policy_after"]),
        "ledger_limits_match_current_policy": canonical(ledger.get("limits")) == canonical(policy),
        "restricted_flags_active": policy.get("enabled") is True and policy.get("no_new_training") is True and policy.get("no_new_model_download") is True,
        "totals": totals, "remaining": {key: policy[key]-value for key,value in totals.items()},
        "totals_within_limits": all(value <= policy[key] for key,value in totals.items()),
        "new_request_duration_caps_unchanged": all(0 < row["request_limit_seconds"] <= 300 for row in new_requests),
        "unfinished_reservations": [row["id"] for row in new_requests if row["status"] == "reserved"],
        "storage_estimate_bytes": ledger.get("storage_estimate_bytes"),
        "storage_warning": ledger.get("storage_warning"),
    }
    forbidden_jobs = [{k: job.get(k) for k in ("id", "kind", "state", "created_at")}
                      for job in new_jobs if job.get("kind") in FORBIDDEN_KINDS]
    forbidden_requests = [row for row in new_requests if row.get("kind") in FORBIDDEN_KINDS]
    c_free = shutil.disk_usage("C:/").free
    failures = []
    if not all(item["original_rows_byte_identical"] for item in checks.values()): failures.append("original_database_rows_changed")
    if not all(item["unchanged"] for item in frozen): failures.append("frozen_neural_files_changed")
    if not all(item.get("unchanged", True) for item in evidence): failures.append("original_immutable_evidence_changed")
    for name in ("baseline_ledger_hash_matches_start", "baseline_request_count_consistent", "baseline_request_prefix_exact_json",
                 "request_ids_unique", "authorized_policy_changes_only", "authorized_cap_arithmetic_matches", "policy_matches_authorized_after", "ledger_limits_match_current_policy",
                 "restricted_flags_active", "totals_within_limits", "new_request_duration_caps_unchanged"):
        if not ledger_checks[name]: failures.append(name)
    if forbidden_jobs or forbidden_requests: failures.append("recorded_new_training_or_download")
    result = {
        "started_at": started, "database_snapshot_ended_at": db_snapshot_end,
        "finished_at": datetime.now(timezone.utc).isoformat(), "root": str(root),
        "baseline": str(baseline_path.relative_to(root)), "baseline_sha256": sha(baseline_path),
        "scope": "Read-only SQL mode=ro/query_only plus existing file hashes. Only the output report is written.",
        "status": "PASS_AT_SNAPSHOT" if not failures else "REVIEW_REQUIRED", "failures": failures,
        "database": checks, "frozen_neural_files": frozen, "existing_evidence_files": evidence,
        "evidence_counts": {"baseline_total": len(evidence), "immutable_checked": sum("unchanged" in row for row in evidence),
                            "authorized_mutable_ledger": 1, "frozen_neural_source": len(frozen)},
        "resource_ledger": ledger_checks,
        "new_job_kind_counts": dict(Counter(job.get("kind", "unknown") for job in new_jobs)),
        "new_jobs": [{k: job.get(k) for k in ("id", "kind", "state", "created_at", "session_id")} for job in new_jobs],
        "new_audit_records": [{k: item.get(k) for k in ("id", "action", "entity_id", "created_at")} for item in new_audit],
        "no_new_training_download_evidence": {"forbidden_new_jobs": forbidden_jobs, "forbidden_new_ledger_requests": forbidden_requests,
            "model_files": model_metadata(root, datetime.fromisoformat(baseline["timestamp"])),
            "source_offline_and_training_guards": source_markers(root)},
        "C_free_bytes": c_free, "C_free_meets_existing_cap": c_free >= policy["min_C_free_bytes"],
        "external_or_paid_calls": {"status": "no_new_recorded_remote_or_paid_model_work_in_audited_paths",
            "evidence": "Recorded model jobs use existing local/offline workers; this audit makes no network calls.",
            "limitation": "No OS-wide network capture or billing access. These records cannot prove that no unrelated process or unrecorded external transfer occurred."},
        "limitations": [
            "Root may be running new verification while this snapshot is read; rerun after jobs finish.",
            "Original DB comparison includes every column and original payload byte string; new IDs are separately reported.",
            "Baseline has an aggregate per table, so a mismatch proves change but cannot identify changed fields without a full prior DB copy.",
            "Storage estimate is the existing budget ledger's estimate, not a fresh full project-plus-external dependency inventory.",
            "models/*/runtime-structure.json is mutable load metadata (models/worker.py), distinct from frozen neural source and historical evidence files.",
            "No model inference, training, download, audio generation or UI validation was performed by this audit.",
        ],
    }
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("runs/student-experience/20261027/preservation-interim.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    out = (root / args.output).resolve()
    if not out.is_relative_to(root / "runs/student-experience") or out.name in {"preservation-start.json", "additional-authorization.json"}:
        raise ValueError("Output must be a separate student-experience report, never a baseline/authorization file.")
    report = audit(root, out)
    print(json.dumps({"status": report["status"], "failures": report["failures"],
        "original_rows": sum(value["original_count_present"] for value in report["database"].values()),
        "new_rows": sum(value["new_count"] for value in report["database"].values()),
        "evidence_counts": report["evidence_counts"],
        "budget_prefix_identical": report["resource_ledger"]["baseline_request_prefix_exact_json"],
        "new_job_kinds": report["new_job_kind_counts"], "report": str(out)}, ensure_ascii=False))
