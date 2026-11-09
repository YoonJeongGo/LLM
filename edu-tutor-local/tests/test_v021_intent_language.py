"""Developer fixtures authored after the v021 holdout freeze; no holdout inputs."""
import copy
import pytest
from edu_tutor.problems.models import normalize_problem,infer_basic_intent,canonical


def problem(question):
    return normalize_problem({"task_kind":"write_sql","raw_text":question,"confirmed":True,
        "tables":[{"name":"readings","columns":[{"name":"item","type":"INTEGER"},
            {"name":"score","type":"INTEGER"},{"name":"zone","type":"TEXT"}],
            "rows":[[1,0,"동"],[2,None,"서"],[3,-4,"동"],[4,0,"서"]]}]})


@pytest.mark.parametrize("condition",["score >= -4 AND score IS NOT NULL",
    "score가 -4 이상 AND score가 NULL이 아닌", "(score = 0 OR score IS NULL) AND item > 1"])
def test_labelled_intent_uses_question_and_schema(condition):
    p=problem(f"출력 열: score, item; 행 조건: {condition}; 정렬 기준: score DESC, item ASC.")
    before=copy.deepcopy(p)
    intent,scope=infer_basic_intent(p,p["raw_text"])
    assert scope=="bounded_language_select_v2"
    assert intent["select_columns"]==["score","item"]
    assert intent["where"] and intent["order_by"]==[{"column":"score","direction":"desc"},{"column":"item","direction":"asc"}]
    assert p==before


@pytest.mark.parametrize("q,cols,ordered",[
    ("score 내림차순, 동점이면 item 오름차순으로 item와 score를 보여 주세요.",["item","score"],True),
    ("score가 양수인 행의 item를 오름차순으로 조회하고 선택 이유를 설명하세요.",["item"],True),
    ("score가 NULL인 행의 item를 item 오름차순으로 보여 주세요.",["item"],True),
    ("score가 0 이상인 행만 대상으로 item와 score를 score 내림차순, item 오름차순으로 보여 주세요.",["item","score"],True),
    ("출력: item, score",["item","score"],False),
])
def test_complete_natural_forms_and_unordered_case(q,cols,ordered):
    p=problem(q)
    intent,scope=infer_basic_intent(p,q)
    assert intent,scope
    assert intent["select_columns"]==cols
    assert bool(intent["order_by"]) is ordered


def test_group_aggregate_predicate_order_all_independently_named():
    q="출력: zone, SUM(score), COUNT(*); 조건: score >= 0; 그룹: zone; 그룹 조건: SUM(score) >= 1; 정렬: SUM(score) DESC, zone ASC."
    p=problem(q)
    intent,scope=infer_basic_intent(p,q)
    assert scope=="bounded_language_aggregate_v2"
    assert intent["group_by"]==["zone"] and intent["where"]=="score >= 0"
    assert intent["having"]=="SUM(score) >= 1" and intent["order_by"][0]["column"]=="SUM(score)"
    assert [a["function"] for a in intent["aggregates"]]==["sum","count"]


@pytest.mark.parametrize("q",[
    "출력: missing; 조건: score > 0",
    "출력: item; 조건: score >=; 정렬: item ASC",
    "출력: item; 조건: score > 0; 단 zone은 서만",
    "출력: item; 조건: score > 0 ORDER BY item",
    "출력: item; 조건: score > 0; DELETE FROM readings",
    "출력: item; 조건: random() > 0",
    "출력: item; 정렬: score DESC; 정렬: item ASC",
    "출력: item; 정렬: score DESC NULLS FIRST",
    "출력: item; 그룹 조건: COUNT(*) > 0",
    "출력: SUM(score), zone; 그룹: zone",
    "출력: item; 조건: score",
    "출력: item; 조건: score > 0; 원본을 수정해 줘",
    "출력: item; 정렬: item ASC LIMIT 1",
    "item와 score를 오름차순으로 조회해 주세요.",
])
def test_unparsed_qualifiers_missing_fields_and_unsupported_operations_fail_closed(q):
    p=problem(q)
    assert infer_basic_intent(p,q)[0] is None


def test_literal_content_is_not_rewritten_as_korean_boolean_logic():
    p=problem("출력: item; 조건: zone = '또는 NULL인'; 정렬: item ASC")
    intent,_=infer_basic_intent(p,p["raw_text"])
    assert intent["where"]=="zone = '또는 NULL인'"


def test_data_copies_are_not_natural_conditions_and_trailing_requirements_remain():
    p=problem("출력: item; 정렬: item ASC")
    data='readings(item,score,zone)='+canonical(p["tables"][0]["rows"])
    intent,_=infer_basic_intent(p,data+". "+p["raw_text"])
    assert intent and intent["where"] is None
    assert infer_basic_intent(p,data+". "+p["raw_text"]+" 단 첫 행만")[0] is None


def test_old_explicit_aggregate_intent_canonical_fields_stay_unchanged():
    old={"table":"readings","aggregates":[{"function":"count","column":"*","distinct":False}],
         "group_by":[]}
    raw=problem("COUNT(*)")
    raw["intent"]=old
    normalized=normalize_problem(raw)
    assert normalized["intent"]==old
    assert "select_columns" not in normalized["intent"] and "order_by" not in normalized["intent"]


def test_column_names_values_and_selection_order_generalize():
    p=problem("출력: SCORE, ITEM; 조건: SCORE <= -4; 정렬: SCORE ASC, ITEM DESC")
    intent,_=infer_basic_intent(p,p["raw_text"])
    assert intent["select_columns"]==["score","item"]
    assert intent["where"]=="score <= -4"
    p["tables"][0]["rows"].append([8,10,"서"])
    assert infer_basic_intent(p,p["raw_text"])[0]==intent


def test_conflicting_structured_intent_cannot_override_clear_student_text():
    p=problem("출력: item; 조건: score > 0; 정렬: item ASC")
    intent,_=infer_basic_intent(p,p['raw_text'])
    p['intent']=copy.deepcopy(intent)
    assert infer_basic_intent(p,p['raw_text'])[0] is not None
    p['intent']['where']='score < 0'
    assert infer_basic_intent(p,p['raw_text'])[0] is None


@pytest.mark.parametrize('q',[
    '전체 행 수와 score가 NULL이 아닌 행 수를 차례대로 구해 줘.',
    'SQLite 범위에서 전체 행 수와 score 값이 NULL이 아닌 행 수를 이 순서대로 구해 줘.',
])
def test_existing_dual_count_is_not_mistaken_for_row_filter(q):
    p=problem(q)
    intent,scope=infer_basic_intent(p,q)
    assert scope=='bounded_language_aggregate'
    assert [a['column'] for a in intent['aggregates']]==['*','score']


@pytest.mark.parametrize('q,where,cols',[
    ('zone 내림차순, 같은 그룹은 score 오름차순, 같은 score는 item 순서로 세 열을 보여 주세요.',None,['item','score','zone']),
    ('NULL을 제외하고 score 오름차순, 동점은 item 순서로 item와 score를 보여 주세요.','score IS NOT NULL',['item','score']),
    ('score가 0이 아닌 행(NULL 제외)의 item를 오름차순으로 조회하고 선택 이유를 설명하세요.','score <> 0',['item']),
])
def test_unambiguous_tie_connectors_nonnull_sort_and_redundant_null_note(q,where,cols):
    p=problem(q)
    intent,reason=infer_basic_intent(p,q)
    assert intent,reason
    assert intent['select_columns']==cols and intent['where']==where


@pytest.mark.parametrize('q',[
    '출력: 두 열',
    '출력: NULL을 제외한 score',
    'score가 NULL인 행(NULL 제외)의 item를 오름차순으로 조회해 주세요.',
    'NULL을 제외하고 item와 score를 조회해 주세요.',
])
def test_ambiguous_projection_and_contradictory_null_modifier_require_input(q):
    p=problem(q)
    assert infer_basic_intent(p,q)[0] is None

