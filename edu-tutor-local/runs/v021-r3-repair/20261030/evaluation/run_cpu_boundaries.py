"""Run the frozen six CPU boundary cases only after a product build freeze.

No API, JobManager, budget ledger, models, audio or vision entry point is called.
Product explanation/SQL validation functions are intentionally the system under test.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_case(case):
    from edu_tutor.problems.models import normalize_problem, infer_basic_intent
    from edu_tutor.problems.evidence import verify_answer, display_answer
    from edu_tutor.problems.sql_response import extract_sql_candidate
    from edu_tutor.lessons.verified import generate_verified_plan, validated_logical_stage

    ident = case["id"]
    if ident in {"C01", "C02"}:
        problem = normalize_problem({"task_kind": "query_result", "confirmed": True,
            "raw_text": "주어진 SQLite 조회의 원본 행별 계산과 정렬 결과를 설명해 주세요.",
            "query": case["base_query"], "tables": case["tables"]})
        original_tables = copy.deepcopy(problem["tables"])
        evidence = verify_answer(problem, json.dumps({"sql": case["base_query"], "explanation": "CPU 입력"}), problem["raw_text"])
        message = {"id": ident + "-source", "problem": problem, "evidence": evidence, "content": display_answer(evidence)}
        parent = {"id": ident + "-lesson", "source_message_id": message["id"], **generate_verified_plan(message, problem["raw_text"], ident + "-plan")}
        if not parent.get("speech_allowed"):
            return {"status": "SETUP_NOT_SUPPORTED", "parent": parent, "evidence": evidence}
        table = evidence["working_tables"][0]
        ri, ci = case["selected_source_row_index"], 1
        context = {"lesson_id": parent["id"], "step": 1, "problem_revision": problem["revision"],
            "selected_cell": {"cell_id": table["cell_ids"][ri][ci], "row_id": table["row_ids"][ri],
                              "column_id": table["column_ids"][ci], "table_element_id": table["id"]}}
        context["_verified_logical_stage"] = validated_logical_stage(parent, message, context)
        if not context["_verified_logical_stage"]:
            return {"status": "SETUP_CONTEXT_UNVERIFIED", "parent": parent}
        child = {**copy.deepcopy(message), "id": ident + "-supplement", "lesson_context": context}
        result = generate_verified_plan(child, case["question"], ident + "-supplement-plan")
        text = " ".join(s.get("speech", "") for s in (result.get("plan") or {}).get("steps", []))
        if ident == "C01":
            reason = result.get("reason", "")
            passed = not result.get("speech_allowed") and any(t in reason for t in ("어느", "지정", "확인", "모호"))
        else:
            null_item = next((i for i in result.get("explanation_fulfillment", {}).get("items", []) if i.get("kind") == "null_comparison"), {})
            passed = (bool(result.get("speech_allowed")) and "NULL인 행이 없습니다" in text
                      and null_item.get("evidence", {}).get("comparison_row_ids") == [])
        return {"status": "PASS_AUTOMATED_CONTRACT" if passed else "FAIL_EXPECTED_CLASSIFICATION", "result": result,
                "actual_speech": text, "original_tables_preserved": original_tables == message["problem"]["tables"],
                "human_semantic_review": "H_PENDING"}
    if ident in {"C03", "C04"}:
        problem = normalize_problem({"task_kind": "write_sql", "confirmed": True, "raw_text": case["question"], "tables": case["tables"]})
        intent, reason = infer_basic_intent(problem, case["question"])
        if ident == "C03":
            passed = intent is None and "미지원" in reason and any(v in reason.casefold() for v in ("윈도우", "lead", "window", "창"))
        else:
            passed = intent is None and "미지원" not in reason and any(v in reason for v in ("확인", "기준", "누락", "조건"))
        return {"status": "PASS_AUTOMATED_CONTRACT" if passed else "FAIL_EXPECTED_CLASSIFICATION", "intent": intent, "reason": reason}
    try:
        candidate = extract_sql_candidate(case["raw_response"])
        error = None
    except ValueError as exc:
        candidate, error = None, str(exc)
    passed = (candidate is None and error is not None and "ambiguous" in error if ident == "C05"
              else candidate == json.JSONDecoder().raw_decode(case["raw_response"])[0]["sql"] and error is None)
    return {"status": "PASS_AUTOMATED_CONTRACT" if passed else "FAIL_EXPECTED_CLASSIFICATION", "candidate": candidate, "error": error}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--product-freeze", type=Path, required=True)
    parser.add_argument("--ack-frozen-build", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Never overwrite a previous CPU boundary run")
    frozen = read(args.product_freeze)
    hashes = frozen.get("source_hashes")
    if not isinstance(hashes, dict):
        raise ValueError("Use the final execution-version.json with source_hashes")
    checked = {}
    for name, expected in hashes.items():
        if name.startswith("src/edu_tutor/") and name.endswith(".py"):
            path = ROOT / name
            if not path.is_file() or sha(path) != expected:
                raise ValueError("Frozen product source changed: " + name)
            checked[name] = expected
    required = {"src/edu_tutor/problems/models.py", "src/edu_tutor/problems/evidence.py",
                "src/edu_tutor/lessons/verified.py", "src/edu_tutor/problems/sql_response.py",
                "src/edu_tutor/problems/explanation_requests.py", "src/edu_tutor/lessons/requested_explanations.py"}
    if not required <= checked.keys():
        raise ValueError("Freeze omits a tested product source")
    inputs = read(BASE / "freeze.json")
    if sha(BASE / "cpu-boundaries.json") != inputs["files"]["cpu-boundaries.json"]:
        raise ValueError("Frozen CPU boundaries changed")
    cases = read(BASE / "cpu-boundaries.json")["cases"]
    output = {"at": datetime.now(timezone.utc).isoformat(), "purpose": "separate CPU boundary audit, not actual-model accuracy",
              "product_freeze": str(args.product_freeze), "product_freeze_sha256": sha(args.product_freeze),
              "input_sha256": sha(BASE / "cpu-boundaries.json"), "tool_sha256": sha(Path(__file__)), "cases": [],
              "source_hashes": checked, "actual_generation_count": 0, "ledger_mutation": False, "human_review": "H_PENDING"}
    for case in cases:
        try:
            actual = run_case(case)
        except Exception as exc:
            actual = {"status": "CPU_RUNNER_OR_PRODUCT_ERROR", "error": f"{type(exc).__name__}: {exc}"}
        output["cases"].append({"id": case["id"], "theme": case["theme"], "question": case["question"], "expected": case["expected"], **actual})
    output["counts"] = {"planned": 6, "pass": sum(c["status"] == "PASS_AUTOMATED_CONTRACT" for c in output["cases"]),
                        "failure": sum(c["status"] == "FAIL_EXPECTED_CLASSIFICATION" for c in output["cases"]),
                        "setup_or_error": sum(c["status"] not in {"PASS_AUTOMATED_CONTRACT", "FAIL_EXPECTED_CLASSIFICATION"} for c in output["cases"])}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"saved": str(args.output), "counts": output["counts"]}))


if __name__ == "__main__":
    main()
