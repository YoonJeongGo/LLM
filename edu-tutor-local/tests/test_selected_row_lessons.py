"""CPU checks with authored development data, never a model-quality score."""
import copy

import pytest

from edu_tutor.lessons.plans import scene_at
from edu_tutor.lessons.verified import generate_verified_plan, validated_logical_stage
from edu_tutor.problems.evidence import display_answer, verify_answer
from edu_tutor.problems.models import normalize_problem


def development_problem():
    return normalize_problem({"task_kind":"query_result", "raw_text":"개발 검증용 새 표의 원본부터 최종 결과까지 설명해 줘.",
        "confirmed":True, "query":"SELECT team, COUNT(*) AS people, SUM(score) AS total FROM study_results WHERE attended=1 GROUP BY team HAVING SUM(score)>=50 ORDER BY team",
        "tables":[{"name":"study_results", "columns":[{"name":"student","type":"TEXT"}, {"name":"team","type":"TEXT"},
            {"name":"score","type":"INTEGER"}, {"name":"attended","type":"INTEGER"}],
            "rows":[["하린","청",35,1],["도윤","청",25,1],["서아","청",90,0],["지호","백",40,1],["유나","백",None,1],["민재","홍",70,1]]}]})


def answer(p, row=None, column=0, stage=3):
    evidence=verify_answer(p,"실제 모델 초안과 구분하는 테스트용 잘못된 숫자 999",p["raw_text"])
    message={"id":"answer", "problem":p, "evidence":evidence, "content":display_answer(evidence),
        "raw_model_response":"테스트용 초안 999", "lesson_context":{"lesson_id":"original","step":stage}}
    source=copy.deepcopy(message);source.pop("lesson_context")
    original={"id":"original",**generate_verified_plan(source,p["raw_text"],"original-plan")}
    scope=validated_logical_stage(original,source,message["lesson_context"])
    if scope:message["lesson_context"]["_verified_logical_stage"]=scope
    if row is not None:
        table=evidence["working_tables"][0]
        message["lesson_context"]["selected_cell"]={"table_element_id":table["id"], "row_id":table["row_ids"][row],
            "column_id":table["column_ids"][column], "cell_id":table["cell_ids"][row][column],
            # Deliberately false client display fields must never enter speech.
            "value":999, "row_index":999, "column_index":999}
    return message


def supplement(message):
    return generate_verified_plan(message,"왜 이 행이 포함돼?","supplement")


def test_selected_source_row_explains_executed_where_group_having_and_board():
    message=answer(development_problem(),0)
    before=copy.deepcopy(message)
    result=supplement(message)
    assert result["speech_allowed"] and len(result["plan"]["steps"])==1
    unit=result["plan"]["steps"][0]
    assert "student=하린" in unit["speech"] and "attended=1" in unit["speech"]
    assert "team=청 그룹" in unit["speech"] and "SUM(score)는 60" in unit["speech"]
    assert "HAVING SUM(score) >= 50 조건을 통과" in unit["speech"]
    assert "원본 한 행이 아니라" in unit["speech"] and "999" not in unit["speech"]
    scene=scene_at(result["plan"],0)
    assert scene["highlights"][0]["row_indices"]==[0]
    reason=next(item for item in scene["elements"].values() if item["type"]=="text")
    assert "WHERE attended = 1 조건을 통과" in reason["text"]
    assert "COUNT(*)는 2" in reason["text"] and "COUNT(*)" not in unit["speech"]
    assert "현재 음성 범위: HAVING" in reason["text"]
    result_table=scene["elements"][message["evidence"]["id"]+"-result"]
    assert result_table["rows"]==[["청",2,60],["홍",1,70]]
    assert message==before


def test_excluded_source_row_is_not_claimed_included_despite_question():
    unit=supplement(answer(development_problem(),2))["plan"]["steps"][0]
    assert "4열 값은 0" in unit["speech"] and "집계 입력에서 제외" in unit["speech"]
    assert "SUM(score)는" not in unit["speech"]
    assert "최종 결과에 남습니다" not in unit["speech"]


def test_null_cell_keeps_where_membership_separate_from_aggregate_and_having():
    result=supplement(answer(development_problem(),4,2,stage=2))
    speech=result["plan"]["steps"][0]["speech"]
    assert "score=NULL" in speech
    assert "COUNT(*)는 2" in speech and "SUM(score)는 40" in speech
    assert "NULL이므로 해당 집계에 더하지" in speech
    text=next(a["text"] for a in result["plan"]["steps"][0]["board_actions"] if a["type"]=="text")
    assert "집계 입력에 포함" in text and "이 그룹은 최종 결과에서 제외" in text


def test_group_survival_uses_hidden_keys_even_when_aggregates_are_identical():
    p=development_problem()
    p["query"]="SELECT COUNT(*) AS n FROM study_results GROUP BY team HAVING team='청'"
    # Both 청 and 백 now have 2 rows: a result-value match cannot identify which
    # group's count was selected by HAVING.
    p["tables"][0]["rows"].pop(2)
    first=supplement(answer(p,0))["plan"]["steps"][0]["speech"]
    rejected=supplement(answer(p,2))["plan"]["steps"][0]["speech"]
    assert "최종 결과에 남습니다" in first
    assert "최종 결과에서 제외됩니다" in rejected


@pytest.mark.parametrize("bad",["missing","unknown_cell","wrong_row","wrong_column","result_table"])
def test_ambiguous_or_stale_selection_stops_instead_of_guessing(bad):
    message=answer(development_problem(),0)
    selected=message["lesson_context"]["selected_cell"]
    if bad=="missing":message["lesson_context"].pop("selected_cell")
    if bad=="unknown_cell":selected["cell_id"]="not-present"
    if bad=="wrong_row":selected["row_id"]="other-row"
    if bad=="wrong_column":selected["column_id"]="other-column"
    if bad=="result_table":selected["table_element_id"]="derived-result"
    result=supplement(message)
    assert result["plan"] is None and not result["speech_allowed"]
    assert result["status"]=="verification_stopped" and result["reason"]


def test_unsupported_row_trace_does_not_speak_a_generic_result_as_row_reason():
    p=development_problem()
    p["query"]="WITH x AS (SELECT * FROM study_results) SELECT COUNT(*) FROM x"
    message=answer(p,0)
    assert message["evidence"]["status"]=="verified" and message["evidence"]["logical_steps"] is None
    result=supplement(message)
    assert not result["speech_allowed"] and result["plan"] is None


def test_new_values_and_other_schema_flow_through_without_example_specific_logic():
    p=normalize_problem({"task_kind":"query_result","raw_text":"별도로 작성한 개발 예시","confirmed":True,
        "query":"SELECT bucket, AVG(amount) AS mean FROM inventory WHERE enabled IS NOT NULL GROUP BY bucket HAVING AVG(amount)>10",
        "tables":[{"name":"inventory","columns":[{"name":"bucket","type":"TEXT"},{"name":"amount","type":"INTEGER"},{"name":"enabled","type":"INTEGER"}],
            "rows":[["X",12,1],["X",28,0],["Y",99,None]]}]})
    accepted=supplement(answer(p,1,1))["plan"]["steps"][0]["speech"]
    assert "amount=28" in accepted and "AVG(amount)는 20.0" in accepted and "bucket=X" in accepted
    rejected=supplement(answer(p,2))["plan"]["steps"][0]["speech"]
    assert "3열 값은 널" in rejected and "집계 입력에서 제외" in rejected


def test_having_alias_is_preserved_in_group_survival_projection():
    p=development_problem()
    p["query"]="SELECT team, SUM(score) AS total FROM study_results WHERE attended=1 GROUP BY team HAVING total>=50"
    evidence=answer(p,0)["evidence"]
    assert evidence["logical_steps"] is not None
    assert {tuple(g["values"]):g["having_passed"] for g in evidence["logical_steps"]["groups"]}=={("청",):True,("백",):False,("홍",):True}


def test_clock_dependent_predicate_does_not_get_a_repeat_execution_row_explanation():
    p=development_problem()
    p["query"]="SELECT COUNT(*) FROM study_results WHERE date('now') >= '2000-01-01'"
    message=answer(p,0)
    assert message["evidence"]["status"]=="verified"
    assert message["evidence"]["logical_steps"] is None
    assert "시간" in message["evidence"]["calculation"]["reason"]
    result=supplement(message)
    assert not result["speech_allowed"] and result["plan"] is None


@pytest.mark.parametrize("selected_row",[None,0])
@pytest.mark.parametrize("question",["COUNT와 SUM은 뭐가 달라?","이 행에서 COUNT와 SUM은 뭐가 달라?"])
def test_unrelated_followup_does_not_become_a_selected_row_explanation_or_original_lecture(selected_row,question):
    message=answer(development_problem(),selected_row)
    before=copy.deepcopy(message)
    result=generate_verified_plan(message,question,"unrelated-supplement")
    assert result["plan"] is None and not result["speech_allowed"]
    assert result["status"]=="verification_stopped"
    assert result["generation"]["source"]=="supplementary_scope_needs_input"
    assert "포함·제외 이유만" in result["reason"]
    assert message==before and message["raw_model_response"]==before["raw_model_response"]


@pytest.mark.parametrize("stage,spoken,omitted",[(0,"4열이 1인 조건",["COUNT(*)","SUM(score)","HAVING","WHERE","attended"]),
    (1,"team=청 그룹",["COUNT(*)","SUM(score)","HAVING"]),
    (2,"SUM(score)는 60",["HAVING"]),(3,"HAVING SUM(score) >= 50",["COUNT(*)"])])
def test_current_server_verified_stage_limits_speech_but_preserves_complete_board(stage,spoken,omitted):
    result=supplement(answer(development_problem(),0,stage=stage))
    unit=result["plan"]["steps"][0]
    assert spoken in unit["speech"]
    assert all(part not in unit["speech"] for part in omitted)
    text=next(a["text"] for a in unit["board_actions"] if a["type"]=="text")
    assert "전체 계산 근거" in text and "COUNT(*)는 2" in text and "HAVING SUM(score) >= 50" in text
    if stage==0:assert len(unit["speech"])<100


@pytest.mark.parametrize("stage",[-1,5,True,"0",None])
def test_invalid_requested_stage_cannot_get_a_scoped_spoken_explanation(stage):
    message=answer(development_problem(),0,stage=stage)
    assert "_verified_logical_stage" not in message["lesson_context"]
    result=supplement(message)
    assert not result["speech_allowed"] and result["plan"] is None


def test_changed_stored_plan_or_provenance_cannot_establish_known_stage():
    message=answer(development_problem(),0)
    source=copy.deepcopy(message);source.pop("lesson_context")
    record={"id":"original",**generate_verified_plan(source,source["problem"]["raw_text"], "original-plan")}
    assert validated_logical_stage(record,source,{"step":0})["stage"]=="where"
    record["plan"]["steps"][0]["speech"]="검증되지 않은 대체 설명"
    assert validated_logical_stage(record,source,{"step":0}) is None
    record={"id":"original",**generate_verified_plan(source,source["problem"]["raw_text"], "original-plan")}
    record["plan"]["provenance"]="model_generated"
    assert validated_logical_stage(record,source,{"step":0}) is None


def test_logical_flow_arrows_connect_executed_stages_and_clear_removed_endpoints():
    source=answer(development_problem(),0)
    source.pop('lesson_context')
    result=generate_verified_plan(source,source['problem']['raw_text'],'flow')
    plan=result['plan']
    evidence=source['evidence']
    assert sum(a['type']=='arrow' for s in plan['steps'] for a in s['board_actions'])==5
    for index in range(5):
        scene=scene_at(plan,index)
        assert all(a['from_element_id'] in scene['elements'] and a['to_element_id'] in scene['elements']
                   for a in scene['arrows'])
    aggregate=scene_at(plan,2)['elements'][evidence['id']+'-aggregate']
    assert aggregate['rows']==evidence['logical_steps']['before_having']['rows']
    assert scene_at(plan,3)['arrows']==[plan['steps'][3]['board_actions'][-1]]
    assert scene_at(plan,4)['arrows']==[plan['steps'][4]['board_actions'][-1]]


@pytest.mark.parametrize('mutation',['none','cell','timing','speech','extra_arrow','partial_arrows'])
def test_legacy_no_arrow_plan_keeps_strict_stage_binding(mutation):
    source=answer(development_problem(),0)
    source.pop('lesson_context')
    # Persisted pre-v0.2.1 records did not have the independent ordering/WHERE
    # trace extension. Exercise that exact four-stage contract, not a newly
    # generated five-stage plan with arrows removed.
    for key in ('order_by','ordered_group_values','order_ties','before_order','row_evaluations'):
        source['evidence']['logical_steps'].pop(key,None)
    # Database records are separately decoded objects, not the builder's shared
    # in-memory rows. Mutating a saved board must not also mutate source evidence.
    record=copy.deepcopy({'id':'original',**generate_verified_plan(source,source['problem']['raw_text'],'original-plan')})
    arrows=[a for s in record['plan']['steps'] for a in s['board_actions'] if a['type']=='arrow']
    for unit in record['plan']['steps']:
        unit['board_actions']=[a for a in unit['board_actions'] if a['type']!='arrow']
    actions=record['plan']['steps'][0]['board_actions']
    original=next(a for a in actions if a['type']=='table')
    if mutation=='cell':original['rows'][0][0]='변조'
    elif mutation=='timing':original['timing']['end']=0.3
    elif mutation=='speech':record['plan']['steps'][0]['speech']='다른 대사'
    elif mutation=='extra_arrow':record['plan']['steps'][1]['board_actions'].append({**arrows[0],'element_id':'arbitrary'})
    elif mutation=='partial_arrows':record['plan']['steps'][1]['board_actions'].append(arrows[0])
    scope=validated_logical_stage(record,source,{'step':0})
    assert bool(scope)==(mutation=='none')
    if scope:
        followup=answer(development_problem(),0,stage=0)
        followup['evidence']=copy.deepcopy(source['evidence'])
        followup['lesson_context']['_verified_logical_stage']=scope
        assert supplement(followup)['speech_allowed']
