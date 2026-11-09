from importlib.util import module_from_spec, spec_from_file_location
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC=spec_from_file_location('finish_live_precision',Path(__file__).resolve().parents[1]/'scripts/finish_education_live.py')
live=module_from_spec(SPEC);SPEC.loader.exec_module(live)


def freeze(tmp_path, precisions, selected):
    folder=tmp_path/'runs/finish-v2/20261029/education';folder.mkdir(parents=True)
    refs=[]
    for adapter,precision in zip(['base','candidate'],precisions):
        protocol={'adapter':adapter,'final_holdout_read':False,'max_new_tokens':256,'do_sample':False}
        if precision is not None:protocol['precision']=precision
        result=folder/(adapter+'.json')
        result.write_text(json.dumps({'status':'completed','items':[{}]*40,'protocol':protocol}))
        refs.append({'path':str(result.relative_to(tmp_path)),'sha256':hashlib.sha256(result.read_bytes()).hexdigest()})
    manifest={'schema_version':1,'status':'frozen','final_evaluation_authorized':True,
        'final_answers_used_for_selection':False,'frozen_at':'2026-10-29','selection_basis':'CPU fixture',
        'evaluation_adapters':['base','candidate'],'selected_adapter':'base','validation_evidence':refs,
        'final_dataset_sha256':'a'*64}
    if selected is not None:manifest['selected_precision']=selected
    path=folder/'selection.json';path.write_text(json.dumps(manifest));return path


def test_historical_validation_is_nf4_without_mutating_its_protocol():
    protocol={'final_holdout_read':False};before=dict(protocol)
    assert live.protocol_precision(protocol)=='nf4' and protocol==before
    with pytest.raises(ValueError,match='explicit precision'):
        live.protocol_precision({'final_holdout_read':True})
    with pytest.raises(ValueError,match='Invalid recorded'):
        live.protocol_precision({'precision':'unknown'})


@pytest.mark.parametrize('precisions,selected',[(('nf4','bf16'),'bf16'),((None,'bf16'),'bf16'),((None,None),None)])
def test_final_gate_rejects_mixed_or_missing_selected_precision(tmp_path,precisions,selected):
    path=freeze(tmp_path,precisions,selected)
    with pytest.raises(ValueError,match='precision'):
        live.check_selection_freeze(path,'base',root=tmp_path,precision=selected or 'nf4')


@pytest.mark.parametrize('precisions,selected',[((None,None),'nf4'),(('nf4','nf4'),'nf4'),(('bf16','bf16'),'bf16')])
def test_final_gate_accepts_only_comparable_precision_and_rejects_request_change(tmp_path,precisions,selected):
    path=freeze(tmp_path,precisions,selected)
    assert live.check_selection_freeze(path,'candidate',root=tmp_path,precision=selected)['selected_precision']==selected
    with pytest.raises(ValueError,match='Requested final precision'):
        live.check_selection_freeze(path,'candidate',root=tmp_path,precision='bf16' if selected=='nf4' else 'nf4')


def test_prepare_records_precision_in_protocol_and_body_without_network(tmp_path,monkeypatch):
    monkeypatch.setattr(live,'ROOT',tmp_path)
    dataset=tmp_path/'runs/finish-v2/20261028/education/development/validation.jsonl'
    dataset.parent.mkdir(parents=True);dataset.write_text('CPU synthetic data')
    records=[{'id':str(i),'split':'validation','messages':[{'role':'user','content':'SQL example'}]} for i in range(40)]
    monkeypatch.setattr(live,'load_records',lambda paths:records)
    monkeypatch.setattr(live,'validate_dataset',lambda **kwargs:None)
    class NoNetwork:
        def call(self,*args,**kwargs):raise AssertionError('Prepare must not call the API')
    args=SimpleNamespace(split='validation',precision='bf16',adapter='base',run='precision-fixture',execute=False)
    live.evaluate(args,NoNetwork())
    folder=tmp_path/'runs/finish-v2/20261029/education/precision-fixture'
    assert json.loads((folder/'protocol.json').read_text())['precision']=='bf16'
    assert json.loads((folder/'batch-01/submission.json').read_text())['body']['precision']=='bf16'
    original=(folder/'protocol.json').read_bytes()
    args.precision='nf4'
    with pytest.raises(ValueError,match='new explicitly reviewed run'):
        live.evaluate(args,NoNetwork())
    assert (folder/'protocol.json').read_bytes()==original


def test_existing_historical_run_is_preserved_and_requires_new_name(tmp_path,monkeypatch):
    monkeypatch.setattr(live,'ROOT',tmp_path)
    dataset=tmp_path/'runs/finish-v2/20261028/education/development/validation.jsonl'
    dataset.parent.mkdir(parents=True);dataset.write_text('CPU fixture')
    records=[{'id':str(i),'split':'validation'} for i in range(40)]
    monkeypatch.setattr(live,'load_records',lambda paths:records)
    monkeypatch.setattr(live,'validate_dataset',lambda **kwargs:None)
    folder=tmp_path/'runs/finish-v2/20261029/education/historical';folder.mkdir(parents=True)
    protocol=folder/'protocol.json';protocol.write_text(json.dumps({'adapter':'base','historical':'no precision field'}))
    prior=protocol.read_bytes()
    args=SimpleNamespace(adapter='base',run='historical',execute=False)
    with pytest.raises(ValueError,match='new explicitly reviewed run'):
        live.evaluate(args,object())
    assert protocol.read_bytes()==prior
