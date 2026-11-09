"""CPU-only authored development cases; separate from the frozen holdout."""
import copy
import json

import pytest

from edu_tutor.lessons.plans import scene_at
from edu_tutor.lessons.verified import generate_verified_plan, validated_logical_stage
from edu_tutor.problems.evidence import display_answer, verify_answer
from edu_tutor.problems.models import normalize_problem


def projection_source(rows=None, query=None):
    rows = [["low",-3,1],["zero",0,2],["missing",None,2],["same",0,1],["high",9,1]] if rows is None else rows
    problem=normalize_problem({"task_kind":"query_result","raw_text":"직접 작성한 개발 표에서 조건과 정렬 과정을 설명해 주세요.",
        "confirmed":True,"query":query or "SELECT code, amount FROM parcels WHERE amount>=0 ORDER BY amount DESC, priority ASC",
        "tables":[{"name":"parcels","columns":[{"name":"code","type":"TEXT"},{"name":"amount","type":"INTEGER"},{"name":"priority","type":"INTEGER"}],"rows":rows}]})
    evidence=verify_answer(problem,'{"sql":"SELECT nonsense","explanation":"결과는 999이며 NULL은 0입니다."}',problem["raw_text"])
    assert evidence["logical_steps"],evidence
    source={"id":"source-message","session_id":"same-session","problem":problem,"evidence":evidence,
        "content":display_answer(evidence),"raw_model_response":"결과는 999이며 NULL은 0입니다."}
    record={"id":"source-lesson","source_message_id":source["id"],**generate_verified_plan(source,problem["raw_text"],"plan")}
    assert record["speech_allowed"],record
    return source,record


def followup(source,record,stage,row,table_id=None):
    table=source["evidence"]["working_tables"][0]
    context={"lesson_id":record["id"],"step":stage,"problem_revision":source["problem"]["revision"],
        "selected_cell":{"table_element_id":table_id or table["id"],"row_id":table["row_ids"][row],
            "column_id":table["column_ids"][1],"cell_id":table["cell_ids"][row][1],
            "row_index":999,"column_index":999,"value":999}}
    scope=validated_logical_stage(record,source,context)
    assert scope
    context["_verified_logical_stage"]=scope
    message=copy.deepcopy(source)
    message["id"]="followup-message"
    message["lesson_context"]=context
    return message


def explain(message):
    return generate_verified_plan(message,"왜 선택한 이 행이 남아? 정렬 순서도 설명해 줘.","supplement")


def test_projection_rows_order_columns_and_source_cells_are_kept():
    source,record=projection_source()
    plan=record["plan"]
    assert len(plan["steps"])==3
    final=scene_at(plan,2)
    result=final["elements"][source["evidence"]["id"]+"-result"]
    original=source["evidence"]["working_tables"][0]
    assert result["rows"]==[["high",9],["same",0],["zero",0]]
    assert result["row_ids"]==[original["row_ids"][i] for i in [4,3,1]]
    assert result["cell_ids"]==[[original["cell_ids"][i][j] for j in [0,1]] for i in [4,3,1]]
    speech=" ".join(s["speech"] for s in plan["steps"])
    assert "amount의 내림차순" in speech and "priority의 오름차순" in speech
    assert "앞 기준의 값이 같을 때만 다음" in speech
    assert "999" not in speech and "NULL은 0" not in speech
    assert source["raw_model_response"]=="결과는 999이며 NULL은 0입니다."


@pytest.mark.parametrize("rows",[[],[["a",None,1],["b",None,1]],[["a",0,2],["b",0,2]],
    [["a",-2,1],["b",-2,2],["c",3,1]]])
def test_empty_null_zero_negative_duplicate_inputs_keep_consistent_board(rows):
    source,record=projection_source(rows)
    final=scene_at(record["plan"],2)
    result=final["elements"][source["evidence"]["id"]+"-result"]
    assert result["rows"]==source["evidence"]["result"]["rows"]
    trace=scene_at(record["plan"],0)["elements"][source["evidence"]["id"]+"-row-conditions"]
    assert len(trace["rows"])==len(rows)
    if not rows:
        assert result["rows"]==[] and "0행" in record["plan"]["steps"][0]["speech"]


def test_missing_order_never_promises_result_order():
    source,record=projection_source(query="SELECT amount, code FROM parcels WHERE amount IS NOT NULL")
    speech=" ".join(s["speech"] for s in record["plan"]["steps"])
    assert "ORDER BY가 없으므로 결과 행의 순서는 보장되지 않습니다" in speech
    result=scene_at(record["plan"],2)["elements"][source["evidence"]["id"]+"-result"]
    assert result["columns"]==["amount","code"]
    assert result["cell_ids"][0]==[source["evidence"]["working_tables"][0]["cell_ids"][0][i] for i in [1,0]]


@pytest.mark.parametrize("stage",[0,1,2])
def test_selected_zero_row_is_explained_from_current_stage_and_not_client_values(stage):
    source,record=projection_source()
    message=followup(source,record,stage,1)
    result=explain(message)
    assert result["speech_allowed"],result
    speech=result["plan"]["steps"][0]["speech"]
    assert "0" in speech and "TRUE" in speech and "남습니다" in speech
    assert "999" not in speech
    if stage:
        assert "amount의 내림차순" in speech and "3번째" in speech


def test_null_comparison_is_unknown_and_does_not_claim_survival_or_rank():
    source,record=projection_source()
    result=explain(followup(source,record,2,2))
    speech=result["plan"]["steps"][0]["speech"]
    assert "UNKNOWN" in speech and "제외됩니다" in speech
    assert "3번째" not in speech and "이 원본 행이" not in speech


@pytest.mark.parametrize("stage,suffix",[(1,"-project-rows"),(2,"-result")])
def test_selected_derived_row_has_explicit_original_cell_identity(stage,suffix):
    source,record=projection_source()
    selected_table=source["evidence"]["id"]+suffix
    result=explain(followup(source,record,stage,1,selected_table))
    assert result["speech_allowed"],result
    assert "원본 2행" in result["plan"]["steps"][0]["speech"]


@pytest.mark.parametrize("mutation",["speech","rows","gesture","revision","source","step"])
def test_modified_saved_plan_cannot_authorize_followup(mutation):
    source,record=projection_source()
    record=copy.deepcopy(record)
    if mutation=="speech":record["plan"]["steps"][0]["speech"]="false claim"
    if mutation=="rows":record["plan"]["steps"][0]["board_actions"][0]["rows"][0][1]=888
    if mutation=="gesture":record["plan"]["steps"][1]["gesture"]["target_element_id"]="other"
    if mutation=="revision":record["plan"]["problem_revision"]+=1
    if mutation=="source":record["plan"]["source_message_id"]="other"
    if mutation=="step":record["plan"]["steps"][1]["id"]="s99"
    assert validated_logical_stage(record,source,{"step":1}) is None


@pytest.mark.parametrize("mutation",["row_truth","order","projection","row_id","column_id","table","future_table"])
def test_forged_followup_trace_or_cell_stops(mutation):
    source,record=projection_source()
    message=followup(source,record,0,1)
    logical=message["evidence"]["logical_steps"]
    selected=message["lesson_context"]["selected_cell"]
    if mutation=="row_truth":logical["row_evaluations"][1]["truth"]=False
    if mutation=="order":logical["ordered_row_ids"].reverse()
    if mutation=="projection":logical["projection_columns"].reverse()
    if mutation=="row_id":selected["row_id"]="other"
    if mutation=="column_id":selected["column_id"]="other"
    if mutation=="table":selected["table_element_id"]="other"
    if mutation=="future_table":selected["table_element_id"]=source["evidence"]["id"]+"-result"
    result=explain(message)
    assert result["plan"] is None and not result["speech_allowed"] and result["reason"]


def test_compound_where_shows_individual_truth_and_null_does_not_become_zero():
    source,record=projection_source(query="SELECT code, amount FROM parcels WHERE amount>=0 AND priority=2 ORDER BY code")
    result=explain(followup(source,record,0,2))
    speech=result["plan"]["steps"][0]["speech"]
    assert "UNKNOWN" in speech and "AND" in speech and "제외됩니다" in speech
    assert "NULL은 0" not in speech


def group_source():
    problem=normalize_problem({"task_kind":"query_result","raw_text":"개발용 묶음 계산의 조건과 정렬을 설명해 주세요.",
        "confirmed":True,"query":"SELECT lane, COUNT(*) AS n, SUM(units) AS total FROM bins WHERE units>=0 GROUP BY lane HAVING SUM(units)>=3 ORDER BY total DESC, lane ASC",
        "tables":[{"name":"bins","columns":[{"name":"lane","type":"TEXT"},{"name":"units","type":"INTEGER"}],
                  "rows":[["north",3],["east",3],["east",0],["null",None],["low",-1]]}]})
    evidence=verify_answer(problem,"잘못된 원시 설명 999",problem["raw_text"])
    assert evidence["logical_steps"],evidence
    source={"id":"group-source","problem":problem,"evidence":evidence,"content":display_answer(evidence)}
    record={"id":"source-lesson","source_message_id":source["id"],**generate_verified_plan(source,problem["raw_text"],"plan")}
    return source,record


def test_group_having_then_multiple_ordering_has_five_bound_stages():
    source,record=group_source()
    assert record["speech_allowed"] and len(record["plan"]["steps"])==5
    scene=scene_at(record["plan"],4)
    assert scene["elements"][source["evidence"]["id"]+"-result"]["rows"]==[["east",2,3],["north",1,3]]
    result=explain(followup(source,record,4,1))
    assert result["speech_allowed"],result
    assert "ORDER BY" in result["plan"]["steps"][0]["title"]
    assert "1번째" in result["plan"]["steps"][0]["speech"]


def test_old_saved_group_without_new_order_trace_retains_four_stage_binding():
    source,record=group_source()
    for key in ("order_by","ordered_group_values","order_ties","before_order","row_evaluations"):
        source["evidence"]["logical_steps"].pop(key,None)
    old={"id":"source-lesson","source_message_id":source["id"],**generate_verified_plan(source,source["problem"]["raw_text"],"old-plan")}
    assert len(old["plan"]["steps"])==4
    assert validated_logical_stage(old,source,{"step":3})["kind"]=="server_verified_logical_plan_v1"
    assert validated_logical_stage(old,source,{"step":4}) is None

