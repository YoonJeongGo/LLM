"""Narrow missing-threshold classification regression; no actual generation."""
import json
from pathlib import Path
import pytest
from edu_tutor.problems.models import normalize_problem, infer_basic_intent
from edu_tutor.problems.intent_language import _condition
from edu_tutor.problems.evidence import intent_unavailable_status


def problem(question,column="qty"):
    return normalize_problem({"task_kind":"write_sql","raw_text":question,"confirmed":True,
        "tables":[{"name":"stock","columns":[{"name":"item","type":"TEXT"},{"name":column,"type":"INTEGER"}],
                   "rows":[["a",-2],["b",9]]}]})


@pytest.mark.parametrize("column",["qty","amount"])
@pytest.mark.parametrize("adjective",["큰","작은"])
def test_named_column_bare_comparison_requests_actual_missing_threshold(column,adjective):
    q=f"{column}가 {adjective} 행만 item과 {column}로 보여 주고 item 오름차순으로 정렬해 줘."
    intent,reason=infer_basic_intent(problem(q,column),q)
    assert intent is None and intent_unavailable_status(reason)=="needs_input",reason
    assert "기준값이 빠졌" in reason


@pytest.mark.parametrize("expression",["qty가 평균보다 큰","qty가 평균보다 작은"])
def test_out_of_scope_derived_threshold_is_not_called_missing(expression):
    q=f"출력: item; 행 조건: {expression}; 정렬: item ASC"
    intent,reason=infer_basic_intent(problem(q),q)
    assert intent is None and intent_unavailable_status(reason)=="unsupported",reason


@pytest.mark.parametrize("value",[-4,0,6])
@pytest.mark.parametrize("adjective,operator",[("큰",">"),("작은","<")])
def test_explicit_threshold_preserves_existing_condition(value,adjective,operator):
    q=f"출력: item; 행 조건: qty가 {value}보다 {adjective}; 정렬: item ASC"
    p=problem(q)
    assert _condition(f"qty가 {value}보다 {adjective}",p["tables"][0])==f"qty {operator} {value}"
    intent,reason=infer_basic_intent(p,q)
    assert intent is not None,reason
    assert intent["where"]==f"qty {operator} {value}"


def test_disclosed_boundary_original_question_is_not_rewritten():
    path=Path(__file__).resolve().parents[1]/"runs/v021-r3-repair/20261030/evaluation/cpu-boundaries-development-final03.json"
    before=path.read_bytes()
    case=next(c for c in json.loads(before)["cases"] if c["id"]=="C04")
    q=case["question"]
    intent,reason=infer_basic_intent(problem(q),q)
    assert intent is None and intent_unavailable_status(reason)=="needs_input",reason
    assert path.read_bytes()==before
