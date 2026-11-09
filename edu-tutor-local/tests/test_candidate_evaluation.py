from types import SimpleNamespace
import hashlib
import json
import time

import pytest

from candidate_support import load, fake_modules, module, Model


def test_candidate_evaluation_explicit_identity_and_second_eos(tmp_path,monkeypatch):
    candidate=load(monkeypatch,'text_candidate')
    _,_,tokenizer=fake_modules(monkeypatch)
    tokenizer.eos_token_id=151645
    worker=module('edu_tutor.models.worker','src/edu_tutor/models/worker.py',monkeypatch)
    evaluate=module('edu_tutor.models.evaluate_candidate_cpu','src/edu_tutor/models/evaluate.py',monkeypatch)
    model=Model();model.generation_config=SimpleNamespace(eos_token_id=[151645,151643])
    def generate(**kwargs):
        model.calls.append(kwargs)
        class Output:
            def __getitem__(self,part):return self
            def tolist(self):return [7,151643]
        return [Output()]
    model.generate=generate
    loaded=[]
    def loader(root,adapter,**kwargs):
        loaded.append(kwargs)
        return model,tokenizer,{'model_id':candidate.MODEL_ID,'revision':candidate.REVISION,'inference':{'requested_precision':'nf4'}}
    monkeypatch.setattr(worker,'load_text',loader)
    events=[]
    evaluate.evaluation_job({'kind':'text_batch','model_ref':candidate.CANDIDATE,'root':str(tmp_path),
        'cancel_path':str(tmp_path/'cancel'),'precision':'nf4','max_new_tokens':256,
        'items':[{'id':'cold','messages':[{'role':'user','content':'Synthetic CPU fixture'}]},
                 {'id':'warm','messages':[{'role':'user','content':'Synthetic CPU fixture'}]}]},
        lambda event_type,**values:events.append(values))
    assert loaded==[{'precision':'nf4','model_ref':candidate.CANDIDATE}]
    assert len(model.calls)==2 and all(c['eos_token_id']==[151645,151643] for c in model.calls)
    assert all(c['max_new_tokens']==256 and c['do_sample'] is False for c in model.calls)
    assert all(e['finish_reason']=='eos' and e['model_id']==candidate.MODEL_ID and e['revision']==candidate.REVISION for e in events)
    assert [e['model_load_count'] for e in events]==[1,0]


def test_candidate_loader_rejects_old_adapter_before_import_or_gpu(tmp_path,monkeypatch):
    candidate=load(monkeypatch,'text_candidate')
    worker=module('edu_tutor.models.worker','src/edu_tutor/models/worker.py',monkeypatch)
    with pytest.raises(ValueError,match='base-only'):
        worker.load_text(tmp_path,'train-existing-1.7b',model_ref=candidate.CANDIDATE)


def test_candidate_api_literals_and_default(monkeypatch):
    from pydantic import ValidationError
    admin=module('edu_tutor.api.admin_candidate_cpu','src/edu_tutor/api/admin.py',monkeypatch)
    body={'request_id':'test-request','items':[{'id':'fixture','messages':[{'role':'user','content':'fixture'}]}]}
    assert admin.TextBatchInput(**body).model_ref=='installed'
    assert admin.TextBatchInput(**body,model_ref='qwen3-4b-instruct-2507').adapter=='base'
    with pytest.raises(ValidationError):admin.TextBatchInput(**body,model_ref='../outside')
    with pytest.raises(ValidationError):admin.CandidateDownloadInput(candidate_id='Other/model',request_id='request-id')
    with pytest.raises(ValidationError):admin.CandidateDownloadInput(candidate_id='qwen3-4b-instruct-2507',request_id='request-id',url='https://evil.test')


def test_candidate_endpoints_keep_auth_scope_idempotency_and_cancel(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from edu_tutor.api import create_app
    from edu_tutor.models import runtime
    candidate=load(monkeypatch,'text_candidate')
    downloader=load(monkeypatch,'candidate_download')
    module('edu_tutor.api.admin','src/edu_tutor/api/admin.py',monkeypatch)
    local=tmp_path/'.local';local.mkdir();(tmp_path/'runs').mkdir()
    (local/'phase2-policy.json').write_text(json.dumps({'enabled':True,'active_execution_allowance':{
        'id':candidate.SCOPE,'baseline_request_count':0,'baseline_requests_sha256':hashlib.sha256(b'[]').hexdigest(),
        'limits':{'text_requests':4,'gpu_seconds':600,'new_audio_clips':0,'vision_requests':0}}}))
    downloads=[];model_calls=[]
    def fake_download(root,job,scope,cancel,progress):
        downloads.append({'job':job,'scope':scope});progress(.25)
        deadline=time.monotonic()+2
        while not cancel.wait(.01) and time.monotonic()<deadline:pass
        return {'fixture_only':True,'cancelled':cancel.is_set()}
    monkeypatch.setattr(downloader,'download_candidate',fake_download)
    monkeypatch.setattr(candidate,'resolve_candidate',lambda *a,**kw: (tmp_path,{'fixture_only':True}))
    def fake_model(payload,**kwargs):
        model_calls.append(payload)
        for item in payload['items']:yield {'type':'evaluation_item','id':item['id'],'text':'CPU fixture'}
        yield {'type':'done'}
    monkeypatch.setattr(runtime,'run_worker',fake_model)
    app=create_app(tmp_path);token=(local/'auth-token').read_text().strip()
    with TestClient(app,base_url='http://127.0.0.1',headers={'Authorization':'Bearer '+token}) as client:
        url='/api/models/text-candidate/download';body={'request_id':'candidate-download-fixture','candidate_id':candidate.CANDIDATE}
        assert client.post(url,json=body).status_code==409
        assert client.post(url,json=body,headers={'Authorization':'Bearer wrong'}).status_code==401
        headers={'X-Execution-Allowance':candidate.SCOPE}
        assert client.post(url,json={**body,'url':'https://evil.test'},headers=headers).status_code==422
        first=client.post(url,json=body,headers=headers);assert first.status_code==202
        ident=first.json()['id']
        assert client.post(url,json=body,headers=headers).json()['id']==ident
        assert client.post(url,json={**body,'request_id':'different-download'},headers=headers).status_code==409
        client.post('/api/jobs/'+ident+'/cancel')
        for _ in range(100):
            job=client.get('/api/jobs/'+ident).json()
            if job['state'] in {'cancelled','failed','succeeded'}:break
            time.sleep(.01)
        assert job['state']=='cancelled' and len(downloads)<=1
        batch={'request_id':'candidate-batch-fixture','model_ref':candidate.CANDIDATE,'adapter':'base','precision':'nf4',
            'items':[{'id':'synthetic','messages':[{'role':'user','content':'CPU test only'}]}]}
        assert client.post('/api/evaluations/text-batch',json={**batch,'precision':'bf16'},headers=headers).status_code==409
        assert client.post('/api/evaluations/text-batch',json={**batch,'adapter':'train-old'},headers=headers).status_code==409
        assert not model_calls
        r=client.post('/api/evaluations/text-batch',json=batch,headers=headers);assert r.status_code==202
        for _ in range(100):
            job=client.get('/api/jobs/'+r.json()['id']).json()
            if job['state'] in {'cancelled','failed','succeeded'}:break
            time.sleep(.01)
        assert job['state']=='succeeded' and len(model_calls)==1
        assert model_calls[0]['model_ref']==candidate.CANDIDATE and model_calls[0]['execution_allowance_id']==candidate.SCOPE
