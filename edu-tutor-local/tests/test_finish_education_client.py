from importlib.util import module_from_spec, spec_from_file_location
import json
import hashlib
from pathlib import Path
from urllib.error import URLError

import pytest

SPEC=spec_from_file_location('finish_education_live',Path(__file__).resolve().parents[1]/'scripts/finish_education_live.py')
live=module_from_spec(SPEC)
SPEC.loader.exec_module(live)


class FakeClient:
    def __init__(self):
        self.posts=[]
        self.jobs=[]
        self.fail_post=False

    def call(self,path,body=None):
        if body is None:
            assert path=='/api/jobs'
            return self.jobs
        self.posts.append((path,body))
        if self.fail_post:
            raise URLError('fixture transport failed after write')
        job={'id':'fixture-job','kind':'evaluation','state':'queued','request_id':body['request_id']}
        self.jobs.append(job)
        return job


def test_prepare_never_submits_and_execution_preserves_same_request_id(tmp_path):
    client=FakeClient()
    one=live.submit_once(client,tmp_path,'/api/evaluations/text-batch',{'items':[]},'evaluation')
    assert not client.posts and one['status']=='prepared'
    two=live.submit_once(client,tmp_path,'/api/evaluations/text-batch',{'items':[]},'evaluation',execute=True)
    assert len(client.posts)==1 and one['request_id']==two['request_id']
    three=live.submit_once(client,tmp_path,'/api/evaluations/text-batch',{'items':[]},'evaluation',execute=True)
    assert len(client.posts)==1 and three['job_id']=='fixture-job'


def test_ambiguous_post_is_not_retried_without_existing_server_job(tmp_path):
    client=FakeClient();client.fail_post=True
    with pytest.raises(URLError):
        live.submit_once(client,tmp_path,'/api/evaluations/text-batch',{'items':[]},'evaluation',execute=True)
    with pytest.raises(RuntimeError,match='no automatic retry'):
        live.submit_once(client,tmp_path,'/api/evaluations/text-batch',{'items':[]},'evaluation',execute=True)
    assert len(client.posts)==1
    saved=json.loads((tmp_path/'submission.json').read_text())
    client.jobs=[{'id':'recovered','kind':'evaluation','request_id':saved['request_id']}]
    recovered=live.submit_once(client,tmp_path,'/api/evaluations/text-batch',{'items':[]},'evaluation',execute=True)
    assert recovered['job_id']=='recovered' and len(client.posts)==1


def test_reusing_evidence_directory_with_changed_model_is_rejected(tmp_path):
    client=FakeClient()
    live.submit_once(client,tmp_path,'/api/evaluations/text-batch',{'adapter':'base'},'evaluation')
    with pytest.raises(ValueError,match='differs'):
        live.submit_once(client,tmp_path,'/api/evaluations/text-batch',{'adapter':'some-adapter'},'evaluation',execute=True)
    assert not client.posts


def test_final_gate_requires_frozen_comparable_evidence_before_dataset_access(tmp_path):
    folder=tmp_path/'runs/finish-v2/20261029/education'
    folder.mkdir(parents=True)
    with pytest.raises(ValueError,match='explicit selection freeze'):
        live.check_selection_freeze(None,'base',root=tmp_path)
    refs=[]
    for adapter in ['base','candidate']:
        result=folder/(adapter+'.json')
        result.write_text(json.dumps({'status':'completed','items':[{}]*40,
            'protocol':{'adapter':adapter,'final_holdout_read':False,'max_new_tokens':256,'do_sample':False}}))
        refs.append({'path':str(result.relative_to(tmp_path)), 'sha256':hashlib.sha256(result.read_bytes()).hexdigest()})
    manifest={'schema_version':1,'status':'frozen','final_evaluation_authorized':True,
        'final_answers_used_for_selection':False,'frozen_at':'2026-10-29','selection_basis':'fixture decision',
        'evaluation_adapters':['base','candidate'],'selected_adapter':'base','validation_evidence':refs,
        'selected_precision':'nf4',
        'final_dataset_sha256':'a'*64}
    path=folder/'selection.json';path.write_text(json.dumps(manifest))
    assert live.check_selection_freeze(path,'candidate',root=tmp_path)['selected_adapter']=='base'
    with pytest.raises(ValueError,match='exactly one'):
        live.check_selection_freeze(path,'other',root=tmp_path)
    # A final dataset does not exist here; the gate checks selection only.
    (folder/'candidate.json').write_text('{}')
    with pytest.raises(ValueError,match='evidence changed'):
        live.check_selection_freeze(path,'candidate',root=tmp_path)
