import copy
import io
import hashlib
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from edu_tutor.api import create_app
from edu_tutor.problems.models import normalize_problem
from edu_tutor.problems.evidence import verify_answer,display_answer
from edu_tutor.problems.pipeline import model_messages,from_text,from_photo,hypothesis_from_question
from edu_tutor.lessons.verified import generate_verified_plan
from edu_tutor.lessons.verified import concept_plan
from edu_tutor.lessons.verified import value_text
from edu_tutor.lessons.plans import scene_at
from edu_tutor.vision.structure import structure_candidate


def problem(kind="query_result"):
    return normalize_problem({"task_kind":kind,"dialect":"sqlite","raw_text":"COUNT(*)와 COUNT(score)는 차례대로 얼마인가?",
        "confirmed":True,"query":"SELECT COUNT(*) AS people, COUNT(score) AS scores FROM exam_result" if kind=="query_result" else None,
        "tables":[{"name":"exam_result","columns":[{"name":"name","type":"TEXT"},{"name":"score","type":"INTEGER","label":"점수"}],
                   "rows":[["가",80],["나",None],["다",100]]}]})


def test_original_query_and_numeric_plan_ignore_model_wrong_columns():
    p=problem(); e=verify_answer(p,'{"sql":"SELECT total_rows FROM other"}',p["raw_text"])
    assert e["result"]["rows"]==[[3,2]] and e["sql_origin"]=="unchanged_user_query"
    assert e["expected_result_check"]["status"]=="not_available"
    plan=generate_verified_plan({"id":"answer","problem":p,"evidence":e,"content":display_answer(e)},p["raw_text"],"lesson")["plan"]
    assert "3" in plan["steps"][0]["speech"] and "2" in plan["steps"][1]["speech"]
    first=scene_at(plan,0); table=e["original_tables"][0]
    assert first["elements"][table["id"]]["rows"]==p["tables"][0]["rows"]
    assert first["highlights"][0]["row_indices"]==[0,1,2]
    assert len(scene_at(plan,1)["highlights"][-1]["cell_ids"])==2


def test_executable_but_wrong_null_semantics_and_projection_order_stop():
    p=problem("write_sql");p["raw_text"]="점수가 있는 사람 수를 구해 줘."
    e=verify_answer(p,'{"sql":"SELECT COUNT(*) FROM exam_result"}',p["raw_text"])
    assert e["execution"]["status"]=="executed" and e["intent"]["status"]=="mismatch" and e["status"]=="stopped"
    p=problem("write_sql")
    e=verify_answer(p,'{"sql":"SELECT COUNT(score),COUNT(*) FROM exam_result"}',p["raw_text"])
    assert e["intent"]["status"]=="mismatch"
    p['raw_text']='점수가 없는 사람 수를 구해 줘.'
    missing_null=verify_answer(p,'{"sql":"SELECT COUNT(score) FROM exam_result"}',p['raw_text'])
    assert missing_null['status']==missing_null['support_status']==missing_null['intent']['status']=='needs_input'
    assert missing_null['execution']['status']=='not_run' and missing_null['result'] is None
    assert missing_null['logical_steps'] is None and missing_null['can_repair'] is False
    assert 'NULL인 행을 고르는 조건' in missing_null['intent']['scope']
    lesson=generate_verified_plan({'id':'unresolved-null','problem':p,'evidence':missing_null,
        'content':display_answer(missing_null)},p['raw_text'],'unresolved-null-lesson')
    assert lesson['plan'] is None and lesson['speech_allowed'] is False


def test_spoken_float_keeps_same_numeric_value_as_computed_board():
    number=1/3
    assert float(value_text(number))==number


def test_bounded_korean_dual_count_keeps_requested_projection_order():
    p=problem('write_sql');p['raw_text']='전체 행 수와 score가 NULL이 아닌 행 수를 차례대로 구해 줘.'
    correct=verify_answer(p,'{"sql":"SELECT COUNT(*),COUNT(score) FROM exam_result"}',p['raw_text'])
    assert correct['status']=='verified' and correct['result']['rows']==[[3,2]]
    p['raw_text']='score가 NULL이 아닌 행 수와 전체 행 수를 차례대로 구해 줘.'
    reversed_answer=verify_answer(p,'{"sql":"SELECT COUNT(score),COUNT(*) FROM exam_result"}',p['raw_text'])
    assert reversed_answer['status']=='verified' and reversed_answer['result']['rows']==[[2,3]]
    wrong=verify_answer(p,'{"sql":"SELECT COUNT(*),COUNT(score) FROM exam_result"}',p['raw_text'])
    assert wrong['status']=='stopped'


def test_filtered_or_rounded_request_is_not_claimed_as_unfiltered_aggregate():
    p=problem('write_sql')
    # These human-readable filters need confirmation in the bounded app
    # grammar. Do not mislabel that as acceptance of the unfiltered candidate.
    for question,sql,reason in [
        ('가의 점수 평균을 구해 줘.','SELECT AVG(score) FROM exam_result','특정 행 값'),
        ('score가 90보다 큰 사람 수를 구해 줘.','SELECT COUNT(score) FROM exam_result','숫자·비교 조건')]:
        p['raw_text']=question
        unresolved=verify_answer(p,json.dumps({'sql':sql}),question)
        assert unresolved['status']==unresolved['support_status']==unresolved['intent']['status']=='needs_input'
        assert unresolved['execution']['status']=='not_run' and unresolved['result'] is None
        assert unresolved['logical_steps'] is None and unresolved['can_repair'] is False
        assert reason in unresolved['intent']['scope']
        lesson=generate_verified_plan({'id':'unresolved-filter','problem':p,'evidence':unresolved,
            'content':display_answer(unresolved)},question,'unresolved-filter-lesson')
        assert lesson['plan'] is None and lesson['speech_allowed'] is False
    p['raw_text']='score 평균을 반올림해 줘.'
    rounded=verify_answer(p,'{"sql":"SELECT AVG(score) FROM exam_result"}',p['raw_text'])
    assert rounded['status']=='stopped' and rounded['intent']['status']=='unsupported'
    assert rounded['support_status']=='unsupported_intent' and rounded['execution']['status']=='executed'
    assert rounded['result'] is None and rounded['logical_steps'] is None and rounded['can_repair'] is False


def test_alias_and_cte_are_not_reported_unknown_identifiers():
    p=problem();p["query"]="WITH x AS (SELECT score FROM exam_result) SELECT COUNT(*) AS n FROM x"
    e=verify_answer(p,"raw",p["raw_text"])
    assert e["status"]=="verified" and e["schema"]["status"]=="resolved_by_sqlite_prepare"
    assert e["calculation"]["status"]=="outside_supported_trace" and e["result"]["rows"]==[[3]]
    p["query"]="SELECT COUNT(e.score) AS n FROM exam_result AS e"
    assert verify_answer(p,"raw",p["raw_text"])["calculation"]["status"]=="independent_aggregate_match"


def test_group_where_having_trace_and_average_share_input():
    p=problem();p["tables"][0]["columns"].append({"name":"team","type":"TEXT"})
    p["tables"][0]["rows"]=[["가",80,"A"],["나",None,"A"],["다",100,"B"],["라",30,"B"]]
    p["query"]="SELECT team,COUNT(*),SUM(score),AVG(score) FROM exam_result WHERE score IS NULL OR score >= 50 GROUP BY team HAVING COUNT(*)>=2"
    e=verify_answer(p,"raw",p["raw_text"]);trace=e["logical_steps"]
    assert e["result"]["rows"]==[["A",2,80,80.0]]
    assert len(trace["filtered_row_ids"])==3 and len(trace["groups"])==2
    assert len(trace["before_having"]["rows"])==2
    assert trace["kind"]=="logical_teaching_steps_not_physical_execution"
    plan=generate_verified_plan({"id":"m","problem":p,"evidence":e,"content":display_answer(e)},"그룹 설명","l")["plan"]
    assert len(plan["steps"])==4


def test_hypothesis_preserves_original_and_has_separate_cell_ids():
    p=problem(); h=hypothesis_from_question(p,"그럼 셋 다 점수가 없으면?")
    e=verify_answer(p,"raw","모두 NULL이면?",h)
    assert p["tables"][0]["rows"][0][1]==80 and e["original_tables"][0]["rows"][0][1]==80
    assert e["working_tables"][0]["rows"][0][1] is None and e["result"]["rows"]==[[3,0]]
    assert e["original_tables"][0]["id"]!=e["working_tables"][0]["id"]


def test_missing_conditions_and_other_dbms_cannot_become_numbers():
    p=from_text("이 SQL 결과 몇이야?");e=verify_answer(p,"3입니다",p["raw_text"])
    assert e["status"]=="needs_input" and e["execution"]["status"]=="not_run"
    p=problem();p["dialect"]="oracle"
    e=verify_answer(p,"맞습니다",p["raw_text"])
    assert e["status"]=="unsupported" and "SQLite" in display_answer(e)
    missing=from_text("COUNT(*)와 COUNT(score)는 각각 얼마야?")
    assert missing['task_kind']=='query_result'
    assert verify_answer(missing,'3과 2입니다',missing['raw_text'])['status']=='needs_input'
    assert from_text('COUNT(*)는 무슨 뜻이야?')['task_kind']=='concept'


@pytest.mark.parametrize('phrase,dialect',[
    ('Oracle에서','oracle'),('MySQL은','mysql'),('PostgreSQL의','postgresql'),('SQLite에서','sqlite'),
    ('oracle에서는','oracle'),('PostgreSQL에서','postgresql'),
])
def test_dbms_name_with_korean_particle_survives_text_and_photo_projection(phrase,dialect):
    question=phrase+' 이 SQL 결과 몇이야?'
    assert from_text(question)['dialect']==dialect
    p=problem()
    photo={'id':'dbms-fixture','question':question,'sql':p['query'],'tables':p['tables'],
           'revision':2,'confirmed':True,'missing_conditions':[]}
    projected=from_photo(photo)
    assert projected['dialect']==dialect and projected['revision']==2
    assert projected['source']=={'kind':'photo','photo_id':'dbms-fixture'}
    if dialect!='sqlite':
        evidence=verify_answer(projected,'unsupported model number 99',question)
        assert evidence['status']=='unsupported' and evidence['execution']['status']=='not_run'


@pytest.mark.parametrize('identifier',['OracleClient','MySQL_data','PostgreSQL2','xOracle','1MySQL'])
def test_dbms_name_does_not_match_ascii_identifier_substrings(identifier):
    assert from_text(identifier+'의 결과 몇이야?')['dialect']=='sqlite'


def test_explicit_structured_dialect_is_not_reinferred_from_question():
    p=problem();p.update(dialect='postgresql',raw_text='Oracle에서와 SQLite에서의 차이를 비교해 줘.')
    normalized=normalize_problem(p)
    assert normalized['dialect']=='postgresql'
    assert '"dialect":"postgresql"' in model_messages(p['raw_text'],normalized,[])[1]['content']


def test_rag_excerpt_does_not_replace_original_and_oracle_fields_forbidden():
    p=problem();msgs=model_messages(p["raw_text"],p,[{"chunk_id":"c","text":"other(grade) "*500}])
    assert 'exam_result' in msgs[-1]["content"] and 'grade' not in msgs[-1]["content"]
    assert len(msgs[0]["content"])<1500
    with pytest.raises(ValueError):normalize_problem({**p,"expected_rows":[[3,2]]})


def test_task_specific_concept_prompt_does_not_request_sql_answer_json():
    for question in ('DDL이 뭐였지? 사람 추가와 칸 추가가 헷갈려.', 'INSERT와 ALTER는 어떻게 달라?'):
        p=from_text(question)
        system=model_messages(question,p,[])[0]['content']
        assert '평문' in system and 'sql 코드 블록' in system
        assert 'CREATE TABLE' in system and '설명용 새 예시' in system
        assert '생략부호' in system and 'SELECT ...' not in system and 'JSON' not in system
    # Both SQL task formats keep their answer contract after the explicit
    # finish-v2 concise-first-answer instruction (not a model accuracy test).
    for kind in ('query_result','write_sql'):
        p=from_text('DDL과 INSERT의 차이?');p['task_kind']=kind
        system=model_messages(p['raw_text'],p,[])[0]['content']
        assert hashlib.sha256(system.encode()).hexdigest()=='d4990ac4429fcf741f68eadd6d510b489e9dd39deeecc2452be4c1869a72cbb6'
        assert 'JSON {"sql"' in system


def test_ocr_structure_preserves_actual_text_and_requires_explicit_schema():
    text="exam_result(name TEXT, score INTEGER)\n| name | score |\n| 가 | 80 |\n| 나 | NULL |\nSELECT AVG(score) FROM exam_result;"
    result=structure_candidate({"original_text":text,"question":text})
    assert result["original_text"]==text and result["tables"][0]["rows"]==[["가",80],["나",None]]
    assert result["structure_extraction"]["accuracy"]=="not_established"
    assert structure_candidate({"original_text":"가 80 나 NULL"}).get("tables",[])==[]


def test_concept_example_speech_uses_executed_changes_not_model_free_prose():
    p=from_text('DDL과 INSERT의 차이?')
    raw="잘못된 자유 문장 999.\n```sql\nCREATE TABLE people (name TEXT); INSERT INTO people VALUES ('Kim'); ALTER TABLE people ADD COLUMN score INTEGER;\n```"
    m={'id':'m','problem':p,'evidence':verify_answer(p,raw,p['raw_text']),'content':raw,'raw_model_response':raw}
    result=concept_plan(m,p['raw_text'],'l')
    assert result['status']=='verified_example_plan' and result['speech_allowed']
    assert len(result['plan']['steps'])==3
    assert '999' not in ''.join(s['speech'] for s in result['plan']['steps'])
    assert result['example_evidence']['free_prose_verification']=='not_verified'
    assert '실행 전' in str(result['plan']) and '실행 후' in str(result['plan'])
    m.update(content='일반 설명만 있습니다.',raw_model_response='일반 설명만 있습니다.')
    assert not concept_plan(m,p['raw_text'],'l2')['speech_allowed']


BAD_EXAMPLE="설명용 새 예시:\n```sql\nCREATE TABLE people (name TEXT, score INTEGER); INSERT INTO people VALUES ('Alice', 95); ALTER TABLE people ADD COLUMN score INTEGER;\n```"
ACTUAL_BARE_EXAMPLE="핵심 답: INSERT INTO ... VALUES는 기존 명단에 새 사람을 추가하고, ALTER TABLE ADD COLUMN은 점수 열을 추가합니다.\n\n설명용 새 예시:\n```\nCREATE TABLE people (name TEXT, score INTEGER);\nINSERT INTO people VALUES ('Alice', 95);\nALTER TABLE people ADD COLUMN score INTEGER;\n```"
REPAIRED_EXAMPLE="```sql\nCREATE TABLE people (name TEXT); INSERT INTO people VALUES ('Alice'); ALTER TABLE people ADD COLUMN score INTEGER;\n```"


@pytest.mark.parametrize('raw',[BAD_EXAMPLE,ACTUAL_BARE_EXAMPLE])
def test_failed_concept_sql_is_audit_only_and_never_a_teaching_board(raw):
    p=from_text('INSERT와 ALTER는 어떻게 달라?')
    message={'id':'failed-example','problem':p,'content':raw,'raw_model_response':raw}
    result=concept_plan(message,p['raw_text'],'failed-lesson')
    assert result['plan'] is None and result['status']=='verification_stopped'
    assert not result['speech_allowed'] and 'duplicate column' in result['reason']
    assert result['fallback_text']==raw
    assert result['example_evidence']['steps']==[]
    assert len(result['example_evidence']['partial_steps_audit_only'])==2


@pytest.fixture
def client(tmp_path):
    app=create_app(tmp_path)
    token=(tmp_path/'.local/auth-token').read_text()
    with TestClient(app,base_url="http://127.0.0.1:8000",headers={"Authorization":"Bearer "+token}) as c:yield c


def wait(client,ident):
    for _ in range(800):
        job=client.get('/api/jobs/'+ident).json()
        if job['state'] in {'succeeded','failed','blocked','cancelled','interrupted'}:return job
        time.sleep(.01)
    raise AssertionError('job timeout')


def answer(client,content,p=None,**extra):
    session=client.post('/api/sessions',json={}).json()
    body={"content":content,**extra}
    if p:body['problem']=p
    response=client.post(f"/api/sessions/{session['id']}/messages",json=body)
    assert response.status_code==202,response.text
    job=wait(client,response.json()['job_id']);assert job['state']=='succeeded',job
    msg=next(m for m in client.get(f"/api/sessions/{session['id']}/messages").json() if m['id']==job['result']['message_id'])
    return session,msg


def make_lesson(client,session,msg):
    lesson=client.post('/api/lessons',json={'session_id':session['id'],'message_id':msg['id']}).json()
    job=client.post(f"/api/lessons/{lesson['id']}/generate").json()
    assert wait(client,job['job_id'])['state']=='succeeded'
    return client.get('/api/lessons/'+lesson['id']).json()


@pytest.mark.parametrize('raw',[BAD_EXAMPLE,ACTUAL_BARE_EXAMPLE])
def test_concept_repair_is_once_per_source_and_preserves_original_answer(client,monkeypatch,raw):
    import edu_tutor.models.runtime as runtime
    calls=[]
    def fake(messages,**kwargs):
        calls.append({'messages':messages,'adapter':kwargs['adapter'],'max_new_tokens':kwargs.get('max_new_tokens')})
        kwargs['metadata_out'].update(finish_reason='eos',adapter_id='base',model_id='actual-fixture',revision='pinned-fixture')
        yield raw if len(calls)==1 else REPAIRED_EXAMPLE
    monkeypatch.setattr(runtime,'generate',fake)
    question='기존 명단의 INSERT와 점수 열을 만드는 ALTER는 어떻게 달라?'
    session,msg=answer(client,question)
    lesson=make_lesson(client,session,msg)
    assert len(calls)==2 and calls[1]['adapter']=='base' and calls[1]['max_new_tokens']==384
    submitted=json.loads(calls[1]['messages'][1]['content'])
    assert submitted['original_question']==question and submitted['raw_candidate']==raw
    assert 'duplicate column' in submitted['actual_execution_error']
    assert 'Alice' not in calls[1]['messages'][0]['content']
    assert lesson['status']=='verified_example_plan' and lesson['speech_allowed']
    assert len(lesson['plan']['steps'])==3 and lesson['fallback_text']==raw
    attempts=lesson['generation']['example_model_attempts']
    assert len(attempts)==2 and attempts[0]['text']==raw and attempts[1]['text']==REPAIRED_EXAMPLE
    assert attempts[0]['check_result']['status']=='blocked' and attempts[1]['check_result']['status']=='verified'
    assert attempts[1]['generation_snapshot']['revision']=='pinned-fixture'
    repeated=client.post('/api/lessons/'+lesson['id']+'/generate').json()
    assert wait(client,repeated['job_id'])['state']=='succeeded'
    second=make_lesson(client,session,msg)
    assert second['status']=='verified_example_plan' and len(calls)==2
    assert second['generation']['repair_model_calls_this_generation']==0
    saved=next(m for m in client.get('/api/sessions/'+session['id']+'/messages').json() if m['id']==msg['id'])
    assert saved==msg


@pytest.mark.parametrize('repair_outcome',['same_error','no_sql','truncated','wrong_adapter'])
def test_invalid_concept_repair_stops_without_another_attempt(client,monkeypatch,repair_outcome):
    import edu_tutor.models.runtime as runtime
    calls=[]
    def fake(messages,**kwargs):
        calls.append(messages)
        kwargs['metadata_out'].update(finish_reason='eos',adapter_id='base')
        if len(calls)==1:
            yield BAD_EXAMPLE
        else:
            if repair_outcome=='wrong_adapter':kwargs['metadata_out']['adapter_id']='different-adapter'
            yield '일반 설명만 있음' if repair_outcome=='no_sql' else BAD_EXAMPLE if repair_outcome=='same_error' else REPAIRED_EXAMPLE
            if repair_outcome=='truncated':
                kwargs['metadata_out']['finish_reason']='length'
                raise runtime.GenerationIncomplete('truncated fixture')
    monkeypatch.setattr(runtime,'generate',fake)
    session,msg=answer(client,'INSERT와 ALTER는 어떻게 달라?')
    first=make_lesson(client,session,msg)
    assert first['plan'] is None and not first['speech_allowed']
    assert first['generation']['example_model_attempts'][1]['accepted'] is False
    assert first['generation']['raw_repair_response']
    second=make_lesson(client,session,msg)
    assert len(calls)==2 and second['plan'] is None and not second['speech_allowed']
    assert client.post('/api/lessons/'+second['id']+'/speech',json={}).status_code==409


def test_concept_without_sql_does_not_trigger_example_repair(client,monkeypatch):
    import edu_tutor.models.runtime as runtime
    calls=[]
    def fake(messages,**kwargs):
        calls.append(messages);kwargs['metadata_out'].update(finish_reason='eos',adapter_id='base')
        yield 'INSERT는 행을 추가하고 ALTER는 표 구조를 바꿉니다.'
    monkeypatch.setattr(runtime,'generate',fake)
    session,msg=answer(client,'INSERT와 ALTER는 어떻게 달라?')
    lesson=make_lesson(client,session,msg)
    assert len(calls)==1 and not lesson['speech_allowed']
    assert lesson['example_evidence']['status']=='not_available'


def test_cancelled_concept_repair_keeps_partial_audit_and_consumes_one_attempt(client,monkeypatch):
    import edu_tutor.models.runtime as runtime
    calls=[];entered=threading.Event();release=threading.Event()
    def fake(messages,**kwargs):
        calls.append(messages)
        kwargs['metadata_out'].update(finish_reason='eos',adapter_id='base')
        if len(calls)==1:
            yield BAD_EXAMPLE
        else:
            yield REPAIRED_EXAMPLE
            entered.set();release.wait(3)
    monkeypatch.setattr(runtime,'generate',fake)
    session,msg=answer(client,'INSERT와 ALTER는 어떻게 달라?')
    lesson=client.post('/api/lessons',json={'session_id':session['id'],'message_id':msg['id']}).json()
    job=client.post('/api/lessons/'+lesson['id']+'/generate').json()
    assert entered.wait(2)
    try:
        pending=client.get('/api/lessons/'+lesson['id']).json()
        assert pending['plan'] is None and not pending['speech_allowed']
        # A second lesson for the same answer cannot race into another model call.
        concurrent=make_lesson(client,session,msg)
        assert len(calls)==2 and concurrent['plan'] is None
        client.post('/api/jobs/'+job['job_id']+'/cancel')
    finally:
        release.set()
    assert wait(client,job['job_id'])['state']=='cancelled'
    cancelled=client.get('/api/lessons/'+lesson['id']).json()
    assert cancelled['generation']['raw_repair_response']==REPAIRED_EXAMPLE
    assert cancelled['generation']['example_repair_state']=='cancelled'
    again=make_lesson(client,session,msg)
    assert len(calls)==2 and again['plan'] is None and not again['speech_allowed']


def test_actual_candidate_fixture_saved_separately_and_one_repair_only(client,monkeypatch):
    import edu_tutor.models.runtime as runtime
    calls=[]
    def fake(messages,**kwargs):
        calls.append(messages);kwargs['metadata_out'].update(finish_reason='eos')
        return iter(['{"sql":"SELECT COUNT(absent) FROM exam_result"}'])
    monkeypatch.setattr(runtime,'generate',fake)
    p=problem('write_sql');p['raw_text']='점수가 있는 사람 수를 구해 줘.'
    session,msg=answer(client,p['raw_text'],p)
    assert len(calls)==2 and len(msg['model_attempts'])==2
    assert msg['raw_model_response']=='{"sql":"SELECT COUNT(absent) FROM exam_result"}'
    assert msg['evidence']['status']=='stopped' and '확인 필요' in msg['content']
    lesson=make_lesson(client,session,msg)
    assert lesson['plan'] is None and not lesson['speech_allowed']
    assert client.post('/api/lessons/'+lesson['id']+'/speech',json={}).status_code==409


def test_confirmed_aggregate_model_error_uses_separate_app_calculation_without_retry(client,monkeypatch):
    import edu_tutor.models.runtime as runtime
    calls=[]
    raw='{"sql":"SELECT COUNT(*) FROM exam_result","explanation":"NULL인 사람만 셉니다."}'
    def fake(messages,**kwargs):
        calls.append(messages);kwargs['metadata_out'].update(finish_reason='eos')
        return iter([raw])
    monkeypatch.setattr(runtime,'generate',fake)
    p=problem('write_sql');p['raw_text']='점수가 있는 사람 수를 구해 줘.'
    session,msg=answer(client,p['raw_text'],p)
    assert len(calls)==1 and len(msg['model_attempts'])==1
    assert msg['raw_model_response']==raw
    assert msg['evidence']['app_correction']['original_candidate']['intent']['status']=='mismatch'
    assert msg['evidence']['result']['rows']==[[2]] and msg['provenance']=='tool_derived'
    lesson=make_lesson(client,session,msg)
    assert lesson['speech_allowed'] and lesson['plan']
    speech=' '.join(s['speech'] for s in lesson['plan']['steps'])
    assert 'NULL인 사람만' not in speech and '2' in speech


def test_tool_query_and_two_supplemental_questions_keep_original(client,monkeypatch):
    import edu_tutor.models.runtime as runtime
    monkeypatch.setattr(runtime,'generate',lambda *a,**kw:iter(['잘못된 원시 숫자 99']))
    p=problem();session,msg=answer(client,p['raw_text'],p);lesson=make_lesson(client,session,msg)
    table=msg['evidence']['original_tables'][0]
    context={'lesson_id':lesson['id'],'problem_revision':1,'step':0,'selected_cell':{'column_name':'score','cell_id':table['cell_ids'][1][1]}}
    original=copy.deepcopy(lesson['plan'])
    for question,expected in [('점수가 없는데 왜 사람 수에는 들어가?',[[3,2]]),('그럼 셋 다 점수가 없으면?',[[3,0]])]:
        sub=client.post(f"/api/sessions/{session['id']}/messages",json={'content':question,'lesson_context':context}).json()
        job=wait(client,sub['job_id']);assert job['state']=='succeeded',job
        msg=next(m for m in client.get(f"/api/sessions/{session['id']}/messages").json() if m['id']==job['result']['message_id'])
        assert msg['evidence']['result']['rows']==expected
        supplement=make_lesson(client,session,msg)
        assert len(supplement['plan']['steps'])==1
        speech=supplement['plan']['steps'][0]['speech']
        assert len(speech)<=60 and '점수 값' in speech and '3개' in speech
        assert ('2개' if expected==[[3,2]] else '0개') in speech
        context['lesson_id']=supplement['id']
    assert client.get('/api/lessons/'+lesson['id']).json()['plan']==original


def test_photo_revision_invalidates_plan_voice_and_new_calculation(client,monkeypatch):
    import edu_tutor.models.runtime as runtime
    monkeypatch.setattr(runtime,'generate',lambda *a,**kw:iter(['raw']))
    buf=io.BytesIO();Image.new('RGB',(20,20),'white').save(buf,'PNG')
    photo=client.post('/api/photos',files={'file':('test.png',buf.getvalue(),'image/png')}).json()
    p=problem();p['query']='SELECT AVG(score) FROM exam_result'
    path='/api/photos/'+photo['id']
    client.patch(path,json={'question':'주어진 SQL의 결과는?','sql':p['query'],'tables':p['tables']});client.post(path+'/confirm')
    session=client.post('/api/sessions',json={}).json()
    job=wait(client,client.post(path+'/solve',json={'session_id':session['id']}).json()['job_id'])
    msg=next(m for m in client.get(f"/api/sessions/{session['id']}/messages").json() if m['id']==job['result']['message_id'])
    assert msg['evidence']['result']['rows']==[[90.0]]
    lesson=make_lesson(client,session,msg)
    p['tables'][0]['rows'][0][1]=20
    client.patch(path,json={'tables':p['tables']});client.post(path+'/confirm')
    invalid=client.get('/api/lessons/'+lesson['id']).json()
    assert invalid['valid'] is False and invalid['audio_steps']==[]
    assert client.post('/api/lessons/'+lesson['id']+'/speech',json={}).status_code==409
    job=wait(client,client.post(path+'/solve',json={'session_id':session['id']}).json()['job_id'])
    msg=next(m for m in client.get(f"/api/sessions/{session['id']}/messages").json() if m['id']==job['result']['message_id'])
    assert msg['evidence']['result']['rows']==[[60.0]]


@pytest.mark.parametrize('state',['current','edited','reconfirmed','unconfirmed','deleted'])
def test_photo_answer_validity_is_read_only_and_stale_answer_cannot_create_lesson(client,monkeypatch,state):
    import edu_tutor.models.runtime as runtime
    monkeypatch.setattr(runtime,'generate',lambda *a,**kw:iter(['original model answer']))
    buf=io.BytesIO();Image.new('RGB',(20,20),'white').save(buf,'PNG')
    photo=client.post('/api/photos',files={'file':('source.png',buf.getvalue(),'image/png')}).json()
    path='/api/photos/'+photo['id'];p=problem()
    client.patch(path,json={'question':'주어진 SQL의 결과는?','sql':p['query'],'tables':p['tables']})
    confirmed=client.post(path+'/confirm').json()
    session=client.post('/api/sessions',json={}).json()
    job=wait(client,client.post(path+'/solve',json={'session_id':session['id']}).json()['job_id'])
    assert job['state']=='succeeded'
    message_id=job['result']['message_id'];store=client.app.state.store
    original=copy.deepcopy(store.get('messages',message_id))
    if state in {'edited','reconfirmed'}:
        p['tables'][0]['rows'][0][1]=20
        client.patch(path,json={'tables':p['tables']})
        if state=='reconfirmed':client.post(path+'/confirm')
    elif state=='unconfirmed':
        # Check confirmation independently of revision, including recovered records.
        unconfirmed=store.get('photos',photo['id']);unconfirmed['confirmed']=False
        store.put('photos',unconfirmed)
    elif state=='deleted':
        assert client.delete(path).status_code==200
    shown=next(m for m in client.get('/api/sessions/'+session['id']+'/messages').json() if m['id']==message_id)
    assert shown['valid'] is (state=='current')
    expected_revision=None if state=='deleted' else confirmed['revision']+(1 if state in {'edited','reconfirmed'} else 0)
    assert shown['current_problem_revision']==expected_revision
    assert shown['content']==original['content'] and shown['raw_model_response']==original['raw_model_response']
    before_count=len(store.list('lessons'))
    created=client.post('/api/lessons',json={'session_id':session['id'],'message_id':message_id})
    if state=='current':
        assert created.status_code==201
    else:
        assert shown['invalidated_reason'] and created.status_code==409
        assert len(store.list('lessons'))==before_count
    assert store.get('messages',message_id)==original


def test_other_session_inference_busy_does_not_save_rejected_user_message(client,monkeypatch):
    import edu_tutor.models.runtime as runtime
    entered=threading.Event();release=threading.Event()
    def fake(*args,**kwargs):
        entered.set();release.wait(3);yield '개념 설명'
    monkeypatch.setattr(runtime,'generate',fake)
    one=client.post('/api/sessions',json={}).json();two=client.post('/api/sessions',json={}).json()
    job=client.post('/api/sessions/'+one['id']+'/messages',json={'content':'DDL이 뭐야?'}).json()
    assert entered.wait(2)
    rejected=client.post('/api/sessions/'+two['id']+'/messages',json={'content':'보존할 질문'})
    assert rejected.status_code==409 and client.get('/api/sessions/'+two['id']+'/messages').json()==[]
    release.set();assert wait(client,job['job_id'])['state']=='succeeded'


def test_failed_demo_and_legacy_plan_are_preserved_but_not_spoken_or_regenerated(client):
    demo=client.get('/api/lessons/demo').json()
    demo['plan']['steps'][-1]['board_actions'][-1]['rows'][0][-1]=999
    client.app.state.store.put('lessons',demo)
    assert client.post('/api/lessons/'+demo['id']+'/speech',json={}).status_code==409
    old={'id':'historical-lesson','is_demo':False,'plan':copy.deepcopy(demo['plan']),'source_message_id':'unknown','status':'structured_unverified'}
    client.app.state.store.put('lessons',old)
    result=client.get('/api/lessons/historical-lesson').json()
    assert result['valid'] is False and result['plan']==old['plan']
    assert client.post('/api/lessons/historical-lesson/generate').status_code==409
    assert client.post('/api/lessons/historical-lesson/speech',json={}).status_code==409
    assert client.app.state.store.get('lessons',old['id'])==old


def test_photo_source_cannot_be_forged_as_typed_input(client):
    p=problem();p['source']={'kind':'photo','photo_id':'unconfirmed-source'}
    session=client.post('/api/sessions',json={}).json()
    response=client.post('/api/sessions/'+session['id']+'/messages',json={'content':'풀이','problem':p})
    assert response.status_code==422
    assert client.get('/api/sessions/'+session['id']+'/messages').json()==[]
    with pytest.raises(ValueError):normalize_problem({**p,'source':{'kind':'photo'}})
    with pytest.raises(ValueError):normalize_problem({**p,'source':{'kind':'typed','photo_id':'p'}})


def test_doctor_navigation_uses_recorded_report_without_cuda_probe(client,monkeypatch):
    import edu_tutor.doctor as doctor
    def forbidden(*args,**kwargs):raise AssertionError('ordinary navigation probed CUDA')
    monkeypatch.setattr(doctor,'collect_doctor',forbidden)
    root=client.app.state.store.root
    folder=root/'runs/environment';folder.mkdir(parents=True)
    report={'project_root':str(root),'timestamp':'2026-01-01T00:00:00Z','gpu':[{'free_mib':123}], 'cuda':{'available':True}}
    (folder/'startup-doctor.json').write_text(json.dumps(report))
    response=client.get('/api/doctor').json()
    assert response['cached'] and response['recorded_at']==report['timestamp']
    assert '현재값' in response['cache_notice'] and response['gpu']==report['gpu']


def test_explicit_doctor_refresh_uses_shared_queue_and_preserves_cached_time(client,monkeypatch):
    import edu_tutor.doctor as doctor
    root=client.app.state.store.root
    monkeypatch.setattr(doctor,'collect_doctor',lambda **kwargs:{'project_root':str(root),'timestamp':'2026-10-26T00:00:00Z','gpu':[],'cuda':None})
    sub=client.post('/api/doctor/refresh');assert sub.status_code==202
    assert wait(client,sub.json()['job_id'])['state']=='succeeded'
    assert client.get('/api/doctor').json()['recorded_at']=='2026-10-26T00:00:00Z'
