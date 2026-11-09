"""CPU-only proof/teaching checks for existing direct aggregate lessons."""
import copy
import json

import pytest

from edu_tutor.lessons.plans import scene_at
from edu_tutor.lessons.verified import generate_verified_plan, validated_logical_stage
from edu_tutor.problems.evidence import display_answer, verify_answer
from edu_tutor.problems.models import normalize_problem


def prepared(values=None, expressions=None, table_name="measurements", column="reading"):
    values=[8,None,0,-2,8] if values is None else values
    expressions=expressions or ["COUNT(*)",f"COUNT({column})",f"SUM({column})"]
    question="직접 작성한 개발 예시의 집계 과정을 설명해 주세요."
    problem=normalize_problem({"task_kind":"query_result","raw_text":question,"confirmed":True,
        "query":f"SELECT {', '.join(expressions)} FROM {table_name}",
        "tables":[{"name":table_name,"columns":[{"name":"label","type":"TEXT"},{"name":column,"type":"REAL"}],
            "rows":[[f"row-{i}",value] for i,value in enumerate(values)]}]})
    evidence=verify_answer(problem,"CPU raw draft 999",question)
    assert evidence["status"]=="verified" and evidence["logical_steps"]
    source={"id":"a"*32,"session_id":"b"*32,"problem":problem,"evidence":evidence,
        "content":display_answer(evidence),"raw_model_response":"CPU raw draft 999"}
    record=copy.deepcopy({"id":"c"*32,"source_message_id":source["id"],
        **generate_verified_plan(source,question,"source-plan")})
    assert record["speech_allowed"]
    return source,record


def followup(source,record,index=1,row=2,selected_column=1):
    table=source["evidence"]["working_tables"][0]
    context={"lesson_id":record["id"],"step":index,"problem_revision":source["problem"]["revision"],
        "selected_cell":{"table_element_id":table["id"],"row_id":table["row_ids"][row],
            "column_id":table["column_ids"][selected_column],"cell_id":table["cell_ids"][row][selected_column],
            "value":999,"row_index":999,"column_index":999}}
    scope=validated_logical_stage(record,source,context)
    if scope:context["_verified_logical_stage"]=scope
    message=copy.deepcopy(source);message["id"]="d"*32;message["lesson_context"]=context
    return message


def explain(message):
    return generate_verified_plan(message,"왜 선택한 원본 행이 포함돼? NULL인 행과 비교해서 설명해 줘.","supplement")


def test_current_count_column_links_zero_to_one_and_actual_null_row_without_rewriting_source():
    source,record=prepared()
    before=copy.deepcopy((source,record))
    message=followup(source,record)
    scope=message["lesson_context"]["_verified_logical_stage"]
    assert scope["kind"]=="server_verified_direct_aggregate_plan_v1"
    assert scope["index"]==1 and scope["step_id"]=="s2" and scope["stage"]=="aggregate"
    assert scope["aggregate_key"]=={"function":"count","column":"reading","distinct":False}
    result=explain(message);unit=result["plan"]["steps"][0]
    assert "0은 NULL이 아니므로 값 한 개로 셉니다" in unit["speech"]
    assert "원본 2행은 NULL이므로 세지 않습니다" in unit["speech"]
    assert "COUNT(reading) 결과는 4" in unit["speech"]
    assert "COUNT(*)" not in unit["speech"] and "SUM(" not in unit["speech"] and "999" not in unit["speech"]
    scene=scene_at(result["plan"],0)
    table=source["evidence"]["working_tables"][0]
    cells=scene["highlights"][0]["cell_ids"]
    assert table["cell_ids"][2][1] in cells and table["cell_ids"][1][1] in cells
    assert scene["elements"][source["evidence"]["id"]+"-result"]["rows"]==source["evidence"]["result"]["rows"]
    assert (source,record)==before and message["raw_model_response"]=="CPU raw draft 999"


@pytest.mark.parametrize("count",[1,2,3])
def test_existing_direct_plan_lengths_bind_real_index_to_one_current_aggregate(count):
    expressions=["COUNT(*)","COUNT(reading)","SUM(reading)"][:count]
    source,record=prepared(expressions=expressions)
    for index,expression in enumerate(expressions):
        result=explain(followup(source,record,index=index))
        speech=result["plan"]["steps"][0]["speech"]
        assert expression in speech
        assert all(other not in speech for other in expressions if other!=expression)


@pytest.mark.parametrize("function,expected",[("COUNT(*)",5),("COUNT(reading)",4),("SUM(reading)",14),
    ("AVG(reading)",3.5),("MIN(reading)",-2),("MAX(reading)",8)])
def test_existing_aggregate_operations_use_executed_inputs_and_do_not_claim_zero_is_extreme(function,expected):
    source,record=prepared(expressions=[function]);result=explain(followup(source,record,index=0))
    unit=result["plan"]["steps"][0]
    assert source["evidence"]["result"]["rows"]==[[expected]] and str(expected) in unit["speech"]
    if function.startswith("SUM"):assert "0을 더하므로 합계는 변하지" in unit["speech"]
    if function.startswith("AVG"):assert "0을 합에 더하고 값의 개수에 한 개" in unit["speech"] and "4개로 나누면" in unit["speech"]
    if function.startswith(("MIN","MAX")):assert "비교 대상에 포함" in unit["speech"] and "0이 최솟값" not in unit["speech"]


@pytest.mark.parametrize("function",["COUNT","SUM","AVG","MIN","MAX"])
def test_all_null_input_does_not_invent_a_nonnull_or_zero_comparison(function):
    source,record=prepared(values=[None,None],expressions=[f"{function}(reading)"])
    speech=explain(followup(source,record,index=0,row=0))["plan"]["steps"][0]["speech"]
    assert "NULL이므로" in speech and "반면" not in speech
    assert ("결과는 0" in speech) if function=="COUNT" else ("결과는 NULL" in speech)
    assert "나누면" not in speech


def test_no_null_input_does_not_invent_an_actual_null_row_and_changed_names_use_data():
    source,record=prepared(values=[0,-5,-5],expressions=["COUNT(amount)"],table_name="other_source",column="amount")
    speech=explain(followup(source,record,index=0,row=0))["plan"]["steps"][0]["speech"]
    assert "COUNT(amount)" in speech and "0은 NULL이 아니므로 값 한 개" in speech
    assert "결과는 3" in speech and "반면 원본" not in speech and "reading" not in speech


@pytest.mark.parametrize("function",["COUNT","SUM","AVG","MIN","MAX"])
def test_distinct_repeated_value_uses_existing_trace_and_does_not_count_a_duplicate_again(function):
    source,record=prepared(values=[0,None,-2,0],expressions=[f"{function}(DISTINCT reading)"])
    first=explain(followup(source,record,index=0,row=0))["plan"]["steps"][0]["speech"]
    duplicate=explain(followup(source,record,index=0,row=3))["plan"]["steps"][0]["speech"]
    assert "한 번만 사용" in first and "집계 입력을 늘리지 않습니다" in duplicate
    assert "값 한 개로 셉니다" not in duplicate


def test_empty_table_cannot_supply_a_selected_source_row():
    source,record=prepared(values=[],expressions=["COUNT(reading)"])
    context={"lesson_id":record["id"],"step":0,"selected_cell":{"cell_id":"invented"}}
    context["_verified_logical_stage"]=validated_logical_stage(record,source,context)
    message={**source,"lesson_context":context}
    result=explain(message)
    assert result["plan"] is None and not result["speech_allowed"] and "선택한 셀" in result["reason"]


@pytest.mark.parametrize("mutation",["speech","board","row_ids","target","timing","source","revision","nested","foreign_lesson_source"])
def test_changed_saved_plan_or_source_cannot_get_direct_scope(mutation):
    source,record=prepared();record=copy.deepcopy(record)
    if mutation=="speech":record["plan"]["steps"][1]["speech"]="다른 설명"
    if mutation=="board":record["plan"]["steps"][0]["board_actions"][0]["rows"][0][1]=777
    if mutation=="row_ids":record["plan"]["steps"][0]["board_actions"][0]["row_ids"][0]="foreign"
    if mutation=="target":record["plan"]["steps"][1]["gesture"]["target_element_id"]="foreign"
    if mutation=="timing":record["plan"]["steps"][0]["board_actions"][0]["timing"]["end"]=.1
    if mutation=="source":record["plan"]["source_message_id"]="foreign"
    if mutation=="revision":record["plan"]["problem_revision"]+=1
    if mutation=="nested":source["lesson_context"]={"lesson_id":"previous"}
    if mutation=="foreign_lesson_source":record["source_message_id"]="foreign"
    assert validated_logical_stage(record,source,{"step":1}) is None


@pytest.mark.parametrize("index",[-1,3,True,1.0,"1",None])
def test_invalid_direct_step_never_maps_to_a_different_four_stage_scope(index):
    source,record=prepared()
    assert validated_logical_stage(record,source,{"step":index}) is None


@pytest.mark.parametrize("mutation",["reordered","different_key","different_id","different_step","different_problem","different_revision","foreign_source","wrong_row","wrong_column","wrong_table"])
def test_supplementary_evidence_and_selection_must_still_match_the_proved_current_aggregate(mutation):
    source,record=prepared();message=followup(source,record);scope=message["lesson_context"]["_verified_logical_stage"]
    if mutation=="reordered":message["evidence"]["logical_steps"]["aggregates"].reverse()
    if mutation=="different_key":scope["aggregate_key"]["function"]="sum"
    if mutation=="different_id":scope["aggregate_id"]="other-aggregate"
    if mutation=="different_step":message["lesson_context"]["step"]=0
    if mutation=="different_problem":scope["problem_id"]="foreign"
    if mutation=="different_revision":scope["problem_revision"]+=1
    if mutation=="foreign_source":scope["source_lesson_id"]="foreign"
    if mutation=="wrong_row":message["lesson_context"]["selected_cell"]["row_id"]="foreign"
    if mutation=="wrong_column":message["lesson_context"]["selected_cell"]["column_id"]="foreign"
    if mutation=="wrong_table":message["lesson_context"]["selected_cell"]["table_element_id"]="foreign"
    result=explain(message)
    assert result["plan"] is None and not result["speech_allowed"] and result["reason"]


def test_condition_sum_followup_remains_outside_the_direct_proof_scope():
    source,record=prepared(expressions=["COUNT(*)","SUM(reading IS NOT NULL)"])
    assert validated_logical_stage(record,source,{"step":1}) is None
    result=explain(followup(source,record,index=1))
    assert result["plan"] is None and result["generation"]["source"]=="conditional_sum_scope_needs_input"


def test_direct_api_rebuilds_scope_instead_of_accepting_forged_client_claim(client,monkeypatch):
    from test_phase2_backend import answer,make_lesson,wait
    import edu_tutor.models.runtime as runtime
    monkeypatch.setattr(runtime,"generate",lambda *args,**kwargs:iter(["CPU raw draft only"]))
    source,_=prepared();problem=source["problem"]
    session,answer_message=answer(client,problem["raw_text"],problem)
    record=make_lesson(client,session,answer_message)
    context=followup(answer_message,record)["lesson_context"]
    context["_verified_logical_stage"]={"kind":"server_verified_direct_aggregate_plan_v1","index":0,"aggregate_key":{"function":"sum"}}
    response=client.post(f"/api/sessions/{session['id']}/messages",json={"content":"왜 이 행이 포함돼?","lesson_context":context})
    assert response.status_code==202
    job=wait(client,response.json()["job_id"]);assert job["state"]=="succeeded"
    message=next(m for m in client.get(f"/api/sessions/{session['id']}/messages").json() if m["id"]==job["result"]["message_id"])
    scope=message["lesson_context"]["_verified_logical_stage"]
    assert scope["index"]==1 and scope["aggregate_key"]["function"]=="count"
    lesson=make_lesson(client,session,message)
    assert "0은 NULL이 아니므로 값 한 개" in lesson["plan"]["steps"][0]["speech"]
    assert message["raw_model_response"]=="CPU raw draft only"


# Reuse only the existing temporary-root/fake-model API fixture, never live app state.
from test_phase2_backend import client
