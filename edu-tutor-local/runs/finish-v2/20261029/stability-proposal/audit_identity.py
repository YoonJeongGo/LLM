"""Read only exported new8 answers. No API/model imports or production writes."""
import argparse
import hashlib
import json
from pathlib import Path


def checks(snapshot, expected):
    info = snapshot.get('inference') or {}
    dtypes = info.get('actual_parameter_dtypes_elements') or {}
    return {
        'worker_origin': snapshot.get('source') == 'worker_metadata',
        'installed_model_id': snapshot.get('model_id') == expected['model_id'],
        'installed_revision': snapshot.get('revision') == expected['revision'],
        'base_adapter': snapshot.get('adapter_id') == 'base',
        'requested_bf16': snapshot.get('requested_precision') == 'bf16' and info.get('requested_precision') == 'bf16',
        'actual_unquantized': info.get('actual_is_loaded_in_4bit') is False and info.get('quantization') == 'none',
        'actual_bf16_parameters': info.get('load_dtype') == 'torch.bfloat16' and set(dtypes) == {'torch.bfloat16'}
            and all(type(n) is int and n > 0 for n in dtypes.values()),
        'actual_cuda0': info.get('actual_parameter_devices') == ['cuda:0'],
        'two_eos': type(snapshot.get('eos_token_ids')) is list and len(snapshot['eos_token_ids']) == 2
            and all(type(x) is int for x in snapshot['eos_token_ids']) and set(snapshot['eos_token_ids']) == {151645, 151643},
    }


def audit(report_dir):
    summary = json.loads((report_dir / 'summary.json').read_text(encoding='utf-8'))
    expected = summary['frozen_execution']['state']['model']
    rows, missing = [], []
    for case in summary['cases']:
        data = json.loads(Path(case['evidence']).read_text(encoding='utf-8'))
        evidence = data.get('actual_model_evidence') or []
        if not evidence:
            if not (data.get('missing_condition_safety') and all(data['missing_condition_safety'].values())):
                missing.append({'case': case['id'], 'reason': 'No actual model evidence; not an identity pass'})
            continue
        for item in evidence:
            snap = item.get('snapshot') or {}
            values = checks(snap, expected)
            values['request_reservation_bound'] = item.get('pass') is True
            rows.append({'case': case['id'], 'message_id': item.get('message_id'), 'kind': 'final_snapshot',
                         'pass': all(values.values()), 'checks': values, 'snapshot': snap})
        for answer in data.get('answers') or []:
            for attempt in (answer.get('raw_model') or {}).get('attempts') or []:
                snap = attempt.get('generation_snapshot') or {}
                values = checks(snap, expected)
                rows.append({'case': case['id'], 'message_id': answer.get('id'), 'kind': 'attempt',
                             'attempt': attempt.get('attempt'), 'pass': all(values.values()), 'checks': values, 'snapshot': snap})
    return {'scope': 'Independent identity audit; does not alter collector or imply education quality',
            'source_summary_sha256': hashlib.sha256((report_dir / 'summary.json').read_bytes()).hexdigest(),
            'expected': expected, 'rows': rows, 'missing_model_cases': missing,
            'status': 'PASS_IDENTITY_ONLY' if rows and all(r['pass'] for r in rows) and not missing else 'INCOMPLETE_OR_IDENTITY_FAILURE',
            'model_calls': 0, 'production_writes': 0}


def audit_actual(path):
    """Before collection, inspect only final browser records and linked ledger rows."""
    root = Path(__file__).resolve().parents[4]
    record = json.loads(path.read_text(encoding='utf-8'))
    if record.get('status') in {'RUNNING', None} or not record.get('completed_at'):
        raise ValueError('Do not audit a running browser record')
    expected = record['before']['model']
    messages, lessons = {}, {}
    def visit(value):
        if isinstance(value, dict):
            if value.get('role') == 'assistant' and value.get('id'):
                if value['id'] in messages and messages[value['id']] != value:
                    raise ValueError('Conflicting assistant snapshots in one browser record')
                messages[value['id']] = value
            if value.get('source_message_id') and 'is_demo' in value and value.get('id'):
                lessons[value['id']] = value
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    for response in record.get('responses', []):
        visit(response.get('value'))
    ledger = json.loads((root / 'runs/phase2/current/resource-budget.json').read_text(encoding='utf-8'))
    rows = []
    for answer in messages.values():
        posted = next((r['value'] for r in record['responses'] if r.get('method') == 'POST'
                       and isinstance(r.get('value'), dict) and r['value'].get('request_id') == answer.get('request_id')), {})
        reservations = [r for r in ledger['requests'] if r.get('job_id') == posted.get('job_id') and r.get('kind') in {'text', 'text_batch'}]
        for kind, attempt, snap in [('final_snapshot', None, answer.get('generation_snapshot') or {}),
                                  *[('attempt', a.get('attempt'), a.get('generation_snapshot') or {}) for a in answer.get('model_attempts') or []]]:
            values = checks(snap, expected)
            values['request_reservation_bound'] = bool(reservations) and all(r.get('status') == 'completed' and
                r.get('execution_allowance_id') == record['before']['budget']['accounting_scope'] for r in reservations)
            rows.append({'case': record['id'], 'message_id': answer['id'], 'kind': kind, 'attempt': attempt,
                         'checks': values, 'pass': all(values.values()), 'snapshot': snap,
                         'reservation_ids': [r.get('id') for r in reservations]})
    # Concept example repair is a lesson job, separate from the original answer.
    # Failed generation can still have actual precision metadata; retain its
    # failure/acceptance separately instead of turning identity into success.
    for lesson in lessons.values():
        for attempt in (lesson.get('generation') or {}).get('example_model_attempts') or []:
            if attempt.get('kind') != 'repair':
                continue
            posted = next((r['value'] for r in record['responses'] if r.get('method') == 'POST'
                and r.get('path') == '/api/lessons/'+lesson['id']+'/generate' and isinstance(r.get('value'), dict)), {})
            reservations = [r for r in ledger['requests'] if r.get('job_id') == posted.get('job_id') and r.get('kind') in {'text', 'text_batch'}]
            snap = attempt.get('generation_snapshot') or {}
            values = checks(snap, expected)
            values['repair_reservation_accounted_in_scope'] = bool(reservations) and all(r.get('status') in {'completed', 'failed_or_cancelled'} and
                r.get('execution_allowance_id') == record['before']['budget']['accounting_scope'] for r in reservations)
            rows.append({'case': record['id'], 'lesson_id': lesson['id'], 'kind': 'concept_example_repair',
                'attempt': attempt.get('attempt'), 'checks': values, 'pass': all(values.values()), 'snapshot': snap,
                'generation_state': attempt.get('state'), 'accepted': attempt.get('accepted'),
                'reservation_states': [r.get('status') for r in reservations],
                'boundary': 'Precision identity only; failed or rejected repair remains failed/rejected.'})
    safe_stop = record.get('status') == 'EXPECTED_MISSING_CONDITION_STOP_NO_EXPLANATION' and not rows
    return {'scope': 'Read-only actual browser record identity audit; no education or latency reclassification',
            'source_actual_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'actual': str(path.resolve()),
            'expected': expected, 'rows': rows, 'model_calls': 0, 'production_writes': 0,
            'status': 'NOT_APPLICABLE_PHOTO_SAFE_STOP' if safe_stop else 'PASS_IDENTITY_ONLY'
                if rows and all(r['pass'] for r in rows) else 'INCOMPLETE_OR_IDENTITY_FAILURE'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--report-dir', type=Path)
    mode.add_argument('--actual', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Preserve old output; choose a new file')
    result = audit_actual(args.actual.resolve()) if args.actual else audit(args.report_dir.resolve())
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'output': str(args.output.resolve()), 'rows': len(result['rows'])}))
    raise SystemExit(0 if result['status'] in {'PASS_IDENTITY_ONLY', 'NOT_APPLICABLE_PHOTO_SAFE_STOP'} else 1)
