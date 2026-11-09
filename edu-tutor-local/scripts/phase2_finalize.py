"""Read-only preservation and conservative storage inventory for v0.2."""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/phase2/current"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(path):
    path = Path(path)
    result = {"path": str(path), "exists": path.exists(), "bytes": 0, "files": 0,
              "errors": [], "skipped_links": []}
    if path.is_file():
        result.update(bytes=path.stat().st_size, files=1)
        return result
    if not path.exists():
        return result
    pending = [path]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        stat = entry.stat(follow_symlinks=False)
                        if entry.is_symlink() or getattr(stat, "st_file_attributes", 0) & 0x400:
                            result["skipped_links"].append(entry.path)
                        elif entry.is_dir(follow_symlinks=False):
                            pending.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            result["bytes"] += stat.st_size
                            result["files"] += 1
                    except OSError as exc:
                        result["errors"].append({"path": entry.path, "error": str(exc)})
        except OSError as exc:
            result["errors"].append({"path": str(directory), "error": str(exc)})
    return result


def main():
    start = json.loads((OUT / "preservation-start.json").read_text(encoding="utf-8"))
    checks = {}
    with sqlite3.connect((ROOT / ".local/tutor.sqlite3").as_uri() + "?mode=ro", uri=True) as db:
        for table, baseline in start.items():
            if "ids" not in baseline:
                continue
            # Table names originate only from this fixed start inventory.
            assert table in {"messages", "jobs", "photos", "lessons", "evaluation_reviews"}
            rows = db.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
            selected = [row for row in rows if row[0] in baseline["ids"]]
            actual = hashlib.sha256(json.dumps(selected, ensure_ascii=False).encode()).hexdigest()
            checks[table] = {"original_count": baseline["count"], "preserved_count": len(selected),
                "current_total": len(rows), "sha256": actual,
                "byte_identical_original_rows": actual == baseline["sha256"]}
        jobs = [json.loads(row[0]) for row in db.execute("SELECT payload FROM jobs")]
        training = [job for job in jobs if job.get("kind") in {"train", "training"}]
    original = start["preserved_original_source"]
    checks["original_source_zip"] = {"path": original["path"], "sha256": digest(Path(original["path"]))}
    checks["original_source_zip"]["unchanged"] = checks["original_source_zip"]["sha256"] == original["sha256"]
    checks["training_job_ids"] = [job["id"] for job in training]
    checks["checked_at"] = datetime.now(timezone.utc).isoformat()
    (OUT / "preservation-final.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")

    previous = json.loads((OUT / "storage-verified-start.json").read_text(encoding="utf-8"))
    parts = [inventory(path) for path in sorted(ROOT.iterdir())]
    external_paths = [Path(item["path"]) for item in previous["external_inventory"]]
    # The source attachments and v0.2 extracted material also belong to the task.
    external_paths += [(Path.home() / "Desktop/edu_tutor_codex_pack.zip"),
                      (Path.home() / "Desktop/edu_tutor_next_v02.zip")]
    external = [inventory(path) for path in dict.fromkeys(external_paths)]
    total = sum(item["bytes"] for item in parts + external)
    storage = {"timestamp": datetime.now(timezone.utc).isoformat(), "root": str(ROOT),
        "data_root": str(ROOT / ".local"), "unit": "decimal GB = 1000000000 bytes",
        "project_parts": parts, "external_inventory": external,
        "project_bytes": sum(item["bytes"] for item in parts), "conservative_total_bytes": total,
        "conservative_total_GB": total / 1e9, "disk_C": shutil.disk_usage("C:/")._asdict(),
        "disk_D": shutil.disk_usage("D:/")._asdict(), "F_exists": Path("F:/").exists(),
        "shared_attribution": "Whole shared pip cache and base Python included; exact task-only share unknown. No unrelated user temp scan. Project temp is inside .local and counted.",
        "under_50GB": total <= 50_000_000_000, "warning_40GB": total >= 40_000_000_000,
        "C_free_at_least_50GB": shutil.disk_usage("C:/").free >= 50_000_000_000,
        "inventory_complete": not any(item["errors"] for item in parts + external)}
    (OUT / "storage-final.json").write_text(json.dumps(storage, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"original_records_unchanged": all(value["byte_identical_original_rows"] for value in checks.values() if isinstance(value, dict) and "byte_identical_original_rows" in value),
        "original_source_unchanged": checks["original_source_zip"]["unchanged"],
        "training_jobs": len(training), "storage_GB": total / 1e9,
        "C_free_GB": storage["disk_C"]["free"] / 1e9, "complete": storage["inventory_complete"]}))


if __name__ == "__main__":
    main()
