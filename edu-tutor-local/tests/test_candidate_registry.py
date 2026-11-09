"""Live checkout candidate source tests: no actual network, model, GPU or live ledger."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest

from candidate_support import load, FIXTURE


@pytest.fixture
def candidate(monkeypatch):return load(monkeypatch,'text_candidate')


def metadata():return json.loads(FIXTURE.read_text(encoding='utf-8'))


def test_official_metadata_pins_and_total(candidate):
    m=candidate.validate_inventory(metadata())
    assert m['download_bytes']==8060915998 and len(m['files'])==12
    assert m['model_id']==candidate.MODEL_ID and m['revision']==candidate.REVISION
    assert not m['download_complete']
    assert all(x['path'] in candidate.FILES and '/' not in x['path'] for x in m['files'])


@pytest.mark.parametrize('mutation',['revision','license','id','shard_size','shard_hash','blob','duplicate','missing','metadata_size'])
def test_inventory_drift_is_rejected(candidate,mutation):
    m=metadata()
    if mutation in ['revision','license','id']:
        if mutation=='revision':m['sha']='0'*40
        if mutation=='id':m['id']='Other/model'
        if mutation=='license':m['cardData']['license']='unknown'
    else:
        row=next(r for r in m['siblings'] if r['rfilename']=='model-00001-of-00003.safetensors')
        if mutation=='shard_size':row['size']+=1
        if mutation=='shard_hash':row['lfs']['sha256']='0'*64
        if mutation=='blob':next(r for r in m['siblings'] if r['rfilename']=='config.json')['blobId']='0'*40
        if mutation=='duplicate':m['siblings'].append(deepcopy(row))
        if mutation=='missing':m['siblings'].remove(row)
        if mutation=='metadata_size':next(r for r in m['siblings'] if r['rfilename']=='config.json')['size']+=1
    with pytest.raises(ValueError):candidate.validate_inventory(m)


@pytest.mark.parametrize('mutation',['length','lfs_hash','blob_hash'])
def test_actual_file_digest_failure(candidate,tmp_path,mutation):
    p=tmp_path/'tiny';p.write_bytes(b'fixture')
    entry={'path':'tiny','size':7,'sha256':hashlib.sha256(b'fixture').hexdigest(),
        'git_blob_sha1':hashlib.sha1(b'blob 7\0fixture').hexdigest()}
    assert candidate.file_identity(p,entry)==entry['sha256']
    if mutation=='length':entry['size']=8
    if mutation=='lfs_hash':entry['sha256']='0'*64
    if mutation=='blob_hash':entry['git_blob_sha1']='0'*40
    with pytest.raises(ValueError):candidate.file_identity(p,entry)


@pytest.mark.parametrize('model_ref,adapter,precision',[
    ('../text',None,'nf4'),('qwen3-4b-instruct-2507','train-old','nf4'),
    ('qwen3-4b-instruct-2507',None,'bf16'),('qwen3-4b-instruct-2507',None,'fp16')])
def test_candidate_identity_adapter_and_precision_before_any_file(candidate,tmp_path,model_ref,adapter,precision):
    with pytest.raises(ValueError):candidate.resolve_candidate(tmp_path,model_ref,adapter,precision)
    assert not (tmp_path/'.local').exists()


def test_completed_tiny_fixture_resolution_and_tamper_guard(candidate,tmp_path,monkeypatch):
    folder=candidate.candidate_folder(tmp_path);folder.mkdir(parents=True)
    file=folder/'config.json';file.write_bytes(b'{}')
    entry={'path':'config.json','size':2,'sha256':hashlib.sha256(b'{}').hexdigest(),
           'git_blob_sha1':hashlib.sha1(b'blob 2\0{}').hexdigest()}
    monkeypatch.setattr(candidate,'FILES',frozenset({'config.json'}))
    monkeypatch.setattr(candidate,'PINNED_FILES',{'config.json':deepcopy(entry)})
    manifest={'candidate_id':candidate.CANDIDATE,'model_id':candidate.MODEL_ID,'revision':candidate.REVISION,
        'license':'apache-2.0','authorization_id':candidate.SCOPE,'download_complete':True,'files':[entry]}
    path=folder/'model-manifest.json';path.write_text(json.dumps(manifest))
    assert candidate.resolve_candidate(tmp_path,candidate.CANDIDATE)[0]==folder
    manifest['files'][0]['sha256']='0'*64;path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):candidate.resolve_candidate(tmp_path,candidate.CANDIDATE)


@pytest.mark.parametrize('values,token',[([151645,151643],151645),([151643,151645],151645)])
def test_eos_two_official_endings(candidate,values,token):
    model=SimpleNamespace(generation_config=SimpleNamespace(eos_token_id=values))
    assert set(candidate.candidate_eos_ids(model,SimpleNamespace(eos_token_id=token)))=={151645,151643}


@pytest.mark.parametrize('values,token',[([151645],151645),([151645,151643],99),([151645,False],151645),('151645',151645)])
def test_bad_eos_configuration_stops(candidate,values,token):
    model=SimpleNamespace(generation_config=SimpleNamespace(eos_token_id=values))
    with pytest.raises(ValueError):candidate.candidate_eos_ids(model,SimpleNamespace(eos_token_id=token))


@pytest.mark.parametrize('url', ['http://huggingface.co/x','https://evil.com/x','https://huggingface.co.evil.com/x',
    'https://user:secret@huggingface.co/x','https://huggingface.co:444/x','file:///weights'])
def test_unapproved_redirect_is_rejected(candidate,monkeypatch,url):
    d=load(monkeypatch,'candidate_transfer')
    with pytest.raises(ValueError):d.official_url(url)


def download_fixture(monkeypatch,candidate,tmp_path,*,fail=False):
    from edu_tutor.models import budget
    d=load(monkeypatch,'candidate_download');events=[]
    monkeypatch.setattr(budget,'policy',lambda root:{'enabled':True})
    monkeypatch.setattr(budget,'status',lambda root:{'active_execution_allowance':{'id':candidate.SCOPE,'accounting':'scope_only_preserve_lifetime'}})
    def reserve(root,payload,timeout):
        events.append(('reserve',payload.copy()));return (root,None,str(len(events)),0),0
    monkeypatch.setattr(budget,'reserve',reserve)
    monkeypatch.setattr(budget,'finish_download',lambda r,n,ok:events.append(('finish',n,ok)))
    raw=b'new fixture body'
    m={'download_complete':False,'download_bytes':len(raw),'files':[{'path':'config.json','size':len(raw),
        'sha256':hashlib.sha256(raw).hexdigest(),'git_blob_sha1':None}]}
    monkeypatch.setattr(d,'validate_inventory',lambda info:deepcopy(m))
    def receive(root,url,target,**kwargs):
        events.append(('open',url))
        if '/api/models/' in url:data=b'{}'
        elif fail:raise TimeoutError('synthetic transfer failure')
        else:data=raw
        target.write_bytes(data)
        return {'body_bytes':len(data),'transferred_bytes':len(data),'hops':[]}
    monkeypatch.setattr(d,'bounded_receive',receive)
    return d,events,raw


def test_download_stages_commits_preserves_old_base_and_charges_twice(candidate,tmp_path,monkeypatch):
    d,events,raw=download_fixture(monkeypatch,candidate,tmp_path)
    old=tmp_path/'.local/models/text/preserved';old.parent.mkdir(parents=True);old.write_bytes(b'old')
    result=d.download_candidate(tmp_path,'a'*32,candidate.SCOPE,threading.Event())
    folder=candidate.candidate_folder(tmp_path)
    assert result['status']=='completed_download_only' and result['new_model_calls']==0
    assert (folder/'config.json').read_bytes()==raw and old.read_bytes()==b'old'
    assert (folder/'model-manifest.json').is_file()
    assert not list(folder.parent.glob('.*.partial'))
    reservations=[e[1] for e in events if e[0]=='reserve']
    assert len(reservations)==2 and all(r['candidate_id']==candidate.CANDIDATE and r['execution_allowance_id']==candidate.SCOPE for r in reservations)
    assert [e[1:] for e in events if e[0]=='finish']==[(2,True),(len(raw),True)]
    with pytest.raises(ValueError):d.download_candidate(tmp_path,'b'*32,candidate.SCOPE,threading.Event())
    assert len([e for e in events if e[0]=='open'])==2


def test_failed_download_keeps_staging_reservation_and_never_retries(candidate,tmp_path,monkeypatch):
    d,events,raw=download_fixture(monkeypatch,candidate,tmp_path,fail=True)
    with pytest.raises(TimeoutError):d.download_candidate(tmp_path,'c'*32,candidate.SCOPE,threading.Event())
    assert len([e for e in events if e[0]=='open'])==2
    assert [e[1:] for e in events if e[0]=='finish'][-1]==(len(raw)+d.REDIRECT_BYTES_PER_FILE,False)
    folder=candidate.candidate_folder(tmp_path)
    assert not folder.exists() and list(folder.parent.glob('.*.partial'))
    report=json.loads((tmp_path/'runs'/('candidate-download-'+'c'*32)/'result.json').read_text(encoding='utf-8'))
    assert report['status']=='failed_or_cancelled' and report['failure_byte_accounting']=='full_reserved_maximum_retained'


def test_pre_cancelled_download_does_not_open_network(candidate,tmp_path,monkeypatch):
    d,events,raw=download_fixture(monkeypatch,candidate,tmp_path)
    event=threading.Event();event.set()
    with pytest.raises(RuntimeError):d.download_candidate(tmp_path,'d'*32,candidate.SCOPE,event)
    assert not any(e[0]=='open' for e in events)


def test_wrong_scope_and_job_id_never_touch_network(candidate,tmp_path,monkeypatch):
    d,events,_=download_fixture(monkeypatch,candidate,tmp_path)
    for ident,scope in [('e'*32,'wrong'),('../escape',candidate.SCOPE)]:
        with pytest.raises(ValueError):d.download_candidate(tmp_path,ident,scope,threading.Event())
    assert not events and not (tmp_path/'runs').exists()


