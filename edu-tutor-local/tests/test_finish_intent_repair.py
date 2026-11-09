"""New developer fixtures only; no dataset IDs, names or answers in rules."""
import copy
import json
import pytest

from edu_tutor.problems.models import normalize_problem,infer_basic_intent
from edu_tutor.problems.evidence import verify_answer,display_answer,intent_sql
from edu_tutor.problems.app_correction import verify_with_app_correction
from edu_tutor.lessons.verified import generate_verified_plan
from edu_tutor.lessons.plans import scene_at


def group_problem(rows,group='region',value='reading',*,kind='REAL'):
    return normalize_problem({'task_kind':'write_sql','confirmed':True,
        'raw_text':f'{group}별 NULL을 제외한 {value} 평균을 보여 주세요.',
        'tables':[{'name':'measurements','columns':[{'name':group,'type':'TEXT'},
            {'name':value,'type':kind}],'rows':rows}]})


@pytest.mark.parametrize('rows,expected',[
    ([['north',4],['north',None],['south',0],['south',-6],['south',-6]],[['north',4],['south',-4]]),
    ([],[]),([['north',None],['south',None]],[['north',None],['south',None]]),
    ([[None,0],[None,8],['other',None]],[[None,4],['other',None]])])
def test_clear_group_roles_keep_original_rows_null_groups_and_board(rows,expected):
    p=group_problem(rows);before=copy.deepcopy(p)
    intent,scope=infer_basic_intent(p,p['raw_text'])
    assert scope=='bounded_language_group_average' and intent['group_by']==['region']
    raw=json.dumps({'sql':'SELECT region, AVG(reading) AS mean FROM measurements GROUP BY region'})
    e=verify_with_app_correction(p,raw,p['raw_text'])
    assert e['status']=='verified' and e['calculation']['status']=='independent_aggregate_match'
    assert sorted(e['result']['rows'],key=repr)==sorted(expected,key=repr)
    assert 'app_correction' not in e and e['sql_origin']=='model_candidate' and p==before
    message={'id':'fixture-message','problem':p,'evidence':e,'content':display_answer(e),'raw_model_response':raw}
    lesson=generate_verified_plan(message,p['raw_text'],'fixture-lesson')
    assert lesson['plan'] and len(lesson['plan']['steps'])==4
    scene=scene_at(lesson['plan'],3)
    assert scene['elements'][e['id']+'-result']['rows']==e['result']['rows']
    assert len(e['logical_steps']['groups'])==len(expected)


def test_names_case_and_values_derive_from_schema():
    p=group_problem([['alpha',-11],['alpha',5]],group='Zone_9',value='Offset_2')
    p['raw_text']='SQLite. zone_9별 OFFSET_2의 평균을 구하는 SQL을 작성해 주세요.'
    intent,_=infer_basic_intent(p,p['raw_text'])
    assert intent['group_by']==['Zone_9'] and intent['aggregates'][0]['column']=='Offset_2'
    e=verify_answer(p,json.dumps({'sql':intent_sql(intent)}),p['raw_text'])
    assert e['result']['rows']==[['alpha',-3]]


def test_explanation_stage_order_is_not_newly_treated_as_result_sorting():
    p=group_problem([['north',1]])
    p['raw_text']='AVG(reading)을 원본에서 결과 순서대로 설명해 주세요.'
    intent,scope=infer_basic_intent(p,p['raw_text'])
    assert intent and scope=='bounded_language_aggregate' and not intent['group_by']


@pytest.mark.parametrize('extra',[' 오름차순으로',' reading이 1 이상인 행만',
    ' 양수만',' 조건에 따라',' 다른 조건은 생략',' region과 reading별로',' WHERE reading IS NOT NULL'])
def test_group_request_with_sort_filter_or_unparsed_text_stays_stopped(extra):
    p=group_problem([['north',1]])
    p['raw_text']+=extra
    assert infer_basic_intent(p,p['raw_text'])[0] is None


@pytest.mark.parametrize('sql',[
    'SELECT region, AVG(reading) FROM measurements GROUP BY region ORDER BY region',
    'SELECT region, AVG(reading) FROM measurements WHERE reading IS NOT NULL GROUP BY region',
    'SELECT AVG(reading) FROM measurements GROUP BY region',
    'SELECT region, region, AVG(reading) FROM measurements GROUP BY region',
    'SELECT region, SUM(reading) FROM measurements GROUP BY region',
    'SELECT region, AVG(reading) FROM measurements GROUP BY region HAVING AVG(reading)>0'])
def test_unrequested_model_order_filter_missing_group_or_operation_is_not_repaired(sql):
    p=group_problem([['north',None],['south',0]])
    e=verify_with_app_correction(p,json.dumps({'sql':sql}),p['raw_text'])
    assert e['status']=='stopped' and 'app_correction' not in e


def test_multitable_unknown_schema_and_nonnumeric_group_average_fail_closed():
    p=group_problem([['north','one']],kind='TEXT')
    assert infer_basic_intent(p,p['raw_text'])[0] is None
    p=group_problem([['north',1]])
    p['raw_text']='missing별 reading 평균을 보여 주세요.'
    assert infer_basic_intent(p,p['raw_text'])[0] is None
    p['raw_text']='region별 reading 평균을 보여 주세요.'
    other=copy.deepcopy(p['tables'][0]);other['name']='other';p['tables'].append(other)
    assert infer_basic_intent(p,p['raw_text'])[0] is None


def distinct_problem(values,*,kind='INTEGER'):
    return normalize_problem({'task_kind':'write_sql','confirmed':True,
        'raw_text':'NULL을 제외한 서로 다른 amount의 개수를 구해 주세요.',
        'tables':[{'name':'samples','columns':[{'name':'amount','type':kind},{'name':'other','type':'INTEGER'}],
            'rows':[[value,None if index%2 else 1] for index,value in enumerate(values)]}]})


@pytest.mark.parametrize('values,expected',[([],0),([None,None],0),([0,0],1),([0,None,-8,-8,9],3)])
@pytest.mark.parametrize('qualifier',['','s.'])
def test_same_column_nonnull_filter_is_equivalent_including_empty(values,expected,qualifier):
    p=distinct_problem(values)
    sql=f'SELECT COUNT(DISTINCT {qualifier}amount) FROM samples AS s WHERE {qualifier}amount IS NOT NULL'
    raw=json.dumps({'sql':sql});e=verify_with_app_correction(p,raw,p['raw_text'])
    assert e['status']=='verified' and e['result']['rows']==[[expected]]
    assert e['calculation']['status']=='independent_aggregate_match'
    assert e['sql']==sql and e['sql_origin']=='model_candidate' and 'app_correction' not in e
    assert e['intent']['input_bound_equivalence'][0]['kind']=='count_distinct_same_column_nonnull_filter'


def test_mixed_text_affinity_keeps_semantic_equivalence_without_claiming_python_trace_match():
    p=distinct_problem(['1',1,None,'two','1'],kind='TEXT')
    e=verify_answer(p,json.dumps({'sql':'SELECT COUNT(DISTINCT amount) FROM samples WHERE amount IS NOT NULL'}),p['raw_text'])
    assert e['intent']['status']=='supported_match' and e['execution']['rows']==[[2]]
    assert e['calculation']['status']=='outside_supported_trace' and e['logical_steps'] is None


@pytest.mark.parametrize('sql',[
    'SELECT COUNT(*) FROM samples WHERE amount IS NOT NULL',
    'SELECT COUNT(amount) FROM samples WHERE amount IS NOT NULL',
    'SELECT COUNT(DISTINCT amount) FROM samples WHERE other IS NOT NULL',
    'SELECT COUNT(DISTINCT amount) FROM samples WHERE amount IS NOT NULL AND amount>0',
    'SELECT COUNT(DISTINCT amount) FROM samples WHERE bad.amount IS NOT NULL',
    'SELECT other, COUNT(DISTINCT amount) FROM samples WHERE amount IS NOT NULL GROUP BY other'])
def test_distinct_equivalence_does_not_swallow_whole_rows_other_columns_or_extra_filters(sql):
    p=distinct_problem([None,0,3,3])
    e=verify_answer(p,json.dumps({'sql':sql}),p['raw_text'])
    assert e['status']=='stopped'
    assert not any(v.get('kind')=='count_distinct_same_column_nonnull_filter'
        for v in e['intent'].get('input_bound_equivalence',[])) or e['execution']['status']!='executed'


@pytest.mark.parametrize('question',['서로 다른 전체 행의 개수','COUNT(DISTINCT *)를 구해 주세요.',
    '전체 행의 개수와 amount의 개수를 알려 주세요.'])
def test_no_guessing_distinct_whole_rows_or_compound_count(question):
    p=distinct_problem([1,1,None]);p['raw_text']=question
    assert infer_basic_intent(p,question)[0] is None


def test_v021_explicit_group_sort_is_now_supported_but_not_invented():
    p=group_problem([["north",1]])
    p["raw_text"]+=" region 순서로"
    intent,scope=infer_basic_intent(p,p["raw_text"])
    assert scope=="bounded_language_aggregate_v2"
    assert intent["group_by"]==["region"] and intent["order_by"]==[{"column":"region","direction":"asc"}]
