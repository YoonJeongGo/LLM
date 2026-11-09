"""Authored regressions after disclosed failures, CPU model doubles only."""
import copy
import importlib.util
from pathlib import Path

import pytest

from test_v021r3_explanation_repair import source, ask, words
from edu_tutor.problems.evidence import execute_sql, fixture


@pytest.mark.parametrize("column,chosen,blank,zero", [
    ("reading", "chosen_A", "missing_B", "zero_C"),
    ("amount", "box_red", "box_null", "box_zero"),
])
def test_exact_named_qualified_rows_narrow_comparison_without_changing_sql(column,chosen,blank,zero):
    rows=[[chosen,4,1],[blank,None,3],[zero,0,1],["unasked_null",None,2],["unasked_zero",0,2]]
    m,lesson=source(rows=rows,column=column,query=f"SELECT label, {column} FROM observations WHERE {column}>0 OR priority=3 ORDER BY priority DESC")
    before=copy.deepcopy(m)
    q=f"선택한 {chosen}은 왜 포함돼? {column}가 NULL인 원본 {blank}와, {column}가 똑같이 0인데 빠진 {zero}과도 같은 행 조건으로 비교해 줘. 정렬에서 값이 같은 행들의 순서도 설명해 줘."
    result=ask(m,lesson,q)
    assert result["speech_allowed"],result
    items={i["kind"]:i for i in result["explanation_fulfillment"]["items"]}
    table=m["evidence"]["working_tables"][0]
    assert items["null_comparison"]["evidence"]["comparison_row_ids"]==[table["row_ids"][1]]
    assert items["zero_comparison"]["evidence"]["comparison_row_ids"]==[table["row_ids"][2]]
    assert "원본 2행" in words(result) and "원본 3행" in words(result)
    assert len(result["plan"]["steps"])<=12 and max(map(len,[s["speech"] for s in result["plan"]["steps"]]))<=220
    assert m==before


@pytest.mark.parametrize("question",[
    "왜 선택한 alpha가 포함돼? NULL인 원본 peak와 비교해 줘.",
    "왜 선택한 alpha가 포함돼? 0인데 빠진 blank와 비교해 줘.",
    "왜 이 행이 포함돼? NULL인 blank와 같은 행도 비교해 줘.",
])
def test_qualified_value_mismatch_and_unresolved_same_row_remain_unmet(question):
    m,lesson=source()
    result=ask(m,lesson,question)
    assert not result["speech_allowed"] and result["explanation_fulfillment"]["status"]=="unmet"


@pytest.mark.parametrize("column,selection,labels,expected",[
    ("reading","SUM(reading), COUNT(reading), COUNT(*)",["SUM(reading)","COUNT(reading)","COUNT(*)"],[[None,0,0]]),
    ("units","COUNT(*), MAX(units), AVG(units), COUNT(DISTINCT units)",["COUNT(*)","MAX(units)","AVG(units)","COUNT(DISTINCT units)"],[[0,None,None,0]]),
])
def test_explicit_empty_aggregates_use_separate_verified_input_and_same_spoken_board_values(column,selection,labels,expected):
    m,lesson=source(column=column)
    before=copy.deepcopy(m)
    result=ask(m,lesson,f"선택한 행을 설명해 줘. 별도의 빈 입력 상황이라면 {selection}가 각각 무엇을 반환하는지 구분해 줘.")
    assert result["speech_allowed"],result
    item=next(i for i in result["explanation_fulfillment"]["items"] if i["kind"]=="empty_input")
    proof=item["evidence"]
    assert proof["result_rows"]==expected and proof["result_display_labels"]==labels
    assert proof["source_kind"]=="separate_empty_input_example"
    assert proof["original_sql_unchanged"]==m["evidence"]["sql"]!=proof["sql"]
    empty=copy.deepcopy(m["problem"]);empty["tables"][0]["rows"]=[]
    assert execute_sql(proof["sql"],fixture(empty))["rows"]==expected
    boards=[a for s in result["plan"]["steps"] for a in s["board_actions"] if a.get("type")=="table" and a.get("columns")==labels]
    assert boards and all(a["rows"]==expected for a in boards)
    assert all(label in words(result) for label in labels)
    assert "설명용 새 예시" in words(result) and m==before


@pytest.mark.parametrize("question",[
    "빈 입력이라면 TOTAL(reading)가 무엇을 반환하는지 설명해 줘.",
    "빈 입력이라면 SUM(reading+1), COUNT(*)가 무엇을 반환하는지 설명해 줘.",
    "빈 입력이라면 SUM(unknown), COUNT(*)가 무엇을 반환하는지 설명해 줘.",
    "빈 입력이라면 SUM(*), COUNT(*)가 무엇을 반환하는지 설명해 줘.",
    "빈 입력이라면 SUM(reading), COUNT(가 무엇을 반환하는지 설명해 줘.",
    "빈 입력이라면 SUM(reading)의 결과와 COUNT(*)를 비교해 줘.",
    "빈 입력을 설명해 줘. SUM(reading), COUNT(*)를 비교해 줘.",
    "빈 입력이라면 중앙값을 설명해 줘.",
])
def test_unsupported_or_partial_empty_aggregate_request_is_never_falsely_fulfilled(question):
    m,lesson=source()
    result=ask(m,lesson,question)
    assert not result["speech_allowed"],result
    assert result["explanation_fulfillment"]["status"]=="unmet"
    assert "빈 입력" in result["reason"]


def test_empty_without_explicit_aggregates_preserves_original_query_semantics():
    m,lesson=source()
    result=ask(m,lesson,"빈 입력일 때의 결과도 설명해 줘.")
    item=next(i for i in result["explanation_fulfillment"]["items"] if i["kind"]=="empty_input")
    assert item["evidence"]["sql"]==m["evidence"]["sql"]
    assert item["evidence"]["result_rows"]==[] and item["evidence"]["requested_aggregates"]==[]


@pytest.mark.parametrize("case,expected_null,expected_zero,expected_steps",[("N01",0,5,9),("N02",1,6,11)])
def test_disclosed_original_followups_through_explicit_cpu_double(case,expected_null,expected_zero,expected_steps):
    path=Path(__file__).parents[1]/"runs/v021-r3-repair/20261030/explanations/natural-repair/reprocess_followups.py"
    spec=importlib.util.spec_from_file_location("saved_followup_replay",path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    record=module.run(case);result=record["result"]
    assert record["actual_followup_status"]=="NOT_REACHED" and "CPU double" in record["model_double"]
    assert result["speech_allowed"],result
    assert result["explanation_fulfillment"]["status"]=="fulfilled"
    items={i["kind"]:i for i in result["explanation_fulfillment"]["items"]}
    assert set(items)>={"row_inclusion","null_comparison","zero_comparison","row_comparison","ordering"}
    table=record["base_message"]["evidence"]["working_tables"][0]
    assert items["null_comparison"]["evidence"]["comparison_row_ids"]==[table["row_ids"][expected_null]]
    assert items["zero_comparison"]["evidence"]["comparison_row_ids"]==[table["row_ids"][expected_zero]]
    assert len(result["plan"]["steps"])==expected_steps<=12 and max(record["speech_lengths"])<=220
    if case=="N02":
        assert items["empty_input"]["evidence"]["result_rows"]==[[None,0,0]]
    else:
        assert "원본 2행" in words(result) and "제외" in words(result)
