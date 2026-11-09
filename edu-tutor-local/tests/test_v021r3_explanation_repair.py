"""Authored CPU regression, not an independent accuracy evaluation."""
import copy
import json

import pytest

from edu_tutor.problems.models import normalize_problem, infer_basic_intent
from edu_tutor.problems.evidence import verify_answer, display_answer
from edu_tutor.lessons.verified import generate_verified_plan, validated_logical_stage
from edu_tutor.lessons.plans import scene_at
from edu_tutor.problems.pipeline import hypothesis_from_question


def source(rows=None, column="reading", query=None, raw_text=None, task="query_result"):
    rows = [["alpha", 0, 2], ["blank", None, 2], ["peak", 7, 1], ["low", -3, 1], ["tie", 0, 1]] if rows is None else rows
    sql = query or f"SELECT label, {column} FROM observations WHERE {column} >= 0 ORDER BY {column} DESC, priority ASC, label ASC"
    p = normalize_problem({"task_kind":task, "raw_text":raw_text or "현재 표의 조건과 정렬을 설명해 주세요.",
        "confirmed":True, **({"query":sql} if task == "query_result" else {}),
        "tables":[{"name":"observations","columns":[{"name":"label","type":"TEXT"},{"name":column,"type":"INTEGER"},{"name":"priority","type":"INTEGER"}],"rows":rows}]})
    e = verify_answer(p, json.dumps({"sql":sql,"explanation":"NULL은 0이므로 같은 행입니다."}), p["raw_text"])
    m = {"id":"source-new", "problem":p, "evidence":e, "content":display_answer(e)}
    result = generate_verified_plan(m,p["raw_text"],"source-plan")
    return m,{"id":"original-lesson","source_message_id":m["id"],**result}


def ask(m, lesson, question, row=0, col=1, stage=1):
    table=m["evidence"]["working_tables"][0]
    context={"lesson_id":lesson["id"],"step":stage,"problem_revision":m["problem"]["revision"],
        "selected_cell":{"cell_id":table["cell_ids"][row][col],"row_id":table["row_ids"][row],
                         "column_id":table["column_ids"][col],"table_element_id":table["id"]}}
    context["_verified_logical_stage"]=validated_logical_stage(lesson,m,context)
    child={**copy.deepcopy(m),"id":"supplement-new","lesson_context":context}
    return generate_verified_plan(child,question,"supplement-plan")


def words(result):
    return " ".join(s["speech"] for s in result["plan"]["steps"])


@pytest.mark.parametrize("column,question",[
    ("reading","왜 선택한 이 행이 포함돼? NULL인 행과 비교하고 지금 정렬 순서도 설명해 줘."),
    ("quantity","선택한 행이 남는 이유와 널인 행의 차이를 알려 주세요. 정렬 우선순위도 설명해 주세요."),
    ("score","이 행의 조건을 알려줘. NULL 행과 대조해서 정렬 기준까지 설명해 줘."),
])
def test_selected_row_null_comparison_and_order_all_grounded(column,question):
    m,lesson=source(column=column)
    result=ask(m,lesson,question)
    assert result["speech_allowed"],result
    audit=result["explanation_fulfillment"]
    assert audit["status"]=="fulfilled"
    assert {r["kind"] for r in audit["items"] if r["status"]=="fulfilled"} >= {"row_inclusion","null_comparison","ordering"}
    text=words(result)
    assert "원본 2행" in text and "NULL" in text and "UNKNOWN" in text and "제외" in text
    assert "0" in text and "TRUE" in text and f"{column}의 내림차순" in text
    assert "NULL은 0이므로" not in text
    assert all(len(s["speech"]) <= 260 for s in result["plan"]["steps"])
    assert len(result["plan"]["steps"]) >= 2


def test_absent_null_is_stated_without_inventing_a_source_row():
    m,lesson=source(rows=[["a",0,1],["b",3,2]])
    result=ask(m,lesson,"왜 이 행이 포함돼? NULL행과 비교하고 정렬 순서도 알려줘.")
    assert result["speech_allowed"],result
    assert "NULL인 행이 없습니다" in words(result)
    item=next(x for x in result["explanation_fulfillment"]["items"] if x["kind"]=="null_comparison")
    assert item["evidence"]["comparison_row_ids"]==[]


def test_multiple_null_rows_are_each_checked_not_arbitrarily_chosen():
    m,lesson=source(rows=[["a",0,1],["b",None,1],["c",None,3]],
        query="SELECT label, reading FROM observations WHERE reading >= 0 OR priority=3 ORDER BY priority DESC")
    result=ask(m,lesson,"왜 이 행이 포함돼? NULL인 행들과 비교하고 정렬도 설명해줘.")
    assert result["speech_allowed"],result
    text=words(result)
    assert "원본 2행" in text and "원본 3행" in text and "UNKNOWN" in text and "TRUE" in text
    item=next(x for x in result["explanation_fulfillment"]["items"] if x["kind"]=="null_comparison")
    assert len(item["evidence"]["comparison_row_ids"])==2


def test_explanation_tail_does_not_change_original_filter():
    raw="출력: COUNT(reading), SUM(reading); 행 조건: reading >= 0; NULL과 0의 차이도 설명해 주세요."
    m,lesson=source(raw_text=raw,task="write_sql",query="SELECT COUNT(reading), SUM(reading) FROM observations WHERE reading>=0")
    intent,reason=infer_basic_intent(m["problem"],raw)
    assert intent is not None,reason
    assert intent["where"]=="reading >= 0"
    assert lesson["speech_allowed"],lesson
    assert lesson["explanation_fulfillment"]["status"]=="fulfilled"
    assert "NULL" in words(lesson) and "0" in words(lesson)


@pytest.mark.parametrize("query,expected",[
    ("SELECT COUNT(reading) AS n, SUM(reading) AS total FROM observations",[[0,None]]),
    ("SELECT priority, SUM(reading) AS total FROM observations GROUP BY priority",[]),
])
def test_empty_input_is_separate_executed_example_not_replacement(query,expected):
    m,lesson=source(query=query,raw_text="결과와 빈 입력일 때의 결과도 설명해 주세요.")
    assert lesson["speech_allowed"],lesson
    item=next(x for x in lesson["explanation_fulfillment"]["items"] if x["kind"]=="empty_input")
    assert item["evidence"]["result_rows"]==expected
    assert item["evidence"]["source_kind"]=="separate_empty_input_example"
    assert m["problem"]["tables"][0]["rows"]
    assert "설명용 새 예시" in words(lesson)


@pytest.mark.parametrize("question",["LEAD(reading) 창 함수로 다음 값을 구해 주세요.","LAG를 이용한 이전 행 설명", "ROW_NUMBER 윈도우 함수로 순위를 구해 주세요."])
def test_window_request_is_unsupported_not_missing_operand(question):
    m,_=source()
    intent,reason=infer_basic_intent({**m["problem"],"task_kind":"write_sql"},question)
    assert intent is None and "미지원" in reason


def test_real_missing_comparison_operand_is_still_missing():
    m,_=source()
    intent,reason=infer_basic_intent(m["problem"],"출력: label; 행 조건: reading >=; 정렬 기준: label ASC")
    assert intent is None and "확인" in reason and "미지원" not in reason


def test_followup_unknown_comparison_is_not_silently_fulfilled():
    m,lesson=source()
    result=ask(m,lesson,"왜 이 행이 포함돼? 음수인 행과 비교해 줘.")
    assert not result["speech_allowed"]
    assert result["explanation_fulfillment"]["status"] != "fulfilled"
    assert "비교" in result["reason"]


@pytest.mark.parametrize("row", [1, 2, 3, 4])
def test_other_selected_rows_keep_inclusion_truth_and_comparison_cell_identity(row):
    m,lesson=source()
    result=ask(m,lesson,"선택한 행의 조건과 NULL행 차이를 설명해 줘. 정렬도 알려 줘.",row=row)
    assert result["speech_allowed"],result
    text=words(result)
    assert f"원본 {row+1}행" in text
    if row in (1,3):
        assert "제외" in text and "정렬 결과에 들어가지 않습니다" in text
    table=m["evidence"]["working_tables"][0]
    audit=result["explanation_fulfillment"]
    comparison=next(i for i in audit["items"] if i["kind"]=="null_comparison")
    assert comparison["evidence"]["comparison_cell_ids"] == [table["cell_ids"][1][1]]
    final=scene_at(result["plan"],len(result["plan"]["steps"])-1)
    assert any(table["cell_ids"][1][1] in h.get("cell_ids",[]) for h in final["highlights"])


def test_many_comparison_rows_ask_only_for_target_then_accept_source_row_number():
    m,lesson=source(rows=[["chosen",0,1]]+[[f"n{i}",None,i] for i in range(6)])
    q="왜 이 행이 포함돼? NULL행과 비교해 줘."
    result=ask(m,lesson,q)
    assert not result["speech_allowed"] and "원본 행 번호" in result["reason"]
    narrowed=ask(m,lesson,"왜 이 행이 포함돼? NULL인 원본 3행과 비교해 줘.")
    assert narrowed["speech_allowed"],narrowed
    item=next(i for i in narrowed["explanation_fulfillment"]["items"] if i["kind"]=="null_comparison")
    assert item["evidence"]["comparison_row_ids"]==[m["evidence"]["working_tables"][0]["row_ids"][2]]


def test_multiple_potential_comparison_columns_need_a_column_not_new_table_data():
    m,lesson=source(rows=[["a",0,0],["b",None,None]],
        query="SELECT label FROM observations WHERE reading>=0 OR priority>=0")
    result=ask(m,lesson,"왜 이 행이 포함돼? NULL행과 비교해줘.",col=0)
    assert not result["speech_allowed"] and "열" in result["reason"]
    assert "데이터" not in result["reason"]


def test_comparing_all_null_rows_does_not_create_all_null_hypothesis():
    m,_=source()
    p=m["problem"]
    assert hypothesis_from_question(p,"모든 NULL행과 비교해줘.",{"column_name":"reading"}) is None
    assert hypothesis_from_question(p,"만약 reading을 모두 NULL로 바꾸면?",{"column_name":"reading"})["kind"]=="all_null"


@pytest.mark.parametrize("suffix",[
    "NULL과 0의 차이도 설명하되 reading은 7인 것만 보여줘.",
    "NULL과 0의 차이도 설명해 주세요. 단 priority는 2여야 합니다.",
    "NULL과 0의 차이도 설명해 주세요; 행 조건: priority=2",
])
def test_explanation_suffix_cannot_hide_extra_sql_conditions(suffix):
    m,_=source()
    q="출력: label; 행 조건: reading >= 0; "+suffix
    assert infer_basic_intent(m["problem"],q)[0] is None


def test_window_named_column_is_not_a_window_function():
    m,_=source(column="rank")
    intent,reason=infer_basic_intent(m["problem"],"출력: label, rank; 정렬: rank DESC")
    assert intent is not None,reason


def test_mixed_unhandled_comparison_is_not_hidden_by_a_handled_null_request():
    m,lesson=source()
    result=ask(m,lesson,"왜 이 행이 포함돼? NULL행과 음수인 행 둘 다 비교해 줘.")
    assert not result["speech_allowed"] and "미지원" in result["reason"]


def test_empty_original_table_stays_empty_and_sum_does_not_become_count():
    m,lesson=source(rows=[],query="SELECT COUNT(*) AS n, SUM(reading IS NOT NULL) AS total FROM observations",
        raw_text="현재 결과와 빈 입력일 때의 차이를 설명해줘.")
    assert lesson["speech_allowed"],lesson
    assert m["evidence"]["result"]["rows"]==[[0,None]]
    item=next(i for i in lesson["explanation_fulfillment"]["items"] if i["kind"]=="empty_input")
    assert item["evidence"]["result_rows"]==[[0,None]]


def test_followup_window_request_is_explicitly_unsupported():
    m,lesson=source()
    result=ask(m,lesson,"LEAD를 이용해서 이 행의 다음 값을 설명해 줘.")
    assert not result["speech_allowed"] and "윈도우" in result["reason"] and "미지원" in result["reason"]


def test_existing_plain_aggregate_comparison_is_not_newly_rejected():
    m,lesson=source(query="SELECT COUNT(*), COUNT(reading) FROM observations",raw_text="COUNT(*)와 COUNT(reading)의 차이를 설명해 줘.")
    assert lesson["speech_allowed"],lesson
    assert len(lesson["plan"]["steps"]) == 2


@pytest.mark.parametrize("target", ["7인 행", "'peak'", "다른 행", "민수", "민수행", "읽기가 7인 행"])
def test_handled_null_does_not_hide_unresolved_other_comparison_operand(target):
    m,lesson=source()
    result=ask(m,lesson,f"왜 이 행이 포함돼? NULL행과 {target}도 비교해 줘.")
    if target == "'peak'":
        # Subsequent requested scope: an exact, unique original string resolves
        # this same saved development question. No question/fixture was edited.
        assert result["speech_allowed"],result
        assert "원본 3행" in words(result)
        assert any(i["kind"] == "row_comparison" for i in result["explanation_fulfillment"]["items"])
        return
    assert not result["speech_allowed"], result
    assert result["explanation_fulfillment"]["status"] == "unmet"
    assert "비교" in result["reason"]


def test_null_and_explicit_different_source_row_are_both_explained():
    m,lesson=source()
    result=ask(m,lesson,"왜 이 행이 포함돼? NULL행과 원본 3행도 비교하고 정렬도 설명해줘.")
    assert result["speech_allowed"],result
    items=result["explanation_fulfillment"]["items"]
    assert {i["kind"] for i in items} >= {"row_inclusion", "null_comparison", "row_comparison", "ordering"}
    text=words(result)
    assert "원본 2행" in text and "원본 3행" in text and "7" in text
    assert "UNKNOWN" in text and "TRUE" in text


def test_numbered_other_row_comparison_does_not_require_null_or_zero():
    m,lesson=source()
    result=ask(m,lesson,"왜 이 행이 포함돼? 원본 3행과 비교해 줘.",row=3)
    assert result["speech_allowed"],result
    assert "원본 4행" in words(result) and "원본 3행" in words(result)
    assert "FALSE" in words(result) and "TRUE" in words(result)


@pytest.mark.parametrize("reference", ["'peak'", '"peak"', "peak", "peak행", "peak인 행"])
def test_exact_original_string_resolves_one_row_without_changing_sql(reference):
    m,lesson=source()
    before=copy.deepcopy(m)
    result=ask(m,lesson,f"왜 이 행이 포함돼? NULL행과 {reference}도 비교하고 정렬도 설명해 줘.")
    assert result["speech_allowed"],result
    assert m==before
    item=next(i for i in result["explanation_fulfillment"]["items"] if i["kind"]=="row_comparison")
    assert item["evidence"]["comparison_row_ids"]==[m["evidence"]["working_tables"][0]["row_ids"][2]]
    assert item["evidence"]["exact_value_references"][0]["literal"] == "peak"
    assert "원본 2행" in words(result) and "원본 3행" in words(result)


def test_exact_original_korean_name_and_particles_resolve_without_special_names():
    m,lesson=source(rows=[["선택학생",0,1],["비교학생",7,2],["비어있음",None,3]])
    result=ask(m,lesson,"왜 이 행이 포함돼? 비교학생과 NULL행도 비교해 줘.")
    assert result["speech_allowed"],result
    assert "원본 2행" in words(result) and "원본 3행" in words(result)


@pytest.mark.parametrize("rows,reference,reason",[
    ([["a",0,1],["same",None,2],["same",7,3]],"'same'","어느 행"),
    ([["a",0,1],["other",None,2]],"'missing'","없습니다"),
])
def test_duplicate_or_missing_source_name_is_specific_unmet(rows,reference,reason):
    m,lesson=source(rows=rows)
    result=ask(m,lesson,f"왜 이 행이 포함돼? NULL행과 {reference}도 비교해 줘.")
    assert not result["speech_allowed"] and reason in result["reason"]
    assert result["explanation_fulfillment"]["status"]=="unmet"


def test_source_value_qualifier_must_match_the_referenced_row():
    m,lesson=source()
    result=ask(m,lesson,"왜 이 행이 포함돼? NULL인 'peak'행과 비교해 줘.")
    assert not result["speech_allowed"] and "NULL·0과 다릅니다" in result["reason"]


def test_name_prefix_is_not_an_exact_cell_reference():
    m,lesson=source(rows=[["a",0,1],["이민수",None,2]])
    result=ask(m,lesson,"왜 이 행이 포함돼? NULL행과 민수행도 비교해 줘.")
    assert not result["speech_allowed"]
