"""Authored CPU formatting and explanation boundaries, not model evaluation."""
import json

import pytest

from edu_tutor.problems.sql_response import extract_sql_candidate
from edu_tutor.evaluation.sql_sandbox import extract_sql
from edu_tutor.problems.response_claims import audit_model_explanation
from edu_tutor.problems.models import normalize_problem
from edu_tutor.problems.app_correction import verify_with_app_correction
from edu_tutor.lessons.verified import generate_verified_plan


def response(sql="SELECT COUNT(score) FROM measurements", *, explanation=None, tail=""):
    value = {"sql": sql}
    if explanation is not None:
        value["explanation"] = explanation
    return json.dumps(value, ensure_ascii=False) + tail


@pytest.mark.parametrize("tail", [
    "\n\n설명: NULL을 제외한 값의 개수를 계산합니다.",
    "\n결과 [[2]]입니다.\n| 값 |\n|---|\n| 2 |",
    "\nexplanation: `score`의 `COUNT(score)`를 구합니다. `score IS NOT NULL`인 값만 셉니다.",
    "\r\nCOUNT(*)는 NULL인 행도 포함합니다.",
])
def test_complete_json_prefix_with_one_plain_explanation_keeps_exact_sql(tail):
    sql = "SELECT COUNT(score) FROM measurements"
    assert extract_sql_candidate(response(sql, tail=tail)) == sql


def test_json_prefix_decoder_preserves_escaped_quotes_and_braces_inside_sql():
    sql = "SELECT 'the } and { characters, a\\b and a\"b' AS text"
    assert extract_sql_candidate(response(sql, tail="\n설명: 문자열을 반환합니다.")) == sql


def test_frozen_model_evaluation_extractor_does_not_gain_the_new_format():
    with pytest.raises(ValueError):
        extract_sql(response(tail="\n설명: 원본 값 개수입니다."))


@pytest.mark.parametrize("tail", [
    '\n{"explanation":"다른 설명"}',
    '\n설명 다음 {"sql":"SELECT 2"}',
    '\n```json\n{"explanation":"다른 설명"}\n```',
    '\n```sql\nSELECT 2\n```',
    '\n~~~sql\nSELECT 2\n~~~',
    '\n추가 후보: SELECT 2',
    '\n추가 SQL: `SELECT COUNT(*) FROM measurements`',
    '\nWITH extra AS (SELECT 2) SELECT * FROM extra',
    '\nDELETE FROM measurements',
    '\nPRAGMA writable_schema=ON',
    '\n[ {"sql":"SELECT 2"} ]',
    '\n[[2]]',
    '\ntrue',
])
def test_json_prefix_does_not_pick_a_candidate_from_ambiguous_suffix(tail):
    with pytest.raises(ValueError):
        extract_sql_candidate(response(tail=tail))


@pytest.mark.parametrize("raw", [
    '{"sql":"SELECT 1","sql":"SELECT 2"}\n설명입니다.',
    '{"sql":"SELECT 1","explanation":"first","explanation":"second"}\n설명입니다.',
    '{"sql":"SELECT 1","expected_rows":[[1]]}\n설명입니다.',
    '{"sql":"SELECT 1"\n설명입니다.',
    '{"sql":null}\n설명입니다.',
    '{"sql":" "}\n설명입니다.',
    '{"sql":"SELECT 1","schema_version":NaN}\n설명입니다.',
])
def test_invalid_or_disallowed_json_prefix_never_uses_the_tail_as_a_repair(raw):
    with pytest.raises(ValueError):
        extract_sql_candidate(raw)


def calculation(sql="SELECT COUNT(score) FROM measurements", columns=None, rows=None):
    return {"id": "developer-result", "sql": sql, "execution": {
        "status": "executed", "columns": columns or ["n"], "rows": rows if rows is not None else [[2]]}}


def test_json_explanation_and_tail_arrays_are_audited_separately_without_speech_approval():
    raw = response(explanation="결과 [[2]]입니다.", tail="\n설명: 결과 [[9]]입니다.")
    audit = audit_model_explanation(raw, calculation())
    assert audit["status"] == "detected_contradiction"
    claims = audit["explicit_result_claims"]["claims"]
    assert [c["matches_sql_execution"] for c in claims] == [True, False]
    assert {c["source"] for c in claims} == {"json_explanation", "plain_text_suffix"}
    assert not audit["raw_explanation_approved"] and not audit["used_as_student_speech"]
    assert audit["human_review"] == "H_PENDING"


def test_explicit_single_row_aggregate_scalar_claims_are_compared_to_their_projection():
    sql = "SELECT SUM(score) AS total, AVG(score) AS mean, COUNT(score) AS count FROM measurements"
    raw = response(sql, tail="\nSUM(score)는 0 + 9 = 9, AVG(score)는 (0 + 9) / 2 = 4.5, COUNT(score)는 3입니다.")
    audit = audit_model_explanation(raw, calculation(sql, ["total", "mean", "count"], [[2, 1, 2]]))
    assert audit["status"] == "detected_contradiction"
    claims = audit["explicit_result_claims"]["claims"]
    assert len(claims) == 3 and all(c["matches_sql_execution"] is False for c in claims)
    assert all(c["source"] == "plain_text_suffix" for c in claims)
    assert not audit["raw_explanation_approved"]


@pytest.mark.parametrize("sql,columns,rows,tail", [
    ("SELECT COUNT(score) FROM measurements", ["n"], [[2]], "\nCOUNT(score)는 2입니다."),
    ("SELECT SUM(score) FROM measurements", ["s"], [[None]], "\nSUM(score)는 NULL입니다."),
    ("SELECT AVG(score) FROM measurements", ["a"], [[-0.5]], "\nAVG(score)는 (-2 + 1) / 2 = -0.5입니다."),
])
def test_matching_scalar_or_null_claim_does_not_approve_free_explanation(sql, columns, rows, tail):
    audit = audit_model_explanation(response(sql, tail=tail), calculation(sql, columns, rows))
    assert audit["status"] == "unverified_free_explanation"
    assert audit["explicit_result_claims"]["claims"][0]["matches_sql_execution"] is True
    assert audit["human_review"] == "H_PENDING" and not audit["raw_explanation_approved"]


def test_grouped_scalar_claim_is_not_guessed_to_describe_one_arbitrary_group():
    sql = "SELECT label,SUM(score) FROM measurements GROUP BY label"
    audit = audit_model_explanation(response(sql, tail="\nSUM(score)는 900입니다."),
        calculation(sql, ["label", "SUM(score)"], [["a", 2], ["b", 3]]))
    assert audit["status"] == "unverified_free_explanation"
    assert not audit["explicit_result_claims"]["claims"]
    assert not audit["raw_explanation_approved"]


def test_tail_count_star_false_rule_is_detected_even_without_json_explanation():
    audit = audit_model_explanation(response(tail="\nCOUNT(*)는 NULL인 행을 제외합니다."), calculation())
    assert audit["status"] == "detected_contradiction" and audit["concept_contradictions"]
    assert not audit["used_as_student_speech"]


def problem():
    return normalize_problem({"task_kind": "write_sql", "confirmed": True,
        "raw_text": "COUNT(score)를 구해 주세요.",
        "tables": [{"name": "measurements", "columns": [{"name": "score", "type": "INTEGER"}],
            "rows": [[0], [2], [None]]}]})


def test_correct_candidate_with_wrong_tail_uses_only_verified_values_in_board_and_speech():
    p = problem()
    raw = response(tail="\n설명: 결과 [[98765]]입니다. COUNT(*)는 NULL인 행을 제외합니다.")
    e = verify_with_app_correction(p, raw, p["raw_text"])
    assert e["status"] == "verified" and e["result"]["rows"] == [[2]]
    assert e["raw_model_explanation"]["status"] == "detected_contradiction"
    message = {"id": "dev-answer", "problem": p, "evidence": e, "content": "", "raw_model_response": raw}
    lesson = generate_verified_plan(message, p["raw_text"], "dev-lesson")
    assert lesson["plan"] and lesson["speech_allowed"]
    assert "98765" not in json.dumps(lesson["plan"], ensure_ascii=False)
    assert message["raw_model_response"] == raw


@pytest.mark.parametrize("sql", [
    "SELECT missing FROM measurements",
    "SELECT COUNT(score) FROM measurements; DELETE FROM measurements",
    "ATTACH DATABASE 'bad.sqlite3' AS outside",
])
def test_prefix_format_acceptance_does_not_bypass_schema_and_sql_safety(sql):
    p = problem()
    e = verify_with_app_correction(p, response(sql, tail="\n설명: 확인한 결과입니다."), p["raw_text"])
    assert e["status"] == "stopped" and e["result"] is None and e["logical_steps"] is None
    assert e["schema"]["status"] == "failed" and e["execution"]["status"] != "executed"
    assert "app_correction" not in e
