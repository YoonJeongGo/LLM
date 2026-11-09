"""Development cases after actual N01/N02 failure disclosure, not new holdouts."""
import copy
import json
from pathlib import Path

import pytest

from edu_tutor.problems.models import normalize_problem, infer_basic_intent
from edu_tutor.problems.evidence import verify_answer, intent_sql, display_answer, intent_unavailable_status
from edu_tutor.problems.app_correction import verify_with_app_correction
from edu_tutor.lessons.verified import generate_verified_plan
from edu_tutor.evaluation.sql_sandbox import execute_sql, compare_results
from edu_tutor.problems.evidence import fixture
from edu_tutor.problems.explanation_requests import requested_explanations


def specimen(question, *, table="measurements", value="amount", flag="enabled", group="batch", name="code", state="phase"):
    return normalize_problem({"task_kind":"write_sql","raw_text":question,"confirmed":True,
        "tables":[{"name":table,"columns":[{"name":name,"type":"TEXT"},{"name":value,"type":"INTEGER"},
            {"name":flag,"type":"INTEGER"},{"name":group,"type":"INTEGER"},{"name":state,"type":"TEXT"}],
            "rows":[["one",None,1,2,"open"],["two",0,0,1,"open"],["three",-7,0,3,"open"],
                    ["four",8,1,2,"closed"],["five",12,1,3,"open"]]}]})


def assert_intent(p, expected_sql):
    inferred,reason=infer_basic_intent(p,p["raw_text"])
    assert inferred is not None,reason
    e=verify_answer(p,json.dumps({"sql":expected_sql}),p["raw_text"])
    assert e["status"]=="verified",e
    assert e["calculation"]["status"]=="independent_projection_match"
    return inferred,e


@pytest.mark.parametrize("names,threshold",[
    (("measurements","amount","enabled","batch","code"),-2),
    (("inventory","units","urgent","section","tag"),3),
    (("sensors","reading","active","tier","sensor"),0),
])
def test_complete_sentences_generalize_schema_names_and_numeric_values(names,threshold):
    t,v,f,g,n=names
    q=(f"SQLite에서 {t}를 조회해 줘. {v}가 {threshold}보다 작거나 {f}가 1인 행을 고르고, "
       f"{n}, {v}, {g} 열을 이 순서로 보여 줘. {g}은 오름차순, 같은 {g}에서는 {v} 내림차순, "
       f"둘 다 같으면 {n} 내림차순으로 정렬해 줘. 원본 행이 조건을 통과하는 과정과 최종 순서를 설명해 줘.")
    p=specimen(q,table=t,value=v,flag=f,group=g,name=n)
    before=copy.deepcopy(p)
    _,e=assert_intent(p,f"SELECT {n},{v},{g} FROM {t} WHERE {v} < {threshold} OR {f}=1 ORDER BY {g},{v} DESC,{n} DESC")
    lesson=generate_verified_plan({"id":"cpu","problem":p,"evidence":e,"content":display_answer(e)},q,"cpu-plan")
    assert lesson["speech_allowed"],lesson
    assert p==before


@pytest.mark.parametrize("threshold",[2,7,11])
def test_nested_row_scope_preserves_and_parenthesized_or_and_text_value(threshold):
    q=(f"measurements에서 phase가 open이고 amount가 NULL이 아닌 행 중, amount가 0이거나 {threshold} 이상인 행을 찾아 줘. "
       "출력 열은 code, amount, batch야. batch 내림차순, 그 안에서는 amount 오름차순, "
       "두 값이 같으면 code 오름차순으로 정렬하는 SQLite SQL과 원본에서 결과까지의 과정을 설명해 줘.")
    p=specimen(q)
    intent,e=assert_intent(p,f"SELECT code,amount,batch FROM measurements WHERE phase='open' AND amount IS NOT NULL AND (amount=0 OR amount>={threshold}) ORDER BY batch DESC,amount,code")
    lesson=generate_verified_plan({"id":"cpu","problem":p,"evidence":e,"content":display_answer(e)},q,"cpu-plan")
    assert lesson["speech_allowed"],lesson
    assert not lesson["explanation_fulfillment"]["requested"]
    bad=f"SELECT code,amount,batch FROM measurements WHERE phase='open' AND amount IS NOT NULL AND amount IN (0,{threshold}) ORDER BY batch DESC,amount,code"
    rejected=verify_answer(p,json.dumps({"sql":bad}),q)
    assert rejected["intent"]["status"]=="mismatch" and rejected["status"]=="stopped"
    corrected=verify_with_app_correction(p,json.dumps({"sql":bad}),q)
    assert corrected["status"]=="verified" and corrected["sql_origin"]=="application_correction_from_confirmed_bounded_intent"
    assert corrected["app_correction"]["original_candidate"]["intent"]["status"]=="mismatch"
    for predicate in (f"phase='open' AND amount IS NOT NULL AND amount=0 OR amount>={threshold}",
                      f"phase='open' AND amount IS NOT NULL AND (amount=0 AND amount>={threshold})"):
        wrong_grouping=f"SELECT code,amount,batch FROM measurements WHERE {predicate} ORDER BY batch DESC,amount,code"
        checked=verify_answer(p,json.dumps({"sql":wrong_grouping}),q)
        assert checked["status"]=="stopped" and checked["intent"]["status"]=="mismatch"


@pytest.mark.parametrize("phrase,expected",[
    ("amount가 0보다 크거나 같은", "amount>=0"),
    ("amount가 0보다 작거나 같은", "amount<=0"),
    ("amount가 0보다 작거나 enabled가 1인", "amount<0 OR enabled=1"),
    ("amount가 0보다 크고 enabled가 1인", "amount>0 AND enabled=1"),
    ("amount가 0보다 크거나 같고 enabled가 1인", "amount>=0 AND enabled=1"),
    ("amount가 0이 아닌", "amount<>0"),
    ("phase가 'closed'가 아닌", "phase<>'closed'"),
    ("amount가 0이거나 8 이상인", "amount=0 OR amount>=8"),
])
def test_comparative_connectors_inclusive_comparison_and_negation(phrase,expected):
    q=f"출력: code; 행 조건: {phrase}; 정렬: code ASC"
    p=specimen(q)
    assert_intent(p,f"SELECT code FROM measurements WHERE {expected} ORDER BY code")


@pytest.mark.parametrize("condition",["amount >=","amount가 0보다","amount가", "amount가 0보다 크거나"])
def test_actually_missing_operand_or_boolean_side_stays_needs_input(condition):
    p=specimen(f"출력: code; 행 조건: {condition}; 정렬: code ASC")
    value,reason=infer_basic_intent(p,p["raw_text"])
    assert value is None and intent_unavailable_status(reason)=="needs_input",reason


@pytest.mark.parametrize("ordering",[
    "batch 오름차순, 둘 다 같으면 code 내림차순",
    "batch 오름차순, 같은 amount에서는 code 내림차순",
    "그 안에서는 amount 내림차순, code 오름차순",
    "batch 오름차순, amount 내림차순, code 오름차순, 두 값이 같으면 enabled 내림차순",
])
def test_ambiguous_tie_reference_is_not_discarded(ordering):
    q=f"출력 열은 code, amount야. {ordering}으로 정렬해 줘."
    p=specimen(q)
    value,reason=infer_basic_intent(p,q)
    assert value is None and intent_unavailable_status(reason)=="needs_input",reason


@pytest.mark.parametrize("suffix",[
    "단 enabled는 0인 것만 보여 줘.", "추가로 상위 1개만 보여 줘.",
    "원본 행이 조건을 통과하는 과정과 최종 순서를 설명하되 batch가 2인 것만 보여 줘.",
])
def test_extra_requirements_after_complete_sentences_are_not_silently_trimmed(suffix):
    q="출력 열은 code, amount야. amount 내림차순으로 정렬해 줘. "+suffix
    value,reason=infer_basic_intent(specimen(q),q)
    assert value is None and "미지원" in reason


def test_unsupported_sentence_is_not_labeled_as_missing_student_values():
    q="출력 열은 code, amount야. 값을 삼각파 방식으로 묶어서 정렬해 줘."
    value,reason=infer_basic_intent(specimen(q),q)
    assert value is None and intent_unavailable_status(reason)=="unsupported"


def test_words_inside_quoted_source_value_do_not_become_clause_boundaries():
    q="출력: code; 행 조건: phase = '행 중. 그리고 크거나 같다'; 정렬: code ASC"
    intent,_=infer_basic_intent(specimen(q),q)
    assert intent["where"]=="phase = '행 중. 그리고 크거나 같다'"


def test_initial_null_predicate_is_not_a_comparison_request_but_explicit_comparison_is():
    plain="amount가 NULL이 아닌 행을 골라 원본에서 결과까지의 과정을 설명해 줘."
    assert "null_comparison" not in requested_explanations(plain)["requested"]
    explicit=plain+" NULL과 0의 차이도 설명해 주세요."
    assert {"null_comparison","zero_comparison"} <= set(requested_explanations(explicit)["requested"])


def test_unquoted_word_equal_to_source_column_is_not_guessed_as_text_literal():
    q="출력: code; 행 조건: phase가 code인; 정렬: code ASC"
    intent,reason=infer_basic_intent(specimen(q),q)
    assert intent is None and "문자값인지 다른 원본 열인지" in reason
    assert intent_unavailable_status(reason)=="needs_input"
    quoted="출력: code; 행 조건: phase가 'code'인; 정렬: code ASC"
    assert_intent(specimen(quoted),"SELECT code FROM measurements WHERE phase='code' ORDER BY code")


@pytest.mark.parametrize("case",["N01","N02"])
def test_saved_actual_failure_question_and_response_remain_unchanged(case):
    path=Path(__file__).resolve().parents[1]/f"runs/v021-r3-repair/20261030/student/repair-new-final02/{case}/actual.json"
    original=path.read_bytes();saved=json.loads(original)
    m=next(m for m in saved["actual_messages"] if m["role"]=="assistant")
    p=m["problem"];raw=m["raw_model_response"]
    e=verify_with_app_correction(p,raw,p["raw_text"])
    assert e["status"]=="verified",e
    if case=="N01":
        assert e["intent"]["status"]=="supported_match" and "app_correction" not in e
    else:
        assert e["app_correction"]["original_candidate"]["intent"]["status"]=="mismatch"
        assert e["app_correction"]["candidate_matches_current_fixture_result"] is True
        changed=copy.deepcopy(p);changed["tables"][0]["rows"].append(["DEV_COUNTEREXAMPLE",6,9,"ready"])
        checked=verify_with_app_correction(changed,raw,p["raw_text"])
        assert checked["app_correction"]["model_answer_status"]=="wrong_on_confirmed_fixture"
        assert checked["app_correction"]["candidate_matches_current_fixture_result"] is False
        assert checked["app_correction"]["original_candidate"]["status"]=="stopped"
    lesson=generate_verified_plan({**m,"evidence":e,"content":display_answer(e)},p["raw_text"],"saved-development-plan")
    assert lesson["speech_allowed"],lesson
    assert path.read_bytes()==original
