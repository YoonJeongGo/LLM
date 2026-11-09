"""Numeric MIN/MAX: compare teaching values against isolated SQLite, not prose."""
import json
import re
import sqlite3

import pytest

from edu_tutor.lessons.verified import generate_verified_plan
from edu_tutor.problems.evidence import display_answer, verify_answer
from edu_tutor.problems.models import infer_basic_intent, normalize_problem


def problem(values, *, table="readings", column="amount", column_type="REAL", suffix=""):
    query = f"SELECT MIN({column}) AS low, MAX({column}) AS high FROM {table}{suffix}"
    return normalize_problem({"task_kind": "query_result", "dialect": "sqlite", "confirmed": True,
        "raw_text": "원본 SQL의 최솟값과 최댓값 계산 과정을 설명해 줘.", "query": query,
        "tables": [{"name": table, "columns": [{"name": column, "type": column_type}],
                    "rows": [[v] for v in values]}]})


@pytest.mark.parametrize("values", [[], [None, None], [0, None, 0], [-7, 3, -7, 3, None],
                                    [0.25, -2.5, None, 4.75]])
def test_extrema_trace_voice_and_board_share_actual_values(values):
    p = problem(values)
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE readings(amount REAL)")
        db.executemany("INSERT INTO readings VALUES (?)", [[v] for v in values])
        expected = [list(row) for row in db.execute(p["query"])]
    raw = json.dumps({"sql": p["query"], "explanation": "WRONG_MODEL_PROSE: minimum is 999"})
    e = verify_answer(p, raw, p["raw_text"])
    assert e["calculation"]["status"] == "independent_aggregate_match"
    assert e["result"]["rows"] == expected
    assert [a["result"] for a in e["logical_steps"]["aggregates"]] == expected[0]
    message = {"id": "cpu-extrema", "problem": p, "content": display_answer(e),
               "raw_model_response": raw, "evidence": e}
    result = generate_verified_plan(message, p["raw_text"], "cpu-extrema")
    assert result["speech_allowed"]
    steps = result["plan"]["steps"]
    assert len(steps) == 2
    assert "최솟값" in steps[0]["speech"] and "최댓값" in steps[1]["speech"]
    assert "WRONG_MODEL_PROSE" not in json.dumps(result, ensure_ascii=False)
    for step, value in zip(steps, expected[0]):
        if value is None:
            assert "NULL" in step["speech"]
        else:
            spoken_value = re.search(r"은 (-?\d+(?:\.\d+)?)입니다", step["speech"])
            assert spoken_value and float(spoken_value[1]) == value
    final_tables = [a for a in steps[-1]["board_actions"] if a["type"] == "table"]
    assert any(a["rows"] == expected for a in final_tables)


def test_renamed_filtered_extrema_and_explicit_intent():
    p = problem([-8, 0, 9, 9, None], table="stock_levels", column="units", column_type="INTEGER",
                suffix=" WHERE units >= 0")
    e = verify_answer(p, "", p["raw_text"])
    assert e["result"]["rows"] == [[0, 9]]
    assert [a["included_values"] for a in e["logical_steps"]["aggregates"]] == [[0, 9, 9]] * 2
    p["task_kind"] = "write_sql"
    p["raw_text"] = "MIN(units), MAX(units)를 구해 줘."
    p["query"] = None
    intent, _ = infer_basic_intent(p, p["raw_text"])
    assert [a["function"] for a in intent["aggregates"]] == ["min", "max"]
    sql = "SELECT MIN(units), MAX(units) FROM stock_levels"
    assert verify_answer(p, json.dumps({"sql": sql}), p["raw_text"])["status"] == "verified"


def test_text_order_semantics_are_not_claimed_as_numeric_trace():
    p = problem(["2", "10", None], column_type="TEXT")
    e = verify_answer(p, "", p["raw_text"])
    assert e["result"]["rows"] == [["10", "2"]]
    assert e["calculation"]["status"] == "outside_supported_trace"
    assert "문자열" in e["calculation"]["reason"]
    assert e["logical_steps"] is None


def test_ambiguous_multiple_language_aggregates_ask_for_targets():
    p = problem([2, 9])
    intent, reason = infer_basic_intent(p, "최솟값과 최댓값을 알려 줘.")
    assert intent is None and "여러 집계" in reason
