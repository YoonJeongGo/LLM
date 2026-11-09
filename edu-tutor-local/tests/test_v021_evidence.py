"""Authored CPU development cases, never the frozen v0.2.1 holdout."""
import copy
import json
import math

import pytest

from edu_tutor.problems.evidence import verify_answer, check_intent, intent_sql
from edu_tutor.problems.models import normalize_problem
from edu_tutor.problems.app_correction import verify_with_app_correction


ROWS = [["b", 4, 2], ["a", 4, 1], ["c", 0, 1], ["n", None, 2], ["m", -3, 1], ["a", 4, 1]]


def problem(rows=None, *, query=None, intent=None):
    value = {"task_kind": "query_result" if query else "write_sql", "confirmed": True,
             "raw_text": "개발용 입력의 명시된 의도를 계산합니다.",
             "tables": [{"name": "observations", "columns": [
                 {"name": "label", "type": "TEXT"}, {"name": "amount", "type": "INTEGER"},
                 {"name": "rank_no", "type": "INTEGER"}], "rows": ROWS if rows is None else rows}]}
    if query:
        value["query"] = query
    if intent:
        value["intent"] = {"table": "observations", **intent}
    return normalize_problem(value)


def evidence(p, sql=None, **claims):
    raw = json.dumps({"sql": sql or p.get("query"), **claims})
    return verify_answer(p, raw, p["raw_text"])


def test_three_value_where_multisort_projection_and_duplicate_row_identity():
    p = problem(query="SELECT label, amount FROM observations WHERE amount >= 0 ORDER BY amount DESC, rank_no ASC, label ASC")
    before = copy.deepcopy(p)
    e = evidence(p)
    assert e["status"] == "verified" and e["support_status"] == "verified_lesson_evidence"
    assert e["calculation"]["status"] == "independent_projection_match"
    assert e["result"]["rows"] == [["a", 4], ["a", 4], ["b", 4], ["c", 0]]
    logical = e["logical_steps"]
    assert [row["truth"] for row in logical["row_evaluations"]] == [True, True, True, None, False, True]
    assert len(set(logical["ordered_row_ids"])) == 4
    assert logical["order_ties"][0]["row_ids"] == [logical["row_evaluations"][1]["row_id"], logical["row_evaluations"][5]["row_id"]]
    assert logical["tie_order_guaranteed"] is False and p == before


@pytest.mark.parametrize("rows,where,expected", [
    ([], "amount IS NOT NULL", []),
    ([["x", None, 0], ["y", None, 1]], "amount IS NULL", [["x", None], ["y", None]]),
    ([["x", 0, 0], ["y", None, 1]], "amount >= 0", [["x", 0]]),
    ([["x", -4, 0], ["x", -4, 1], ["y", -2, 2]], "amount < 0", [["x", -4], ["x", -4], ["y", -2]]),
])
def test_empty_null_zero_negative_and_duplicate_boundaries(rows, where, expected):
    e = evidence(problem(rows, query=f"SELECT label, amount FROM observations WHERE {where} ORDER BY amount ASC, rank_no ASC"))
    assert e["calculation"]["status"] == "independent_projection_match"
    assert e["result"]["rows"] == expected


@pytest.mark.parametrize("predicate,truths", [
    ("amount IS NULL OR amount >= 4", [True, True, False, True, False, True]),
    ("NOT (amount < 0)", [True, True, True, None, False, True]),
    ("amount BETWEEN -3 AND 0", [False, False, True, None, True, False]),
    ("amount IN (0, -3, NULL)", [None, None, True, None, True, None]),
    ("amount <> 4 AND rank_no = 1", [False, False, True, False, True, False]),
])
def test_independent_sqlite_three_value_predicates(predicate, truths):
    e = evidence(problem(query=f"SELECT label FROM observations WHERE {predicate}"))
    assert e["logical_steps"] is not None, e
    assert [row["truth"] for row in e["logical_steps"]["row_evaluations"]] == truths
    assert e["logical_steps"]["ordering_guaranteed"] is False


def projection_intent():
    return {"select_columns": ["label", "amount"], "aggregates": [],
            "where": "amount >= 0 AND rank_no = 1",
            "order_by": [{"column": "amount", "direction": "desc"}, {"column": "label", "direction": "asc"}]}


@pytest.mark.parametrize("sql", [
    "SELECT label, amount FROM observations WHERE amount >= 0 AND rank_no = 1 ORDER BY amount DESC, label ASC",
    "SELECT o.label AS name, o.amount AS score FROM observations o WHERE 1 = o.rank_no AND 0 <= o.amount ORDER BY score DESC, name",
    "SELECT label, amount FROM observations WHERE (rank_no = 1) AND (amount >= 0) ORDER BY 2 DESC, 1 ASC",
])
def test_ast_equivalence_aliases_reversed_comparisons_reordered_and_ordinal_order(sql):
    p = problem(intent=projection_intent())
    e = evidence(p, sql)
    assert e["intent"]["status"] == "supported_match", e
    assert e["support_status"] == "verified_lesson_evidence", e
    assert e["result"]["rows"] == [["a", 4], ["a", 4], ["c", 0]]
    assert e["sql_origin"] == "model_candidate"


@pytest.mark.parametrize("sql", [
    "SELECT amount, label FROM observations WHERE amount >= 0 AND rank_no = 1 ORDER BY amount DESC,label",
    "SELECT label, amount FROM observations WHERE amount > 0 AND rank_no = 1 ORDER BY amount DESC,label",
    "SELECT label, amount FROM observations WHERE amount >= 0 ORDER BY amount DESC,label",
    "SELECT label, amount FROM observations WHERE amount >= 0 AND rank_no = 1 ORDER BY amount ASC,label",
    "SELECT label, amount FROM observations WHERE amount >= 0 AND rank_no = 1 ORDER BY label,amount DESC",
    "SELECT label, amount FROM observations WHERE amount >= 0 AND rank_no = 1",
    "SELECT label, amount FROM observations WHERE amount >= 0 AND rank_no = 1 AND amount != 999 ORDER BY amount DESC,label",
])
def test_coincidental_fixture_results_cannot_replace_intent_proof(sql):
    e = evidence(problem(intent=projection_intent()), sql)
    assert e["status"] == "stopped" and e["intent"]["status"] == "mismatch"
    assert e["support_status"] == "invalid_candidate_or_mismatch"


def test_missing_sort_is_not_inferred_from_candidate():
    requested = projection_intent()
    requested["order_by"] = []
    sql = "SELECT label,amount FROM observations WHERE amount>=0 AND rank_no=1 ORDER BY amount DESC,label"
    e = evidence(problem(intent=requested), sql)
    assert e["intent"]["status"] == "mismatch"


@pytest.mark.parametrize("direction,expected", [
    ("ASC", [["n", None], ["m", -3], ["c", 0], ["a", 4], ["a", 4], ["b", 4]]),
    ("DESC", [["a", 4], ["a", 4], ["b", 4], ["c", 0], ["m", -3], ["n", None]]),
])
def test_sqlite_default_null_order_and_secondary_text_binary(direction, expected):
    e = evidence(problem(query=f"SELECT label,amount FROM observations ORDER BY amount {direction},label ASC"))
    assert e["result"]["rows"] == expected and e["logical_steps"]
    assert e["logical_steps"]["order_by"][0]["nulls_first"] is (direction == "ASC")


def test_group_where_having_alias_and_multiple_order_keys_independently_match():
    intent = {"aggregates": [{"function": "sum", "column": "amount"}, {"function": "count", "column": "*"}],
              "group_by": ["rank_no"], "where": "amount IS NULL OR amount >= 0", "having": "SUM(amount) >= 4",
              "order_by": [{"column": "SUM(amount)", "direction": "desc"}, {"column": "rank_no", "direction": "asc"}]}
    sql = "SELECT rank_no,SUM(amount) AS total,COUNT(*) AS n FROM observations WHERE amount >= 0 OR amount IS NULL GROUP BY rank_no HAVING total >= 4 ORDER BY total DESC,rank_no"
    e = evidence(problem(intent=intent), sql)
    assert e["intent"]["status"] == "supported_match", e
    assert e["calculation"]["status"] == "independent_aggregate_match", e
    assert e["result"]["rows"] == [[1, 8, 3], [2, 4, 2]]
    assert e["logical_steps"]["ordered_group_values"] == [[1], [2]]
    assert all(row["included"] for row in e["logical_steps"]["having_evaluations"])


def test_having_aggregate_not_projected_still_has_independent_condition_value():
    p = problem(query="SELECT rank_no,SUM(amount) FROM observations GROUP BY rank_no HAVING COUNT(amount) > 1 ORDER BY rank_no DESC")
    e = evidence(p)
    assert e["logical_steps"], e
    assert e["result"]["rows"] == [[1, 5]]
    assert [g["truth"] for g in e["logical_steps"]["having_evaluations"]] == [False, True]


@pytest.mark.parametrize("query,reason", [
    ("SELECT DISTINCT label FROM observations", "DISTINCT"),
    ("SELECT label FROM observations LIMIT 2", "LIMIT"),
    ("WITH chosen AS (SELECT * FROM observations) SELECT label FROM chosen", "CTE"),
    ("SELECT ROW_NUMBER() OVER (ORDER BY amount) FROM observations", "윈도우"),
    ("SELECT UPPER(label) FROM observations", "출력"),
    ("SELECT label FROM observations WHERE ABS(amount)>0", "함수"),
    ("SELECT label FROM observations ORDER BY label COLLATE NOCASE", "함수"),
    ("SELECT label,label FROM observations", "중복"),
])
def test_unsupported_calculation_does_not_claim_full_lesson_evidence(query, reason):
    e = evidence(problem(query=query))
    assert e["support_status"] == "verified_no_plan", e
    assert e["logical_steps"] is None and reason in e["calculation"]["reason"]


def test_mixed_sqlite_affinity_is_not_silently_taught_as_python_raw_values():
    p = problem(query="SELECT label FROM observations ORDER BY label")
    p["tables"][0]["rows"][0][0] = 4
    e = evidence(p)
    assert e["support_status"] == "verified_no_plan"
    assert "TEXT" in e["calculation"]["reason"]


def test_wrong_structured_model_result_is_separate_from_verified_app_calculation():
    p = problem(intent=projection_intent())
    raw = json.dumps({"sql": intent_sql(p["intent"]), "explanation": '결과 [["invented",999]]입니다.'})
    e = verify_with_app_correction(p, raw, p["raw_text"])
    assert e["status"] == "verified"
    assert e["raw_model_explanation"]["status"] == "detected_contradiction"
    assert e["raw_model_explanation"]["used_as_student_speech"] is False
    assert e["result"]["rows"] == [["a", 4], ["a", 4], ["c", 0]]


def test_verification_timers_are_nonnegative_and_not_part_of_evidence_identity():
    p = problem(query="SELECT label FROM observations")
    a, b = evidence(p), evidence(p)
    assert a["id"] == b["id"]
    assert set(a["timings_seconds"]) == {"extraction", "intent", "execution", "logical_trace", "total"}
    assert all(math.isfinite(value) and value >= 0 for value in a["timings_seconds"].values())
    assert a["timings_seconds"]["total"] >= a["timings_seconds"]["execution"]


def test_unknown_column_and_foreign_table_qualifier_are_invalid_sql_not_supported_answers():
    for sql in ("SELECT missing FROM observations", "SELECT alien.amount FROM observations"):
        e = evidence(problem(intent=projection_intent()), sql)
        assert e["status"] == "stopped" and e["execution"]["status"] != "executed"
        assert e["support_status"] == "invalid_candidate_or_mismatch"


def test_numeric_group_identity_preserves_equal_int_and_integral_float_inputs():
    p = problem([["x", 0.0, 2], ["y", 0, 1], ["z", -2.0, 1]],
                query="SELECT amount,COUNT(*) FROM observations GROUP BY amount ORDER BY amount")
    e = evidence(p)
    assert e["support_status"] == "verified_lesson_evidence", e
    assert e["result"]["rows"] == [[-2, 1], [0, 2]]

