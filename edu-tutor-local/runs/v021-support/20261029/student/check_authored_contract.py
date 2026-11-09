"""CPU fixture validation; private candidate SQL is not a model response."""
from pathlib import Path
import json
from datetime import datetime, timezone
from edu_tutor.problems.models import normalize_problem, infer_basic_intent
from edu_tutor.problems.evidence import verify_answer, display_answer
from edu_tutor.lessons.verified import generate_verified_plan, validated_logical_stage
from edu_tutor.lessons.plans import scene_at
BASE=Path(__file__).resolve().parent
specs=json.loads((BASE/'journeys.json').read_text(encoding='utf-8'))['journeys']
oracles=json.loads((BASE/'private-oracle.json').read_text(encoding='utf-8'))
results=[]
for spec in specs:
    if not spec.get('tables'):continue
    oracle=oracles[spec['id']]
    problem=normalize_problem({'task_kind':spec['task_kind'],'raw_text':spec['question'],
        'tables':spec['tables'],'confirmed':True})
    raw=json.dumps({'sql':oracle['query'],'explanation':'CPU 검증 대사입니다. 이 문장은 수업에서 사용하지 않습니다.'},ensure_ascii=False)
    evidence=verify_answer(problem,raw,spec['question'])
    message={'id':'cpu-'+spec['id'],'session_id':'cpu-session','problem':problem,'evidence':evidence,
        'content':display_answer(evidence),'raw_model_response':raw}
    record={'id':'cpu-lesson-'+spec['id'],'source_message_id':message['id'],**generate_verified_plan(message,spec['question'],'cpu-plan')}
    passed=evidence['status']=='verified' and evidence['result']['rows']==oracle['result']['rows'] and record['speech_allowed']
    row={'id':spec['id'],'pass':passed,'intent':infer_basic_intent(problem,spec['question']),
        'evidence':evidence,'plan':record,'candidate_provenance':'PRIVATE CPU FIXTURE ONLY; not submitted to model or live app'}
    if spec.get('followup') and record.get('plan'):
        f=spec['followup'];index=next(i for i,s in enumerate(record['plan']['steps']) if s['title']==f['step_title'])
        table=evidence['working_tables'][0]; ci=table['columns'].index(f['column']);ri=f['row_index']
        context={'lesson_id':record['id'],'step':index,'problem_revision':problem['revision'],
            'selected_cell':{'table_element_id':table['id'],'row_id':table['row_ids'][ri],
                'column_id':table['column_ids'][ci],'cell_id':table['cell_ids'][ri][ci]}}
        context['_verified_logical_stage']=validated_logical_stage(record,message,context)
        supplement=generate_verified_plan({**message,'id':'cpu-supplement','lesson_context':context},f['question'],'cpu-supplement-plan')
        row['followup']=supplement;row['current_stage']=scene_at(record['plan'],index)
        row['pass'] &= bool(context['_verified_logical_stage']) and supplement['speech_allowed']
    results.append(row)
output={'at':datetime.now(timezone.utc).isoformat(),'kind':'AUTHORED_DEVELOPMENT_CPU_INPUT_CONTRACT_NOT_ACTUAL_MODEL',
    'model_calls':0,'tts_calls':0,'vision_calls':0,'all_pass':all(r['pass'] for r in results),'cases':results}
(BASE/'authored-contract-cpu.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'all_pass':output['all_pass'],'cases':[{k:r[k] for k in ('id','pass')} for r in results]}))
raise SystemExit(0 if output['all_pass'] else 1)
