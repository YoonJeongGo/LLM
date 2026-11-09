"""Read-only evidence summary of actual J04/J05; no API or model calls."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'runs/finish-v2/20261029/education/final02-harness2-j04-j05-read-review.json'
if OUT.exists():
    raise SystemExit('Preserve earlier review; choose another file for a new review')
results = []
for name in ['J04','J05']:
    path = ROOT / 'runs/finish-v2/20261029/student/final02-harness2' / name / 'actual.json'
    d = json.loads(path.read_text('utf-8'))
    assert d['status'] == 'COMPLETED_ACTUAL_JOURNEY_H_PENDING'
    before = d['before']['budget']['active_execution_allowance']
    after = d['after']['active_execution_allowance']
    ev = d['events']
    submit = next(e for e in ev if e['type']=='question_submitted')
    first = next(e for e in ev if e['type']=='audio_playing' and not e.get('supplement'))
    interruption = next(e for e in ev if e['type']=='interruption_submitted')
    media = interruption['media']
    pause = next((e for e in d['native_media'] if e['type']=='pause' and e['at_ms']>=interruption['at_ms']
        and e.get('media_id')==media.get('media_id') and e.get('epoch')==media.get('epoch')
        and e.get('current_src')==media.get('current_src')),None)
    supplemental = next(e for e in ev if e['type']=='audio_playing' and e.get('supplement'))
    original = d['actual_lesson']; plan = original['plan']; supplements = {}
    for response in d['responses']:
        value = response.get('value')
        if isinstance(value,dict) and isinstance(value.get('plan'),dict) and value.get('id')!=original['id']:
            supplements[value['id']] = value
    exact = next(v for v in supplements.values() if v['id']==supplemental.get('lesson_id'))
    record = {'id':name,'source':path.relative_to(ROOT).as_posix(),
        'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'question':d['spec']['question'],'public_query_supplied_by_test_input':d['spec']['query'],
        'raw_model_answer':d['quality']['raw_model_response'],
        'app_answer':d['quality']['actual_app_response'],
        'raw_sql_generation_accuracy_claim':False,
        'raw_vs_app_boundary':'The query is supplied as part of the original question. SQLite and independent calculations establish the app result, not new SQL-writing capability.',
        'main_speeches':[s['speech'] for s in plan['steps']],
        'supplement_question':exact['plan']['question_text'],
        'supplement_speeches':[s['speech'] for s in exact['plan']['steps']],
        'supplement_texts':[a['text'] for s in exact['plan']['steps'] for a in s['board_actions'] if a['type']=='text'],
        'supplement_highlights':[a for s in exact['plan']['steps'] for a in s['board_actions'] if a['type']=='highlight'],
        'technical_requirements_record':d['requirements'],
        'actual_answer_matches_supplied_private_oracle':d['quality']['app_result_matches_private_oracle'],
        'read_review':{
            'actual_sql_recomputed_in_disposable_sqlite':True,
            'numerical_or_column_contradiction_found':False,
            'selected_row_where_reason_agrees_with_source':True,
            'spoken_supplement_scope':'WHERE inclusion only; the board explicitly labels this limit and separately shows group and HAVING evidence',
            'limitation':'The spoken supplement does not recite the full group/HAVING result rationale. Completeness/naturalness for a student remains a human review item.',
            'human_review':'H_PENDING','human_listening_performed':False,
            'agent_visual_inspection': ['J05 completed.png: original, grouped totals and final table plus connecting arrow rendered'] if name=='J05' else [],
            'geometry_boundary':'J03 equation glyph pointer defect was independently found by coordinator; these cases do not establish complete pointer accuracy across the product.',
        },
        'timing_seconds':{
            'question_to_first_explanation_playing':round((first['at_ms']-submit['at_ms'])/1000,6),
            'interruption_to_native_audio_pause':round((pause['at_ms']-interruption['at_ms'])/1000,6) if pause else None,
            'interruption_to_supplement_playing':round((supplemental['at_ms']-interruption['at_ms'])/1000,6),
            'recorded_stage_gaps':[round(e['gap_ms']/1000,6) for e in ev if e['type']=='stage_gap'],
            'measurement':'Browser performance.now with exact original media identity for pause; audio onPlaying, not human first-word listening',
        },
        'original_generation':d['quality'].get('generation_snapshot'),
        'scope_delta':{'text':after['text_used']-before['text_used'],
            'new_audio_attempts':before['audio_remaining']-after['audio_remaining'],
            'vision':before['vision_remaining']-after['vision_remaining'],
            'model_seconds':round(before['seconds_remaining']-after['seconds_remaining'],3)},
        'source_unchanged_at_end':d['source_unchanged_at_end'],
    }
    results.append(record)
repair_path = ROOT / 'runs/finish-v2/20261029/stored-j02-actual-repair/result.json'
repair = json.loads(repair_path.read_text('utf-8'))
report = {'at':datetime.now(timezone.utc).isoformat(),'review':'Agent evidence reading; not human education/listening approval',
    'records':results,'next_cases_executed':[],'J06_J07_J08':'NOT_RUN_PAUSED_FOR_GLYPH_FIX',
    'budget_after_J05':after,
    'later_separate_old_J02_repair':{'evidence':repair_path.relative_to(ROOT).as_posix(),
        'status':repair['status'],'new_lesson_id':repair['new_lesson_id'],'job_id':repair['job_id'],
        'new_text_repair_calls':1,'tts_calls':repair['tts_calls'],
        'original_lesson_unchanged':repair['original_lesson_unchanged'],
        'original_message_unchanged':repair['original_message_unchanged'],
        'meaning':'A failed stored-answer repair, not a successful new lesson or model accuracy improvement'},
    'final80_opened':False,'current_docs_changed':False,'no_further_submissions':True}
OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'report':OUT.relative_to(ROOT).as_posix(),'cases':[{'id':r['id'],
    'timing':r['timing_seconds'],'delta':r['scope_delta']} for r in results]},ensure_ascii=False,indent=2))
