"""Assemble saved, completed fixed-condition evaluation evidence only."""
import collections
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import statistics

EDU=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

conditions=[]
for name in ('final-base-bf16-v1','final-adapter1-bf16-v1'):
    folder=EDU/name
    normalized=read(folder/'result-normalized.json')
    counter=read(folder/'result-sql-counterexamples-v1.json')
    claims=read(folder/'result-explicit-claims-v1.json')
    app=read(folder/'result-app-offline-final-source-r10-v1.json')
    identity=read(folder/'runtime-identity-audit.json')
    assert normalized['status']=='completed' and len(normalized['items'])==80
    assert identity['status']=='PASS_RUNTIME_IDENTITY_ONLY'
    families={}
    for i in normalized['items']:
        family=i['id'].rsplit('_',1)[0]
        row=families.setdefault(family,{'total':0,'sql_count':0,'fixture_value_match':0,'concept_pending':0,'incomplete':0})
        row['total']+=1;row['sql_count']+=i['sql_result_correct'] is not None
        row['fixture_value_match']+=i['sql_result_correct'] is True
        row['concept_pending']+=i['sql_result_correct'] is None
        row['incomplete']+=i['finish_reason']!='eos'
    reasons=collections.Counter()
    for item in app['items']:
        if item.get('status')=='concept_not_automatically_graded':continue
        reasons.update((item.get('evidence') or {}).get('reasons') or [item.get('status')])
    events=[i['raw_model_event'] for i in normalized['items']]
    latencies=[i['phase_timing']['generation_seconds'] for i in events]
    conditions.append({'condition':name,'raw_sql_fixture_results':normalized['summary'],
        'sql_counterexamples':counter['summary'],'explicit_result_claims':claims['summary'],
        'saved_raw_cpu_app_only':app['summary'],'app_new_rag_search':0,'app_new_model_repair':0,'app_new_speech':0,'app_live_lesson_runs':0,
        'app_stop_reasons':dict(reasons),'family_results':families,
        'actual_runtime_identity':identity['status'],'app_source_hashes':app['source_hashes'],
        'started_at':normalized['started_at'],'finished_at':normalized['finished_at'],
        'generation_median_seconds':statistics.median(latencies),'generation_max_seconds':max(latencies),
        'total_output_tokens':sum(i['output_tokens'] for i in events),
        'actual_parameter_dtypes_elements_unique':[json.loads(v) for v in sorted({json.dumps(i['inference']['actual_parameter_dtypes_elements'],sort_keys=True) for i in events})],
        'evidence':{p.name:{'path':str(p),'sha256':sha(p)} for p in [folder/'result.json',folder/'result-normalized.json',
            folder/'result-sql-counterexamples-v1.json',folder/'result-explicit-claims-v1.json',folder/'result-app-offline-final-source-r10-v1.json',folder/'runtime-identity-audit.json']}})
assert conditions[0]['app_source_hashes']==conditions[1]['app_source_hashes']
validation=read(EDU/'validation-app-final-source-r10-comparison.json')
assert all(c['source_hashes']==conditions[0]['app_source_hashes'] for c in validation['conditions'])
root=EDU.parents[3]
freeze=read(EDU/'selection-bf16-frozen-v1.json')
for relative,expected in {**freeze['production_source_hashes'],**freeze.get('additional_source_hashes',{})}.items():
    path=root/relative
    assert (sha(path) if path.is_file() else None)==expected,relative
training=root/'runs/train-f1cc05b37bb04d51ba326468f2fd74a1'
trained=read(training/'training-result.json')
training_summary={k:trained[k] for k in ('dataset_sha256','training_loss','optimizer_steps','actual_microbatches',
    'configured_gradient_accumulation_steps','changed_adapter_parameter_count','finite_gradients','trainable_parameters',
    'frozen_base_requires_grad_false','optimizer_excludes_base','selected_frozen_base_values_unchanged')}
training_summary.update(training_result=str(training/'training-result.json'),reload_result=str(training/'reload-result.json'),
    loss_scope='Mean training loss, not education correctness; final logged train_loss agrees.',
    reload_scope='Separate-process adapter load/generation passed; COUNT NULL answer was incorrect and is preserved.')
value={'recorded_at':datetime.now(timezone.utc).isoformat(),'readiness':'NOT_READY','human_review':'H_PENDING',
    'conditions':conditions,'new_actual_text':160,'automatic_retries':0,'new_training':0,'new_speech':0,'new_vision':0,
    'same_teacher_source_all_validation_and_final':True,'selected_student_adapter':'base','adapter1_status':'TRAINED_NOT_PROMOTED',
    'overall_education_accuracy':None,'model_teacher_selection_changed_after_final':False,
    'training1_actual_evidence':training_summary,'post_cpu_grading_all_frozen_source_hashes_match':True,
    'limitations':[
        'SQL denominator60 and concepts20 are separate; no full80 education correctness score is assigned.',
        'Fixed fixture value agreement is not semantic proof; no found counterexample is not proof of correctness.',
        'Array claim detector covers explicit machine-readable result arrays only. Zero arrays does not approve prose.',
        'App measurement reprocesses saved raw output through current CPU verification/planning only; no fresh RAG, repair model, speech, or live classroom.',
        'CPU proposal/tests ran concurrently. Batch runtime is not an isolated speed benchmark or student first-audio latency.',
        'Historical validation generated with twoEOS but classified one; final explicitly generates/classifies both EOS IDs. Preserve old labels.',
        'Agent read-review is not human pedagogic/listening review. Actual human review remains pending.'
    ]}
target=EDU/'final160-education-comparison.json';assert not target.exists(),'Preserve prior comparison'
target.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(target)
