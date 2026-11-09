"""One-shot selection freeze, no final dataset access and no POST."""
import sys,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
root=Path(__file__).resolve().parents[4];sys.path.insert(0,str(root/'scripts'))
from finish_education_live import check_selection_freeze,Client
folder=Path(__file__).resolve().parent;path=folder/'selection-bf16-frozen-v1.json'
assert not path.exists(),'Preserve existing freeze; no overwrite'
prepared=folder/'selection-bf16-prepared.json';value=json.loads(prepared.read_text(encoding='utf-8'));stamp=datetime.now(timezone.utc).isoformat()
def reference(path):
    p=root/path;return {'path':str(p.relative_to(root)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
freeze=json.loads((root/'runs/finish-v2/20261029/student/final03/execution-version.json').read_text(encoding='utf-8'))
for p,h in freeze['source_hashes'].items():
    actual=hashlib.sha256((root/p).read_bytes()).hexdigest() if (root/p).is_file() else None
    assert actual==h,p
value.update(status='frozen',final_evaluation_authorized=True,frozen_at=stamp,
    authorization={'scope':'finish-local-tutor-20261028-v1','explicit_root_final_go_received':True,
        'ordered_conditions':['base/bf16','train-f1cc05b37bb04d51ba326468f2fd74a1/bf16'],
        'maximum_new_text':160,'extra_training':False,'new_tts':False,'new_vision':False,'automatic_retry':False},
    prepared_source=reference(prepared),final_data_opened_before_freeze=False,
    source_version='r11_same_production_source_as_r10_final03',production_source_hashes=freeze['source_hashes'],
    product_and_eval_source_frozen=True,
    final_execution_guard='Authorized after final03 eight attempts, exact binding regrade, explicit cancellation/cache guards, and same-source r11 restart. Failures remain failures; no student-ready claim.',
    observed_failures_preserved=['J02 example/repair','J06 OCR source mismatch','J08 missing condition not identified'],
    selection_unchanged_after_final_access=True,
    evidence=[reference(Path(p)) for p in ['runs/finish-v2/20261029/student/final03/execution-version.json',
        'runs/finish-v2/20261029/student/final03/report-binding-v2-20261029T054109464134Z/summary.json',
        'runs/finish-v2/20261029/education/collector-numeric-binding-v2/cpu-tests-24.xml',
        'runs/finish-v2/20261029/stability/restart-r11-comparison.json',
        'runs/finish-v2/20261029/server-r11-process.json','runs/finish-v2/20261029/server-r11-effective.json',
        'runs/finish-v2/20261029/education/validation-app-final-source-r10-comparison.json']],
    additional_source_hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in [
        'scripts/finish_education_live.py','src/edu_tutor/models/evaluate.py','src/edu_tutor/models/worker.py',
        'src/edu_tutor/models/runtime.py','src/edu_tutor/models/text_eos.py'] if (root/p).exists()})
path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
gates=[]
for adapter in value['evaluation_adapters']:
    checked=check_selection_freeze(path,adapter,precision='bf16')
    gates.append({'adapter':adapter,'precision':'bf16','passed':True,'freeze_sha256':checked['reference']['sha256']})
budget=Client().preflight('text',160)
(folder/'final-preflight.json').write_text(json.dumps({'at':stamp,'gates':gates,'budget':budget,
    'final_body_read':False,'model_post_count':0},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'freeze':str(path),'gates':gates,'text_remaining':budget['active_execution_allowance']['text_remaining'],
    'seconds_remaining':budget['active_execution_allowance']['seconds_remaining'],'final_body_read':False,'model_post_count':0},ensure_ascii=False))
