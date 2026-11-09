"""Final read-only preservation audit, with an explicit mutation allowlist."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/student-latency/20261027/condition-recovery"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    before = read(OUT / "before.json")
    old_ledger = read(OUT / "before-resource-budget.json")
    ledger = read(ROOT / "runs/phase2/current/resource-budget.json")
    actual = read(OUT / "actual.json")
    source = read(OUT / "actual-source-snapshot.json")
    status = read(ROOT / "STATUS.json")
    old_status = read(OUT / "before-STATUS.json")
    expected = {"src/edu_tutor/problems/evidence.py", "src/edu_tutor/lessons/verified.py", "src/edu_tutor/api/app.py",
        "web/src/App.tsx", "web/tests/student-fixture.spec.ts", "runs/student-experience/20261027/index.html",
        "runs/phase2/current/resource-budget.json", "STATUS.json", "HANDOFF.md", "docs/PROGRESS_BRIEFING.md", "docs/CHATGPT_HANDOFF.md"}
    changed = [name for name, sha in before["files"].items() if not (ROOT/name).is_file() or digest(ROOT/name) != sha]
    tables = {}
    with sqlite3.connect((ROOT / ".local/tutor.sqlite3").as_uri()+"?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        for name, old in before["database_row_hashes"].items():
            now = {r[0]: hashlib.sha256(json.dumps(r, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
                   for r in db.execute(f"SELECT * FROM {name}")}
            tables[name] = {"old_rows": len(old), "now_rows": len(now), "added_rows": len(now)-len(old),
                "changed_or_missing_old_ids": [i for i, sha in old.items() if now.get(i) != sha]}
        active_jobs = [j for (payload,) in db.execute("SELECT payload FROM jobs")
                       if (j := json.loads(payload))["state"] not in {"succeeded", "failed", "cancelled", "blocked", "interrupted"}]
    model_meta = {}
    for p in (ROOT / ".local/models").rglob("*"):
        if p.is_file():
            stat = p.stat()
            model_meta[p.relative_to(ROOT).as_posix()] = {"bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    new_requests = ledger["requests"][len(old_ledger["requests"]):]
    new_audio_ids = {x["audio_id"] for x in read(OUT / "audio-manifest.json")}
    old_audio_integrity = []
    for meta in (ROOT / ".local/audio").glob("*.json"):
        if meta.stem in new_audio_ids:
            continue
        value = read(meta); wav = meta.with_suffix(".wav")
        old_audio_integrity.append({"audio_id": meta.stem, "wav_exists": wav.is_file(),
            "checksum_matches_saved_metadata": wav.is_file() and digest(wav) == value.get("checksum")})
    archived_audio = []
    for clip in read(ROOT / "runs/student-experience/20261027/manifest.json")["audio"]:
        wav = Path(clip["source_wav"]); meta = wav.with_suffix(".json")
        archived_audio.append({"audio_id": clip["audio_id"], "wav_matches_prior_manifest": digest(wav) == clip["wav_sha256"],
                               "metadata_matches_prior_manifest": digest(meta) == clip["original_json_sha256"]})
    checks = {
        "only_allowlisted_existing_files_changed": set(changed) <= expected,
        "all_460_original_database_rows_exact": all(not v["changed_or_missing_old_ids"] for v in tables.values()),
        "only_five_new_records": sum(v["added_rows"] for v in tables.values()) == 5,
        "historical_126_requests_exact": ledger["requests"][:len(old_ledger["requests"])] == old_ledger["requests"],
        "only_two_successful_scoped_speech_attempts": len(new_requests) == 2 and all(r["kind"] == "speech_batch" and r["status"] == "completed"
            and r["new_audio_clips"] == 1 and r["vision_requests"] == 0 and r["execution_allowance_id"] == "20261027-new-text1-tts2" for r in new_requests),
        "policy_bytes_unchanged_no_new_grant": digest(ROOT / ".local/phase2-policy.json") == digest(OUT / "before-phase2-policy.json"),
        "no_unfinished_jobs_or_reservations": not active_jobs and all(r["status"] != "reserved" for r in ledger["requests"]),
        "model_file_metadata_exact": model_meta == before["model_file_metadata"],
        "source_and_bundle_match_actual": all(digest(ROOT/name) == sha for name, sha in source["files"].items()),
        "historical_handoff_exact_suffix": (ROOT / "HANDOFF.md").read_bytes().endswith((OUT / "before-HANDOFF.md").read_bytes()),
        "original_failure_status_record_unchanged": status["limited_new_lesson"] == old_status["limited_new_lesson"],
        "not_ready_and_human_pending_retained": status["overall_status"] == "PARTIAL_PRODUCT_NOT_READY" and status["human_review"] == "not_reviewed"
            and status["conditional_aggregate_recovery"]["human_review"] == "H_PENDING" and not status["conditional_aggregate_recovery"]["student_ready"],
        "old_audio_integrity_against_saved_metadata": all(r["wav_exists"] and r["checksum_matches_saved_metadata"] for r in old_audio_integrity),
        "archived_original_audio_hashes_unchanged": all(r["wav_matches_prior_manifest"] and r["metadata_matches_prior_manifest"] for r in archived_audio),
        "actual_no_blocked_network_or_script_errors": not actual["blocked_requests"] and not actual["errors"],
    }
    report = {"at": datetime.now(timezone.utc).isoformat(), "status": "PASS" if all(checks.values()) else "REVIEW_REQUIRED",
        "checks": checks, "tables": tables, "baseline_files": len(before["files"]), "changed_existing_files": changed,
        "old_audio_integrity": old_audio_integrity, "archived_audio_hash_comparison": archived_audio,
        "audio_scope": "All existing WAVs checked against saved metadata; prior exact hash comparisons limited to archived manifest entries. No unsupported all-metadata before/after claim.",
        "new_resource_requests": new_requests, "old_failure_paths_unchanged": all(not p.startswith("runs/student-latency/20261027/new-lesson/") for p in changed),
        "model_scope": "Size/mtime metadata of all model files; no new weight-content hashing claim."}
    (OUT / "preservation-final.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": checks, "rows_before": sum(t["old_rows"] for t in tables.values()),
                      "rows_now": sum(t["now_rows"] for t in tables.values()), "changed_files": changed}, ensure_ascii=False))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
