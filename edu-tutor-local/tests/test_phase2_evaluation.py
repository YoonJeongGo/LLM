"""CPU-only grading/oracle/input-separation checks, never model accuracy evidence."""
import json

import pytest

from edu_tutor.evaluation.comparison import compare_results_v2
from edu_tutor.evaluation.phase2_diagnostics import (authored_cases, freeze_diagnostics,
    grade_response, public_prompt, request_body, grade_app_response, grade_raw_model)
from edu_tutor.evaluation.sql_sandbox import compare_results, execute_sql


def actual(rows, columns=None):
    return {"status": "executed", "columns": ["v"] if columns is None else columns, "rows": rows}


def expected(rows, **kwargs):
    return {"columns": ["v"], "rows": rows, **kwargs}


@pytest.mark.parametrize("left,right,ordered,wanted", [
    ([[1], [1], [None]], [[None], [1], [1]], False, True),
    ([[1], [1], [None]], [[None], [1], [2]], False, False),
    ([[1], [2]], [[2], [1]], True, False),
    ([], [], True, True),
    ([[None]], [[0]], False, False),
    ([[1]], [[True]], False, False),
    ([["1"]], [[1]], False, False),
])
def test_duplicate_null_order_type_contract(left, right, ordered, wanted):
    result = compare_results_v2(actual(left), expected(right, row_order="ordered" if ordered else "multiset"))
    assert result["match"] is wanted


def test_unspecified_alias_fix_is_explicit_and_frozen_v1_stays_strict():
    output = actual([[6]], ["COUNT(*)"])
    target = {"columns": ["pairs"], "rows": [[6]]}
    assert compare_results(output, target) is False
    assert compare_results_v2(output, target)["match"] is False
    relaxed = compare_results_v2(output, target, columns_required=False)
    assert relaxed["match"] is True
    assert relaxed["column_names_match"] is False
    assert compare_results_v2(actual([[6, 6]], ["a", "b"]), target, columns_required=False)["match"] is False


def test_tolerance_matching_uses_complete_assignment_not_greedy():
    # Greedy incorrectly consumes 0 for .1, although .1->.2 and 0->0 matches.
    output = actual([[.1], [0]])
    target = expected([[0], [.2]], numeric_abs_tolerance=.11)
    assert compare_results(output, target) is False
    assert compare_results_v2(output, target)["match"] is True
    assert compare_results_v2(actual([[.1], [0], [0]]), expected([[0], [.2], [.3]], numeric_abs_tolerance=.11))["match"] is False


def test_relative_tolerance_is_explicit_and_nonfinite_rejected():
    assert compare_results_v2(actual([[1_000_000.01]]), expected([[1_000_000]], numeric_abs_tolerance=1e-9))["match"] is False
    assert compare_results_v2(actual([[1_000_000.01]]), expected([[1_000_000]], numeric_rel_tolerance=1e-7))["match"] is True
    assert compare_results_v2(actual([[float("inf")]]), expected([[float("inf")]]))["match"] is False
    with pytest.raises(ValueError):
        compare_results_v2(actual([[1]]), expected([[1]], numeric_abs_tolerance=-1))


def test_query_that_executes_but_answers_different_intent_is_not_correct():
    case = next(case for case in authored_cases() if case["id"] == "N05")
    raw = json.dumps({"sql": "SELECT COUNT(*) AS row_count, COUNT(*) AS value_count FROM readings"})
    grade = grade_response(case, case["oracle"], raw)
    assert grade["actual"]["status"] == "executed"
    assert grade["status"] == "incorrect_result"
    assert grade["actual"]["rows"] == [[4, 4]]


def test_oracle_reference_fields_never_reach_api_request():
    question = next(case for case in authored_cases() if case["id"] == "N05")
    contaminated = {**question, "reference_sql": "REFERENCE_SENTINEL", "expected_rows": "EXPECTED_SENTINEL",
                    "oracle": {"reference_sql": "SECRET_SENTINEL"}, "notes": "PRIVATE_NOTES_SENTINEL"}
    body = request_body(contaminated, "model_only", "request", adapter="base")
    wire = json.dumps(body, ensure_ascii=False)
    assert "SENTINEL" not in wire
    assert '"oracle"' not in wire and '"expected"' not in wire and '"reference_sql"' not in wire
    assert body["verification_mode"] == "model_only" and body["use_rag"] is False
    assert "query" not in body["problem"]
    assert request_body(question, "rag_only", "r")["use_rag"] is True
    assert request_body(question, "rag_tools", "r")["verification_mode"] == "tools"


def test_given_sql_is_public_problem_but_reference_answer_is_not():
    case = next(case for case in authored_cases() if case["id"] == "N06")
    body = request_body(case, "rag_tools", "request")
    assert case["question_sql"] in body["content"]
    assert body["problem"]["query"] == case["question_sql"]
    assert "reference_sql" not in json.dumps(body)
    assert case["oracle"]["expected"]["rows"] != body["problem"]["tables"][0]["rows"]


def test_frozen_new12_oracles_execute_independently_and_cannot_be_silently_changed(tmp_path):
    manifest = freeze_diagnostics(tmp_path)
    assert manifest["categories"] == {"concept": 4, "query": 6, "missing_or_dbms": 2}
    assert len(manifest["reference_replay"]) == 6
    assert all(item["comparison"]["match"] for item in manifest["reference_replay"])
    assert freeze_diagnostics(tmp_path) == manifest
    questions = json.loads((tmp_path / "questions.json").read_text(encoding="utf-8"))
    assert all("oracle" not in item for item in questions["questions"])
    (tmp_path / "questions.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen diagnostics changed"):
        freeze_diagnostics(tmp_path)


def test_concept_keyword_hits_never_become_human_or_correctness_pass():
    case = authored_cases()[0]
    grade = grade_response(case, case["oracle"], "DDL DML INSERT ALTER TABLE")
    assert grade["status"] == "rubric_review_pending"
    assert grade["human_review"] == "not_reviewed"


def test_aliases_cte_and_count_star_execute_without_naive_name_rejection():
    fixture = {"tables": [{"name": "sample", "columns": [{"name": "v", "type": "INTEGER"}], "rows": [[1], [None], [3]]}]}
    result = execute_sql("WITH x AS (SELECT v AS value FROM sample) SELECT COUNT(*) AS all_rows, COUNT(value) AS present FROM x", fixture)
    assert result == {"status": "executed", "columns": ["all_rows", "present"], "rows": [[3, 2]]}
    assert execute_sql("SELECT total_rows FROM sample", fixture)["status"] == "error"


def test_sql_execution_error_is_distinct_from_wrong_values():
    case = authored_cases()[4]
    grade = grade_response(case, case["oracle"], json.dumps({"sql":"SELECT absent_column FROM readings"}))
    assert grade["status"] == "execution_error"
    assert grade["actual"]["status"] == "error"


def test_model_grade_never_substitutes_corrected_app_content():
    case = authored_cases()[4]
    good = json.dumps({"sql":case["oracle"]["reference_sql"]})
    assert grade_raw_model(case,case["oracle"],{"content":good})["status"] == "raw_output_unavailable"
    assert grade_raw_model(case,case["oracle"],{"content":good,"raw_model_response":good,
        "generation_snapshot":{"finish_reason":"length"}})["status"] == "truncated_or_incomplete"
    assert grade_raw_model(case,case["oracle"],{"content":"changed","raw_model_response":good,
        "generation_snapshot":{"finish_reason":"eos"}})["status"] == "correct_result"
    assert grade_app_response(case,case["oracle"],{"content":good,
        "generation_snapshot":{"finish_reason":"length"}})["status"] == "truncated_or_incomplete"


def test_tool_correct_values_need_actual_display_and_sql_requested_task():
    case = authored_cases()[4]
    evidence = {"status":"verified","sql":case["oracle"]["reference_sql"],
                "result":{"columns":["row_count","value_count"],"rows":[[4,3]]}}
    table = "원본 입력으로 계산했습니다.\nrow_count | value_count\n4 | 3"
    # A correct table alone does not answer a request to write SQL.
    assert grade_app_response(case,case["oracle"],{"evidence":evidence,"content":table})["status"] == "wrong_task_format"
    content=table+'\n```sql\n'+evidence["sql"]+'\n```'
    assert grade_app_response(case,case["oracle"],{"evidence":evidence,"content":content})["status"] == "correct_result"
    assert grade_app_response(case,case["oracle"],{"evidence":evidence,"content":content.replace('4 | 3','4 | 4')})["status"] == "display_mismatch"


def test_clarification_and_safe_stop_are_not_counted_as_correct_result():
    case=authored_cases()[4]
    assert grade_app_response(case,case["oracle"],{"evidence":{"status":"needs_input","reasons":["표 필요"]}})["status"] == "clarification_needed"
    assert grade_app_response(case,case["oracle"],{"evidence":{"status":"stopped","reasons":["지원 범위 밖"]}})["status"] == "safe_stop"


def test_explicit_v2_regrades_json_fence_without_changing_original_contract():
    case=authored_cases()[6]
    raw='```json\n'+json.dumps({'sql':case['oracle']['reference_sql']})+'\n```'
    assert grade_response(case,case['oracle'],raw)['status']=='ungradable_format'
    assert grade_response(case,case['oracle'],raw,grading_protocol='json_fence_v2')['status']=='correct_result'
    # Extracting a complete JSON fence does not make an incorrect query correct.
    bad='```json\n'+json.dumps({'sql':'SELECT COUNT(*) AS n FROM visits'})+'\n```'
    assert grade_response(case,case['oracle'],bad,grading_protocol='json_fence_v2')['status']=='incorrect_result'


def test_v2_does_not_turn_query_echo_or_incomplete_output_into_answer():
    case=authored_cases()[5]
    echoed='```json\n'+json.dumps({'sql':case['question_sql']})+'\n```'
    assert grade_response(case,case['oracle'],echoed,grading_protocol='json_fence_v2')['status']=='ungradable_format'
    sql_case=authored_cases()[6]
    raw='```json\n'+json.dumps({'sql':sql_case['oracle']['reference_sql']})+'\n```'
    answer={'raw_model_response':raw,'generation_snapshot':{'finish_reason':'length_or_timeout'}}
    assert grade_raw_model(sql_case,sql_case['oracle'],answer,grading_protocol='json_fence_v2')['status']=='truncated_or_incomplete'


def test_v2_saved_raw_candidate_does_not_relabel_actual_app_safe_stop():
    case=authored_cases()[6]
    raw='```json\n'+json.dumps({'sql':case['oracle']['reference_sql']})+'\n```'
    answer={'raw_model_response':raw,'generation_snapshot':{'finish_reason':'eos'},
            'content':'확인 필요: 지원 범위 밖','evidence':{'status':'stopped','reasons':['지원 범위 밖']}}
    assert grade_raw_model(case,case['oracle'],answer,grading_protocol='json_fence_v2')['status']=='correct_result'
    assert grade_app_response(case,case['oracle'],answer,grading_protocol='json_fence_v2')['status']=='safe_stop'
