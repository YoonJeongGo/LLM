"""Authored CPU safety regressions; no independent evaluation inputs."""
import copy
import json
import pytest
from edu_tutor.problems.models import normalize_problem
from edu_tutor.problems.evidence import verify_answer,display_answer
from edu_tutor.lessons.verified import generate_verified_plan,condition_row_speech
from edu_tutor.lessons.verified import ordering_speech,validated_logical_stage

def source(kind,question,query,rows,*,column_type='INTEGER'):
    data={'task_kind':kind,'raw_text':question,'confirmed':True,
        'tables':[{'name':'readings','columns':[{'name':'score','type':column_type}],'rows':[[v] for v in rows]}]}
    if kind=='query_result':data['query']=query
    p=normalize_problem(data)
    raw=json.dumps({'sql':query,'explanation':'원시 모델 초안은 그대로 보존한다.'},ensure_ascii=False)
    e=verify_answer(p,raw,question)
    return {'id':'safety-source','session_id':'safety-session','problem':p,'evidence':e,'content':display_answer(e),'raw_model_response':raw}

@pytest.mark.parametrize('value',[7,0,-3,None])
@pytest.mark.parametrize('predicate',['score IS NOT NULL','NOT (score IS NULL)','score IS NULL'])
def test_null_condition_speech_uses_source_value_not_not_operand_truth(value,predicate):
    m=source('query_result','조건을 설명해 주세요.','SELECT score FROM readings WHERE '+predicate,[value])
    e=m['evidence'];assert e['logical_steps']
    original=copy.deepcopy(m)
    speech=condition_row_speech(e['logical_steps'],e['working_tables'][0],0)
    assert 'score의 값은 '+('NULL' if value is None else str(value))+'이고' in speech
    assert '값은 True이고' not in speech and '값은 False이고' not in speech
    assert m==original

def test_write_sql_without_independent_trace_never_becomes_result_only_speech():
    m=source('write_sql','NULL을 제외한 서로 다른 score의 개수를 구해 주세요.',
        'SELECT COUNT(DISTINCT score) FROM readings WHERE score IS NOT NULL',['1',1,None,'two','1'],column_type='TEXT')
    e=m['evidence'];assert e['status']=='verified' and e['logical_steps'] is None
    assert e['sql_origin']=='model_candidate' and e['support_status']=='verified_no_plan'
    original=copy.deepcopy(m)
    lesson=generate_verified_plan(m,m['problem']['raw_text'],'safety-plan')
    assert lesson['plan'] is None and not lesson['speech_allowed']
    assert e['calculation']['reason'] in lesson['reason']
    assert m==original

def test_actual_given_query_result_keeps_only_explicit_execution_summary():
    m=source('query_result','주어진 SQL의 실행 결과를 확인해 주세요.',
        'SELECT SUM(score > 0) FROM readings',[None,0,7,-3])
    assert m['evidence']['sql_origin']=='unchanged_user_query' and m['evidence']['logical_steps'] is None
    lesson=generate_verified_plan(m,m['problem']['raw_text'],'safety-query-plan')
    assert lesson['speech_allowed'] and len(lesson['plan']['steps'])==1
    assert lesson['plan']['verification']['status']=='execution_grounded'
    assert '중간 계산 설명은 지원 범위 밖' in lesson['plan']['steps'][0]['speech']
    assert lesson['generation']['source']=='confirmed_user_query_execution_only'

@pytest.mark.parametrize('origin',['model_candidate','application_from_confirmed_bounded_intent',None])
def test_result_only_source_cannot_masquerade_as_student_supplied_query(origin):
    m=source('query_result','실행 결과 확인','SELECT SUM(score > 0) FROM readings',[0,7])
    m['evidence']['sql_origin']=origin
    lesson=generate_verified_plan(m,m['problem']['raw_text'],'safety-origin-plan')
    assert lesson['plan'] is None and not lesson['speech_allowed']

def test_brief_order_preserves_priority_directions_and_relevant_ties():
    logical={'order_by':[{'column':'reading','direction':'DESC','nulls_first':False},
        {'column':'urgency','direction':'ASC','nulls_first':True},{'column':'device','direction':'ASC','nulls_first':True}], 'order_ties':[]}
    speech=ordering_speech(logical,brief=True)
    assert speech.index('reading의 내림차순')<speech.index('urgency의 오름차순')<speech.index('device의 오름차순')
    assert '앞 값이 같을 때만' in speech
    assert len(speech)<len(ordering_speech(logical))
    logical['order_ties']=[{'row_ids':['x','y'],'values':[0,1,'same']}]
    assert '순서는 미지정' in ordering_speech(logical,brief=True)
    assert '순서는 보장되지 않습니다' in ordering_speech({'order_by':[]},brief=True)

@pytest.mark.parametrize('rows,ri', [([[7],[0],[None],[-2]],1), ([[7],[0],[None],[-2]],2), ([[0],[0],[None]],0)])
def test_brief_current_row_keeps_original_null_value_truth_and_observed_position(rows,ri):
    values=[r[0] for r in rows]
    m=source('query_result','현재 선택한 행의 조건과 순서를 설명해 주세요.',
        'SELECT score FROM readings WHERE score IS NULL OR score >= 0 ORDER BY score DESC',values)
    original={**generate_verified_plan(m,m['problem']['raw_text'],'main'),'id':'main','source_message_id':m['id']}
    table=m['evidence']['working_tables'][0]
    context={'lesson_id':'main','step':1,'problem_revision':m['problem']['revision'],
        'selected_cell':{'table_element_id':table['id'],'row_id':table['row_ids'][ri],
            'column_id':table['column_ids'][0],'cell_id':table['cell_ids'][ri][0]}}
    context['_verified_logical_stage']=validated_logical_stage(original,m,context)
    assert context['_verified_logical_stage']
    supplement=generate_verified_plan({**m,'lesson_context':context},'왜 선택한 이 행이 포함돼? 정렬 순서도 설명해 줘.','supplement')
    assert supplement['speech_allowed'],supplement
    speech=supplement['plan']['steps'][0]['speech']
    assert ('NULL' if values[ri] is None else str(values[ri])) in speech and 'TRUE' in speech
    assert 'score의 내림차순' in speech
    rank=m['evidence']['logical_steps']['ordered_row_ids'].index(table['row_ids'][ri])+1
    assert f'{rank}번째' in speech
