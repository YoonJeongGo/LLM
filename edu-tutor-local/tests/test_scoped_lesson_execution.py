"""A denied repair must retain the original failed answer and never speak it."""
from test_phase2_backend import client, problem, answer, make_lesson


def test_single_call_grant_stops_repair_but_preserves_raw_answer(client, monkeypatch):
    from edu_tutor.models import runtime, budget
    calls = []
    # Unknown schema cannot use the new independently derived aggregate path.
    raw = '{"sql":"SELECT COUNT(absent) FROM exam_result"}'

    def fake(messages, **kwargs):
        calls.append(messages)
        kwargs['metadata_out'].update(finish_reason='eos')
        return iter([raw])

    monkeypatch.setattr(runtime, 'generate', fake)
    monkeypatch.setattr(budget, 'status', lambda _: {
        'active_execution_allowance': {'text_remaining': 0, 'seconds_remaining': 800}})
    p = problem('write_sql')
    p['raw_text'] = '점수가 있는 사람 수를 구해 줘.'
    session, msg = answer(client, p['raw_text'], p)
    assert len(calls) == 1 and len(msg['model_attempts']) == 1
    assert msg['raw_model_response'] == raw
    assert msg['evidence']['status'] == 'stopped'
    assert msg['evidence']['repair_skipped'] == 'explicit_execution_allowance_exhausted'
    lesson = make_lesson(client, session, msg)
    assert lesson['plan'] is None and not lesson['speech_allowed']
    assert client.post('/api/lessons/'+lesson['id']+'/speech', json={}).status_code == 409


def test_confirmed_app_calculation_needs_no_extra_model_allowance(client, monkeypatch):
    from edu_tutor.models import runtime, budget
    calls=[]
    raw='{"sql":"SELECT COUNT(*) FROM exam_result"}'
    def fake(messages, **kwargs):
        calls.append(messages)
        kwargs['metadata_out'].update(finish_reason='eos')
        return iter([raw])
    monkeypatch.setattr(runtime,'generate',fake)
    monkeypatch.setattr(budget,'status',lambda _: {'active_execution_allowance':{'text_remaining':0,'seconds_remaining':0}})
    p=problem('write_sql');p['raw_text']='점수가 있는 사람 수를 구해 줘.'
    _,msg=answer(client,p['raw_text'],p)
    assert len(calls)==1 and msg['raw_model_response']==raw
    assert msg['evidence']['app_correction']['new_model_calls']==0
    assert msg['evidence']['app_correction']['original_candidate']['intent']['status']=='mismatch'
    assert msg['evidence']['result']['rows']==[[2]]
