from copy import deepcopy
import json

from edu_tutor.training.finish_app_score import app_score_response, public_problem, summarize_app


def sample():
    return {'id':'self_authored_cpu_fixture', 'sql_dialect':'sqlite',
        'messages':[{'role':'system','content':'SQLite 튜터'},
                    {'role':'user','content':'COUNT(*)와 COUNT(value)를 구하세요.'},
                    {'role':'assistant','content':'PRIVATE_ASSISTANT_REFERENCE'}],
        'fixture':{'tables':[{'name':'samples','columns':[{'name':'value','type':'INTEGER'}],
                             'rows':[[None],[0],[-2],[8]]}]},
        'expected':{'sql':'PRIVATE_REFERENCE_SQL_DO_NOT_INJECT', 'columns':['n','valued'],
                    'rows':[[4,3]], 'row_order':'ordered'}}


def test_public_problem_never_uses_expected_sql_or_assistant():
    row=sample();problem=public_problem(row)
    assert problem['task_kind']=='write_sql'
    assert 'query' not in problem and 'intent' not in problem
    assert 'PRIVATE_' not in json.dumps(problem)
    problem['tables'][0]['rows'][0][0]=999
    assert row['fixture']['tables'][0]['rows'][0][0] is None


def test_app_numeric_plan_derives_correct_count_and_preserves_raw_error_separately():
    row=sample()
    raw=json.dumps({'sql':'SELECT COUNT(*) AS n, COUNT(value) AS valued FROM samples',
                    'explanation':'COUNT(value)는 NULL인 행만 셉니다.'},ensure_ascii=False)
    score=app_score_response(row,raw,'eos')
    assert score['accepted'] and score['accepted_result_correct']
    speech=' '.join(step['speech'] for step in score['lesson']['plan']['steps'])
    assert 'NULL을 제외한 값' in speech and 'NULL인 행만' not in speech
    wrong=deepcopy(row);wrong['expected']['rows']=[[9,9]]
    other=app_score_response(wrong,raw,'eos')
    assert other['lesson']==score['lesson']
    # The private oracle may change grading, never the product evidence.
    # Wall-clock measurement is naturally different between independent calls.
    first_evidence=deepcopy(score['evidence']);second_evidence=deepcopy(other['evidence'])
    first_evidence.pop('timings_seconds');second_evidence.pop('timings_seconds')
    assert first_evidence==second_evidence
    assert other['accepted_result_correct'] is False


def test_unsupported_and_truncated_responses_are_not_correct_or_retried():
    row=sample();row['messages'][1]['content']='value의 순위를 윈도우 함수로 조회하세요.'
    stopped=app_score_response(row,json.dumps({'sql':'SELECT ROW_NUMBER() OVER (ORDER BY value) AS rank FROM samples'}),'eos')
    assert not stopped['accepted'] and not stopped['accepted_result_correct']
    incomplete=app_score_response(sample(),'SELECT COUNT(*) FROM samples','length')
    assert not incomplete['accepted'] and incomplete['new_model_calls']==0
    summary=summarize_app([stopped,incomplete])
    assert summary['stopped_or_unsupported']==2 and summary['accepted_result_correct']==0
