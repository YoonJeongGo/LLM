"""Student-facing procedure statements from actual isolated SQLite evidence."""
import copy
import json

import pytest

from edu_tutor.problems.models import normalize_problem
from edu_tutor.problems.evidence import verify_answer,display_answer
from edu_tutor.lessons.verified import generate_verified_plan,validated_logical_stage,logical_aggregate_speech
from edu_tutor.lessons.plans import scene_at


def lesson(sql,rows=None):
    if rows is None:rows=[['a',4],['a',None],['b',0],['b',-8],[None,None]]
    p=normalize_problem({'task_kind':'query_result','confirmed':True,'raw_text':'개발 검증용 SQL의 계산 과정을 설명해 주세요.',
        'query':sql,'tables':[{'name':'readings','columns':[{'name':'category','type':'TEXT'},
            {'name':'measure','type':'REAL'}],'rows':rows}]})
    e=verify_answer(p,'',p['raw_text'])
    assert e['status']=='verified' and e['calculation']['status']=='independent_aggregate_match'
    source={'id':'source-fixture','problem':p,'evidence':e,'content':display_answer(e)}
    record=generate_verified_plan(source,p['raw_text'],'lesson-fixture')
    record['id']='lesson-fixture'
    assert record['speech_allowed'] and record['plan']
    return source,record


def test_no_where_or_having_does_not_invent_a_filter_and_avg_teaches_sum_over_count():
    source,record=lesson('SELECT category, AVG(measure) AS mean FROM readings GROUP BY category')
    e=source['evidence'];steps=record['plan']['steps']
    assert '조건이 없으므로 원본 5행을 모두' in steps[0]['speech']
    assert '원본 1열의 값이 같은 행끼리' in steps[1]['speech'] and '3개' in steps[1]['speech']
    assert '원본 2열' in steps[2]['speech'] and 'NULL을 제외한 값을 더한 뒤' in steps[2]['speech']
    assert '값의 개수로 나누어 평균' in steps[2]['speech'] and '결과는 NULL' in steps[2]['speech']
    assert '그룹을 거르는 조건이 없어' in steps[3]['speech'] and '3행' in steps[3]['speech']
    speech=' '.join(item['speech'] for item in steps)
    assert all(word not in speech for word in ['SQLite','검증','대조','WHERE를 통과','HAVING 조건을 적용'])
    assert [s['id'] for s in steps]==['s1','s2','s3','s4']
    assert scene_at(record['plan'],3)['elements'][e['id']+'-result']['rows']==e['result']['rows']
    assert validated_logical_stage(record,source,{'step':2})['stage']=='aggregate'


def test_where_filters_rows_having_filters_computed_groups_and_count_zero_is_kept():
    source,record=lesson('SELECT category, COUNT(*), COUNT(measure), SUM(measure), AVG(measure) '
        'FROM readings WHERE measure >= 0 GROUP BY category HAVING COUNT(*) >= 1')
    steps=record['plan']['steps'];e=source['evidence']
    assert '각 행이 주어진 조건에 맞는지' in steps[0]['speech'] and '5행 중 2행' in steps[0]['speech']
    assert '행을 하나씩 세어 전체 행 수' in steps[2]['speech']
    assert 'NULL을 제외하고 값이 있는 칸의 개수' in steps[2]['speech']
    assert '0도 값이므로 포함' in steps[2]['speech']
    assert '값을 더해 합계' in steps[2]['speech'] and '개수로 나누어 평균' in steps[2]['speech']
    assert '각 그룹의 집계값' in steps[3]['speech'] and '맞는 그룹만 남깁니다' in steps[3]['speech']
    assert '최종 결과는 2행' in steps[3]['speech'] and len(e['result']['rows'])==2


def test_no_group_by_uses_one_input_collection_instead_of_inventing_group_keys():
    _,record=lesson('SELECT COUNT(*), COUNT(measure), SUM(measure), AVG(measure) FROM readings WHERE measure >= 0')
    steps=record['plan']['steps']
    assert '그룹 열이 없으므로 남은 행 전체를 한 묶음' in steps[1]['speech']
    assert '원본 2열' in steps[2]['speech'] and '같은 행끼리' not in steps[1]['speech']


@pytest.mark.parametrize('rows,sql,expected,zero_spoken',[
    ([['a',None],['b',0],['c',-2]],'SELECT COUNT(measure) FROM readings',2,True),
    ([['a',None],['b',2]],'SELECT COUNT(measure) FROM readings',1,False),
    ([['a',None],['b',0]],'SELECT COUNT(*) FROM readings',2,False),
    ([['a',0],['b',0],['c',None]],'SELECT COUNT(DISTINCT measure) FROM readings',1,True)])
def test_zero_rule_uses_actual_counted_values_and_keeps_existing_numeric_result(rows,sql,expected,zero_spoken):
    source,record=lesson(sql,rows)
    speech=record['plan']['steps'][0]['speech']
    assert ('0도 값이므로 포함' in speech)==zero_spoken
    assert f'{expected}입니다.' in speech and source['evidence']['result']['rows']==[[expected]]
    assert scene_at(record['plan'],0)['elements'][source['evidence']['id']+'-result']['rows']==[[expected]]


def test_empty_group_input_does_not_claim_that_a_calculation_or_filter_happened():
    _,record=lesson('SELECT category, AVG(measure) FROM readings GROUP BY category',[])
    steps=record['plan']['steps']
    assert '원본 0행을 모두' in steps[0]['speech']
    assert '그룹은 0개' in steps[1]['speech']
    assert steps[2]['speech']=='집계할 그룹이 없어 계산할 결과도 없습니다.'
    assert '최종 결과는 0행' in steps[3]['speech']


@pytest.mark.parametrize('no_arrows',[False,True])
def test_exact_saved_old_wording_retains_stage_binding_but_tampering_does_not(no_arrows):
    source,record=lesson('SELECT category, COUNT(*) FROM readings GROUP BY category',
        [['a',1],['a',2],['b',3]])
    old=copy.deepcopy(record)
    speeches=['원본 3행 중 WHERE를 통과한 행은 3개입니다. 학습용 논리 순서입니다.',
        '남은 행을 2개 그룹으로 묶습니다.','각 그룹의 실제 입력값으로 집계하고 SQLite 결과와 대조했습니다.',
        'HAVING 조건을 적용한 최종 SELECT 결과는 2행입니다.']
    for step,speech in zip(old['plan']['steps'],speeches):
        step['speech']=speech
        if no_arrows:step['board_actions']=[a for a in step['board_actions'] if a['type']!='arrow']
    before=copy.deepcopy(old)
    assert validated_logical_stage(old,source,{'step':1})['stage']=='group'
    assert old==before
    old['plan']['steps'][2]['speech']='모든 결과는 999입니다.'
    assert validated_logical_stage(old,source,{'step':1}) is None
    old=copy.deepcopy(before)
    result=next(a for a in old['plan']['steps'][3]['board_actions'] if a['type']=='table')
    result['rows']=[['wrong',999]]
    assert validated_logical_stage(old,source,{'step':1}) is None


def test_long_identifiers_stay_bound_to_board_positions_and_within_speech_limit():
    columns=['a'+str(i)+'x'*60 for i in range(8)]
    aggregates=[{'function':'avg','column':name,'distinct':True,'count':0,'included_values':[]}
        for name in columns]
    speech=logical_aggregate_speech({'aggregates':aggregates,'group_columns':['g']},{'columns':columns})
    assert len(speech)<=1000 and all(f'원본 {i+1}열' in speech for i in range(8))
    assert speech.count('중복된 값은 한 번만')==8
