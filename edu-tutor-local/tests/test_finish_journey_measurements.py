"""Synthetic clock events only; these tests are not measured student latency."""
import importlib.util
from pathlib import Path
import sys
import copy
import io
import wave
import json
import subprocess
import pytest


SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('finish_collect_journeys',SCRIPTS/'finish_collect_journeys.py')
collector=importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def test_stop_timing_requires_native_pause_for_the_interrupted_lesson():
    media={'media_id':1,'epoch':2,'current_src':'blob:original'}
    record={'native_media':[{'type':'pause','at_ms':95,'lesson_id':'original',**media},
                            {'type':'pause','at_ms':102,'lesson_id':'other',**media},
                            {'type':'pause','at_ms':107,'lesson_id':'original',**media}]}
    timing={'interruptions':[{'submission_event':{'at_ms':100,'lesson_record_id':'original'},
                              'old_audio_stopped_ms':0.2}]}
    timing['interruptions'][0]['submission_event']['media']=media
    row=collector.native_interruptions(record,timing)['interruptions'][0]
    assert row['old_audio_stopped_ms']==7 and row['old_audio_stop_evidence']=='native_media_pause_event'


def test_missing_native_pause_does_not_turn_synchronous_property_into_measured_stop():
    timing={'interruptions':[{'submission_event':{'at_ms':100,'lesson_record_id':'original'},
                             'old_audio_stopped_ms':0.2,'synchronous_paused_property_ms':0.2}]}
    row=collector.native_interruptions({'native_media':[]},timing)['interruptions'][0]
    assert row['old_audio_stopped_ms'] is None
    assert row['synchronous_paused_property_ms']==0.2


def test_unmeasured_failures_are_not_zero_milliseconds_in_measured_statistics():
    rows=[None,100,300,None]
    assert collector.measured_stats(rows)=={'measured_count':2,'median_ms':200,'max_ms':300}
    assert len(rows)==4
    assert collector.measured_stats([None])['median_ms'] is None


def test_pause_after_resume_is_not_the_interrupt_stop():
    media={'media_id':1,'epoch':2,'current_src':'blob:original'}
    submitted={'at_ms':100,'lesson_record_id':'original','media':media}
    record={'events':[{'type':'lesson_resumed','lesson_record_id':'original','at_ms':200}],
            'native_media':[{'type':'pause','at_ms':900,'lesson_id':'original',**media}]}
    row=collector.native_interruptions(record,{'interruptions':[{'submission_event':submitted}]})['interruptions'][0]
    assert row['old_audio_stopped_ms'] is None


@pytest.mark.parametrize('ending',[False,None])
def test_changed_or_unrecorded_final_source_freeze_is_rejected(ending):
    with pytest.raises(ValueError,match='Mixed execution'):
        collector.assert_frozen_record({'version':'v1','source_hashes':{'x':'a'},'source_unchanged_at_end':ending},{'source_hashes':{'x':'a'}},'v1')


def test_changed_fixed_source_is_rejected_even_if_record_claims_unchanged():
    with pytest.raises(ValueError,match='Mixed execution'):
        collector.assert_frozen_record({'version':'v1','source_hashes':{'runtime.py':'changed'},'source_unchanged_at_end':True},
            {'source_hashes':{'runtime.py':'frozen'}},'v1')


def test_unrelated_old_lesson_cannot_supply_question_latency():
    record={'events':[{'type':'question_submitted','at_ms':100,'input_kind':'text'},
        {'type':'audio_playing','at_ms':110,'lesson_record_id':'stale','supplement':False}], 'responses':[]}
    played=[{'valid_explanation_by_record_linkage':True,'event_index':1,'event':record['events'][1],'lesson_id':'stale','audio_id':'old'}]
    row=collector.bound_latencies(record,played,[],{'stale':{'source_message_id':'old-message'}})['question_to_first_valid_explanation'][0]
    assert row['first_valid_explanation_ms'] is None and row['status']!='MEASURED'


def pcm(silent=False):
    stream=io.BytesIO()
    with wave.open(stream,'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(22050)
        wav.writeframes((b'\0\0' if silent else b'\x10\x00')*4410)
    return stream.getvalue()


def playback_fixture(monkeypatch,tmp_path):
    from edu_tutor.speech import provider
    step={'id':'s1','speech':'검증 대사','gesture':{'kind':'point','target_element_id':'table'},
          'board_actions':[{'type':'table','element_id':'table','columns':['x'],'rows':[[2]]}]}
    lesson={'id':'lesson','speech_allowed':True,'source_message_id':'answer','plan':{'steps':[step]}}
    rect={'x':1,'y':1,'width':20,'height':20}
    content=[{'id':'table','columns':['x'],'rows':[[{'id':'cell','text':'2'}]]}]
    media={'lesson_id':'lesson','step_id':'s1','media_id':1,'epoch':2,'current_src':'blob:clip','volume':1,'muted':False,'playbackRate':1,'currentTime':0}
    event={'type':'audio_playing','at_ms':110,'at_iso':'2026-10-29T00:00:01Z','epoch':2,'lesson_record_id':'lesson','step_id':'s1',
        'dom_lesson_record_id':'lesson','dom_step_id':'s1',
        'caption':'검증 대사','media':media,'board_content':content,'elements':[{'id':'table','rect':rect}],
        'pointer_end':{'x':5,'y':5},'cells':[]}
    binding=collector.lesson_binding(lesson)
    lesson['speech_binding_fingerprint']=binding
    clip={'audio_id':'audio','step_id':'s1','binding_fingerprint':binding}
    record={'events':[event],'responses':[{'at':'2026-10-29T00:00:00Z',
        'path':'/api/lessons/lesson/speech','status':200,
        'value':{'binding_fingerprint':binding,'steps':[clip]}}],
        'native_media':[{'type':'playing','at_ms':109,**media}], 'blob_bytes':{'blob:clip':{'sha256':'digest'}}}
    played=[{'event':event,'event_index':0,'lesson_id':'lesson','step_id':'s1','audio_id':'audio','valid_explanation_by_record_linkage':True}]
    exports={'audio':{'generation_metadata':{'provider':'windows_sapi_local','voice':'fixture','model_load_count':0},
        'wav_sha256':'digest','metadata_checksum_matches_wav':True,'metadata_duration_matches_wav':True}}
    checked={'hit':True,'audio':{'audio_id':'audio'},'wave_bytes':pcm()}
    monkeypatch.setattr(provider,'cached_audio',lambda *a,**k:checked)
    return record,played,{'lesson':lesson},exports,checked


def test_exact_native_blob_plan_pcm_binding_and_system_voice_regime(monkeypatch,tmp_path):
    record,played,lessons,exports,_=playback_fixture(monkeypatch,tmp_path)
    result=collector.validate_playbacks(tmp_path,record,lessons,played,exports)[0]
    assert result['valid_explanation_by_record_linkage']
    assert result['tts_load_regime']=='local_system_voice_no_neural_model_load'
    assert result['pointer_binding']['status']=='PASS'


@pytest.mark.parametrize('defect',['volume_zero','muted','wrong_blob','wrong_epoch','wrong_media','wrong_script','wrong_binding','wrong_duration','silent','invalid_cache','stale_dom','missing_response_status','wrong_response_path','wrong_response_binding','missing_captured_binding'])
def test_invalid_evidence_never_counts_as_valid_first_explanation(monkeypatch,tmp_path,defect):
    record,played,lessons,exports,checked=playback_fixture(monkeypatch,tmp_path)
    if defect=='volume_zero':record['native_media'][0]['volume']=0
    elif defect=='muted':record['native_media'][0]['muted']=True
    elif defect=='wrong_blob':record['blob_bytes']['blob:clip']['sha256']='other'
    elif defect=='wrong_epoch':record['native_media'][0]['epoch']=1
    elif defect=='wrong_media':record['native_media'][0]['media_id']=9
    elif defect=='wrong_script':played[0]['event']['caption']='다른 대사'
    elif defect=='wrong_binding':record['responses'][0]['value']['steps'][0]['binding_fingerprint']='other'
    elif defect=='wrong_duration':exports['audio']['metadata_duration_matches_wav']=False
    elif defect=='silent':checked['wave_bytes']=pcm(True)
    elif defect=='invalid_cache':checked['hit']=False
    elif defect=='stale_dom':played[0]['event']['dom_lesson_record_id']='different'
    elif defect=='missing_response_status':record['responses'][0].pop('status')
    elif defect=='wrong_response_path':record['responses'][0]['path']='/api/lessons/other/speech'
    elif defect=='wrong_response_binding':record['responses'][0]['value']['binding_fingerprint']='other'
    elif defect=='missing_captured_binding':lessons['lesson'].pop('speech_binding_fingerprint')
    assert not collector.validate_playbacks(tmp_path,record,lessons,played,exports)[0]['valid_explanation_by_record_linkage']


@pytest.mark.parametrize('board',[[],[{'id':'table','columns':['x'],'rows':[[{'id':'cell','text':'99'}]]}]])
def test_first_audio_time_is_separate_from_board_quality(monkeypatch,tmp_path,board):
    record,played,lessons,exports,_=playback_fixture(monkeypatch,tmp_path)
    played[0]['event']['board_content']=board
    result=collector.validate_playbacks(tmp_path,record,lessons,played,exports)[0]
    assert result['valid_explanation_by_record_linkage']
    assert not result['board_binding']['pass']
    # These do not become successful classroom journeys: complete during-play
    # scene checks remain a separate required verdict below.


def restored_fixture():
    board=[{'id':'table','rows':[[{'id':'cell','text':'2'}]]}]
    old={'media_id':1,'epoch':3,'currentTime':1.2}
    interrupted={'type':'interruption_submitted','at_ms':100,'lesson_record_id':'original','step_id':'s2','selected_cell_id':'cell','media':old,'board_content':board}
    playing={'type':'audio_playing','at_ms':301,'lesson_record_id':'original','step_id':'s2','media':{'media_id':2,'epoch':1,'currentTime':1.21},
             'board_content':copy.deepcopy(board),'cells':[{'id':'cell','selected':True}]}
    return {'events':[interrupted,{'type':'lesson_resumed','at_ms':300,'lesson_record_id':'original'},playing],'native_media':[]}


def test_return_requires_restored_content_position_selection_and_new_media():
    assert collector.restoration_checks(restored_fixture())[0]['pass']


@pytest.mark.parametrize('defect',['step','board','position','selection','old_media','late_replay'])
def test_return_event_alone_cannot_hide_restoration_failures(defect):
    record=restored_fixture();played=record['events'][-1]
    if defect=='step':played['step_id']='s1'
    elif defect=='board':played['board_content'][0]['rows'][0][0]['text']='99'
    elif defect=='position':played['media']['currentTime']=0
    elif defect=='selection':played['cells']=[]
    elif defect=='old_media':played['media']['media_id']=1
    elif defect=='late_replay':record['native_media']=[{'type':'playing','at_ms':400,'media_id':1}]
    assert not collector.restoration_checks(record)[0]['pass']


def test_missing_transition_remains_in_denominator():
    lesson={'plan':{'steps':[{'id':'s1'},{'id':'s2'},{'id':'s3'}]}}
    rows=collector.transition_measurements({'native_media':[]},{'lesson':lesson},[{'lesson_id':'lesson','valid_explanation_by_record_linkage':False}])
    assert len(rows)==2 and all(r['gap_ms'] is None for r in rows)


def test_false_custom_end_does_not_prove_native_completion():
    record={'events':[{'type':'audio_ended','lesson_record_id':'lesson','step_id':'s1'}],'native_media':[]}
    rows=collector.completed_steps(record,{'lesson':{'plan':{'steps':[{'id':'s1'}]}}},[{'lesson_id':'lesson','step_id':'s1','valid_explanation_by_record_linkage':True,'event':{'media':{'media_id':1},'epoch':2,'at_ms':10}}])
    assert rows[0]['pass'] is False


def test_request_answer_lesson_chain_is_required_and_sufficient_for_timing():
    session='a'*32
    events=[{'type':'question_submitted','at_ms':100,'at_iso':'2026-10-29T00:00:00Z','input_kind':'text'},
        {'type':'audio_playing','at_ms':160,'lesson_record_id':'lesson','supplement':False}]
    record={'events':events,'responses':[{'method':'POST','path':f'/api/sessions/{session}/messages',
        'at':'2026-10-29T00:00:01Z','request':{'content':'new question'},'value':{'request_id':'request'}}]}
    played=[{'valid_explanation_by_record_linkage':True,'event_index':1,'event':events[1],'lesson_id':'lesson','audio_id':'clip'}]
    messages=[{'id':'answer','role':'assistant','request_id':'request'}]
    result=collector.bound_latencies(record,played,messages,{'lesson':{'source_message_id':'answer'}})
    assert result['question_to_first_valid_explanation'][0]['first_valid_explanation_ms']==60
    result=collector.bound_latencies(record,played,messages,{'lesson':{'source_message_id':'different'}})
    assert result['question_to_first_valid_explanation'][0]['first_valid_explanation_ms'] is None


def test_actual_model_proof_counts_repairs_and_requires_scoped_reservations():
    record={'before':{'budget':{'accounting_scope':'scope'}},'responses':[{'method':'POST','value':{'request_id':'r','job_id':'job'}}]}
    answer={'id':'answer','role':'assistant','request_id':'r','raw_model_response':'model answer',
        'generation_snapshot':{'worker_pid':123,'revision':'rev','source':'worker_metadata','output_tokens':12},'model_attempts':[{},{}]}
    rows=[{'job_id':'job','kind':'text','status':'completed','execution_allowance_id':'scope'} for _ in range(2)]
    evidence=collector.model_evidence(record,[answer],{'requests':rows})[0]
    assert evidence['pass'] and evidence['reservation_count']==evidence['recorded_model_attempt_count']==2
    rows[0]['execution_allowance_id']='different'
    assert not collector.model_evidence(record,[answer],{'requests':rows})[0]['pass']


def test_null_original_context_cannot_crash_selected_row_audit():
    result=collector.selected_row_checks({'events':[]},[],[{'role':'assistant','lesson_context':None}],
        {'followup':{'column':'x','row_index':0,'value':2}})
    assert result['status']=='FAIL'


@pytest.mark.parametrize('plan',[None,{}, {'steps':[]}])
def test_stopped_supplement_without_plan_retains_selected_row_failure(plan):
    record={'events':[{'type':'interruption_submitted','selected_cell_id':'source-zero',
        'cells':[{'id':'source-zero','selected':True}],
        'board_content':[{'columns':['minutes'],'rows':[[{'id':'source-zero','text':'0'}]]}]}]}
    messages=[{'id':'supplement','role':'assistant',
        'lesson_context':{'selected_cell':{'cell_id':'source-zero'}}}]
    lessons=[{'source_message_id':'supplement','status':'verification_stopped','plan':plan}]
    result=collector.selected_row_checks(record,lessons,messages,
        {'followup':{'column':'minutes','row_index':0,'value':0}})
    assert result=={'status':'FAIL','selected_cell_matches_requested_nonempty_row':True,
        'supplement_message_retained_selected_cell':True,
        'supplement_plan_highlights_selected_cell':False,'semantic_explanation_review':'H_PENDING'}


def test_equation_requires_exact_renderer_output():
    step={'id':'s1','speech':'eq','board_actions':[{'type':'equation','element_id':'equation','latex':'2+3=5'}]}
    event={'caption':'eq','board_content':[{'id':'equation','equation_html':'<span>2+3=5</span>'}]}
    lesson={'plan':{'steps':[step]}}
    assert collector.board_binding(event,lesson,step,{'2+3=5':'<span>2+3=5</span>'})['pass']
    assert not collector.board_binding(event,lesson,step,{'2+3=5':'<span>2+3=6</span>'})['pass']


def scene_fixture():
    step={'id':'s1','speech':'표를 설명합니다.','gesture':{'kind':'point','target_element_id':'table'},
        'board_actions':[{'type':'clear','target':'all'},
            {'type':'code','element_id':'sql','code':'SELECT x FROM t'},
            {'type':'table','element_id':'table','columns':['x'],'rows':[[2.0]],'cell_ids':[['cell']]}]}
    lesson={'id':'lesson','plan':{'steps':[step]}}
    media={'media_id':1,'epoch':2,'currentTime':9,'duration':10,'lesson_id':'lesson','step_id':'s1'}
    sample={'lesson_record_id':'lesson','step_id':'s1','dom_lesson_record_id':'lesson','dom_step_id':'s1',
        'at_ms':9000,'media':media,'caption':step['speech'],'arrows':[],
        'board_content':[{'id':'sql','code':'SELECT x FROM t\n'},
            {'id':'table','columns':['x'],'rows':[[{'id':'cell','text':'2'}]]}],
        'elements':[{'id':'table','rect':{'x':0,'y':0,'width':20,'height':20}}],
        'cells':[],'pointer_end':{'x':10,'y':10}}
    played=[{'lesson_id':'lesson','step_id':'s1','valid_explanation_by_record_linkage':True,
        'event':{'media':{'media_id':1},'epoch':2}}]
    return {'scene_samples':[sample]},{'lesson':lesson},played


def test_empty_scene_at_audio_start_does_not_prevent_later_board_validation():
    record,lessons,played=scene_fixture()
    assert collector.active_scene(lessons['lesson'],'s1',0)['elements']=={}
    checked=collector.scene_binding_checks(record,lessons,played)[0]
    assert checked['pass'] and checked['complete_late_sample_count']==1


@pytest.mark.parametrize('defect',['missing_table','wrong_number','wrong_cell_id','extra_old_element','wrong_pointer','wrong_dom','partial_code','no_late_sample','no_samples'])
def test_actual_scene_errors_do_not_pass_even_when_audio_is_valid(defect):
    record,lessons,played=scene_fixture();sample=record['scene_samples'][0]
    if defect=='missing_table':sample['board_content'].pop()
    elif defect=='wrong_number':sample['board_content'][1]['rows'][0][0]['text']='99'
    elif defect=='wrong_cell_id':sample['board_content'][1]['rows'][0][0]['id']='other-cell'
    elif defect=='extra_old_element':sample['board_content'].append({'id':'old','text':'stale'})
    elif defect=='wrong_pointer':sample['pointer_end']={'x':99,'y':99}
    elif defect=='wrong_dom':sample['dom_step_id']='s2'
    elif defect=='partial_code':sample['board_content'][0]['code']='SELECT x'
    elif defect=='no_late_sample':sample['media']['currentTime']=5
    elif defect=='no_samples':record['scene_samples']=[]
    assert not collector.scene_binding_checks(record,lessons,played)[0]['pass']


def test_cleared_element_is_not_accepted_as_valid_old_content():
    lesson={'plan':{'steps':[{'id':'s1','board_actions':[{'type':'text','element_id':'old','text':'old'}]},
        {'id':'s2','speech':'new','board_actions':[{'type':'clear','target':'old','timing':{'start':0,'end':0}},
            {'type':'text','element_id':'new','text':'new','timing':{'start':0,'end':0}}]}]}}
    scene=collector.active_scene(lesson,'s2',.9)
    assert set(scene['elements'])=={'new'}
    event={'caption':'new','board_content':[{'id':'old','text':'old'},{'id':'new','text':'new'}]}
    assert not collector.board_binding(event,lesson,lesson['plan']['steps'][1],expected_scene=scene)['pass']


def test_arrow_must_connect_its_actual_source_and_target():
    scene={'arrows':{'flow':{'from_element_id':'from','to_element_id':'to'}}}
    sample={'stage_rect':{'x':100,'y':100},'elements':[
        {'id':'from','rect':{'x':110,'y':110,'width':50,'height':20}},
        {'id':'to','rect':{'x':210,'y':110,'width':50,'height':20}}],
        'arrows':[{'id':'flow','x1':60,'y1':20,'x2':110,'y2':20}]}
    assert collector.arrow_binding(sample,scene)['pass']
    sample['arrows'][0]['x2']=999
    assert not collector.arrow_binding(sample,scene)['pass']


def test_transition_sample_skipped_needs_another_complete_stable_sample():
    record,lessons,played=scene_fixture()
    record['scene_samples'][0]['media']['currentTime']=10*2/3
    result=collector.scene_binding_checks(record,lessons,played)[0]
    assert not result['pass'] and result['samples'][0]['status']=='SKIPPED_ACTION_BOUNDARY'


@pytest.mark.parametrize('mutation',['precision_policy_appears','precision_policy_changes','journey_changes'])
def test_actual_harness_freeze_covers_precision_and_question_changes(tmp_path,mutation):
    """Execute only the real file-hash function; no API, browser or model calls."""
    project=SCRIPTS.parent
    js=r'''
import {readFileSync,writeFileSync,mkdirSync,readdirSync,existsSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import vm from 'node:vm';
const [fixture,harness,mutation]=process.argv.slice(1);
const source=readFileSync(harness,'utf8');
const body=source.slice(source.indexOf('function sources() {'),source.indexOf('const terminal ='));
const put=(name,value)=>{const path=resolve(fixture,name);mkdirSync(resolve(path,'..'),{recursive:true});writeFileSync(path,value);};
put('src/edu_tutor/models/text_precision.py','fixture precision');
put('src/edu_tutor/models/text_session.py','fixture session');
put('src/edu_tutor/models/text_session_worker.py','fixture worker');
put('src/edu_tutor/problems/app_correction.py','fixture app correction');
put('web/dist/index.html','<script src="/app.js"></script>');
put('web/dist/app.js','fixture build');
put('runs/finish-v2/20261029/student/journeys.json','{"journeys":[]}');
if(mutation==='precision_policy_changes')put('.local/text-inference-policy.json','{"precision":"nf4"}');
const context={root:fixture,input:{journeys:[]},resolve,readFileSync,readdirSync,existsSync,
 sha:path=>createHash('sha256').update(readFileSync(path)).digest('hex')};
vm.createContext(context);vm.runInContext(body+'\nthis.computeSources=sources;',context);
const before=context.computeSources();
if(mutation==='journey_changes')put('runs/finish-v2/20261029/student/journeys.json','{"journeys":[{"id":"changed"}]}');
else put('.local/text-inference-policy.json','{"precision":"bf16"}');
const after=context.computeSources();
console.log(JSON.stringify({before,after}));
'''
    result=subprocess.run(['node','--input-type=module','-e',js,str(tmp_path),
        str(project/'web/scripts/finish-student-journeys.mjs'),mutation],capture_output=True,text=True,encoding='utf-8',timeout=20)
    assert result.returncode==0,result.stderr
    report=json.loads(result.stdout)
    assert report['before']!=report['after']
    for name in ['text_precision.py','text_session.py','text_session_worker.py']:
        assert report['before']['src/edu_tutor/models/'+name]
    assert report['before']['src/edu_tutor/problems/app_correction.py']
    if mutation=='precision_policy_appears':assert report['before']['.local/text-inference-policy.json'] is None
