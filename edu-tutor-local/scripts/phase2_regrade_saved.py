"""CPU-only corrected SQL extraction replay; preserve all actual run reports.

This is not a new model run and cannot turn a historical app safe-stop into a
successful student-facing answer. Original protocols, raw responses and app
outcomes remain immutable, while this separate result records format effects.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from edu_tutor.evaluation.phase2_audit import digest, write_json
from edu_tutor.evaluation.phase2_diagnostics import grade_raw_model
from edu_tutor.problems.sql_response import SQL_EXTRACTION_PROTOCOL
from phase2_snapshot import snapshot


def main():
    base=ROOT/'runs/phase2/current/diagnostics'
    out=base/'corrected-json-fence-v2'
    out.mkdir(exist_ok=False)
    paths=['base-v02-model_only/report.json','rag-tools-v02-rag_tools/report.json',
           'adapter-v02-model_only/report.json','development18/public-v02-rag_tools/report.json']
    protected={path:digest(base/path) for path in paths}
    write_json(out/'source-before.json',snapshot(ROOT))
    result={'tier':'T0_saved_T2_output_replay','created_at':datetime.now(timezone.utc).isoformat(),
        'protocol':SQL_EXTRACTION_PROTOCOL,'grading_protocol':'json_fence_v2','human_review':'not_reviewed',
        'scope':'Original primary model responses re-extracted and numerically compared only. No GPU, no regeneration, no training, no promotion.',
        'actual_app_outcomes':'Unchanged; saved app safe-stops remain safe-stops. This is not a hypothetical product success rate.',
        'dataset_usage_status':'development_after_results_informed_format_fix','protected_sha256_before':protected,'runs':[]}
    for path in paths:
        original=json.loads((base/path).read_text(encoding='utf-8'))
        data=base/'development18' if original['suite']=='development18' else base
        questions={q['id']:q for q in json.loads((data/'questions.json').read_text(encoding='utf-8'))['questions']}
        oracles=json.loads((data/'oracles.json').read_text(encoding='utf-8'))['oracles']
        row={'original_report':path,'run_id':original['run_id'],'mode':original['mode'],'suite':original['suite'],
             'original_counts':original['counts'],'actual_app_coverage':original['coverage'],'items':[]}
        for item in original['items']:
            question=questions[item['id']]
            answer=item.get('answer')
            corrected=grade_raw_model(question,oracles[item['id']],answer,grading_protocol='json_fence_v2') if answer else item['raw_model_grade']
            attempts=[]
            for attempt in (answer or {}).get('model_attempts',[])[1:]:
                attempt_answer={'raw_model_response':attempt['text'],'generation_snapshot':attempt.get('generation_snapshot',{})}
                attempts.append({'attempt':attempt['attempt'],'grade':grade_raw_model(question,oracles[item['id']],attempt_answer,grading_protocol='json_fence_v2')})
            row['items'].append({'id':item['id'],'category':item['category'],'task_type':question['task_type'],
                'original_raw_grade':item['raw_model_grade'],'corrected_primary_raw_grade':corrected,
                'actual_app_grade_unchanged':item['app_display_grade'],'repair_candidate_grades_diagnostic_only':attempts})
        row['corrected_primary_raw_counts']=dict(Counter(i['corrected_primary_raw_grade']['status'] for i in row['items']))
        row['changed_primary_ids']=[i['id'] for i in row['items'] if i['original_raw_grade']['status']!=i['corrected_primary_raw_grade']['status']]
        row['query_denominator']=sum(i['category']=='query' for i in row['items'])
        result['runs'].append(row)
    after={path:digest(base/path) for path in paths}
    if after!=protected:
        raise RuntimeError('Protected actual reports changed during regrading')
    result['protected_sha256_after']=after
    result['original_reports_unchanged']=True
    write_json(out/'report.json',result)
    for directory in (base,base/'development18'):
        write_json(directory/'usage-status.json',{'status':'development_after_results_informed_format_fix',
            'updated_at':result['created_at'],'reason':'Actual saved responses revealed a fenced JSON extraction false-negative. Product parser and this explicit-v2 grader were then changed; original freeze manifests and scores are preserved as historical evidence.',
            'protocol':SQL_EXTRACTION_PROTOCOL,'human_review':'not_reviewed','original_question_oracle_files_changed':False,
            'corrected_report':str((out/'report.json').relative_to(ROOT))})
    print(json.dumps({'original_reports_unchanged':True,'runs':[{'run_id':r['run_id'],'counts':r['corrected_primary_raw_counts'],'changed_ids':r['changed_primary_ids']} for r in result['runs']]},ensure_ascii=False))


if __name__=='__main__':
    main()
