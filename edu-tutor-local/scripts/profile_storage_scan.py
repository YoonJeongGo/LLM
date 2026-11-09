"""Read-only exact storage-function comparison; never reserves model work."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time

from edu_tutor.models import budget

ROOT = Path(__file__).resolve().parents[1]
PROPOSAL = ROOT / "runs/finish-v2/20261029/storage-scan-proposal.py"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    if not args.name.replace("-", "").replace("_", "").isalnum():
        raise SystemExit("Safe unique artifact name required")
    out = ROOT / "runs/finish-v2/20261029" / (args.name + ".json")
    if out.exists():
        raise SystemExit("Preserve previous measurements; select a new name")
    spec = importlib.util.spec_from_file_location("storage_candidate", PROPOSAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ledger = ROOT / "runs/phase2/current/resource-budget.json"
    report = {"kind": "read_only_CPU_no_reservation", "scanned_roots": ["runs", ".local"],
        "cache": "fresh enumeration on each call; no persistent size cache", "results": []}
    before = hashlib.sha256(ledger.read_bytes()).hexdigest()
    for name, function in [("current_before", budget.mutable_bytes), ("candidate", module.mutable_bytes), ("current_after", budget.mutable_bytes)]:
        start = time.perf_counter()
        size = function(ROOT)
        report["results"].append({"method": name, "bytes": size, "seconds": time.perf_counter()-start})
    report["same_bytes_all_three"] = len({row["bytes"] for row in report["results"]}) == 1
    report["ledger_unchanged_during_scan"] = before == hashlib.sha256(ledger.read_bytes()).hexdigest()
    report["notice"] = "Concurrent file writes may change totals between scans; equality is claimed only if all three actual byte totals match. No API latency is measured."
    out.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
