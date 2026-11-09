"""Report binding must not silently accept changed playback data."""
import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from finish_binding_evidence import binding_evidence, equivalent, fingerprint

def fixture():
    server={'id':'lesson-a','plan':{'steps':[{'id':'s1','speech':'평균은 6.0입니다.',
        'board_actions':[{'rows':[[18,6.0]]}]}]},'problem':{'rows':[[12],[6],[0]]},
        'generation_epoch':1,'source_message_id':'answer-a','speech_allowed':True,'fallback_text':None}
    captured=copy.deepcopy(server);captured['plan']['steps'][0]['board_actions'][0]['rows'][0][1]=6
    hashed=fingerprint(server);captured['speech_binding_fingerprint']=hashed
    event={'lesson_record_id':'lesson-a','step_id':'s1','at_iso':'2026-10-29T00:00:03Z'}
    response={'at':'2026-10-29T00:00:01Z','method':'GET','status':200,'path':'/api/lessons/lesson-a/speech',
        'value':{'binding_fingerprint':hashed,'steps':[{'audio_id':'audio-a','step_id':'s1','binding_fingerprint':hashed}]}}
    # A later generic lesson summary lacks the speech-endpoint binding.
    summary={'at':'2026-10-29T00:00:02Z','status':200,'path':'/api/lessons/lesson-a',
        'value':{'audio_steps':[{'audio_id':'audio-a','step_id':'s1'}]}}
    return {'responses':[response,summary]},server,captured,event

def test_exact_server_binding_with_browser_integral_float_and_later_unbound_summary():
    record,server,captured,event=fixture()
    evidence=binding_evidence(record,server,captured,event,'audio-a')
    assert evidence['pass']
    assert len(evidence['representation_differences'])==1
    assert evidence['binding_response']['at']=='2026-10-29T00:00:01Z'

@pytest.mark.parametrize('kind',['number','fraction','speech','bool','server_change','captured_hash',
    'future','wrong_lesson','wrong_step','latest_bad_binding','missing_binding','bad_status'])
def test_rejects_changed_or_unbound_data(kind):
    record,server,captured,event=fixture();response=record['responses'][0]
    if kind=='number':captured['plan']['steps'][0]['board_actions'][0]['rows'][0][1]=7
    elif kind=='fraction':captured['plan']['steps'][0]['board_actions'][0]['rows'][0][1]=6.5
    elif kind=='speech':captured['plan']['steps'][0]['speech']='다른 대사'
    elif kind=='bool':captured['generation_epoch']=True
    elif kind=='server_change':server['problem']['rows'][0][0]=13
    elif kind=='captured_hash':captured['speech_binding_fingerprint']='x'*64
    elif kind=='future':response['at']='2026-10-29T00:00:04Z'
    elif kind=='wrong_lesson':response['path']='/api/lessons/lesson-b/speech'
    elif kind=='wrong_step':response['value']['steps'][0]['step_id']='s2'
    elif kind=='missing_binding':response['value'].pop('binding_fingerprint')
    elif kind=='bad_status':response['status']=409
    elif kind=='latest_bad_binding':
        bad=copy.deepcopy(response);bad['at']='2026-10-29T00:00:02Z'
        bad['value']['binding_fingerprint']='x'*64
        bad['value']['steps'][0]['binding_fingerprint']='x'*64
        record['responses'].append(bad)
    assert not binding_evidence(record,server,captured,event,'audio-a')['pass']

@pytest.mark.parametrize('server,browser,expected',[(6.0,6,True),(6.5,6,False),(True,1,False),
    (6.0,'6',False),(float('inf'),1,False),(-0.0,0,False),(float(2**53),2**53,False),
    ([6.0],[6,7],False),({'x':6.0},{'y':6},False)])
def test_type_normalization_is_narrow(server,browser,expected):
    assert equivalent(server,browser)[0] is expected
