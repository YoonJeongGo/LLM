"""Regrade saved validation outputs using the existing app's strict JSON-fence parser.

Original raw results and legacy grades are preserved. No new inference occurs.
This correction measures parsing/results, not improved model explanations.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from edu_tutor.training.data import load_records
from edu_tutor.training.finish_score import score_response,summarize
from edu_tutor.problems.sql_response import extract_sql_candidate,SQL_EXTRACTION_PROTOCOL,_JSON_FENCE
from finish_education_live import check_selection_freeze,protocol_precision


def regrade(folder):
    folder=Path(folder).resolve()
    if not folder.is_relative_to(ROOT/'runs/finish-v2/20261029/education'):
        raise ValueError('Only finish validation evidence directories are supported')
    source=folder/'result.json'
    original=json.loads(source.read_text(encoding='utf-8'))
    if original['status']!='completed':raise ValueError('Wait for completed original measurement')
    dataset=ROOT/original['protocol']['dataset']
    final=original['protocol'].get('final_holdout_read') is True
    expected_path=ROOT/('runs/finish-v2/20261028/education/final/test.jsonl' if final else 'runs/finish-v2/20261028/education/development/validation.jsonl')
    if dataset.resolve()!=expected_path:
        raise ValueError('Unrecognized frozen dataset path')
    if final:
        reference=original['protocol'].get('selection_freeze') or {}
        selection=check_selection_freeze(ROOT/reference.get('path',''),original['protocol']['adapter'],
            precision=protocol_precision(original['protocol'],require_explicit=True))
        if selection['reference']!=reference:
            raise ValueError('Selection freeze differs from original final evaluation')
    if hashlib.sha256(dataset.read_bytes()).hexdigest()!=original['protocol']['dataset_sha256']:
        raise ValueError('Frozen dataset hash changed')
    records={r['id']:r for r in load_records([dataset])}
    if len(original['items'])!=(80 if final else 40) or set(records)!={i['id'] for i in original['items']}:
        raise ValueError('Complete original measurement required')
    scores=[]
    for old in original['items']:
        text=old.get('actual_answer') or ''
        score=score_response(records[old['id']],text,old['finish_reason'],extractor=extract_sql_candidate)
        match=_JSON_FENCE.fullmatch(text) if isinstance(text,str) else None
        try:parsed=json.loads(match.group(1) if match else text)
        except ValueError:parsed={}
        if 'expected' in records[old['id']]:
            score['explanation_present']=isinstance(parsed,dict) and isinstance(parsed.get('explanation'),str) and bool(parsed['explanation'].strip())
        score.update(question=old['question'],actual_answer=old.get('actual_answer'),
            raw_model_event=old.get('raw_model_event'),job_id=old.get('job_id'),batch=old.get('batch'),
            original_legacy_grade={k:old.get(k) for k in ['answered','sql_result_correct','failure']})
        scores.append(score)
    result={**original,'items':scores,'summary':summarize(scores),'regraded_at':datetime.now(timezone.utc).isoformat(),
        'original_result_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'original_legacy_summary':original['summary'],'new_inference':False,'model_quality_improvement':False,
        'grading_protocol':SQL_EXTRACTION_PROTOCOL,
        'grading_notice':'Existing app parser accepts one complete unambiguous JSON fence. No SQL/answer repair or model call. SQL results and explanation quality remain separate.',
        'parser_sha256':hashlib.sha256((ROOT/'src/edu_tutor/problems/sql_response.py').read_bytes()).hexdigest()}
    target=folder/'result-normalized.json'
    if target.exists():
        prior=json.loads(target.read_text(encoding='utf-8'))
        if prior['original_result_sha256']!=result['original_result_sha256'] or prior['items']!=scores:
            raise ValueError('Saved normalized grading differs; keep it and use an explicitly new grading version')
        return prior
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder');args=parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8');result=regrade(args.folder)
    print(json.dumps({'summary':result['summary'],'legacy':result['original_legacy_summary'],
                      'new_inference':False,'grading_protocol':result['grading_protocol']},ensure_ascii=False))
