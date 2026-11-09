"""Link current synthesis to completed job output AND charged reservation.

A manifest cache_hit only says bytes exist when fetched; it does not establish
that they existed before this question. Original observations stay unchanged.
"""
from pathlib import Path
import json
import shutil
import collect_journeys as collector

BASE=Path(__file__).resolve().parent
OUT=BASE/'final-v021-r3-combined'
read,write=collector.read,collector.write

def main():
    backup=OUT/'before-audio-provenance-audit'
    backup.mkdir(exist_ok=False)
    for name in ['summary.json','compact-results.json','gallery.html',*[f'J{i:02d}.json' for i in range(1,9)]]:
        shutil.copy2(OUT/name,backup/name)
    summary=read(OUT/'summary.json');compact=read(OUT/'compact-results.json')
    cases=[];audit=[]
    for item in compact['cases']:
        case=read(OUT/(item['id']+'.json'));raw=read(Path(case['actual_json']))
        rows=[]
        for play in case['playback']:
            matches=[]
            for job in raw.get('owned_jobs',[]):
                if job.get('kind')!='speech' or job.get('state')!='succeeded':continue
                for clip in (job.get('result') or {}).get('steps',[]):
                    if clip.get('audio_id')==play['audio_id'] and clip.get('step_id')==play['step_id'] and job['result'].get('lesson_id')==play['lesson_id']:
                        charged=[r for r in case.get('case_reservations',[]) if r.get('job_id')==job['id'] and r.get('status')=='completed' and r.get('new_audio_clips',0)>0]
                        if clip.get('cache_hit') is False and charged:
                            matches.append({'job_id':job['id'],'job_finished_at':job['updated_at'],'job_result_cache_hit':False,
                                'reservation_ids':[r['id'] for r in charged],'new_audio_charged':sum(r['new_audio_clips'] for r in charged),
                                'host_timing':clip.get('host_timing'),'dispatch_timing':clip.get('dispatch_timing'),'parent_timing':clip.get('parent_timing'),
                                'completion':clip.get('completion'),'elapsed_seconds':clip.get('elapsed_seconds')})
            provenance={'audio_id':play['audio_id'],'step_id':play['step_id'],'lesson_id':play['lesson_id'],
                'manifest_cache_hit_observed':play.get('tts_clip_cache_hit'),
                'current_case_synthesis':'FRESH_SYNTHESIS_COMPLETED_AND_CHARGED' if matches else 'REUSED_EXISTING_WAV' if play.get('tts_clip_cache_hit') is True else 'NOT_ESTABLISHED',
                'generation_metadata_historical_for_this_case':False if matches else True if play.get('tts_clip_cache_hit') is True else None,
                'completed_job_and_ledger_proof':matches,
                'interpretation':'Fresh means this attempt synthesized and charged these bytes, even if a later manifest reports cache_hit=true. Repeated playback of a fresh clip is not another synthesis.'}
            play['actual_generation_provenance']=provenance
            rows.append(provenance)
        for question in case['timings']['question_to_first_valid_explanation']:
            question['first_audio_generation_provenance']=next((r for r in rows if r['audio_id']==question.get('audio_id')),None)
        for event in item['events']:
            proof=next((r for r in rows if r['audio_id']==event.get('first_audio_id')),None)
            event['first_audio_manifest_cache_hit']=event.pop('first_audio_cache_hit',None)
            event['first_audio_generation']=proof['current_case_synthesis'] if proof else None
            event['first_audio_cache_hit_before_this_case']=False if proof and proof['current_case_synthesis'].startswith('FRESH') else True if proof and proof['current_case_synthesis']=='REUSED_EXISTING_WAV' else None
            event['first_audio_provenance']=proof
        case['audio_provenance_audit']={'protocol':'completed_job_plus_charged_reservation_v1','clips':rows,
            'original_manifest_interpretation_preserved':True,'new_model_TTS_OCR_calls':0}
        write(OUT/(case['id']+'.json'),case);cases.append(case)
        audit.append({'case':case['id'],'clips':rows})
    summary['question_events']=[q for c in cases for q in c['timings']['question_to_first_valid_explanation']]
    summary['audio_provenance_protocol']='completed_job_plus_charged_reservation_v1'
    summary['audio_provenance_notice']='Original manifest cache_hit is not pre-question cache status. Consult first_audio_generation_provenance; initial derived reports preserved in before-audio-provenance-audit.'
    write(OUT/'summary.json',summary);write(OUT/'compact-results.json',compact)
    write(OUT/'audio-provenance-audit.json',{'cases':audit,'model_TTS_OCR_calls':0})
    collector.write_gallery(OUT,cases,{a['audio_id']:a for a in summary['audio']})
    print(json.dumps({'status':'AUDITED_WITH_ORIGINALS_PRESERVED','first_audio':[{c['id']:[e['first_audio_generation'] for e in c['events']]} for c in compact['cases']]},ensure_ascii=False))

if __name__=='__main__':main()
