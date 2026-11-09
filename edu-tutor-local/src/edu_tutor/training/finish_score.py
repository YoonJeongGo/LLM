"""Offline holdout scoring; never imports answers into a generation worker."""
from __future__ import annotations

import json

from edu_tutor.evaluation.sql_sandbox import compare_results, execute_sql, extract_sql


def public_item(record):
    return {'id':record['id'], 'messages':[dict(m) for m in record['messages'] if m['role'] in {'system','user'}]}


def score_response(record, text, finish_reason, *, executor=execute_sql, extractor=extract_sql):
    """Result correctness is separate from explanation and human quality.

    SQL column aliases were not requested by these exercises. Ignore aliases for
    value grading but retain strict contract matching as a separate field.
    """
    result={'id':record['id'],'finish_reason':finish_reason,'answered':False,
        'sql_result_correct':False if 'expected' in record else None,
        'explanation_quality':'H_PENDING','overall_education_pass':None}
    if finish_reason!='eos':
        return {**result,'failure':'incomplete_generation'}
    if not text or not text.strip():return {**result,'failure':'empty_response'}
    if 'expected' not in record:
        return {**result,'answered':True,'concept_review':'REQUIRES_CLAIM_AND_HUMAN_REVIEW','text':text,
                'notice':'Nonempty response is not a correct concept answer; no automatic pass assigned.'}
    try:sql=extractor(text)
    except ValueError as exc:return {**result,'failure':'sql_parse:'+str(exc)}
    actual=executor(sql,record['fixture'],dialect=record.get('sql_dialect','sqlite'))
    result.update(sql=sql,actual=actual,answered=actual.get('status')=='executed',
                  strict_result_contract=compare_results(actual,record['expected']))
    comparable={**actual,'columns':record['expected']['columns']} if len(actual.get('columns',[]))==len(record['expected']['columns']) else actual
    result['sql_result_correct']=compare_results(comparable,record['expected'])
    try:parsed=json.loads(text)
    except ValueError:parsed={}
    explanation=parsed.get('explanation') if isinstance(parsed,dict) else None
    result['explanation_present']=bool(isinstance(explanation,str) and explanation.strip())
    result['notice']='Executed result comparison only. SQL success or correct values do not approve the full explanation.'
    return result


def summarize(items):
    sql=[i for i in items if i['sql_result_correct'] is not None]
    return {'total':len(items),'answered':sum(i['answered'] for i in items),
            'sql_total':len(sql),'sql_result_correct':sum(i['sql_result_correct'] for i in sql),
            'incomplete':sum(i['finish_reason']!='eos' for i in items),
            'concept_review_pending':sum(i['sql_result_correct'] is None for i in items),
            'explanation_and_human_review':'H_PENDING','education_ready':False}
