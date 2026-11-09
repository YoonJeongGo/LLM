"""Active inference code T0 contracts. Fake torch/Transformers only; no model or live state."""
from contextlib import nullcontext
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[1]

def module(name, path, monkeypatch):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    loaded=importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules,name,loaded)
    spec.loader.exec_module(loaded)
    return loaded

class Storage:
    def __init__(self, pointer, size):self.pointer,self.size=pointer,size
    def data_ptr(self):return self.pointer
    def nbytes(self):return self.size

class Parameter:
    def __init__(self, storage, dtype='bf16', device='cuda:0'):
        self.storage,self.dtype,self.device=storage,dtype,device
    def untyped_storage(self):return self.storage
    def numel(self):return self.storage.size//2

class Model:
    device='cuda:0'
    config=SimpleNamespace(to_dict=lambda:{'tie_word_embeddings':True})
    def __init__(self, quantized=False):
        self.is_loaded_in_4bit=quantized
        self.embedding=Parameter(Storage(10,24))
        self.linear=Parameter(Storage(20,48),'uint8' if quantized else 'bf16')
        self.calls=[]
    def parameters(self):return iter([self.embedding,self.embedding,self.linear])
    def get_input_embeddings(self):return SimpleNamespace(weight=self.embedding)
    def get_output_embeddings(self):return SimpleNamespace(weight=self.embedding)
    def named_modules(self):return []
    def eval(self):return self
    def generate(self,**kwargs):
        self.calls.append(kwargs)
        class Tokens:
            def __getitem__(self,key):return self
            def tolist(self):return [7,99]
        return [Tokens()]

def fake_modules(monkeypatch,bf16=True):
    cuda=SimpleNamespace(is_available=lambda:True,is_bf16_supported=lambda:bf16,
        memory_allocated=lambda:100,memory_reserved=lambda:120,max_memory_allocated=lambda:140,
        max_memory_reserved=lambda:160,reset_peak_memory_stats=lambda:None,synchronize=lambda:None,
        mem_get_info=lambda:(700,1000))
    torch=SimpleNamespace(cuda=cuda,bfloat16='bf16',float16='fp16',inference_mode=nullcontext)
    calls=[]
    def load(folder,**kwargs):
        calls.append(kwargs)
        return Model(quantized='quantization_config' in kwargs)
    class Inputs(dict):
        def to(self,_device):return self
    tok=SimpleNamespace(pad_token_id=0,eos_token_id=99,
        apply_chat_template=lambda *a,**k:Inputs(input_ids=SimpleNamespace(shape=[1,3])),
        decode=lambda *a,**k:'CPU fixture output, not an actual model answer')
    transformers=SimpleNamespace(AutoModelForCausalLM=SimpleNamespace(from_pretrained=load),
        AutoTokenizer=SimpleNamespace(from_pretrained=lambda *a,**k:tok),
        BitsAndBytesConfig=lambda **kwargs:kwargs,StoppingCriteria=object,StoppingCriteriaList=list)
    monkeypatch.setitem(sys.modules,'torch',torch)
    monkeypatch.setitem(sys.modules,'transformers',transformers)
    return torch,calls,tok

def root(tmp_path):
    folder=tmp_path/'.local/models/text';folder.mkdir(parents=True)
    (folder/'model-manifest.json').write_text(json.dumps({'model_id':'CPU-fixture','revision':'fixture'}))
    return tmp_path

@pytest.mark.parametrize('precision,quantized',[('nf4',True),('bf16',False)])
def test_only_explicit_mode_changes_loader_and_actual_storage_metadata(tmp_path,monkeypatch,precision,quantized):
    torch,calls,_=fake_modules(monkeypatch)
    worker=module('edu_tutor.models.worker','src/edu_tutor/models/worker.py',monkeypatch)
    model,_,meta=worker.load_text(root(tmp_path),precision=precision)
    assert ('quantization_config' in calls[0])==quantized
    assert calls[0]['torch_dtype']=='bf16' and calls[0]['device_map']=={'':0}
    assert calls[0]['local_files_only'] and calls[0]['trust_remote_code'] is False
    assert meta['inference']['actual_is_loaded_in_4bit']==quantized
    assert meta['inference']['unique_parameter_storage_bytes']==72
    assert meta['inference']['unique_parameter_storage_count']==2
    assert meta['inference']['word_embeddings_tied']

def test_bf16_unsupported_never_falls_back_or_starts_weight_load(tmp_path,monkeypatch):
    _,calls,_=fake_modules(monkeypatch,bf16=False)
    worker=module('edu_tutor.models.worker','src/edu_tutor/models/worker.py',monkeypatch)
    with pytest.raises(RuntimeError,match='FP16 fallback is forbidden'):worker.load_text(root(tmp_path),precision='bf16')
    assert calls==[]

def test_default_nf4_retains_existing_fp16_compute_fallback(tmp_path,monkeypatch):
    _,calls,_=fake_modules(monkeypatch,bf16=False)
    worker=module('edu_tutor.models.worker','src/edu_tutor/models/worker.py',monkeypatch)
    worker.load_text(root(tmp_path))
    assert calls[0]['quantization_config']['bnb_4bit_quant_type']=='nf4'
    assert calls[0]['torch_dtype']=='fp16'

def test_unknown_precision_is_rejected_before_import_or_loading(tmp_path,monkeypatch):
    _,calls,_=fake_modules(monkeypatch)
    worker=module('edu_tutor.models.worker','src/edu_tutor/models/worker.py',monkeypatch)
    with pytest.raises(ValueError):worker.load_text(tmp_path,precision='fp16')
    assert not calls

def test_actual_cpu_offload_or_unexpected_quantization_is_rejected(monkeypatch):
    torch,_,_=fake_modules(monkeypatch)
    worker=module('edu_tutor.models.worker','src/edu_tutor/models/worker.py',monkeypatch)
    model=Model();model.linear.device='cpu'
    with pytest.raises(RuntimeError,match='no CPU offload'):worker.inference_snapshot(model,'bf16','bf16',torch)
    with pytest.raises(RuntimeError,match='still quantized'):worker.inference_snapshot(Model(True),'bf16','bf16',torch)
    with pytest.raises(RuntimeError,match='did not confirm 4bit'):worker.inference_snapshot(Model(False),'nf4','bf16',torch)

@pytest.mark.parametrize('precision',['nf4','bf16'])
def test_two_items_share_loaded_model_keep_128_greedy_and_record_phase_memory(tmp_path,monkeypatch,precision):
    _,_,tok=fake_modules(monkeypatch)
    worker=module('edu_tutor.models.worker','src/edu_tutor/models/worker.py',monkeypatch)
    evaluate=module('edu_tutor.models.evaluate_precision_cpu','src/edu_tutor/models/evaluate.py',monkeypatch)
    loaded=[];model=Model()
    model.generation_config=SimpleNamespace(eos_token_id=[151645,151643])
    tok.eos_token_id=151645  # Explicit local generation fixture; global helper stays unchanged.
    def load(*args,**kwargs):
        loaded.append(kwargs)
        return model,tok,{'revision':'fixture','inference':{'requested_precision':precision,'loader_import_seconds':0}}
    monkeypatch.setattr(worker,'load_text',load)
    events=[];messages=[{'role':'user','content':'CPU synthetic test question'}]
    evaluate.evaluation_job({'kind':'text_batch','root':str(tmp_path),'cancel_path':str(tmp_path/'cancel'),
        'precision':precision,'max_new_tokens':128,'items':[{'id':'cold','messages':messages},{'id':'warm','messages':messages}]},
        lambda kind,**values:events.append(values))
    assert loaded==[{'precision':precision}]
    assert len(model.calls)==2 and all(c['max_new_tokens']==128 and c['do_sample'] is False for c in model.calls)
    assert events[0]['model_object_id']==events[1]['model_object_id']
    assert [e['model_load_count'] for e in events]==[1,0]
    assert events[1]['phase_timing']['runtime_import_seconds']==0
    assert events[1]['phase_timing']['load_excluding_loader_import_seconds']==0
    assert all(e['memory']['request_peak_reserved_bytes']==160 for e in events)
    assert all(e['input_tokens']==3 and e['output_tokens']==2 and e['precision']==precision for e in events)

def test_legacy_evaluation_ignores_foreign_precision_and_remains_nf4(tmp_path,monkeypatch):
    _,_,tok=fake_modules(monkeypatch)
    worker=module('edu_tutor.models.worker','src/edu_tutor/models/worker.py',monkeypatch)
    evaluate=module('edu_tutor.models.evaluate_precision_cpu','src/edu_tutor/models/evaluate.py',monkeypatch)
    seen=[]
    model=Model();model.generation_config=SimpleNamespace(eos_token_id=[151645,151643]);tok.eos_token_id=151645
    monkeypatch.setattr(worker,'load_text',lambda *a,**kw:(seen.append(kw) or model,tok,{'revision':'fixture'}))
    evaluate.evaluation_job({'kind':'evaluation','precision':'bf16','root':str(tmp_path),
        'cancel_path':str(tmp_path/'cancel'),'questions':[{'id':'q','question':'CPU test only'}]},lambda *a,**k:None)
    assert seen==[{'precision':'nf4'}]

def test_api_field_is_strict_and_default_does_not_change(monkeypatch):
    admin=module('edu_tutor.api.admin_precision_cpu','src/edu_tutor/api/admin.py',monkeypatch)
    value={'request_id':'fixture-only','items':[{'id':'q','messages':[{'role':'user','content':'test'}]}]}
    assert admin.TextBatchInput.model_validate(value).precision=='nf4'
    assert admin.TextBatchInput.model_validate({**value,'precision':'bf16'}).precision=='bf16'
    with pytest.raises(ValueError):admin.TextBatchInput.model_validate({**value,'precision':'fp16'})

def test_authenticated_api_transports_precision_and_explicit_scope_only(tmp_path,monkeypatch):
    import hashlib
    from fastapi.testclient import TestClient
    from edu_tutor.api import create_app
    from edu_tutor.models import runtime
    module('edu_tutor.api.admin','src/edu_tutor/api/admin.py',monkeypatch)
    local=tmp_path/'.local';local.mkdir()
    (tmp_path/'runs').mkdir()
    (local/'phase2-policy.json').write_text(json.dumps({'enabled':True,'active_execution_allowance':{
        'id':'fixture-scope','baseline_request_count':0,'baseline_requests_sha256':hashlib.sha256(b'[]').hexdigest(),
        'limits':{'text_requests':4,'gpu_seconds':600,'new_audio_clips':0,'vision_requests':0}}}))
    seen=[]
    def fake(payload,**kwargs):
        seen.append(payload)
        for item in payload['items']:yield {'type':'evaluation_item','id':item['id'],'text':'CPU fixture'}
        yield {'type':'done'}
    monkeypatch.setattr(runtime,'run_worker',fake)
    app=create_app(tmp_path)
    token=(local/'auth-token').read_text().strip()
    body={'request_id':'fixture-request','precision':'bf16','max_new_tokens':128,
          'items':[{'id':'cold','messages':[{'role':'user','content':'CPU test only'}]},
                   {'id':'warm','messages':[{'role':'user','content':'CPU test only'}]}]}
    with TestClient(app,base_url='http://127.0.0.1',headers={'Authorization':'Bearer '+token}) as client:
        assert client.post('/api/evaluations/text-batch',json=body).status_code==409
        bad=client.post('/api/evaluations/text-batch',json={**body,'precision':'fp16'},headers={'X-Execution-Allowance':'fixture-scope'})
        assert bad.status_code==422 and not seen
        response=client.post('/api/evaluations/text-batch',json=body,headers={'X-Execution-Allowance':'fixture-scope'})
        assert response.status_code==202,response.text
        for _ in range(100):
            job=client.get('/api/jobs/'+response.json()['id']).json()
            if job['state'] in {'succeeded','failed','blocked','cancelled'}:break
            time.sleep(.01)
        assert job['state']=='succeeded'
        assert len(seen)==1 and seen[0]['precision']=='bf16' and seen[0]['execution_allowance_id']=='fixture-scope'
        assert len(seen[0]['items'])==2 and seen[0]['max_new_tokens']==128
