"""Local TestClient, fake workers, temporary files. Actual generation always zero."""
import copy,io,json,time,importlib,threading
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from edu_tutor.api import create_app
from edu_tutor.models import budget,runtime
from edu_tutor.models.execution_context import bind_scope,execution_allowance,student_session,requested_student_session
from edu_tutor.problems.pipeline import from_text
from test_student_budget_cpu import policy,SCOPE,limits

def ended(client,ident):
    for _ in range(150):
        value=client.get('/api/jobs/'+ident).json()
        if value['state'] in {'succeeded','blocked','failed','cancelled','interrupted'}:return value
        time.sleep(.01)
    pytest.fail('CPU fake job did not finish')

@pytest.fixture
def app_fixture(tmp_path,monkeypatch):
    policy(tmp_path)
    monkeypatch.setattr(budget,'_storage_check',lambda *a,**k:None)
    seen=[]
    def fake_worker(payload,**kwargs):
        seen.append(dict(payload))
        yield {'type':'delta','text':'CPU fixture answer'}
        yield {'type':'done'}
    monkeypatch.setattr(runtime,'_run_worker',fake_worker)
    def fake_generate(messages,root=None,job_id=None,cancel_event=None,**kwargs):
        for event in runtime.run_worker({'kind':'text','job_id':job_id},root=root,cancel_event=cancel_event,timeout=30):
            if event['type']=='delta':yield event['text']
    monkeypatch.setattr(runtime,'generate',fake_generate)
    app=create_app(tmp_path)
    token=(tmp_path/'.local/auth-token').read_text().strip()
    with TestClient(app,base_url='http://127.0.0.1:8000',headers={'Authorization':'Bearer '+token}) as client:
        yield client,app,tmp_path,seen

def session(client):return client.post('/api/sessions',json={'title':'CPU student session'}).json()['id']
def start(client,ident,**values):
    return client.post(f'/api/sessions/{ident}/budget',json={'request_id':'start-'+ident,**limits(**values)})
def headers(ident):return {'X-Student-Session':ident}
def message(client,ident,header=None,**values):
    return client.post(f'/api/sessions/{ident}/messages',headers=header or {},json={'content':'CPU fixture only','request_id':str(time.monotonic()),'verification_mode':'model_only',**values})

def saved_lesson(app,session_id):
    store=app.state.store;problem=from_text('CPU fixture only')
    question=store.put('messages',{'id':'1'*32,'session_id':session_id,'role':'user','content':'CPU fixture only','request_id':'fixture'})
    answer=store.put('messages',{'id':'2'*32,'session_id':session_id,'role':'assistant','content':'CPU fixture answer','request_id':'fixture','problem':problem})
    return store.put('lessons',{'id':'3'*32,'source_message_id':answer['id'],'source_session_id':session_id,
        'problem':problem,'is_demo':False,'valid':True,'speech_allowed':True,'generation_epoch':1,
        'plan':{'steps':[{'id':'s1','speech':'CPU fixture speech','board_actions':[{'type':'text','element_id':'source','text':'preserved'}]}]},
        'audio_steps':[{'step_id':'s1','audio_id':'d'*64,'voice':'fixture','provider':'test_cpu'}]})

def test_mount_reads_no_budget_and_does_not_create_or_run(app_fixture):
    client,app,root,seen=app_fixture;ident=session(client)
    assert client.get(f'/api/sessions/{ident}/budget').json()['exists'] is False
    assert budget.status(root)['active_execution_allowance']['text_remaining']==6 and seen==[]
    assert client.get('/api/jobs').json()==[]

def test_explicit_student_request_uses_bound_cap_and_real_context_transport(app_fixture):
    client,app,root,seen=app_fixture;ident=session(client)
    assert start(client,ident).status_code==201
    result=message(client,ident,headers(ident))
    assert result.status_code==202,result.text
    assert ended(client,result.json()['job_id'])['state']=='succeeded'
    assert len(seen)==1 and seen[0]['student_session_id']==ident and seen[0]['execution_allowance_id']==SCOPE
    assert budget.student_budget(root,ident)['used']['text_requests']==1

@pytest.mark.parametrize('header_kind',['missing','developer_only','other_student','unknown_student'])
def test_budgeted_session_cannot_bypass_or_charge_a_different_session(app_fixture,header_kind):
    client,app,root,seen=app_fixture;a=session(client);b=session(client);start(client,a);start(client,b)
    requested={'missing':{},'developer_only':{'X-Execution-Allowance':SCOPE},'other_student':headers(b),'unknown_student':headers('c'*32)}[header_kind]
    before=copy.deepcopy(app.state.store.get('sessions',a))
    response=message(client,a,requested)
    assert response.status_code==409,response.text
    assert seen==[] and app.state.store.get('sessions',a)==before
    assert client.get('/api/jobs').json()==[] and client.get(f'/api/sessions/{a}/messages').json()==[]

def test_student_header_cannot_create_implicit_budget(app_fixture):
    client,app,root,seen=app_fixture;ident=session(client)
    assert message(client,ident,headers(ident)).status_code==409
    assert not budget.student_budget(root,ident)['exists'] and seen==[]

def test_development_path_retained_and_does_not_inherit_student_context(app_fixture):
    client,app,root,seen=app_fixture;a=session(client);b=session(client);start(client,a)
    ended(client,message(client,a,headers(a)).json()['job_id'])
    result=message(client,b,{'X-Execution-Allowance':SCOPE})
    assert ended(client,result.json()['job_id'])['state']=='succeeded'
    assert seen[0]['student_session_id']==a and 'student_session_id' not in seen[1]
    assert budget.status(root)['usage_by_purpose']['development']['text_requests']==1

def test_same_start_is_idempotent_conflicting_start_and_parent_overflow_rejected(app_fixture):
    client,app,root,seen=app_fixture;ident=session(client)
    first=start(client,ident);assert first.status_code==201
    assert start(client,ident).json()==first.json()
    assert start(client,ident,text_requests=2).status_code==409
    other=session(client);assert start(client,other,text_requests=7).status_code==409
    assert seen==[]

def test_closed_session_keeps_exact_bound_cache_get_without_charge(app_fixture,monkeypatch):
    from edu_tutor.speech import provider
    client,app,root,seen=app_fixture;ident=session(client);start(client,ident);lesson=saved_lesson(app,ident)
    monkeypatch.setattr(provider,'cached_audio',lambda *a,**k:{'hit':True,'audio':{'audio_id':'d'*64,'voice':'fixture','provider':'test_cpu'},'wave_bytes':b'CPU bytes, not actual WAV'})
    monkeypatch.setattr(provider,'status',lambda *a,**k:{'ready':False,'reason':'CPU fixture'})
    assert client.post(f'/api/sessions/{ident}/budget/close',headers=headers(ident)).status_code==200
    assert client.post(f'/api/sessions/{ident}/budget/close',headers=headers(ident)).status_code==200
    before=(root/'runs/phase2/current/resource-budget.json').read_bytes()
    manifest=client.get(f'/api/lessons/{lesson["id"]}/speech',headers=headers(ident)).json()
    clip=manifest['steps'][0]
    assert client.get(clip['audio_url'],headers=headers(ident)).content==b'CPU bytes, not actual WAV'
    assert message(client,ident,headers(ident)).status_code==409
    assert client.post(f'/api/lessons/{lesson["id"]}/speech',headers=headers(ident),json={}).status_code==409
    assert before==(root/'runs/phase2/current/resource-budget.json').read_bytes() and seen==[]

def test_photo_upload_transcription_and_solve_keep_same_student_owner(app_fixture,monkeypatch):
    from edu_tutor.models import vision_runtime
    client,app,root,seen=app_fixture;a=session(client);b=session(client);start(client,a);start(client,b)
    buffer=io.BytesIO();Image.new('RGB',(4,4),'white').save(buffer,format='PNG')
    created=client.post('/api/photos',headers=headers(a),data={'session_id':a},files={'file':('cpu.png',buffer.getvalue(),'image/png')})
    assert created.status_code==201,created.text
    photo=created.json();assert photo['session_id']==a
    assert client.post(f'/api/photos/{photo["id"]}/transcribe',headers=headers(b)).status_code==409
    assert client.post(f'/api/photos/{photo["id"]}/transcribe',headers={'X-Execution-Allowance':SCOPE}).status_code==409
    def fake_vision(path,root=None,job_id=None,cancel_event=None):
        list(runtime.run_worker({'kind':'vision','job_id':job_id},root=root,cancel_event=cancel_event,timeout=30))
        return {'original_text':'CPU fixture question','question':'CPU fixture question','tables':[],'sql':''}
    monkeypatch.setattr(vision_runtime,'transcribe',fake_vision)
    result=client.post(f'/api/photos/{photo["id"]}/transcribe',headers=headers(a))
    assert ended(client,result.json()['job_id'])['state']=='succeeded'
    assert seen[-1]['student_session_id']==a and seen[-1]['kind']=='vision'
    client.post(f'/api/photos/{photo["id"]}/confirm')
    assert client.post(f'/api/photos/{photo["id"]}/solve',headers=headers(b),json={'session_id':b}).status_code==409
    result=client.post(f'/api/photos/{photo["id"]}/solve',headers=headers(a),json={'session_id':a})
    assert result.status_code==202,result.text
    assert ended(client,result.json()['job_id'])['state']=='succeeded'
    assert all(p['student_session_id']==a for p in seen)

def test_new_speech_uses_actual_lesson_owner_not_header_choice(app_fixture,monkeypatch):
    from edu_tutor.speech import provider
    client,app,root,seen=app_fixture;a=session(client);b=session(client);start(client,a);start(client,b);lesson=saved_lesson(app,a)
    def fake_prepare(text,root=None,job_id=None,cancel_event=None,**kwargs):
        list(runtime.run_worker({'kind':'speech','job_id':job_id},root=root,cancel_event=cancel_event,timeout=30))
        return {'audio_id':'e'*64,'url':'/api/audio/'+'e'*64,'voice':'fixture','provider':'test_cpu'}
    monkeypatch.setattr(provider,'prepare',fake_prepare)
    assert client.post(f'/api/lessons/{lesson["id"]}/speech',headers=headers(b),json={'step_id':'s1'}).status_code==409
    assert client.post(f'/api/lessons/{lesson["id"]}/speech',headers={'X-Execution-Allowance':SCOPE},json={'step_id':'s1'}).status_code==409
    result=client.post(f'/api/lessons/{lesson["id"]}/speech',headers=headers(a),json={'step_id':'s1'})
    assert ended(client,result.json()['job_id'])['state']=='succeeded'
    assert seen[-1]['student_session_id']==a and budget.student_budget(root,a)['used']['new_audio_clips']==1

def test_runtime_rejects_header_not_validated_against_saved_source(app_fixture):
    client,app,root,seen=app_fixture;ident=session(client);start(client,ident)
    token=requested_student_session.set(ident);scope=execution_allowance.set(SCOPE)
    try:
        with pytest.raises(budget.ResourceBudgetExceeded):bind_scope({'kind':'text'})
    finally:requested_student_session.reset(token);execution_allowance.reset(scope)
    assert seen==[]

@pytest.mark.parametrize('available,expected_attempts',[(1,1),(2,2)])
def test_repair_uses_same_student_cap_or_preserves_raw_answer_when_exhausted(app_fixture,monkeypatch,available,expected_attempts):
    client,app,root,seen=app_fixture;ident=session(client);start(client,ident,text_requests=available)
    app_module=importlib.import_module('edu_tutor.api.app')
    counter=[]
    def check(*args):
        counter.append(1)
        return {'status':'stopped','can_repair':len(counter)==1,'reasons':['CPU fixture repair need'],
                'execution':{'status':'not_run'}}
    monkeypatch.setattr(app_module,'verify_answer',check)
    result=message(client,ident,headers(ident),verification_mode='tools')
    job=ended(client,result.json()['job_id'])
    assert job['state']=='succeeded',job
    answer=app.state.store.get('messages',job['result']['message_id'])
    assert len(seen)==expected_attempts and len(answer['model_attempts'])==expected_attempts
    assert all(item['student_session_id']==ident for item in seen)
    assert budget.student_budget(root,ident)['used']['text_requests']==expected_attempts
    assert answer['raw_model_response']=='CPU fixture answer'
    if available==1:assert answer['evidence']['repair_skipped']=='student_session_budget_exhausted'

def test_plan_repair_budget_denial_retains_old_board_audio_and_advances_epoch(app_fixture,monkeypatch):
    from edu_tutor.lessons import concepts
    client,app,root,seen=app_fixture;ident=session(client);start(client,ident,text_requests=1)
    lesson=saved_lesson(app,ident)
    answer=app.state.store.get('messages',lesson['source_message_id']);answer['evidence']={'status':'concept_unverified'};app.state.store.put('messages',answer)
    reservation,_=budget.reserve(root,{'kind':'text','execution_allowance_id':SCOPE,'student_session_id':ident},2)
    budget.finish(reservation,True)
    def denied(*args,root=None,job_id=None,cancel_event=None,**kwargs):
        list(runtime.run_worker({'kind':'text','job_id':job_id},root=root,cancel_event=cancel_event,timeout=30))
        pytest.fail('Exhausted repair must not run')
    monkeypatch.setattr(concepts,'generate_concept_plan',denied)
    response=client.post(f'/api/lessons/{lesson["id"]}/generate',headers=headers(ident))
    assert response.status_code==202,response.text
    assert ended(client,response.json()['job_id'])['state']=='blocked'
    stored=app.state.store.get('lessons',lesson['id'])
    assert stored['plan']==lesson['plan'] and stored['audio_steps']==lesson['audio_steps']
    assert stored['speech_allowed'] is True and stored['generation_epoch']==lesson['generation_epoch']+1
    assert seen==[] and budget.student_budget(root,ident)['used']['text_requests']==1

def test_close_while_own_job_active_is_rejected_then_cancel_settles_without_reset(app_fixture,monkeypatch):
    client,app,root,seen=app_fixture;ident=session(client);start(client,ident)
    entered=threading.Event()
    def blocking(payload,root=None,cancel_event=None,**kwargs):
        seen.append(payload);entered.set()
        yield {'type':'delta','text':'CPU partial'}
        assert cancel_event.wait(5),'Test cleanup cancel required'
        raise RuntimeError('CPU cancelled fixture')
    monkeypatch.setattr(runtime,'_run_worker',blocking)
    response=message(client,ident,headers(ident));job_id=response.json()['job_id']
    try:
        assert entered.wait(3)
        assert client.post(f'/api/sessions/{ident}/budget/close',headers=headers(ident)).status_code==409
    finally:client.post('/api/jobs/'+job_id+'/cancel')
    assert ended(client,job_id)['state']=='cancelled'
    assert client.post(f'/api/sessions/{ident}/budget/close',headers=headers(ident)).status_code==200
    assert budget.student_budget(root,ident)['used']['text_requests']==1
    rows=json.loads((root/'runs/phase2/current/resource-budget.json').read_text())['requests']
    assert len(rows)==1 and rows[0]['status']=='failed_or_cancelled'

def test_budget_management_header_cannot_close_other_student(app_fixture):
    client,app,root,seen=app_fixture;a=session(client);b=session(client);start(client,a);start(client,b)
    assert client.post(f'/api/sessions/{a}/budget/close',headers=headers(b)).status_code==409
    assert budget.student_budget(root,a)['state']=='active'

def test_unauthenticated_budget_creation_is_rejected_without_metadata_write(app_fixture):
    client,app,root,seen=app_fixture;ident=session(client)
    response=client.post(f'/api/sessions/{ident}/budget',headers={'Authorization':''},json={'request_id':'anonymous',**limits()})
    assert response.status_code==401
    assert not budget.student_budget(root,ident)['exists'] and seen==[]

def test_api_reconstruction_keeps_student_budget_and_pending_reservation(tmp_path,monkeypatch):
    policy(tmp_path);monkeypatch.setattr(budget,'_storage_check',lambda *a,**k:None)
    first=create_app(tmp_path);token=(tmp_path/'.local/auth-token').read_text().strip()
    auth={'Authorization':'Bearer '+token}
    with TestClient(first,base_url='http://127.0.0.1:8000',headers=auth) as client:
        ident=session(client);assert start(client,ident).status_code==201
        budget.reserve(tmp_path,{'kind':'text','execution_allowance_id':SCOPE,'student_session_id':ident},15)
        before=client.get(f'/api/sessions/{ident}/budget').json()
    second=create_app(tmp_path)
    with TestClient(second,base_url='http://127.0.0.1:8000',headers=auth) as client:
        after=client.get(f'/api/sessions/{ident}/budget').json()
        assert after==before and after['used']['seconds']==15 and after['used']['text_requests']==1
        assert client.post(f'/api/sessions/{ident}/budget',json={'request_id':'new-after-restart',**limits()}).status_code==409
