"""Explicit fake generation configuration; no model, voice or final-data calls."""
from contextlib import nullcontext
from copy import deepcopy
import json
import queue
import sys
from types import SimpleNamespace

import pytest

from edu_tutor.models import worker, evaluate, runtime
from edu_tutor.models.text_eos import generation_eos_ids
from test_text_precision import fake_modules, Model


def inference():
    return {"fixture_only":True,"requested_precision":"nf4","quantization":"nf4_double",
            "load_dtype":"torch.bfloat16","actual_is_loaded_in_4bit":True,
            "actual_parameter_devices":["cuda:0"],"actual_parameter_dtypes_elements":{"torch.uint8":10}}


@pytest.mark.parametrize("values", [None, [151645], [151643], [151645,151643,151643], [151645,False], [151645,"151643"]])
def test_actual_generation_config_is_required_and_cannot_silently_fall_back(values):
    model=SimpleNamespace(generation_config=SimpleNamespace(eos_token_id=values))
    with pytest.raises(ValueError,match="Production"):
        generation_eos_ids(model,SimpleNamespace(eos_token_id=151645))


def test_only_explicit_missing_config_cpu_seam_can_use_a_synthetic_token():
    with pytest.raises(ValueError):generation_eos_ids(object(),SimpleNamespace(eos_token_id=9))
    assert generation_eos_ids(object(),SimpleNamespace(eos_token_id=9),cpu_fixture=True)==[9]
    with pytest.raises(ValueError):
        generation_eos_ids(SimpleNamespace(generation_config=SimpleNamespace(eos_token_id=[151645])),
                           SimpleNamespace(eos_token_id=151645),cpu_fixture=True)


def text_fixture(monkeypatch,last):
    class Tokens(list):
        def __getitem__(self,key):
            value=super().__getitem__(key)
            return Tokens(value) if isinstance(key,slice) else value
        def tolist(self):return list(self)
    class Inputs(dict):
        def to(self,device):return self
    class Streamer:
        def __init__(self,*args,**kwargs):self.queue=queue.Queue()
        def end(self):self.queue.put(None)
        def __next__(self):
            value=self.queue.get(timeout=2)
            if value is None:raise StopIteration
            return value
    calls=[]
    def generate(**kwargs):
        calls.append(kwargs)
        kwargs['streamer'].queue.put('CPU fixture explanation')
        kwargs['streamer'].end()
        return [Tokens([1,2,7,last])]
    model=SimpleNamespace(device='cuda:0',generation_config=SimpleNamespace(eos_token_id=[151645,151643]),generate=generate)
    tokenizer=SimpleNamespace(eos_token_id=151645,pad_token_id=151643,
        apply_chat_template=lambda *args,**kwargs:Inputs(input_ids=SimpleNamespace(shape=(1,2))),
        decode=lambda *args,**kwargs:'CPU fixture explanation')
    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace(inference_mode=nullcontext,
        cuda=SimpleNamespace(max_memory_allocated=lambda:0,get_device_name=lambda *a:'CPU fixture')))
    monkeypatch.setitem(sys.modules,'transformers',SimpleNamespace(TextIteratorStreamer=Streamer,
        StoppingCriteria=object,StoppingCriteriaList=list))
    # Marked synthetic inference plus completed real-loader-style metadata.
    # download_complete prevents the CPU fallback from hiding missing config.
    meta={'model_id':'CPU fixture','revision':'fixture','download_complete':True,'inference':inference()}
    return model,tokenizer,meta,calls


@pytest.mark.parametrize('last',[151645,151643])
@pytest.mark.parametrize('route',['per_request','resident_loader'])
def test_student_generation_passes_both_actual_eos_and_preserves_completion(tmp_path,monkeypatch,last,route):
    model,tokenizer,meta,calls=text_fixture(monkeypatch,last)
    loads=[];events=[]
    def loader(*args,**kwargs):loads.append(kwargs);return model,tokenizer,meta
    monkeypatch.setattr(worker,'load_text',loader)
    kwargs={} if route=='per_request' else {'model_loader':loader,'residency':{'request_model_load_count':0,'model_instance_id':'cpu-fixture'}}
    worker.text_job({'root':str(tmp_path),'run_dir':str(tmp_path),'cancel_path':str(tmp_path/'cancel'),
        'precision':'nf4','messages':[],'max_new_tokens':16},
        emit_fn=lambda event_type,**values:events.append({'type':event_type,**values}),**kwargs)
    report=next(event for event in events if event['type']=='metadata')
    assert len(loads)==1 and len(calls)==1
    assert calls[0]['eos_token_id']==[151645,151643]
    assert report['finish_reason']=='eos' and report['eos_token_ids']==[151645,151643]
    assert json.loads((tmp_path/'result.json').read_text(encoding='utf-8'))['eos_token_ids']==[151645,151643]
    if route=='resident_loader':assert report['model_load_count']==0


def test_completed_loader_metadata_cannot_use_missing_config_fallback(tmp_path,monkeypatch):
    model,tokenizer,meta,calls=text_fixture(monkeypatch,151645)
    del model.generation_config
    events=[]
    with pytest.raises(ValueError,match='Production'):
        worker.text_job({'root':str(tmp_path),'run_dir':str(tmp_path),'cancel_path':str(tmp_path/'cancel'),
            'precision':'nf4','messages':[],'max_new_tokens':16},model_loader=lambda *a,**k:(model,tokenizer,meta),
            emit_fn=lambda *a,**k:events.append(a))
    assert not calls and not events and not (tmp_path/'result.json').exists()


@pytest.mark.parametrize('last',[151645,151643])
@pytest.mark.parametrize('model_ref',['installed','qwen3-4b-instruct-2507'])
def test_evaluation_stopping_configuration_and_classifier_agree(tmp_path,monkeypatch,last,model_ref):
    _,_,tokenizer=fake_modules(monkeypatch)
    tokenizer.eos_token_id=151645
    model=Model();model.generation_config=SimpleNamespace(eos_token_id=[151645,151643])
    def generate(**kwargs):
        model.calls.append(kwargs)
        class Output:
            def __getitem__(self,key):return self
            def tolist(self):return [7,last]
        return [Output()]
    model.generate=generate
    monkeypatch.setattr(worker,'load_text',lambda *a,**k:(model,tokenizer,{'model_id':'CPU fixture','revision':'fixture'}))
    events=[]
    evaluate.evaluation_job({'kind':'text_batch','root':str(tmp_path),'cancel_path':str(tmp_path/'cancel'),
        'model_ref':model_ref,'precision':'nf4','max_new_tokens':16,
        'items':[{'id':'synthetic','messages':[{'role':'user','content':'CPU fixture only'}]}]},
        lambda event_type,**values:events.append(values))
    assert len(model.calls)==1 and model.calls[0]['eos_token_id']==[151645,151643]
    assert events[0]['finish_reason']=='eos' and events[0]['eos_token_ids']==[151645,151643]


def test_evaluation_missing_generation_configuration_stops_before_generate(tmp_path,monkeypatch):
    _,_,tokenizer=fake_modules(monkeypatch)
    model=Model()
    monkeypatch.setattr(worker,'load_text',lambda *a,**k:(model,tokenizer,{'revision':'fixture'}))
    with pytest.raises(ValueError,match='Production'):
        evaluate.evaluation_job({'kind':'text_batch','root':str(tmp_path),'cancel_path':str(tmp_path/'cancel'),
            'items':[{'id':'synthetic','messages':[{'role':'user','content':'CPU fixture'}]}]},lambda *a,**k:None)
    assert not model.calls


def test_api_generation_snapshot_keeps_verified_eos_metadata(tmp_path,monkeypatch):
    monkeypatch.setattr(runtime,'model_status',lambda *a:{'ready':True})
    event={'type':'metadata','finish_reason':'eos','requested_precision':'nf4','inference':inference(),
           'eos_token_ids':[151645,151643]}
    monkeypatch.setattr(runtime,'run_worker',lambda *a,**k:iter([deepcopy(event)]))
    metadata={}
    assert list(runtime.generate([{'role':'user','content':'CPU fixture'}],root=tmp_path,metadata_out=metadata))==[]
    assert metadata['eos_token_ids']==[151645,151643]
