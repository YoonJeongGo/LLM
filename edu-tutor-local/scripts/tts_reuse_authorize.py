"""Register the user's explicit two-TTS grant once; never reset usage."""
import hashlib
import json
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock
from edu_tutor.models.budget import status

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/student-latency/20261027/tts-worker-reuse"
IDENT = "20261027-tts-worker-reuse-2calls"


def main():
    # Recorded CPU gates are prerequisites, not claims of real GPU success.
    for name in ("cpu-api-related-final.xml", "cpu-api-binding-final.xml", "cpu-owned-interpreter-final.xml", "cpu-time-share-final.xml"):
        parsed = ET.parse(OUT/name)
        suites = list(parsed.getroot().iter("testsuite"))
        if not suites or any(int(s.get("failures", 0))+int(s.get("errors", 0)) for s in suites):
            raise SystemExit("CPU gate has not passed: "+name)
    with sqlite3.connect((ROOT/".local/tutor.sqlite3").as_uri()+"?mode=ro", uri=True) as db:
        jobs = [json.loads(r[0]) for r in db.execute("SELECT payload FROM jobs")]
    if any(j["state"] not in {"succeeded", "failed", "cancelled", "blocked", "interrupted"} for j in jobs):
        raise SystemExit("Active jobs exist; do not change policy")
    policy_path = ROOT / ".local/phase2-policy.json"
    with FileLock(str(ROOT / ".local/phase2-budget.lock")):
        limits = json.loads(policy_path.read_text(encoding="utf-8"))
        if (limits.get("active_execution_allowance") or {}).get("id") == IDENT:
            print("Authorization already active; counters and baseline unchanged")
            return
        if any(item.get("id") == IDENT for item in limits.get("execution_allowance_history", [])):
            raise SystemExit("Authorization exists in history; do not grant it again")
        ledger = json.loads((ROOT/"runs/phase2/current/resource-budget.json").read_text(encoding="utf-8"))
        rows = ledger["requests"]
        baseline = json.loads((OUT/"before-resource-budget.json").read_text(encoding="utf-8"))["requests"]
        if rows != baseline or any(r["status"] == "reserved" for r in rows):
            raise SystemExit("Usage changed since baseline; inspect before granting")
        used_seconds = sum(r["charged_seconds"] for r in rows)
        used_audio = sum(r["new_audio_clips"] for r in rows)
        remaining = min(600.0, limits["gpu_seconds"]-used_seconds)
        if remaining < 14 or limits["gpu_seconds"] != 5400 or used_audio != limits["new_audio_clips"]:
            raise SystemExit("Limits no longer match explicit exhausted-audio grant")
        prefix = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        source = OUT/"user-instruction.txt"
        grant = {"id": IDENT, "baseline_request_count": len(rows), "baseline_requests_sha256": hashlib.sha256(prefix).hexdigest(),
            "limits": {"text_requests": 0, "new_audio_clips": 2, "vision_requests": 0, "gpu_seconds": remaining},
            "runtime_scope": "tts_session_benchmark", "source": source.relative_to(ROOT).as_posix(),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "note": "Explicit user invocation of attached instruction. Two independent same-sentence cold/warm syntheses only; failures count, no retries, no transfer of old scope time."}
        prior = limits["active_execution_allowance"]
        limits.setdefault("execution_allowance_history", []).append(prior)
        limits.update(new_audio_clips=used_audio+2, active_execution_allowance=grant)
        record = {"at": datetime.now(timezone.utc).isoformat(), "authorization": grant,
            "user_explicitly_invoked_attachment": True, "previous_active_grant_preserved": prior,
            "old_scope_time_not_transferred": True, "used_before": {"requests": len(rows), "audio": used_audio, "seconds": used_seconds},
            "new_global_audio_limit": used_audio+2, "global_seconds_limit": limits["gpu_seconds"],
            "no_training_download_text_vision_paid_upload": True, "policy_before_sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest()}
        (OUT/"authorization.json").write_text(json.dumps(record, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        temporary = policy_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(limits, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        temporary.replace(policy_path)
    print(json.dumps(status(ROOT), ensure_ascii=False))


if __name__ == "__main__":
    main()
