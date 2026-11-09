"""CPU only: source data is not a predicate; SQL still needs intent evidence."""
import copy
import json

import pytest

from edu_tutor.lessons.plans import scene_at
from edu_tutor.lessons.verified import generate_verified_plan
from edu_tutor.problems.evidence import display_answer, verify_answer
from edu_tutor.problems.models import intent_question_text, normalize_problem
from edu_tutor.problems.pipeline import model_messages


def sample(question="전체 행 수와 amount가 NULL이 아닌 행 수를 차례대로 구하는 SQL을 작성해 줘."):
    table={"name":"readings", "columns":[{"name":"person","type":"TEXT"},
        {"name":"amount","type":"INTEGER"},{"name":"rank_value","type":"INTEGER"}],
        "rows":[["우림",17,1],["노아",None,2],["도담",17,3],["시온",29,4]]}
    declaration="readings(person,amount,rank_value)="+json.dumps(table["rows"],ensure_ascii=False)
    return normalize_problem({"task_kind":"write_sql","dialect":"sqlite","confirmed":True,
        "raw_text":"DBMS: SQLite.\n"+declaration+"\n"+question,"tables":[table]})


def answer(problem,sql):
    return verify_answer(problem,json.dumps({"sql":sql,"explanation":"untrusted prose 999"}),problem["raw_text"])


def test_one_sql_answer_becomes_two_complete_shared_evidence_steps_without_model_plan():
    problem=sample(); original=copy.deepcopy(problem)
    sql="SELECT COUNT(*) AS n, COUNT(amount) AS available FROM readings"
    evidence=answer(problem,sql)
    assert evidence["status"]=="verified" and evidence["result"]["rows"]==[[4,3]]
    lesson=generate_verified_plan({"id":"answer","problem":problem,"evidence":evidence,
        "content":display_answer(evidence)},problem["raw_text"],"lesson")
    assert lesson["speech_allowed"] and lesson["generation"]["model_plan_calls"]==0
    plan=lesson["plan"]
    assert len(plan["steps"])==2
    assert all(len(s["speech"])<=80 and s["speech"].endswith(".") for s in plan["steps"])
    assert "4" in plan["steps"][0]["speech"] and "3" in plan["steps"][1]["speech"]
    assert "999" not in " ".join(s["speech"] for s in plan["steps"])
    first,last=scene_at(plan,0),scene_at(plan,1)
    assert first["elements"][evidence["working_tables"][0]["id"]]["rows"]==problem["tables"][0]["rows"]
    assert first["elements"][evidence["id"]+"-sql"]["code"]==sql
    assert last["elements"][evidence["id"]+"-result"]["rows"]==[[4,3]]
    assert problem==original
    prompt=model_messages(problem["raw_text"],problem,[])
    assert declaration_of(problem) in prompt[1]["content"]
    assert "SELECT COUNT" not in prompt[1]["content"]


def declaration_of(problem):
    return problem["raw_text"].splitlines()[1]


@pytest.mark.parametrize("alteration",["different_rows","different_columns","trailing_predicate","malformed_json"])
def test_mismatched_or_malformed_declarations_are_not_dropped(alteration):
    problem=sample(); text=problem["raw_text"]
    if alteration=="different_rows":text=text.replace("29","30")
    if alteration=="different_columns":text=text.replace("person,amount,rank_value","person,rank_value,amount")
    if alteration=="trailing_predicate":text=text.replace("\n전체", " amount >= 20\n전체")
    if alteration=="malformed_json":text=text.replace("null","NULL")
    separated=intent_question_text(problem,text)
    if alteration=="trailing_predicate":
        # Exact original rows may be excluded even on an inline question, but
        # the appended WHERE-like request must still block an unfiltered answer.
        assert 'amount >= 20' in separated
        assert declaration_of(problem) not in separated
    else:
        assert separated==text
    problem["raw_text"]=text
    assert answer(problem,"SELECT COUNT(*),COUNT(amount) FROM readings")["status"]!="verified"


@pytest.mark.parametrize("question",[
    "amount가 20 이상인 행 수를 구해 줘.",
    "우림의 amount 평균을 구해 줘.",
    "person이 UNKNOWN인 행만 대상으로 COUNT(*), SUM(amount)를 구해 줘.",
    "rank_value별로 COUNT(amount)를 구해 줘.",
    "amount 평균을 반올림해 줘.",
])
def test_data_removal_does_not_remove_real_request_conditions(question):
    problem=sample(question)
    assert question in intent_question_text(problem,problem["raw_text"])
    assert answer(problem,"SELECT COUNT(*),COUNT(amount) FROM readings")["status"]!="verified"


def test_wrong_null_count_swapped_projection_and_extra_filter_remain_blocked():
    problem=sample()
    for sql in ["SELECT COUNT(*),COUNT(*) FROM readings", "SELECT COUNT(amount),COUNT(*) FROM readings",
                "SELECT COUNT(*),COUNT(amount) FROM readings WHERE amount IS NOT NULL"]:
        evidence=answer(problem,sql)
        assert evidence["execution"]["status"]=="executed"
        assert evidence["status"]=="stopped" and evidence["intent"]["status"]=="mismatch"


def test_korean_particle_selects_explicit_column_among_multiple_numeric_columns():
    problem=sample("amount의 평균을 구해 줘.")
    assert answer(problem,"SELECT AVG(amount) FROM readings")["status"]=="verified"
    assert answer(problem,"SELECT AVG(rank_value) FROM readings")["status"]=="stopped"


def test_explicit_group_column_and_unseen_filter_are_not_lost_with_data_removed():
    problem=sample("rank_value별로 COUNT(amount)를 구해 줘.")
    assert answer(problem,"SELECT COUNT(amount) FROM readings")["status"]=="stopped"
    problem=sample("person이 UNKNOWN인 행만 대상으로 COUNT(*), SUM(amount)를 구해 줘.")
    assert answer(problem,"SELECT COUNT(*), SUM(amount) FROM readings")["status"]=="stopped"


def test_dialect_and_unsafe_sql_guards_are_unchanged():
    problem=sample();problem["dialect"]="oracle"
    assert answer(problem,"SELECT COUNT(*),COUNT(amount) FROM readings")["status"]=="unsupported"
    problem["dialect"]="sqlite"
    evidence=answer(problem,"SELECT COUNT(*),COUNT(amount) FROM readings; DELETE FROM readings")
    assert evidence["status"]=="stopped" and evidence["execution"]["status"]!="executed"
