"""Temporary state and no worker/model calls; proposed session budget contract."""
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,time
from pathlib import Path
import pytest
from edu_tutor.models import budget

SCOPE='fixture-approved-total'
A='a'*32
B='b'*32

def policy(root):
    (root/'.local').mkdir(exist_ok=True)
    (root/'runs/phase2/current').mkdir(parents=True)
    value={'enabled':True,'gpu_seconds':5400,'new_audio_clips':23,'vision_requests':6,
        'min_C_free_bytes':0,'system_volume':str(root),'per_request_seconds':300,
        'active_execution_allowance':{'id':SCOPE,'baseline_request_count':0,
          'baseline_requests_sha256':hashlib.sha256(b'[]').hexdigest(),
          'accounting':'scope_only_preserve_lifetime','runtime_scope':'finish_local_tutor',
          'limits':{'gpu_seconds':50,'text_requests':6,'new_audio_clips':4,'vision_requests':2,
            'training_experiments':0,'download_bytes':0,'new_text_candidates':0,'new_tts_candidates':0}}}
    (root/'.local/phase2-policy.json').write_text(json.dumps(value),encoding='utf-8')
    (root/'runs/phase2/current/resource-budget.json').write_text('{"requests":[]}',encoding='utf-8')

@pytest.fixture
def root(tmp_path,monkeypatch):
    policy(tmp_path)
    monkeypatch.setattr(budget,'_storage_check',lambda *a,**k:None)
    return tmp_path

def limits(**changes):
    return {'seconds':20,'text_requests':3,'new_audio_clips':2,'vision_requests':1,**changes}

def start(root,session=A,**changes):
    return budget.student_budget(root,session,limits=limits(**changes),request_id='start-'+session)

def reserve(root,session=A,kind='text',timeout=2,**values):
    payload={'kind':kind,'job_id':'fixture-job','execution_allowance_id':SCOPE,**values}
    if session is not None:payload['student_session_id']=session
    return budget.reserve(root,payload,timeout)

def rows(root):
    return json.loads((root/'runs/phase2/current/resource-budget.json').read_text())['requests']

def test_lookup_never_creates_and_explicit_start_does_not_top_up_parent(root):
    before=budget.status(root)['active_execution_allowance']
    assert budget.student_budget(root,A)['exists'] is False
    created=start(root)
    assert created['state']=='active' and created['effective_remaining']==limits()
    assert budget.status(root)['active_execution_allowance']==before and rows(root)==[]

@pytest.mark.parametrize('change',[{'seconds':51},{'text_requests':7},{'new_audio_clips':5},{'vision_requests':3},
    {'seconds':float('inf')},{'seconds':float('nan')},{'seconds':True},{'text_requests':True},
    {'text_requests':-1},{'seconds':0},{'text_requests':0,'new_audio_clips':0,'vision_requests':0}])
def test_invalid_or_parent_exceeding_cap_cannot_create(root,change):
    with pytest.raises(budget.ResourceBudgetExceeded):start(root,**change)
    assert not budget.student_budget(root,A)['exists'] and rows(root)==[]

def test_idempotent_start_close_preserves_limits_and_never_reopens(root):
    assert start(root)==start(root)
    before=budget.student_budget(root,A)
    with pytest.raises(budget.ResourceBudgetExceeded):start(root,text_requests=1)
    closed=budget.student_budget(root,A,close=True)
    assert closed==budget.student_budget(root,A,close=True)==start(root)
    assert closed['limits']==before['limits'] and all(v==0 for v in closed['effective_remaining'].values())
    with pytest.raises(budget.ResourceBudgetExceeded):reserve(root)

def test_separate_student_and_development_counts_share_parent_total(root):
    start(root);start(root,B)
    reserve(root);reserve(root,None);reserve(root,B,kind='speech_batch',items=[{'id':'clip'}])
    assert budget.student_budget(root,A)['used']['text_requests']==1
    assert budget.student_budget(root,B)['used']['text_requests']==0
    totals=budget.status(root)
    assert totals['usage_by_purpose']['student_sessions']['text_requests']==1
    assert totals['usage_by_purpose']['development']['text_requests']==1
    assert totals['active_execution_allowance']['text_remaining']==4
    assert totals['active_execution_allowance']['audio_remaining']==3

def test_multiple_sessions_cannot_overcommit_actual_parent_calls(root):
    start(root,text_requests=4);start(root,B,text_requests=4)
    for _ in range(4):reserve(root,A)
    for _ in range(2):reserve(root,B)
    with pytest.raises(budget.ResourceBudgetExceeded):reserve(root,B)
    assert len(rows(root))==6 and budget.student_budget(root,B)['effective_remaining']['text_requests']==0

def test_caps_cannot_exceed_reduced_parent_remainder(root):
    for _ in range(5):reserve(root,None)
    with pytest.raises(budget.ResourceBudgetExceeded):start(root,text_requests=2)

def test_parallel_last_slot_is_reserved_only_once(root):
    start(root,text_requests=1)
    def attempt(_):
        try:reserve(root);return 'reserved'
        except budget.ResourceBudgetExceeded:return 'blocked'
    with ThreadPoolExecutor(max_workers=2) as pool:out=list(pool.map(attempt,range(2)))
    assert sorted(out)==['blocked','reserved'] and len(rows(root))==1

def test_reservation_charges_both_immediately_and_restart_keeps_it(root):
    start(root,seconds=5)
    reservation,duration=reserve(root,timeout=300)
    assert duration==5
    assert budget.student_budget(root,A)['used']['seconds']==5
    assert budget.status(root)['gpu_seconds_remaining']==45
    with pytest.raises(budget.ResourceBudgetExceeded):reserve(root)
    # A new read has no process-local counters to reset; unfinished stays charged.
    assert json.loads((root/'runs/phase2/current/resource-budget.json').read_text())['requests'][0]['status']=='reserved'

def test_failed_or_cancelled_attempt_counts_and_settles_same_row(root):
    start(root);reservation,_=reserve(root)
    r,p,ident,_=reservation
    budget.finish((r,p,ident,time.monotonic()-.01),False)
    assert rows(root)[0]['status']=='failed_or_cancelled'
    view=budget.student_budget(root,A)
    assert view['used']['text_requests']==1 and view['remaining']['text_requests']==2
    assert 0<view['used']['seconds']<1

@pytest.mark.parametrize('kind',['training','download','text_batch'])
def test_student_session_is_not_a_new_general_execution_grant(root,kind):
    start(root)
    with pytest.raises(budget.ResourceBudgetExceeded):reserve(root,kind=kind,items=[{}])
    assert rows(root)==[]

def test_empty_unknown_session_never_falls_back_to_development(root):
    with pytest.raises(budget.ResourceBudgetExceeded):reserve(root)
    assert rows(root)==[]

def test_policy_disable_cannot_make_student_execution_unlimited(root):
    start(root)
    file=root/'.local/phase2-policy.json';value=json.loads(file.read_text());value['enabled']=False;file.write_text(json.dumps(value))
    with pytest.raises(budget.ResourceBudgetExceeded):reserve(root)
    assert rows(root)==[]

def test_historical_prefix_and_lifetime_rows_survive_student_start_and_use(root):
    history=[{'id':'historical','kind':'text','charged_seconds':100,'new_audio_clips':0,'vision_requests':0,'status':'failed_or_cancelled'}]
    ledger=root/'runs/phase2/current/resource-budget.json';ledger.write_text(json.dumps({'requests':history}))
    path=root/'.local/phase2-policy.json';value=json.loads(path.read_text())
    value['active_execution_allowance'].update(baseline_request_count=1,
        baseline_requests_sha256=hashlib.sha256(json.dumps(history,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest())
    path.write_text(json.dumps(value))
    start(root);reserve(root)
    assert rows(root)[0]==history[0]
    assert budget.status(root)['lifetime']['model_seconds']==102
    assert budget.status(root)['active_execution_allowance']['seconds_remaining']==48
