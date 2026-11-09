"""Developer-authored CPU boundaries, separate from independent evaluation."""
import json

import pytest

from edu_tutor.problems import evidence as module
from edu_tutor.problems.app_correction import verify_with_app_correction
from edu_tutor.problems.models import normalize_problem


def problem(question):
    return normalize_problem({
        "task_kind": "write_sql", "confirmed": True, "raw_text": question,
        "tables": [{"name": "readings", "columns": [
            {"name": "item", "type": "INTEGER"},
            {"name": "amount", "type": "INTEGER"},
            {"name": "label", "type": "TEXT"}],
            "rows": [[1, 0, "a"], [2, None, "b"], [3, -4, "a"]]}]})


@pytest.mark.parametrize("question", [
    "평균을 구해 주세요.",
    "출력 열: label; 행 조건: amount >",
])
@pytest.mark.parametrize("raw", [
    "No SQL was returned.",
    json.dumps({"sql": "SELECT absent FROM readings"}),
    json.dumps({"sql": "SELECT AVG(amount) FROM readings"}),
])
def test_missing_original_intent_precedes_candidate_diagnostics_and_execution(question, raw, monkeypatch):
    def forbidden_execution(*args, **kwargs):
        raise AssertionError("An incomplete original request must not execute a guessed candidate")
    monkeypatch.setattr(module, "execute_sql", forbidden_execution)
    p = problem(question)
    e = verify_with_app_correction(p, raw, question)
    assert e["status"] == e["support_status"] == e["intent"]["status"] == "needs_input"
    assert e["execution"]["status"] == "not_run" and e["schema"]["status"] == "not_checked"
    assert e["can_repair"] is False and e["logical_steps"] is None
    assert "app_correction" not in e and "sql_origin" not in e


def test_explicit_unsupported_operator_is_not_relabelled_as_missing_input():
    p = problem("출력 열: label; 행 조건: label LIKE 'a%'")
    raw = json.dumps({"sql": "SELECT label FROM readings WHERE label LIKE 'a%'"})
    e = verify_with_app_correction(p, raw, p["raw_text"])
    assert e["support_status"] == "unsupported_intent" and e["intent"]["status"] == "unsupported"
    assert e["result"] is None and e["logical_steps"] is None and "app_correction" not in e


@pytest.mark.parametrize("sql", ["SELECT absent FROM readings", "SELECT amount FROM unknown_table"])
def test_confirmed_intent_with_wrong_schema_stays_candidate_failure(sql):
    p = problem("출력 열: amount")
    e = module.verify_answer(p, json.dumps({"sql": sql}), p["raw_text"])
    assert e["status"] == "stopped" and e["support_status"] == "invalid_candidate_or_mismatch"
    assert e["schema"]["status"] == "failed" and e["execution"]["status"] != "executed"


def test_confirmed_intent_with_correct_sql_still_requires_and_passes_independent_trace():
    p = problem("출력 열: item, amount; 행 조건: amount IS NOT NULL; 정렬 기준: amount ASC, item DESC")
    raw = json.dumps({"sql": "SELECT item, amount FROM readings WHERE amount IS NOT NULL ORDER BY amount ASC, item DESC"})
    e = module.verify_answer(p, raw, p["raw_text"])
    assert e["status"] == "verified" and e["support_status"] == "verified_lesson_evidence"
    assert e["calculation"]["status"] == "independent_projection_match"
    assert e["result"]["rows"] == [[3, -4], [1, 0]]


def test_missing_input_direct_intent_check_does_not_relabel_it_unsupported():
    p = problem("평균을 구해 주세요.")
    checked, intent = module.check_intent("SELECT AVG(amount) FROM readings", p, p["raw_text"])
    assert checked["status"] == "needs_input" and intent is None
