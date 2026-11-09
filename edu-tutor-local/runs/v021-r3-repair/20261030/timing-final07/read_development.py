"""Terminal actual + bound worker files only; no DB/WAV or model execution."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.util
import json

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]
spec=importlib.util.spec_from_file_location('saved_timings',OUT.parent/'timing-final04/read_timings.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
def pick(obj,keys):return {k:obj.get(k) for k in keys}
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
parser=argparse.ArgumentParser();parser.add_argument('case',choices=['N01','N02']);args=parser.parse_args()
path=OUT.parent/'student/repair-development-final07'/args.case/'actual.json'
raw=path.read_bytes();a=json.loads(raw);assert a.get('completed_at') and a['status']!='RUNNING'
receipt=read(Path(str(path)+'.writer.json'));journal=Path(str(path)+'.journal.jsonl')
with journal.open('rb') as stream:
 stream.seek(0,2);size=stream.tell();stream.seek(max(0,size-65536));tail=stream.read()
assert tail.endswith(b'\n');marker=json.loads(tail.splitlines()[-1])
assert marker==receipt and marker['commit_complete'] is True and marker['type']=='finalized'
assert marker['final_sha256']==hashlib.sha256(raw).hexdigest() and marker['final_bytes']==len(raw)
assert Path(marker['actual_path']).resolve()==path.resolve() and Path(marker['journal_path']).resolve()==journal.resolve()
assert marker['recording_mode']==a['recording_mode']=='incremental_worker_journal_v1'
messages=[m for m in a['actual_messages'] if m.get('role')=='assistant']
submits=[e for e in a['events'] if e['type']=='question_submitted']
posts=[r for r in a['requests'] if r.get('method')=='POST' and r.get('path')=='/api/sessions/'+a['owned_session_id']+'/messages']
assert len(messages)==len(submits)==len(posts)
rows=[]
for i,(m,s,p) in enumerate(zip(messages,submits,posts)):
 g=m['generation_snapshot'];job=next(j for j in a['owned_jobs'] if j.get('kind')=='chat' and j.get('request_id')==m['request_id'])
 cycle=a['followup_cycles'][i-1] if i else None
 lesson_id=cycle['supplement_id'] if cycle else a['actual_lesson']['id']
 play=next(e for e in a['events'] if e['type']=='audio_playing' and e.get('lesson_id')==lesson_id)
 native=next(e for e in a['native_media'] if e['type']=='playing' and all(e.get(k)==play.get(k) for k in ('lesson_id','step_id','epoch')))
 speech=next(e for e in a['events'] if e['type']=='speech_ready' and e.get('lesson_id')==lesson_id and e.get('step_id')==play['step_id'] and e['at_ms']<native['at_ms'])
 iso=lambda x:datetime.fromisoformat(x.replace('Z','+00:00'))
 postms=s['at_ms']+(iso(p['at'])-iso(s['at_iso'])).total_seconds()*1000
 trace=helper.worker_trace(g)
 session_dir=ROOT/'runs'/('text-session-'+g['instance_id'])
 events=[json.loads(line) for line in (session_dir/'events.jsonl').read_text(encoding='utf-8').splitlines() if line]
 acks=[e for e in events if e.get('type')=='activity_ack' and e.get('job_id')==job['id']]
 state=read(session_dir/'session.json')
 row={'ordinal':i+1,'cohort':cycle['cohort'] if cycle else 'primary','request_id':m['request_id'],
  'question':next(x['content'] for x in a['actual_messages'] if x.get('role')=='user' and x.get('request_id')==m['request_id']),
  'lesson_id':lesson_id,'raw_model_response':m.get('raw_model_response'),'model_attempts':m.get('model_attempts'),
  'text_identity':pick(g,['worker_pid','process_start_time','instance_id','model_instance_id','model_python_id','request_model_load_count','cumulative_model_load_count']),
  'metadata':g,'worker_trace':trace,'owned_chat_storage':job.get('storage_timing'),
  'question_submitted_to_native_seconds':(native['at_ms']-s['at_ms'])/1000,
  'POST_to_native_seconds':(native['at_ms']-postms)/1000,
  'ui_first_meaningful_text':'NOT_MEASURED', 'first_voice_cached_event':speech.get('cached'),
  'first_voice_audio_id':speech.get('audio_id'),'activity_acks':acks,
  'session_exit_snapshot':pick(state,['status','reason','process_exit_confirmed','actual_worker_exit_confirmed']),
  'cancelled_owned_speech_jobs':[pick(j,['id','state','error','created_at','updated_at']) for j in a['owned_jobs'] if j['kind']=='speech' and j['state']=='cancelled']}
 if cycle:
  button=cycle['interruption']['at_ms'];pause=cycle['original_native_pause']['at_ms']
  first=cycle['first_supplement_playing'];firstnative=next(e for e in a['native_media'] if e['type']=='playing' and all(e.get(k)==first.get(k) for k in ('lesson_id','step_id','epoch')))
  end_events=[e for e in a['native_media'] if e['type']=='ended' and e.get('lesson_id')==lesson_id]
  lastend=max(e['at_ms'] for e in end_events)
  row['interruption']={'button_to_native_pause_seconds':(pause-button)/1000,
   'button_to_supplement_native_seconds':(firstnative['at_ms']-button)/1000,
   'supplement_native_duration_through_last_end_seconds':(lastend-firstnative['at_ms'])/1000,
   'last_supplement_end_to_original_audio_playing_seconds':(cycle['resumed_playing']['at_ms']-lastend)/1000,
   'checks':cycle['checks'],'status':cycle['status'],'cohort':cycle['cohort']}
 rows.append(row)
result={'at':datetime.now(timezone.utc).isoformat(),'actual_path':str(path.relative_to(ROOT)),
 'actual_sha256':hashlib.sha256(raw).hexdigest(),'status':a['status'],'source_unchanged':a['source_unchanged_at_end'],
 'writer_commit':'VERIFIED','writer_receipt':receipt,
 'questions':rows,'student_used':a['student_budget_before_close']['used'],'human_review':'H_PENDING',
 'scope':'Development regression. Repeat is separate stability action, excluded from accuracy denominator. Raw/model/app/content judgments remain separate. DB/WAV collector still pending.'}
(OUT/(args.case+'-file-data.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'case':args.case,'rows':[{**pick(r,['ordinal','cohort','question_submitted_to_native_seconds','POST_to_native_seconds','first_voice_cached_event']),
 'identity':r['text_identity'],'interruption':r.get('interruption')} for r in rows]},ensure_ascii=False))
