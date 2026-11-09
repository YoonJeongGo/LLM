"""Validate completed frozen final runs; no requests, model, or prompt mutation."""
import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[4]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def audit(folder):
    folder=Path(folder).resolve();result=read(folder/'result.json')
    assert result['status']=='completed' and len(result['items'])==80
    protocol=result['protocol'];freeze=read(ROOT/protocol['selection_freeze']['path'])
    assert sha(ROOT/protocol['selection_freeze']['path'])==protocol['selection_freeze']['sha256']
    assert protocol['precision']=='bf16' and protocol['max_new_tokens']==256
    assert protocol['do_sample'] is False and protocol['rag'] is False and protocol['final_holdout_read'] is True
    checks=[]
    for number in range(1,21):
        batch=folder/f'batch-{number:02d}'
        raw=read(batch/'raw-result.json');job=read(batch/'job.json');submission=read(batch/'submission.json')
        assert job['state']=='succeeded' and len(raw['items'])==4
        items=raw['items'];body=submission['body']
        assert body['adapter']==protocol['adapter'] and body['precision']=='bf16' and body['max_new_tokens']==256
        assert all(set(i)=={'id','messages'} and all(set(m)=={'role','content'} and m['role'] in {'system','user'} for m in i['messages']) for i in body['items'])
        expected_adapter=None if protocol['adapter']=='base' else protocol['adapter']
        actual_adapter=raw.get('adapter')
        assert actual_adapter is None if expected_adapter is None else expected_adapter in str(actual_adapter)
        assert len({i['worker_pid'] for i in items})==1 and len({i['model_object_id'] for i in items})==1
        for item in items:
            assert item['model_ref']=='installed' and item['model_id']==freeze['selected_model']['model_id']
            assert item['revision']==freeze['selected_model']['revision'] and item['precision']=='bf16'
            assert item['eos_token_ids']==freeze['final_expected_eos_token_ids']
            assert item['max_new_tokens']==256 and item['inference']['actual_is_loaded_in_4bit'] is False
            assert item['inference']['requested_precision']=='bf16' and item['inference']['load_dtype']=='torch.bfloat16'
        checks.append({'batch':number,'job_id':job['id'],'adapter':actual_adapter,
            'worker_pid':items[0]['worker_pid'],'model_object_id':items[0]['model_object_id'],
            'loads':[i['model_load_count'] for i in items],'finish_reasons':[i['finish_reason'] for i in items],
            'input_only_public_system_user':True,'identity_precision_eos_pass':True})
    source={}
    for path,expected in {**freeze['production_source_hashes'],**freeze.get('additional_source_hashes',{})}.items():
        p=ROOT/path;actual=sha(p) if p.is_file() else None
        source[path]={'expected':expected,'actual':actual,'match':expected==actual}
    assert all(v['match'] for v in source.values())
    value={'at':datetime.now(timezone.utc).isoformat(),'status':'PASS_RUNTIME_IDENTITY_ONLY',
        'education_quality':'NOT_IMPLIED','condition':protocol['adapter'],'items':80,'batches':checks,
        'source_hashes':source,'freeze_sha256':protocol['selection_freeze']['sha256'],
        'result_sha256':sha(folder/'result.json'),'model_calls':0,
        'boundary':'Per-batch fresh worker, four items share one loaded model. Not cross-batch resident reuse or student latency.'}
    target=folder/'runtime-identity-audit.json';assert not target.exists(),'Preserve prior audit'
    target.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'status':value['status'],'condition':value['condition'],'items':80,'source_hashes_match':True}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder');args=p.parse_args()
    print(json.dumps(audit(args.folder),ensure_ascii=False))
