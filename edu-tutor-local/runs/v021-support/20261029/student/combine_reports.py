"""Read-only collection/combination of identical-product classroom attempts.

Preserves failed source statuses. Runs no model, OCR or speech generator.
"""
from pathlib import Path
import copy
import json
from datetime import datetime, timezone
import collect_journeys as collector

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[3]
VERSIONS=['final-v021-r3-student-v2','final-v021-r3-student-v3','final-v021-r3-student-v4','final-v021-r3-student-v5']
OUT=BASE/'final-v021-r3-combined'
read=collector.read
write=collector.write

def main():
    if OUT.exists():
        raise ValueError('Combined evidence already exists; do not overwrite')
    freezes={v:read(BASE/v/'execution-version.json') for v in VERSIONS}
    allowed={'runs/v021-support/20261029/student/journeys.mjs'}
    anchor=freezes[VERSIONS[0]]['source_hashes']
    differences={}
    for version,value in freezes.items():
        paths=set(anchor)|set(value['source_hashes'])
        changed=[p for p in sorted(paths) if anchor.get(p)!=value['source_hashes'].get(p)]
        if set(changed)-allowed:
            raise ValueError('Product/configuration drift: '+str(changed))
        if value['input_sha256']!=freezes[VERSIONS[0]]['input_sha256']:
            raise ValueError('Authored inputs changed')
        differences[version]=changed
    reports={v:collector.collect(ROOT,v) for v in VERSIONS}
    summaries={v:read(p/'summary.json') for v,p in reports.items()}
    OUT.mkdir()
    chosen={f'J{i:02d}':VERSIONS[1] for i in range(1,9)}
    chosen.update(J01=VERSIONS[0],J06=VERSIONS[3])
    cases=[];questions=[];interruptions=[];gaps=[];audio={};compact=[]
    for ident,version in chosen.items():
        case=read(reports[version]/(ident+'.json'))
        case['source_report']=str(reports[version]/(ident+'.json'))
        case['source_version']=version
        raw=read(Path(case['actual_json']))
        review={'human_education_and_listening':'H_PENDING','raw_status_preserved':case['status']}
        completed=next((s for s in raw.get('samples',[]) if s.get('label')=='completed'),None)
        boundary=completed.get('at_ms') if completed else None
        main=[p for p in case['playback'] if boundary is None or p['event']['at_ms']<=boundary]
        later=[p for p in case['playback'] if boundary is not None and p['event']['at_ms']>boundary]
        case['playback_partitions']={'boundary_event':'first saved completed screen before responsive/font settings inspection','boundary_at_ms':boundary,
            'requested_lesson':{'event_count':len(main),'valid_event_count':sum(bool(p['valid_explanation_by_record_linkage']) for p in main),'all_valid':bool(main) and all(p['valid_explanation_by_record_linkage'] for p in main)},
            'post_completion_UI_inspection':{'event_count':len(later),'valid_event_count':sum(bool(p['valid_explanation_by_record_linkage']) for p in later),
                'events':[{'at_ms':p['event']['at_ms'],'step_id':p['step_id'],'validation':p['validation'],'media':p['event'].get('media')} for p in later]},
            'interpretation':'Original full-event failures remain. Settings-to-classroom remount triggered an unwanted play attempt at the saved end position; full audible replay is not established. Blob bytes were sampled before late cleanup events and are missing for some post-completion attempts. This is both an app lifecycle issue and a measurement gap, not a corrected successful event.'}
        if ident=='J01':
            checks=case['evidence_requirements']
            exception=raw.get('errors')==['Student budget closure: TypeError: closed.ok is not a function']
            closure=raw.get('student_budget_closed') or {}
            good=bool(exception and not raw.get('blocked_requests') and closure.get('status')==200
                and closure.get('value',{}).get('state')=='closed' and raw.get('source_unchanged_at_end') is True
                and case['playback_partitions']['requested_lesson']['all_valid']
                and all(v for k,v in checks.items() if k not in {'no_browser_or_cleanup_errors','valid_bound_playback'}))
            review.update(technical_status='TECHNICAL_PLAYBACK_CONFIRMED_WITH_PRESERVED_HARNESS_ERROR' if good else 'NOT_ESTABLISHED',
                scope='Original FAILED_EVIDENCE_INTEGRITY remains. Only playback/board/source/normal-end/closed-budget evidence is separately reviewed.',
                exact_known_harness_error=exception,actual_budget_closed=closure.get('value',{}).get('state')=='closed',
                requested_lesson_playback=case['playback_partitions']['requested_lesson'],post_completion_inspection=case['playback_partitions']['post_completion_UI_inspection'],
                technical_requirements_except_separately_reported_errors={k:v for k,v in checks.items() if k not in {'no_browser_or_cleanup_errors','valid_bound_playback'}})
        if ident=='J04':
            review.update(full_question_coverage='PARTIAL',reason=case['spec']['followup'].get('known_coverage_limit') or
                'Selected zero row condition/rank explained; explicit comparison to the NULL row was not supplied. Question remains unchanged.')
        if ident=='J06':
            case['linked_previous_failed_attempts']=[]
            for prior_version in VERSIONS[1:3]:
                prior=read(reports[prior_version]/'J06.json')
                case['linked_previous_failed_attempts'].append({'actual_json':prior['actual_json'],'source_report':str(reports[prior_version]/'J06.json'),
                    'status':prior['status'],'failure':prior['failure'],'same_question_and_image':True,
                    'rerun_reason':'Saved-candidate label locator failure repaired and ultimately verified against actual saved DOM with real UI correction/confirmation before final retry; closed immutable caps were preserved.',
                    'extra_independent_questions':0,'original_OCR_preserved':True})
            case['saved_original_photo_correction_without_generation']=str(BASE/'saved-J06-correction-ui/result.json')
        case['separate_review']=review
        write(OUT/(ident+'.json'),case)
        cases.append(case)
        q=case['timings']['question_to_first_valid_explanation']
        questions.extend(copy.deepcopy(q))
        interruptions.extend({'case':ident,**x} for x in case['timings']['interruptions'])
        gaps.extend({'case':ident,**x} for x in case['timings']['stage_gaps'])
        for entry in summaries[version]['audio']:
            if entry['audio_id'] in {p['audio_id'] for p in case['playback']}:
                audio.setdefault(entry['audio_id'],entry)
        events=[]
        for question in q:
            played=next((p for p in case['playback'] if p.get('audio_id')==question.get('audio_id')),None)
            events.append({'input_kind':question.get('input_kind'),'status':question.get('status'),
                'first_valid_explanation_seconds':question['first_valid_explanation_ms']/1000 if question.get('first_valid_explanation_ms') is not None else None,
                'text_load_regime':question.get('text_model_load_regime'),'text_worker_evidence':question.get('text_worker_evidence'),
                'first_audio_cache_hit':played.get('tts_clip_cache_hit') if played else None,
                'first_audio_id':question.get('audio_id'),'tts_load_regime':question.get('tts_load_regime')})
        compact.append({'id':ident,'status':case['status'],'separate_review':review,'events':events,
            'photo':case['timings'].get('photo'),'photo_check':case.get('photo_check'),
            'interruptions':[{'old_audio_stopped_seconds':x['old_audio_stopped_ms']/1000 if x.get('old_audio_stopped_ms') is not None else None,
                'supplement_started_seconds':x['supplement_started_ms']/1000 if x.get('supplement_started_ms') is not None else None,
                'stop_evidence':x.get('old_audio_stop_evidence')} for x in case['timings']['interruptions']],
            'stage_gaps_seconds':[x['gap_ms']/1000 if x.get('gap_ms') is not None else None for x in case['timings']['stage_gaps']],
            'evidence_requirements':case['evidence_requirements'],'failure':case.get('failure'),'playback_partitions':case['playback_partitions'],
            'student_used':(raw.get('student_budget_before_close') or {}).get('used'),
            'audio_clip_events':len(case['playback']),'unique_audio_files':len({p['audio_id'] for p in case['playback']}),
            'linked_record':str(OUT/(ident+'.json'))})
    attempts=[];seen=set()
    for version in ['final-v021-r3',*VERSIONS]:
        for path in sorted((BASE/version).glob('J*/actual.json')):
            record=read(path)
            usage=(record.get('student_budget_before_close') or {}).get('used',{})
            ident=record.get('owned_session_id')
            if ident in seen and usage:raise ValueError('Duplicate student usage allocation')
            if ident:seen.add(ident)
            attempts.append({'case':record['id'],'version':version,'status':record['status'],'failure':record.get('failure'),
                'actual_json':str(path),'student_session':ident,'used':usage,'counted_as_new_distinct_question':False})
    totals={k:sum(a['used'].get(k,0) for a in attempts) for k in ['seconds','text_requests','new_audio_clips','vision_requests']}
    proof={'status':'PASS','allowed_harness_difference_only':sorted(allowed),'actual_changed_paths':differences,
        'all_other_source_setting_and_input_hashes_equal':True,'non_harness_frozen_files':len(anchor)-1,
        'production_py_ps1_count':len([p for p in anchor if p.startswith('src/edu_tutor/')]),
        'deployment_receipt':str(ROOT/'runs/v021-support/20261029/deployment-r3.json')}
    summary={'at':datetime.now(timezone.utc).isoformat(),'version':'final-v021-r3-combined','human_review':'H_PENDING','readiness':'NOT_READY',
        'provenance':read(BASE/'journeys.json')['provenance'],'same_product_build_proof':proof,'source_reports':{v:str(p) for v,p in reports.items()},
        'cases':[{'id':c['id'],'status':c['status'],'failure':c.get('failure'),'separate_review':c['separate_review'],'evidence':str(OUT/(c['id']+'.json'))} for c in cases],
        'question_events':questions,'interruptions':interruptions,'stage_gaps':gaps,'audio':list(audio.values()),
        'planned_distinct_journeys':8,'planned_question_events':10,'actual_attempts_including_harness_failures':attempts,
        'actual_total_usage_including_failed_attempts':totals,
        'question_to_audio':collector.measured_stats(q.get('first_valid_explanation_ms') for q in questions),
        'interrupt_to_native_pause':collector.measured_stats(q.get('old_audio_stopped_ms') for q in interruptions),
        'interrupt_to_supplement':collector.measured_stats(q.get('supplement_started_ms') for q in interruptions),
        'stage_gap':collector.measured_stats(q.get('gap_ms') for q in gaps),
        'interpretation':'Eight authored development journeys, not independent evaluation. J01 failed raw harness status remains; separate technical review may confirm linked playback. J04 full question remains partial. J06 repeated only after a reproduced harness cause fix and counts once in distinct questions; every original attempt and expense remains.'}
    write(OUT/'summary.json',summary)
    write(OUT/'compact-results.json',{'cases':compact,'usage':totals,'same_product_build_proof':proof,'readiness':'NOT_READY','human_review':'H_PENDING'})
    write(OUT/'same-product-build-proof.json',proof)
    collector.write_gallery(OUT,cases,audio)
    print(OUT)

if __name__=='__main__':main()
