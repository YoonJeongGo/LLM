"""Read-only replay/audit of saved v1 model outputs and public v0.2 oracles.

Only new phase2 artifacts are written. No model, training or network work occurs.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from .comparison import compare_results_v2
from .sql_sandbox import compare_results, execute_sql, extract_sql


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# These annotations are offline inspection notes about saved outputs, never model
# generation rules or answer routing. Evidence is the complete raw response below.
NOTES = {
    "correlated_group_max": {
        "baseline": [("sql_semantics", "전체 MAX만 사용해 팀 나의 id=3을 누락합니다. team 상관 조건이 없습니다."),
                     ("explanation_contradiction", "주어진 team/pay 정보가 충분한데 팀별 조건이 부족하다고 설명합니다.")],
        "adapter": [("sql_semantics", "질문에 없는 manager_id=1 AND pay=160 조건으로 id=3을 누락합니다.")]},
    "not_exists_antijoin": {"baseline": [], "adapter": []},
    "cross_product_count": {
        "baseline": [("task_format_mismatch", "설명은 3×2=6으로 맞지만 SQL은 행 수가 아니라 조합된 두 열/여섯 행을 반환합니다.")],
        "adapter": [("grader_contract_false_negative", "반환값 [[6]]은 맞습니다. 질문에서 요구하지 않은 pairs 별칭만 달라 기존 채점에서 실패했습니다.")]},
    "union_distinct_set": {
        "baseline": [("sql_semantics", "합집합 대신 동등 조인 후 산술 합을 구해 [[4]]를 반환합니다.")],
        "adapter": [("truncated_output", "256토큰 상한, EOS 없음, JSON 미완성입니다."),
                    ("repetition", "원문을 반복하고 SQL은 SELECT ... 자리표시자입니다.")]},
    "intersect_common_set": {
        "baseline": [("sql_semantics", "교집합 한 열 대신 SELECT * 조인 두 열 [[2,2]]를 반환하며 중복 제거도 없습니다.")],
        "adapter": [("truncated_output", "256토큰 상한, EOS 없음, JSON 미완성입니다."),
                    ("invented_values", "원본에 없는 4 이후 수를 계속 나열하고 SQL은 SELECT ...입니다.")]},
    "except_difference_set": {
        "baseline": [("sql_semantics", "차집합 대신 IN으로 공통값 [[2]]를 반환합니다.")],
        "adapter": [("name_resolution_error", "두 표 모두 v 열이 있으므로 SELECT v가 모호합니다."),
                    ("sql_semantics", "동등 JOIN은 a에만 있는 값을 구하는 차집합이 아닙니다.")]},
    "outer_join_count_child": {
        "baseline": [("sql_semantics", "orders만 그룹화하므로 주문 없는 고객 id=3/0건을 누락합니다.")],
        "adapter": [("sql_semantics", "주문 수 대신 SUM(amount)를 계산하고 주문 없는 고객도 누락합니다.")]},
    "having_count_multiple": {"baseline": [], "adapter": []},
    "real_division_percentage": {
        "baseline": [("sql_semantics", "분자 1건만 계산하고 전체 4건으로 나누기와 ×100을 누락합니다.")],
        "adapter": [("sql_semantics", "백분율 25 대신 해당 행 수 1만 반환합니다.")]},
    "date_month_bucket": {
        "baseline": [("dbms_mismatch", "SQLite에서 month 함수가 없어 실행 실패합니다."),
                     ("explanation_sql_mismatch", "설명은 STRFTIME 필요성을 언급하지만 SQL은 month(day)입니다.")],
        "adapter": [("dbms_mismatch", "SQLite에서 DATE_FORMAT 함수가 없어 실행 실패합니다."),
                    ("sql_semantics", "일 단위 yyyy-MM-dd 및 GROUP BY day는 월별 집계 요구와 다릅니다.")]},
    "scalar_subquery_average": {"baseline": [], "adapter": []},
    "insufficient_schema_clarification": {
        "baseline": [("invented_schema", "주어진 표가 없는데 users(name,sales)를 만들어 SQL을 단정합니다.")],
        "adapter": [("invented_schema", "주어진 표가 없는데 sales_data(name,sales)를 사용합니다."),
                    ("clarification_heuristic_false_positive", "필요/확인 단어 때문에 신호가 true지만 미확인 스키마 SQL을 함께 답했습니다.")]},
}


def audit_previous(root, directory):
    root, directory = Path(root), Path(directory)
    data_path = root / "data/demo/test.jsonl"
    source_paths = {"dataset": data_path, "baseline": root / "runs/eval-baseline-v1/evaluation.json",
                    "adapter": root / "runs/eval-adapter-v1/evaluation.json",
                    "comparison": root / "runs/eval-comparison-v1/comparison.json"}
    before = {key: digest(path) for key, path in source_paths.items()}
    records = [json.loads(line) for line in data_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    reports = {mode: json.loads(source_paths[mode].read_text(encoding="utf-8")) for mode in ("baseline", "adapter")}
    if len(records) != 12 or sum("expected" in record for record in records) != 11:
        raise ValueError("Saved v1 denominator differs from the documented 12/11; do not infer missing data")
    for report in reports.values():
        if report["dataset_sha256"] != before["dataset"]:
            raise ValueError("Saved output/dataset hash mismatch")
    items = []
    totals = {mode: Counter() for mode in reports}
    for record in records:
        question = next(m["content"] for m in record["messages"] if m["role"] == "user")
        item = {"id": record["id"], "kind": "sqlite_query" if "expected" in record else "missing_schema_clarification",
                "question": question, "original_schema_and_values": record.get("fixture"),
                "reference": record.get("expected"), "reference_answer_not_model_input": next(
                    m["content"] for m in record["messages"] if m["role"] == "assistant"), "modes": {}}
        if "expected" in record:
            reference_result = execute_sql(record["expected"]["sql"], record["fixture"])
            item["reference_replay"] = reference_result
            item["reference_oracle_matches"] = compare_results(reference_result, record["expected"])
            if not item["reference_oracle_matches"]:
                raise ValueError(f"Saved reference fails its independent expected result: {record['id']}")
        for mode, report in reports.items():
            output = next(row for row in report["items"] if row["id"] == record["id"])
            analysis = {"original_output_record": output, "raw_response": output["text"],
                        "original_protocol_match": output.get("sql_match"), "confirmed": [], "inferred": [],
                        "extracted_sql": None, "current_replay": None, "old_protocol_replay_match": False,
                        "corrected_protocol": None, "human_review": "not_reviewed"}
            for category, evidence in NOTES[record["problem_family_id"]][mode]:
                analysis["confirmed"].append({"category": category, "evidence": evidence,
                                               "basis": "saved raw response and isolated SQLite replay"})
                totals[mode][category] += 1
            if "expected" in record and output["finish_reason"] == "eos":
                try:
                    sql = extract_sql(output["text"])
                    actual = execute_sql(sql, record["fixture"], dialect=record.get("sql_dialect", "sqlite"))
                    analysis["extracted_sql"] = sql
                    analysis["current_replay"] = actual
                    analysis["old_protocol_replay_match"] = compare_results(actual, record["expected"])
                    # None of the original 11 questions specifies output aliases.
                    analysis["corrected_protocol"] = compare_results_v2(actual, record["expected"], columns_required=False)
                    analysis["corrected_protocol"]["alias_contract_basis"] = "Original question does not require result aliases; positional arity/order still required"
                except ValueError as exc:
                    analysis["extraction_error"] = str(exc)
            elif output["finish_reason"] != "eos":
                analysis["extraction_not_attempted"] = "Preserve frozen protocol: incomplete responses are not repaired or accepted"
                analysis["inferred"].append({"category": "model_repetition_or_training_effect",
                    "evidence": "Repetition follows adapter use, but this experiment cannot identify a causal weight/data mechanism."})
            if "expected" in record:
                totals[mode]["sql_total"] += 1
                totals[mode]["old_protocol_stored_correct"] += bool(output.get("sql_match"))
                totals[mode]["old_protocol_replayed_correct"] += analysis["old_protocol_replay_match"]
                totals[mode]["corrected_protocol_correct"] += bool((analysis["corrected_protocol"] or {}).get("match"))
            totals[mode]["truncated"] += output["finish_reason"] != "eos"
            item["modes"][mode] = analysis
        items.append(item)
    after = {key: digest(path) for key, path in source_paths.items()}
    if before != after:
        raise RuntimeError("Protected source records changed during the audit")
    result = {"created_at": datetime.now(timezone.utc).isoformat(), "tier": "T0_saved_T2_output_replay",
        "scope": "No model rerun. Saved raw responses replayed in isolated SQLite; no old file is modified.",
        "original_total": 12, "original_sql_denominator": 11,
        "twelfth_kind": "missing_schema_clarification", "old_protocol": reports["baseline"]["protocol"],
        "protocol_same_between_modes": reports["baseline"]["protocol"] == reports["adapter"]["protocol"],
        "corrected_protocol": {"version": 2, "changes": ["Do not require aliases absent from the question contract",
            "Unordered numeric tolerance uses complete one-to-one matching rather than greedy matching"],
            "unchanged": ["Original raw outputs", "256-token generation cap", "Truncation is failure",
                          "Positional column count", "NULL semantics", "Duplicate multiplicity", "No RAG"],
            "interpretation": "Regrading saved output is not model improvement; keep old 3/11 results alongside this report"},
        "source_sha256_before": before, "source_sha256_after": after, "source_unchanged": before == after,
        "summary": {mode: dict(counts) for mode, counts in totals.items()},
        "configuration_findings": [
            {"status": "confirmed_from_code_and_saved_token_audit", "finding": "Evaluation and training both use enable_thinking=False and add_generation_prompt for input prefixes. Training masking retained EOS. No template mismatch was established."},
            {"status": "confirmed_from_code", "finding": "Old evaluation requests a short SQL/explanation JSON, not a lecture plan. The two 256-token failures contain repetition; long lesson JSON is not the cause in this test."},
            {"status": "confirmed_from_protocol", "finding": "RAG was off in both old runs, so retrieval cannot explain these 12 outputs. Separate RAG integration failure is retained separately."},
            {"status": "not_established", "finding": "Training data causality and broad model generalization cannot be inferred from one tiny experiment."}],
        "human_review": "not_reviewed", "items": items}
    write_json(directory / "previous-evaluation-audit.json", result)
    lines = ["# v0.1 저장 응답 감사", "", "새 모델 실행 없이 원본 12문항/SQL 11문항을 재검사했습니다. 기존 파일과 3/11 기록을 보존했습니다.", "",
             "| 문항 | 기반 모델 확인된 문제 | 어댑터 확인된 문제 |", "|---|---|---|"]
    for item in items:
        cells = ["; ".join(note["evidence"] for note in item["modes"][mode]["confirmed"]) or "해당 입력의 SQL 결과 일치; 설명 전체 진실성 미검토" for mode in reports]
        lines.append(f"| {item['id']} | {cells[0]} | {cells[1]} |")
    lines += ["", "기존 strict alias 채점은 기반 3/11·어댑터 3/11입니다. 질문에 없던 별칭 요구를 제외한 별도 교정 채점은 기반 3/11·어댑터 4/11입니다. 이는 저장 응답 재채점이며 학습 개선이 아닙니다.",
              "", "실행 성공은 문항에 대한 의미적 정답 또는 설명의 정확성을 보증하지 않습니다. 반조인 답은 주어진 NULL 없는 orders.customer_id에서 일치한 범위만 인정합니다.",
              "", "전체 질문·스키마·기준 SQL/결과·응답 원문·추출 SQL·실행 결과는 previous-evaluation-audit.json에 있습니다."]
    (directory / "PREVIOUS_EVALUATION_AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def verify_pack(root, directory):
    root, directory = Path(root), Path(directory)
    package = root / "docs/source-pack-v02/edu_tutor_next_v02"
    script = package / "tools/verify_fixture_oracles.py"
    # Inspected local package code: reads its fixture, uses :memory:, prints JSON;
    # no network/file writes/commands. Run only that preserved exact source.
    proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
        encoding="utf-8", timeout=30, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if proc.returncode != 0:
        raise RuntimeError("Pack oracle script failed: " + proc.stderr[:500])
    original = json.loads(proc.stdout)
    cases = json.loads((package / "fixtures/sql_cases_v02.json").read_text(encoding="utf-8"))["cases"]
    results = []
    for case in cases:
        fixture = {"tables": [{**table, "columns": [{"name": name, "type": typ} for name, typ in table["columns"]]} for table in case["tables"]]}
        oracle = case["oracle"]
        actual = execute_sql(oracle["reference_sql"], fixture)
        expected = {"columns": oracle["expected_columns"], "rows": oracle["expected_rows"],
                    "row_order": "ordered" if oracle["ordered"] else "multiset",
                    "numeric_abs_tolerance": oracle["numeric_tolerance"],
                    "numeric_rel_tolerance": oracle["numeric_tolerance"]}
        results.append({"id": case["id"], "actual": actual,
                        "comparison": compare_results_v2(actual, expected)})
    result = {"tier": "T0", "scope": "Public development fixture oracle verification only; no model outputs and no educational accuracy claim",
              "provided_script_review": "read_only_memory_SQLite_no_network", "script_sha256": digest(script),
              "fixture_sha256": digest(package / "fixtures/sql_cases_v02.json"), "provided_script_report": original,
              "application_isolated_sandbox": {"total": len(results), "passed": sum(row["comparison"]["match"] for row in results), "results": results},
              "human_review": "not_reviewed"}
    write_json(directory / "development-oracles.json", result)
    return result
