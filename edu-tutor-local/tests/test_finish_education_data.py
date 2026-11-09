import json

import pytest

from edu_tutor.evaluation.sql_sandbox import _execute
from edu_tutor.training.data import DatasetError, validate_dataset
from edu_tutor.training.finish_data import FINAL, TRAIN, VALIDATION, build, exercise
from edu_tutor.training.finish_score import public_item, score_response, summarize


def test_procedural_examples_have_disjoint_families_and_independent_values(tmp_path):
    report=build(tmp_path)
    assert report['counts']=={'train':240,'validation':40,'test':80}
    assert report['family_count']==48
    assert report['independently_calculated_selects']==295
    assert report['sqlite_checks']==355
    assert report['missing_input_rule_checks']==5
    assert not set(TRAIN)&set(VALIDATION) and not set(TRAIN)&set(FINAL) and not set(VALIDATION)&set(FINAL)
    assert report['human_review']=='H_PENDING'
    final=tmp_path/'final/test.jsonl';original=final.read_bytes()
    build(tmp_path)
    assert final.read_bytes()==original
    final.write_text('{}\n',encoding='utf-8')
    with pytest.raises(ValueError,match='frozen'):build(tmp_path)


def test_structural_variant_cannot_cross_split_even_with_different_family():
    a,_=exercise('project',0,'train');b,_=exercise('project',1,'validation')
    b['problem_family_id']='renamed_family'
    with pytest.raises(DatasetError,match='structural SQL family leakage'):
        validate_dataset(records=[a,b],enforce_minimums=False)


def test_generation_payload_cannot_contain_expected_or_assistant_answers():
    record,_=exercise('sum',0,'train');payload=public_item(record)
    assert set(payload)=={'id','messages'}
    assert all(m['role']!='assistant' for m in payload['messages'])
    assert 'expected' not in payload and 'fixture' not in payload


def executor(sql,fixture,**_):
    return _execute({'sql':sql,'fixture':fixture})


def test_scoring_does_not_conflate_aliases_sql_and_explanation_quality():
    record,_=exercise('sum',0,'train')
    answer=json.loads(record['messages'][-1]['content']);answer['sql']=answer['sql'].replace('AS result','AS renamed')
    result=score_response(record,json.dumps(answer),'eos',executor=executor)
    assert result['sql_result_correct'] and not result['strict_result_contract']
    assert result['overall_education_pass'] is None and result['explanation_quality']=='H_PENDING'
    bad={**answer,'sql':answer['sql'].replace('SUM(val)','COUNT(*)')}
    assert not score_response(record,json.dumps(bad),'eos',executor=executor)['sql_result_correct']
    assert not score_response(record,json.dumps(answer),'length',executor=executor)['answered']


def test_concept_and_refusal_are_not_marked_correct():
    concept,_=exercise('create',0,'train');sql,_=exercise('sum',0,'train')
    a=score_response(concept,'어떤 답변','eos');b=score_response(sql,'지원하지 않습니다','eos')
    summary=summarize([a,b])
    assert summary['concept_review_pending']==1 and summary['sql_result_correct']==0
    assert not summary['education_ready']


def test_existing_app_parser_accepts_only_unambiguous_fence_without_answer_repair():
    from edu_tutor.problems.sql_response import extract_sql_candidate
    record,_=exercise('sum',0,'train');answer=record['messages'][-1]['content']
    fenced='```json\n'+answer+'\n```'
    old=score_response(record,fenced,'eos',executor=executor)
    normalized=score_response(record,fenced,'eos',executor=executor,extractor=extract_sql_candidate)
    assert not old['sql_result_correct'] and normalized['sql_result_correct']
    assert normalized['overall_education_pass'] is None
    for ambiguous in [fenced+'\n'+fenced,'extra prose\n'+fenced,
                      '```json\n{"sql":"SELECT 1","sql":"SELECT 2"}\n```']:
        assert not score_response(record,ambiguous,'eos',executor=executor,extractor=extract_sql_candidate)['sql_result_correct']
