"""Align derived timing labels with job+ledger audio provenance, no new calls."""
from pathlib import Path
import shutil
import collect_journeys as collector
BASE=Path(__file__).resolve().parent;OUT=BASE/'final-v021-r3-combined'
read,write=collector.read,collector.write

def regime(proof):
    if not proof:return None
    return {'FRESH_SYNTHESIS_COMPLETED_AND_CHARGED':'fresh_sapi_per_request','REUSED_EXISTING_WAV':'existing_wav_cache'}.get(proof['current_case_synthesis'],'NOT_ESTABLISHED')

def main():
    backup=OUT/'before-audio-regime-reconciliation';backup.mkdir(exist_ok=False)
    for name in ['summary.json','compact-results.json','gallery.html',*[f'J{i:02d}.json' for i in range(1,9)]]:shutil.copy2(OUT/name,backup/name)
    summary=read(OUT/'summary.json');compact=read(OUT/'compact-results.json');cases=[]
    for item in compact['cases']:
        case=read(OUT/(item['id']+'.json'))
        for p in case['playback']:
            proof=p.get('actual_generation_provenance');p['historical_tts_manifest_regime']=p.get('tts_load_regime');p['tts_load_regime']=regime(proof)
            p['original_manifest_historical_flag']=p.get('tts_generation_metadata_is_historical_when_cached')
            p['tts_generation_metadata_is_historical_when_cached']=proof.get('generation_metadata_historical_for_this_case') if proof else None
        for q in case['timings']['question_to_first_valid_explanation']:
            q['historical_tts_manifest_regime']=q.get('tts_load_regime');q['tts_load_regime']=regime(q.get('first_audio_generation_provenance'))
        for a in case['timings']['stage_breakdown']['audio']:
            p=next((p for p in case['playback'] if p['audio_id']==a['audio_id']),{})
            proof=p.get('actual_generation_provenance') or {}
            a['historical_tts_manifest_regime']=a.get('load_regime');a['load_regime']=regime(proof)
            a['manifest_cache_hit']=a.pop('cache_hit',None);a['original_manifest_historical_flag']=a.get('generation_metadata_historical')
            a['generation_metadata_historical']=proof.get('generation_metadata_historical_for_this_case')
            a['current_case_synthesis_proof']=proof.get('completed_job_and_ledger_proof',[])
        for e in item['events']:
            e['historical_tts_manifest_regime']=e.get('tts_load_regime');e['tts_load_regime']=regime(e.get('first_audio_provenance'))
        case['audio_provenance_audit']['timing_regime_reconciled']=True
        write(OUT/(case['id']+'.json'),case);cases.append(case)
    summary['question_events']=[q for c in cases for q in c['timings']['question_to_first_valid_explanation']]
    summary['audio_provenance_notice']+=' Derived tts_load_regime now follows actual current-case synthesis; prior manifest regime is explicitly historical_tts_manifest_regime.'
    summary['same_product_build_proof']['root_full_153_file_post_run_receipt']=str(BASE.parent/'final-preservation.json')
    compact['same_product_build_proof']['root_full_153_file_post_run_receipt']=str(BASE.parent/'final-preservation.json')
    write(OUT/'summary.json',summary);write(OUT/'compact-results.json',compact)
    collector.write_gallery(OUT,cases,{a['audio_id']:a for a in summary['audio']})
    print('PASS: current fresh/cache timing regimes reconciled; originals preserved')

if __name__=='__main__':main()
