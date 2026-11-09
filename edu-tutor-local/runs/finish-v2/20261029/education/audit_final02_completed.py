"""Snapshot-only education review. Reads completed development journeys, never final80."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import argparse

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / 'runs/finish-v2/20261029/student/final02'
OUT = ROOT / 'runs/finish-v2/20261029/education'

NOTES = {
    'J01': {
        'agent_finding': 'Executed CREATE/INSERT states and narration agree with the public question: member has two columns and zero rows, then one person is inserted without changing columns.',
        'educational_shortcomings': [
            'The spoken plan defines DDL but never names DML or explicitly connects INSERT to the requested DDL-versus-DML contrast. The raw text supplies that distinction, so text and spoken teaching coverage differ.',
            'This is evidence for this new example only; it does not verify free-form model prose or independent learning usability.'
        ],
        'critical_numerical_or_sql_contradiction_found_in_app_plan': False,
        'question_completeness': 'PARTIAL_CONCEPT_CONTRAST_IN_SPOKEN_PLAN',
    },
    'J02': {
        'agent_finding': 'The raw model supplied unquoted identifiers containing spaces, no executable CREATE/INSERT setup, and unexecuted Markdown before/after rows. The app blocked speech as an unverified concept lesson.',
        'educational_shortcomings': [
            'No actual value-change example or spoken explanation was delivered; safe stopping is not question-solving success.',
            'Unverified SQL and Markdown table text remain in the manual board/caption. The label discloses that it is unverified, but the displayed explanation is not an executed illustration.',
            'No numeric/original source problem was supplied: these invented example rows must remain separate from student-provided data.'
        ],
        'critical_numerical_or_sql_contradiction_found_in_app_plan': None,
        'question_completeness': 'FAILED_SAFE_STOP_NO_SPOKEN_LESSON',
    },
    'J03': {
        'agent_finding': 'The browser harness timed out finding the problem-type selector before any POST request or question_submitted event. No model answer or lesson exists for this attempt.',
        'educational_shortcomings': ['No teaching outcome can be assessed for this pre-submit automation failure. Keep it separate from a model or SQL accuracy failure.'],
        'critical_numerical_or_sql_contradiction_found_in_app_plan': None,
        'question_completeness': 'NOT_EVALUATED_PRE_SUBMIT_HARNESS_FAILURE',
    },
}

parser = argparse.ArgumentParser()
parser.add_argument('--ids', nargs='+', required=True)
parser.add_argument('--version', required=True)
args = parser.parse_args()
target = OUT / ('final02-education-read-review-' + args.version + '.json')
if target.exists():
    raise SystemExit('Never overwrite a prior read review')
rows = []
for ident in args.ids:
    path = BASE / ident / 'actual.json'
    data = json.loads(path.read_text('utf-8'))
    if data['status'] == 'RUNNING':
        raise SystemExit(f'{ident} is not complete; do not review a moving result')
    lesson = data.get('actual_lesson')
    if not lesson:
        choices = [r['value'] for r in data.get('responses', [])
            if isinstance(r.get('value'), dict) and 'plan' in r['value']]
        lesson = choices[-1] if choices else {}
    quality = data.get('quality') or {}
    raw = quality.get('raw_model_response') or lesson.get('fallback_text')
    if not raw:
        choices = [r['value'].get('fallback_text') for r in data.get('responses', [])
            if isinstance(r.get('value'), dict) and r['value'].get('fallback_text')]
        raw = choices[-1] if choices else None
    row = {'id': ident, 'source': path.relative_to(ROOT).as_posix(),
        'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'completed_at': data.get('completed_at'), 'technical_status': data['status'],
        'question': data.get('spec', {}).get('question'), 'raw_model_answer': raw,
        'post_request_paths': [r.get('path') for r in data.get('requests', []) if r.get('method') == 'POST'],
        'event_types': [e.get('type') for e in data.get('events', [])],
        'actual_app_answer': quality.get('actual_app_response'),
        'app_status': lesson.get('status'), 'app_reason': lesson.get('reason'),
        'failure': data.get('failure'), 'speech_allowed': lesson.get('speech_allowed'),
        'spoken_plan': [{'id': s['id'], 'title': s.get('title'), 'speech': s.get('speech')}
            for s in (lesson.get('plan') or {}).get('steps', [])],
        'example_effects': [{'operation': s.get('operation'), 'effects': s.get('effects')}
            for s in (lesson.get('example_evidence') or {}).get('steps', [])],
        'model_snapshot': quality.get('generation_snapshot'),
        'human_review': 'H_PENDING', 'audio_listened_by_human': False,
        'read_review_kind': 'Agent semantic/code-evidence review, not human educational or listening approval',
    }
    row.update(NOTES.get(ident, {'agent_finding': 'PENDING_AGENT_REVIEW'}))
    rows.append(row)
result = {'at': datetime.now(timezone.utc).isoformat(), 'source_version': 'final02',
    'scope': 'Original development journey evidence only; not final80; no model calls or source edits',
    'human_review': 'H_PENDING', 'records': rows}
target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(target.relative_to(ROOT).as_posix())
