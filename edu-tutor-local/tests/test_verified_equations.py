import json
import pytest

from edu_tutor.problems.models import normalize_problem
from edu_tutor.problems.evidence import verify_answer
from edu_tutor.lessons.verified import generate_verified_plan, aggregate_equation


def lesson(values, function='AVG', task='query_result'):
    query=f'SELECT {function}(reading) AS result FROM measurements'
    question=f'{function}(reading)을 설명해 주세요.'
    problem=normalize_problem({'task_kind':task,'raw_text':question,'confirmed':True,
        'tables':[{'name':'measurements','columns':[{'name':'reading','type':'REAL'}],
                   'rows':[[x] for x in values]}], **({'query':query} if task=='query_result' else {})})
    evidence=verify_answer(problem,json.dumps({'sql':query}),question)
    assert evidence['calculation']['status']=='independent_aggregate_match'
    result=generate_verified_plan({'id':'dev-equation','problem':problem,'evidence':evidence,'content':'CPU fixture'},question,'dev-lesson')
    return evidence,result['plan']


@pytest.mark.parametrize('values,function,formula',[
    ([6,None,0,3],'AVG',r'\frac{9}{3}=3.0'),
    ([-4,None,0,7,7],'SUM','(-4) + 0 + 7 + 7=10'),
    ([], 'AVG',r'\mathrm{AVG}=\mathrm{NULL}'),
    ([None,None], 'SUM',r'\mathrm{SUM}=\mathrm{NULL}'),
    ([0,0], 'AVG',r'\frac{0}{2}=0.0'),
])
def test_equation_and_write_target_use_same_checked_calculation(values,function,formula):
    evidence,plan=lesson(values,function)
    step=plan['steps'][-1]
    equations=[a for a in step['board_actions'] if a['type']=='equation']
    assert len(equations)==1 and equations[0]['latex']==formula
    assert step['gesture']=={'kind':'write','target_element_id':equations[0]['element_id']}
    board=next(a for a in step['board_actions'] if a['type']=='table' and a['caption']=='최종 SELECT 실행 결과')
    assert board['rows']==evidence['result']['rows']
    assert '/0' not in formula and '{0}{0}' not in formula


def test_sql_writing_keeps_its_code_slot_without_equation_overlap():
    _,plan=lesson([2,None,0,8],task='write_sql')
    actions=[a for step in plan['steps'] for a in step['board_actions']]
    assert any(a['type']=='code' for a in actions)
    assert not any(a['type']=='equation' for a in actions)


def test_long_sum_is_bounded_and_exponents_are_numeric_latex():
    _,plan=lesson(list(range(20)),'SUM')
    assert plan['steps'][0]['board_actions'][-1]['latex']==r'\mathrm{SUM}=190'
    assert aggregate_equation({'function':'sum','result':1e20,'included_values':[1e20]})==r'1\times 10^{20}=1\times 10^{20}'


@pytest.mark.parametrize('value',[float('inf'),'\\input{bad}',True])
def test_unchecked_non_numeric_content_cannot_enter_formula(value):
    with pytest.raises(ValueError):
        aggregate_equation({'function':'sum','result':value,'included_values':[value]})
