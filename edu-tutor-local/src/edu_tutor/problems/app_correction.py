"""Derive a bounded app calculation without relabelling a model error.

This path only uses an intent independently extracted from the confirmed
question. It cannot repair an unknown intent, syntax error, missing schema,
unsupported trace or a student-supplied SQL question. The v2 extension retains
the requested projection, predicates, grouping and order as one checked unit.
"""
from __future__ import annotations

import copy
import hashlib
import json

from .evidence import intent_sql, verify_answer
from .models import canonical, infer_basic_intent
from .response_claims import audit_model_explanation
from edu_tutor.evaluation.sql_sandbox import compare_results


def verify_with_app_correction(problem, raw_response, question, hypothesis=None):
    original = verify_answer(problem, raw_response, question, hypothesis)
    original['raw_model_explanation'] = audit_model_explanation(raw_response, original)
    if (problem.get("task_kind") != "write_sql" or hypothesis is not None
            or original.get("status") != "stopped"
            or original.get("execution", {}).get("status") != "executed"
            or original.get("intent", {}).get("status") != "mismatch"
            or original["intent"].get("scope") not in {
                "bounded_language_aggregate", "bounded_language_select_v2", "bounded_language_aggregate_v2"}):
        return original
    requested, scope = infer_basic_intent(problem, problem["raw_text"])
    if (scope not in {"bounded_language_aggregate", "bounded_language_select_v2", "bounded_language_aggregate_v2"} or not requested
            or canonical(requested) != canonical(original["intent"].get("requested"))):
        return original
    # Never derive predicates from the failed model answer. Old aggregate
    # intents retain their original limit; v2 requires the complete parsed
    # student clauses and an independent trace of the reconstructed query.
    if scope == "bounded_language_aggregate" and any(requested.get(k) for k in ("where", "having", "group_by", "order_by")):
        return original
    corrected_sql = intent_sql(requested)
    checked = verify_answer(problem, json.dumps({"sql": corrected_sql}), question)
    if (checked.get("status") != "verified"
            or checked.get("calculation", {}).get("status") not in {"independent_aggregate_match", "independent_projection_match"}
            or not checked.get("logical_steps")):
        return original
    checked["sql_origin"] = "application_correction_from_confirmed_bounded_intent"
    checked['raw_model_explanation'] = copy.deepcopy(original['raw_model_explanation'])
    # Different normalized ASTs are not automatically proof that every
    # equivalent SQL formulation is wrong. Record the narrower fixture fact.
    reference = {"columns": original['execution'].get('columns', []),
        "rows": checked['execution']['rows'],
        "row_order": "ordered" if requested.get('order_by') else "unordered",
        "numeric_abs_tolerance": 1e-9}
    fixture_matches = (len(reference['columns']) == len(checked['execution']['columns'])
        and compare_results(original['execution'], reference))
    checked["app_correction"] = {
        "kind": "bounded_aggregate_reconstruction_v1" if scope == "bounded_language_aggregate" else "bounded_confirmed_select_reconstruction_v2",
        "new_model_calls": 0,
        "raw_model_response_sha256": hashlib.sha256(raw_response.encode("utf-8")).hexdigest(),
        "original_candidate": copy.deepcopy(original),
        "corrected_sql": corrected_sql,
        "reason": "모델 SQL의 집계 의도 불일치를 보존하고, 확정한 질문의 집계 구조에서 앱이 별도 계산했습니다.",
        "model_answer_status": "candidate_equivalence_not_established" if fixture_matches else "wrong_on_confirmed_fixture",
        "candidate_matches_current_fixture_result": fixture_matches,
        "equivalence_notice": "한 표의 값 일치만으로 원문의 의도와 동치라고 승인하지 않습니다. AST가 다르다는 이유만으로 모든 동치 표현을 오답이라고 단정하지도 않습니다.",
        "scope": "조건·그룹·정렬 없는 단일 표 집계; SQLite와 독립 중간 계산 모두 일치" if scope == "bounded_language_aggregate" else
            "학생 원문에서 확인한 단일 표 출력·조건·그룹·정렬; SQLite와 독립 중간 계산 모두 일치",
    }
    return checked
