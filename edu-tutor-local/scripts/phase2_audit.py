"""v0.2 audit/freeze commands are CPU-only; run requires an explicitly scheduled GPU window."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from edu_tutor.evaluation.phase2_audit import audit_previous, verify_pack
from edu_tutor.evaluation.phase2_diagnostics import freeze_diagnostics, freeze_development, run_diagnostics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["audit", "freeze", "run"])
    parser.add_argument("--output", default="runs/phase2/current")
    parser.add_argument("--mode", choices=["model_only", "rag_only", "rag_tools"], default="model_only")
    parser.add_argument("--run-id")
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--max-seconds", type=int, default=1800)
    parser.add_argument("--adapter", default="base")
    parser.add_argument("--suite", choices=["new12", "development18"], default="new12")
    parser.add_argument("--grading-protocol", choices=["original", "json_fence_v2"], default="json_fence_v2",
                        help="Explicit post-fix phase2 grader; original preserves the first-run extraction contract")
    args = parser.parse_args()
    directory = (ROOT / args.output).resolve()
    if not directory.is_relative_to((ROOT / "runs/phase2").resolve()):
        parser.error("Output must remain inside this project's runs/phase2")
    if args.stage == "audit":
        report = audit_previous(ROOT, directory / "audit")
        fixture = verify_pack(ROOT, directory / "audit")
        print(json.dumps({"old_evaluation": report["summary"], "pack_oracles": fixture["provided_script_report"]["passed"],
                          "app_oracles": fixture["application_isolated_sandbox"]["passed"], "sources_unchanged": report["source_unchanged"]}, ensure_ascii=False))
    elif args.stage == "freeze":
        report = freeze_diagnostics(directory / "diagnostics")
        freeze_development(ROOT, directory / "diagnostics")
        print(json.dumps({"total": report["total"], "categories": report["categories"], "questions_sha256": report["questions_sha256"],
                          "oracles_sha256": report["oracles_sha256"]}))
    else:
        if not args.run_id:
            parser.error("--run-id is required so previous diagnostic results cannot be overwritten")
        report = run_diagnostics(ROOT, directory / "diagnostics", mode=args.mode, run_id=args.run_id,
                                 max_seconds=args.max_seconds, ids=args.ids, adapter=args.adapter, suite=args.suite,
                                 grading_protocol=args.grading_protocol)
        print(json.dumps({"status": report["status"], "counts": report.get("counts"), "pending_ids": report["pending_ids"]}))
        return 0 if report["status"] == "completed" else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
