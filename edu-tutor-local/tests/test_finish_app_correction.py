"""A model error stays a model error even when the app derives an answer."""
import copy
import json

import pytest

from edu_tutor.problems.models import normalize_problem
from edu_tutor.problems.app_correction import verify_with_app_correction
from edu_tutor.problems.evidence import verify_answer, display_answer
from edu_tutor.lessons.verified import generate_verified_plan
from edu_tutor.lessons.plans import scene_at


def core_evidence(value):
    value=copy.deepcopy(value)
    value.pop("timings_seconds",None)
    value.pop("raw_model_explanation",None)
    return value


def problem(rows, *, name="samples", col="measure", function="COUNT", distinct=True):
    question = f"{function}({'DISTINCT ' if distinct else ''}{col})를 구하는 SQL을 작성해 주세요."
    return normalize_problem({"task_kind":"write_sql", "dialect":"sqlite", "confirmed":True,
        "raw_text":question, "tables":[{"name":name, "columns":[{"name":col,"type":"INTEGER"}],
            "rows":[[v] for v in rows]}]})


@pytest.mark.parametrize("rows,expected", [([4,None,4,0,-2],3),([],0),([None,None],0),([0,0],1),([-3,-3,2],2)])
def test_distinct_is_derived_from_input_and_raw_failure_is_preserved(rows, expected):
    p=problem(rows); before=copy.deepcopy(p)
    raw=json.dumps({"sql":"SELECT COUNT(measure) FROM samples", "explanation":"모두 999입니다."})
    original=verify_answer(p,raw,p["raw_text"])
    checked=verify_with_app_correction(p,raw,p["raw_text"])
    assert original["status"]=="stopped" and original["intent"]["status"]=="mismatch"
    assert checked["status"]=="verified" and checked["result"]["rows"]==[[expected]]
    assert core_evidence(checked["app_correction"]["original_candidate"])==core_evidence(original)
    assert checked["app_correction"]["new_model_calls"]==0
    assert "질문 의도" in display_answer(checked) and "앱이 확인된 연산" in display_answer(checked)
    assert p==before
    message={"id":"test-answer","problem":p,"evidence":checked,"content":display_answer(checked),"raw_model_response":raw}
    lesson=generate_verified_plan(message,p["raw_text"],"test-lesson")
    assert lesson["speech_allowed"] and lesson["plan"]["provenance"]=="tool_derived"
    assert "999" not in " ".join(step["speech"] for step in lesson["plan"]["steps"])
    scene=scene_at(lesson["plan"],len(lesson["plan"]["steps"])-1)
    assert scene["elements"][checked["id"]+"-result"]["rows"]==[[expected]]


@pytest.mark.parametrize("function,expected", [("COUNT",3),("SUM",-6),("AVG",-2),("MIN",-5),("MAX",0)])
def test_names_values_and_operations_are_not_fixed(function,expected):
    p=problem([-5,None,-1,0],name="new_data",col="offset",function=function,distinct=False)
    raw=json.dumps({"sql":"SELECT COUNT(*) FROM new_data"})
    checked=verify_with_app_correction(p,raw,p["raw_text"])
    assert checked["result"]["rows"]==[[expected]] and checked["app_correction"]


@pytest.mark.parametrize("mutation", ["condition","group","ordering","unknown_column","syntax","unsafe","unconfirmed","missing","other_dbms","given_query","mixed_type"])
def test_unproved_or_unsafe_case_remains_stopped(mutation):
    p=problem([1,None,1]); sql="SELECT COUNT(measure) FROM samples"
    if mutation=="condition":p["raw_text"]+=" measure가 2 이상인 행만."
    if mutation=="group":p["raw_text"]+=" measure별로."
    if mutation=="ordering":p["raw_text"]+=" 내림차순으로."
    if mutation=="unknown_column":sql="SELECT COUNT(absent) FROM samples"
    if mutation=="syntax":sql="SEL COUNT(measure) samples"
    if mutation=="unsafe":sql+="; DELETE FROM samples"
    if mutation=="unconfirmed":p["confirmed"]=False
    if mutation=="missing":p["missing_conditions"]=["잘린 조건"]
    if mutation=="other_dbms":p["dialect"]="oracle"
    if mutation=="given_query":p.update(task_kind="query_result",query="SELECT COUNT(measure) FROM samples")
    if mutation=="mixed_type":
        p["raw_text"]="MIN(measure)를 구하는 SQL을 작성해 주세요."
        p["tables"][0]["columns"][0]["type"]="TEXT"
        p["tables"][0]["rows"]=[["a"],["b"]]
    raw=json.dumps({"sql":sql})
    original=verify_answer(p,raw,p["raw_text"])
    checked=verify_with_app_correction(p,raw,p["raw_text"])
    assert core_evidence(checked)==core_evidence(original) and "app_correction" not in checked


def test_already_correct_answer_and_raw_model_are_unchanged():
    p=problem([1,None,1]); raw=json.dumps({"sql":"SELECT COUNT(DISTINCT measure) FROM samples"})
    assert core_evidence(verify_with_app_correction(p,raw,p["raw_text"]))==core_evidence(verify_answer(p,raw,p["raw_text"]))
