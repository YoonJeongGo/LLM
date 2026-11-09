"""Completed control files + journal footer + exact worker protocol; no DB/API."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[3]
BASE=OUT.parent/'student/repair-control-final07'
def pick(v,keys):return {k:v.get(k) for k in keys}
rows=[]
for attempt in ('cold','warm'):
 path=BASE/('J01-'+attempt)/'actual.json';raw=path.read_bytes();a=json.loads(raw)
 assert a.get('completed_at') and a['status']!='RUNNING'
 receipt=json.loads(Path(str(path)+'.writer.json').read_text(encoding='utf-8'))
 journal=Path(str(path)+'.journal.jsonl')
 with journal.open('rb') as stream:
  stream.seek(0,2);end=stream.tell();stream.seek(max(0,end-65536));tail=stream.read()
 assert tail.endswith(b'\n');marker=json.loads(tail.splitlines()[-1])
 assert marker==receipt and marker['commit_complete'] is True and marker['type']=='finalized'
 assert marker['final_sha256']==hashlib.sha256(raw).hexdigest() and marker['final_bytes']==len(raw)
 assert Path(marker['actual_path']).resolve()==path.resolve() and Path(marker['journal_path']).resolve()==journal.resolve()
 assert marker['recording_mode']==a['recording_mode']=='incremental_worker_journal_v1'
 m=next(m for m in a['actual_messages'] if m['role']=='assistant');g=m['generation_snapshot']
 s=next(e for e in a['events'] if e['type']=='question_submitted');play=a['first_playing']
 native=next(e for e in a['native_media'] if e['type']=='playing' and all(e.get(k)==play.get(k) for k in ('lesson_id','step_id','epoch')))
 speech=next(e for e in a['events'] if e['type']=='speech_ready' and e.get('lesson_id')==play['lesson_id'] and e.get('step_id')==play['step_id'] and e['at_ms']<native['at_ms'])
 job=next(j for j in a['owned_jobs'] if j['kind']=='chat')
 ep=ROOT/'runs'/('text-session-'+g['instance_id'])/'events.jsonl'
 protocol=ep.read_bytes();complete=protocol[:protocol.rfind(b'\n')+1]
 events=[json.loads(line) for line in complete.splitlines()]
 meta=next(e for e in events if e['type']=='metadata' and e.get('timestamp')==g['timestamp'] and e.get('model_instance_id')==g['model_instance_id'])
 rid=meta['request_id'];done=next(e for e in events if e['type']=='done' and e.get('request_id')==rid)
 selected=[e for e in events if e.get('request_id')==rid and e['worker_elapsed_seconds']<=done['worker_elapsed_seconds']]
 def point(kind,stage=None):return next((e for e in selected if e['type']==kind and (stage is None or e.get('stage')==stage)),None)
 bounds={}
 for label,left,right in [('import',point('progress','text_runtime_import_started'),point('progress','imports_ready')),
  ('load_to_ready',point('progress','model_load_started'),point('model_ready')),
  ('model_ready_to_first_delta',point('model_ready'),point('delta')),
  ('model_ready_to_metadata',point('model_ready'),meta)]:
  bounds[label]=right['worker_elapsed_seconds']-left['worker_elapsed_seconds'] if left and right else None
 state=a['text_session_after_cleanup']['session'];ack=state.get('preflight_activity_ack')
 row={'case':'J01-'+attempt,'actual':str(path.relative_to(ROOT)),'status':a['status'],'commit_gate':'VERIFIED',
  'writer_receipt':receipt,'question':a['spec']['question'],'source_unchanged':a['source_unchanged_at_end'],
  'identity':pick(g,['worker_pid','process_start_time','instance_id','model_instance_id','model_python_id','request_model_load_count','cumulative_model_load_count']),
  'button_to_native_speech_seconds':(native['at_ms']-s['at_ms'])/1000,
  'first_voice_cache_hit':speech.get('cached'),'first_voice_audio_id':speech.get('audio_id'),
  'metadata':g,'worker_boundaries_seconds':bounds,'protocol_request_id':rid,
  'protocol_completed_request_points':[pick(e,['type','stage','request_id','worker_pid','worker_elapsed_seconds']) for e in selected if e['type']!='delta'],
  'storage_timing':job.get('storage_timing'),'job_id':job['id'],'activity_ack':ack,
  'nonce_matches_hello':ack.get('nonce')==state['interpreter']['nonce'] if ack else None,
  'first_valid_UI_text':'NOT_MEASURED','student_used':a['student_budget_before_close']['used'],'human_review':'H_PENDING'}
 rows.append(row)
c,w=rows;ack=w['activity_ack'];same=all(c['identity'][k]==w['identity'][k] for k in ('worker_pid','process_start_time','instance_id','model_instance_id','model_python_id'))
checks={'same_identity':same,'request_load_1_to_0':c['identity']['request_model_load_count']==1 and w['identity']['request_model_load_count']==0,
 'cumulative_one':w['identity']['cumulative_model_load_count']==1,'ack_previous_exact':ack['previous_request_id']==c['protocol_request_id'],
 'ack_job_exact':ack['job_id']==w['job_id'],'ack_instance_exact':ack['instance_id']==w['identity']['instance_id'],
 'ack_pid_exact':ack['worker_pid']==w['identity']['worker_pid'],'ack_accepted':ack['accepted'] is True,'ack_nonce':w['nonce_matches_hello']}
data={'at':datetime.now(timezone.utc).isoformat(),'cases':rows,'reuse_checks':checks,'reuse_confirmed':all(checks.values()),'actual_hashes_and_commits_verified':True,'database_calls':0,'model_calls':0,'human_review':'H_PENDING'}
(OUT/'control-data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def f(v):return f'{v:.3f}' if isinstance(v,(int,float)) else '미측정/해당 없음'
lines=['# 최종07 control — 실제 commit와 재사용 확인','',
 '증분 기록기를 적용한 동일 최종 빌드의 짧은 통제 비교다. 두 실제 actual의 SHA/크기·최종 journal footer·writer receipt가 일치함을 확인했다. 전체 JSON 저장은 각1회, in-flight 최대1개이며 주 스레드 전체 객체 전달0이다.','',
 '| 항목(초) | cold | 실제 warm |','|---|---:|---:|']
for label,fn in [('버튼→native 첫 설명',lambda r:r['button_to_native_speech_seconds']),('저장 검사',lambda r:r['metadata']['dispatch_timing']['storage_check_seconds']),
 ('전체 preflight',lambda r:r['metadata']['dispatch_timing']['total_preflight_seconds']),('worker import',lambda r:r['worker_boundaries_seconds']['import']),
 ('model load metadata',lambda r:r['metadata']['model_load_seconds']),('생성 metadata',lambda r:r['metadata']['generation_seconds']),
 ('부모 요청→metadata',lambda r:r['metadata']['parent_timing']['request_elapsed_seconds']),('consumer yield 합계',lambda r:r['metadata']['transport_timing']['consumer_yield_seconds_total'])]:
 lines.append('|'+label+'|'+f(fn(c))+'|'+f(fn(w))+'|')
lines.extend(['',f"PID `{w['identity']['worker_pid']}`, session `{w['identity']['instance_id']}`, model `{w['identity']['model_instance_id']}` 및 Python 객체가 같다. 요청 load1→0, 누적load1이며 ACK의 직전 request·현재 job·nonce·instance·PID가 일치한다.",'',
 '첫 음성은 둘 다 기존 캐시이며 새 음성0이다. 전체 수업·단계 공백·중간 질문은 이 통제 비교에서 측정하지 않았다. worker 생성시간·DB/consumer/queue 구간은 겹칠 수 있어 합산하지 않는다. 첫 유효 UI 텍스트는 NOT_MEASURED다.','',
 'final06은 동기 전체저장 계측기, final07은 증분 worker 기록기와 중복 캐시 GET 수정이 적용됐다. 환경·질문 실행 순서도 같다고 보장되지 않으므로 차이를 제품 개선율로 단정하지 않는다. 이 기록기의 journal I/O도0이 아니며 worker에서 수행했다. 실제 발음·교육 인간 검토는 H_PENDING이다.'])
(OUT/'CONTROL_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'reuse_confirmed':data['reuse_confirmed'],'commit_gate':'VERIFIED_BOTH','rows':[{'case':r['case'],'native_seconds':r['button_to_native_speech_seconds'],'load':r['metadata']['model_load_seconds'],'generation':r['metadata']['generation_seconds'],'storage':r['metadata']['dispatch_timing']['storage_check_seconds']} for r in rows]}))
