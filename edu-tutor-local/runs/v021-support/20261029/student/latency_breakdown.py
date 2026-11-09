"""Read-only linked stage timings. Nested intervals must not be added."""
from datetime import datetime

def iso(value):
    try:return datetime.fromisoformat(value.replace('Z','+00:00')) if value else None
    except (ValueError,TypeError):return None

def breakdown(record,messages,lesson_map,played,timing):
    answers=[]
    for message in messages:
        if message.get('role')!='assistant':continue
        snapshot=message.get('generation_snapshot') or {}
        answers.append({'message_id':message['id'],'request_id':message.get('request_id'),
            'api_core':message.get('latency') or {'status':'NOT_MEASURED'},
            'evidence_timings_seconds':(message.get('evidence') or {}).get('timings_seconds') or {'status':'NOT_MEASURED'},
            'parent_dispatch_timing':snapshot.get('dispatch_timing') or snapshot.get('parent_dispatch_timing') or {'status':'NOT_MEASURED'},
            'parent_worker_interval':snapshot.get('parent_timing') or {'status':'NOT_MEASURED'},
            'model':{k:snapshot.get(k) for k in ('worker_pid','model_instance_id','model_load_count','request_model_load_count','cumulative_model_load_count','model_load_seconds','generation_seconds','elapsed_seconds','input_tokens','output_tokens','finish_reason')},
            'all_model_attempts':[{'attempt':a.get('attempt'),'generation_snapshot':a.get('generation_snapshot')} for a in message.get('model_attempts',[])]})
    audio=[]
    for entry in played:
        snapshot=entry.get('tts_generation_snapshot') or {}
        audio.append({'lesson_id':entry['lesson_id'],'step_id':entry['step_id'],'audio_id':entry['audio_id'],
            'first_play_at_ms':entry['event']['at_ms'],'cache_hit':entry.get('tts_clip_cache_hit'),
            'load_regime':entry.get('tts_load_regime'),'generation_metadata_historical':entry.get('tts_generation_metadata_is_historical_when_cached'),
            'provider':snapshot.get('provider'),'device':snapshot.get('device'),
            'host_timing':snapshot.get('host_timing') or {'status':'NOT_MEASURED'},
            'parent_dispatch_timing':snapshot.get('dispatch_timing') or {'status':'NOT_MEASURED'},
            'duration_seconds':snapshot.get('duration'),'elapsed_seconds':snapshot.get('elapsed_seconds')})
    browser=[]
    events=record.get('events',[])
    pairs=[('cache_manifest_start','cache_manifest_end'),('audio_fetch_start','audio_fetch_end'),('audio_decode_start','audio_decode_end'),('next_cache_prefetch_start','next_cache_prefetch_ready')]
    for start_name,end_name in pairs:
        used=set()
        for first in (e for e in events if e.get('type')==start_name):
            match=next(((i,e) for i,e in enumerate(events) if i not in used and e.get('type')==end_name and e.get('at_ms',-1)>=first.get('at_ms',0) and all(e.get(k)==first.get(k) for k in ('lesson_record_id','step_id','epoch'))),None)
            if match:used.add(match[0])
            browser.append({'interval':start_name+' -> '+end_name,'lesson_id':first.get('lesson_record_id'),'step_id':first.get('step_id'),'epoch':first.get('epoch'),
                'seconds':(match[1]['at_ms']-first['at_ms'])/1000 if match else None,'status':'MEASURED' if match else 'NOT_MEASURED','clock':'same_browser_performance_now'})
    plan_jobs=[]
    for job in record.get('owned_jobs',[]):
        if job.get('kind')!='lesson':continue
        start,end=iso(job.get('created_at')),iso(job.get('updated_at'))
        plan_jobs.append({'job_id':job['id'],'state':job['state'],'created_to_terminal_seconds':(end-start).total_seconds() if start and end else None,
            'scope':'queued job creation to last terminal update; pure plan CPU time is NOT_MEASURED'})
    residuals=[]
    for question in timing.get('question_to_first_valid_explanation',[]):
        answer=next((m for m in messages if m.get('role')=='assistant' and m.get('request_id')==question.get('request_id')),None)
        core=(answer or {}).get('latency',{}).get('request_to_verified_core_seconds')
        first=question.get('first_valid_explanation_ms')
        residuals.append({'request_id':question.get('request_id'),'input_kind':question.get('input_kind'),
            'question_to_first_valid_seconds':first/1000 if isinstance(first,(int,float)) else None,
            'api_core_seconds':core,'difference_seconds':first/1000-core if isinstance(first,(int,float)) and isinstance(core,(int,float)) else None,
            'interpretation':'Boundary difference only: browser submission and API core start/end differ. Includes any remaining API transit/polling/plan/speech/decoding; attribution is NOT_MEASURED. Never sum overlapping nested intervals.'})
    return {'answers':answers,'audio':audio,'browser_intervals':browser,'plan_jobs':plan_jobs,
        'api_roundtrips':[{'method':r['method'],'path':r['path'],'status':r['status'],**r['request_timing']} for r in record.get('responses',[]) if r.get('request_timing') and r['method']!='GET'],
        'unattributed_boundary_differences':residuals,
        'interpretation':'All fields are source metadata or measured intervals, not disjoint additive stages. Storage is nested in reservation/preflight; synthesis is nested in child runtime. Cached WAV timing describes historical creation, not current synthesis. Missing measurements remain NOT_MEASURED.'}
