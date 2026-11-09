"""Small saved-file-only control comparison; no DB/API/model/product imports."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.util
import json

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]
BASE=OUT.parent/'student/repair-control-final06'
spec=importlib.util.spec_from_file_location('saved_timings', OUT.parent/'timing-final04/read_timings.py')
helper=importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def selected(v,keys):return {k:v.get(k) for k in keys}
rows=[]
for attempt in ('cold','warm'):
 path=BASE/('J01-'+attempt)/'actual.json';a=read(path)
 assert a.get('completed_at') and a['status']!='RUNNING'
 messages=[m for m in a['actual_messages'] if m.get('role')=='assistant']
 assert len(messages)==1
 m=messages[0];g=m['generation_snapshot'];job=next(j for j in a['owned_jobs'] if j['kind']=='chat')
 submitted=next(e for e in a['events'] if e['type']=='question_submitted')
 played=a['first_playing']
 native=next(e for e in a['native_media'] if e['type']=='playing' and all(e.get(k)==played.get(k) for k in ('lesson_id','step_id','epoch')))
 ready=next(e for e in a['events'] if e['type']=='plan_ready')
 posts=[r for r in a['requests'] if r.get('method')=='POST' and r.get('path')=='/api/sessions/'+a['owned_session_id']+'/messages']
 assert len(posts)==1
 post=posts[0]
 post_ms=(datetime.fromisoformat(post['at'].replace('Z','+00:00'))-datetime.fromisoformat(submitted['at_iso'].replace('Z','+00:00'))).total_seconds()*1000+submitted['at_ms']
 clip=next(e for e in a['events'] if e['type']=='speech_ready' and e.get('lesson_id')==played['lesson_id'] and e.get('step_id')==played['step_id'] and e['at_ms']<native['at_ms'])
 cache=next(e for e in a['events'] if e['type']=='cache_manifest_end' and e.get('lesson_id')==played['lesson_id'] and e.get('step_id')==played['step_id'] and e['at_ms']<native['at_ms'])
 trace=helper.worker_trace(g)
 state=a['text_session_after_cleanup']['session']
 row={'case':'J01-'+attempt,'status':a['status'],'measurement_mode':a['measurement_mode'],
  'actual_path':str(path.relative_to(ROOT)),'actual_sha256':sha(path),'source_unchanged':a['source_unchanged_at_end'],
  'question':a['spec']['question'],'raw_model_response':m.get('raw_model_response'),
  'ui_first_meaningful_text':'NOT_MEASURED','native_first_speech_button_seconds':(native['at_ms']-submitted['at_ms'])/1000,
  'native_first_speech_post_seconds':(native['at_ms']-post_ms)/1000,
  'button_to_plan_ready_seconds':(ready['at_ms']-submitted['at_ms'])/1000,
  'first_voice_cache_hit':cache['hit'],'first_voice_audio_id':clip.get('audio_id'),
  'first_voice_cache_evidence':selected(cache,['type','at_ms','lesson_id','step_id','hit']),
  'native_first_voice':selected(native,['type','at_ms','lesson_id','step_id','epoch','media_id']),
  'text_identity':selected(g,['worker_pid','process_start_time','instance_id','model_instance_id','model_python_id','request_model_load_count','cumulative_model_load_count']),
  'metadata':selected(g,['model_load_seconds','generation_seconds','input_tokens','output_tokens','elapsed_seconds','parent_timing','transport_timing','dispatch_timing']),
  'worker_trace':trace,'storage_timing':job.get('storage_timing'),
  'activity_ack':state.get('preflight_activity_ack'), 'activity_token':state.get('preflight_activity_token'),
  'latest_request_id':state.get('latest_request_id'),'job_id':job['id'],
  'student_used':a['student_budget_before_close']['used'],
  'human_review':'H_PENDING','not_measured_by_design':['full lesson','stage gaps','followup']}
 rows.append(row)
c,w=rows
checks={k:c['text_identity'][k]==w['text_identity'][k] for k in ('worker_pid','process_start_time','instance_id','model_instance_id','model_python_id')}
ack=w['activity_ack']
checks.update(cold_request_load_one=c['text_identity']['request_model_load_count']==1,
 warm_request_load_zero=w['text_identity']['request_model_load_count']==0,
 cumulative_load_one=w['text_identity']['cumulative_model_load_count']==1,
 ack_accepted=ack.get('accepted') is True,ack_previous_request=ack['previous_request_id']==c['latest_request_id'],
 ack_request_id_unchanged=ack['request_id']==c['latest_request_id'],ack_job=ack['job_id']==w['job_id'],
 ack_instance=ack['instance_id']==w['text_identity']['instance_id'],ack_pid=ack['worker_pid']==w['text_identity']['worker_pid'],
 ack_token=ack['activity_token']==w['activity_token'])
result={'at':datetime.now(timezone.utc).isoformat(),'read_only_saved_files':True,'DB_reads':0,'model_calls':0,
 'cases':rows,'reuse_checks':checks,'reuse_confirmed':all(checks.values()),
 'notice':'Controlled cached-first-voice pair, not full lesson or new independent accuracy. Overlapping timing intervals must not be added. The warm preflight was short, so actual rescue from the prior 52-second preflight is not established.'}
(OUT/'control-data.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def f(v):return f'{v:.3f}' if isinstance(v,(float,int)) else str(v)
lines=['# 최종06 통제 비교 — 동일 worker 재사용 확인, 지연 목표 미달','',
 '2026-10-30 실제 완료된 J01 두 실행만 분석했다. 새 텍스트 각1회, 새 음성0개이며 첫 설명은 둘 다 기존 캐시다. 전체 수업·단계 공백·보충 질문은 이 짧은 통제 비교의 측정 범위가 아니다.','',
 '| 항목 | cold | 실제 warm |','|---|---:|---:|']
for label,fn in [
 ('버튼→첫 native 설명 음성(초)',lambda r:r['native_first_speech_button_seconds']),
 ('POST→첫 native 설명 음성(초)',lambda r:r['native_first_speech_post_seconds']),
 ('버튼→검증된 계획 ready 이벤트(초)',lambda r:r['button_to_plan_ready_seconds']),
 ('저장 검사(초)',lambda r:r['metadata']['dispatch_timing']['storage_check_seconds']),
 ('전체 preflight(초)',lambda r:r['metadata']['dispatch_timing']['total_preflight_seconds']),
 ('worker import 구간(초)',lambda r:r['worker_trace']['boundaries']['runtime_import_window']['seconds']),
 ('metadata 모델 load(초)',lambda r:r['metadata']['model_load_seconds']),
 ('metadata 생성(초)',lambda r:r['metadata']['generation_seconds']),
 ('부모 모델 요청→metadata(초)',lambda r:r['metadata']['parent_timing']['request_elapsed_seconds']),
 ('부모 첫 delta(초; 유효 설명 아님)',lambda r:r['metadata']['transport_timing']['first_delta_consumer_elapsed_seconds']),
 ('consumer yield 합계(초)',lambda r:r['metadata']['transport_timing']['consumer_yield_seconds_total']),
 ('reader queue 합계(초)',lambda r:r['metadata']['transport_timing']['queue_wait_seconds_total']),
 ('DB commit 합계(초)',lambda r:r['storage_timing']['phases']['db_commit']['seconds']),
 ('DB close 합계(초)',lambda r:r['storage_timing']['phases']['db_close']['seconds'])]:
 lines.append('|'+label+'|'+f(fn(c))+'|'+f(fn(w))+'|')
lines.extend(['',
 '시간 구간은 겹친다. generation·consumer·DB·queue를 합해서 총 지연을 만들지 않는다. storage snapshot은 최종 job-state 쓰기 전까지이며 HTTP/SSE 전송까지 포함하지 않는다. 첫 유효 UI 텍스트 시점은 **NOT_MEASURED**이며 첫 delta로 대체하지 않는다.','',
 f"실제 worker PID `{w['text_identity']['worker_pid']}`, session `{w['text_identity']['instance_id']}`, model `{w['text_identity']['model_instance_id']}`, Python 객체 `{w['text_identity']['model_python_id']}`가 같다. 요청 load1→0, 누적load1이다. activity ACK는 accepted=true이며 직전 request·현재 job·token·PID·instance가 모두 일치한다. 상세 원본은 control-data.json과 실제 session events에 남겼다.",'',
 'warm 첫 설명도 10초 목표를 넘는다. warm 생성 자체가 15.781초이며 저장 검사가 4.657초다. final05의 실패는 별도 보존한다: 당시 다음 요청은 저장 검사52.178초 중 idle 만료 후 새 PID/load1로 바뀌어 deadline에 실패했다. 이번에는 갱신 ACK와 실제 reuse는 증명했으나 warm 저장 검사가 짧아 같은 52초 상황의 실제 구조적 복구를 직접 재현한 것은 아니다. cold 저장 검사도39.163초로 계속 느렸으며 host 부하·파일시스템·검사 비용의 근본 원인은 확정하지 않았다.','',
 '정확한 음성 지문/판서 linkage는 기존 collector가 추가 확인한다. 사람이 듣고 교육·발음을 판정한 결과는 없으므로 **H_PENDING/NOT_READY 유지**다.'])
(OUT/'CONTROL_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'reuse_confirmed':result['reuse_confirmed'],'cases':[selected(r,['case','native_first_speech_button_seconds','native_first_speech_post_seconds','first_voice_cache_hit']) for r in rows]},ensure_ascii=False))
