"""Read-only composition of two test-harness versions of one production build.

Never relabel earlier evidence or recompute it against the current source tree.
Only web/scripts/finish-student-journeys.mjs may differ in frozen source hashes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

ALLOWED_TEST_CHANGE = 'web/scripts/finish-student-journeys.mjs'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def compare(first, second):
    a, b = read(first/'execution-version.json'), read(second/'execution-version.json')
    if a['version'] != first.name or b['version'] != second.name:
        raise ValueError('Version label/path mismatch')
    x, y = a['source_hashes'], b['source_hashes']
    if set(x) != set(y):
        raise ValueError('Frozen source inventory changed')
    different = [name for name in x if x[name] != y[name]]
    if different != [ALLOWED_TEST_CHANGE] and set(different) != {ALLOWED_TEST_CHANGE}:
        raise ValueError('Expected exactly one reviewed harness-file change, not production/input drift: '+str(different))
    if a['input_sha256'] != b['input_sha256'] or a['authorization_id'] != b['authorization_id']:
        raise ValueError('Question inputs or approval scope changed')
    for key in ('model', 'speech'):
        if a['state'][key] != b['state'][key]:
            raise ValueError('Effective '+key+' differs between frozen versions')
    product = {name: value for name, value in x.items() if name != ALLOWED_TEST_CHANGE}
    mapping = {f'J{i:02}': str((first if i <= 2 else second)/f'J{i:02}'/'actual.json') for i in range(1, 9)}
    return {'status': 'SAME_FROZEN_PRODUCTION_DIFFERENT_TEST_HARNESS',
            'first_version': a['version'], 'second_version': b['version'],
            'first_freeze': {'path': str(first/'execution-version.json'), 'sha256': sha(first/'execution-version.json')},
            'second_freeze': {'path': str(second/'execution-version.json'), 'sha256': sha(second/'execution-version.json')},
            'different_frozen_files': {name: {'first': x[name], 'second': y[name]} for name in different},
            'production_and_input_hash': digest(product), 'identical_frozen_files_count': len(product),
            'input_sha256': a['input_sha256'], 'model': a['state']['model'], 'speech': a['state']['speech'],
            'case_mapping': mapping, 'model_calls': 0,
            'boundary': 'Same frozen production/input/settings/dist; distinct test-harness versions. Running API PID/birth deployment proof is a separate coordinator artifact. Old failed J03 is preserved and excluded from the chosen latest J03, not rewritten.'}


def stats(values):
    usable = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return {'measured_count': len(usable), 'median_ms': statistics.median(usable) if usable else None,
            'max_ms': max(usable) if usable else None}


def merge(receipt, first_report, second_report):
    summaries = [read(p/'summary.json') for p in (first_report, second_report)]
    if [s['version'] for s in summaries] != [receipt['first_version'], receipt['second_version']]:
        raise ValueError('Collector summary versions do not match the reviewed freezes')
    selected, questions, interruptions, gaps = [], [], [], []
    for number in range(1, 9):
        case_id = f'J{number:02}'
        summary = summaries[0 if number <= 2 else 1]
        case = next(c for c in summary['cases'] if c['id'] == case_id)
        if not case.get('evidence'):
            raise ValueError('Chosen case lacks completed collected evidence: '+case_id)
        evidence_path = Path(case['evidence'])
        evidence = read(evidence_path)
        actual = Path(receipt['case_mapping'][case_id])
        if Path(evidence['actual_json']).resolve() != actual.resolve() or evidence['actual_sha256'] != sha(actual):
            raise ValueError('Selected actual artifact/hash differs: '+case_id)
        actual_data = read(actual)
        if actual_data['version'] != summary['version'] or not actual_data.get('completed_at') or actual_data.get('status') == 'RUNNING':
            raise ValueError('Selected actual is not a completed record of the expected version')
        expected_freeze = summary['frozen_execution']
        receipt_freeze = receipt['first_freeze'] if number <= 2 else receipt['second_freeze']
        if digest(expected_freeze) != digest(read(Path(receipt_freeze['path']))):
            raise ValueError('Collected freeze differs from the reviewed freeze')
        selected.append({**case, 'source_version': summary['version'], 'evidence_sha256': sha(evidence_path),
                         'actual_json': str(actual), 'actual_sha256': sha(actual)})
        for key, target in [('question_events', questions), ('interruptions', interruptions), ('stage_gaps', gaps)]:
            target.extend({**r, 'source_version': summary['version']} for r in summary[key] if r.get('case') == case_id)
    if len(questions) != 10:
        raise ValueError('Preserve all ten planned question events, including failures/safe stop')
    return {'status': 'COMPOSED_EVIDENCE_NOT_PRODUCT_ACCEPTANCE', 'readiness': 'NOT_READY', 'human_review': 'H_PENDING',
            'same_product_receipt': receipt,
            'source_summaries': [{'path': str(p/'summary.json'), 'sha256': sha(p/'summary.json')} for p in (first_report, second_report)],
            'cases': selected, 'question_events': questions, 'interruptions': interruptions, 'stage_gaps': gaps,
            'latency_denominator': 10, 'question_to_audio': stats(q.get('first_valid_explanation_ms') for q in questions),
            'interrupt_to_native_pause': stats(q.get('old_audio_stopped_ms') for q in interruptions),
            'interrupt_to_supplement': stats(q.get('supplement_started_ms') for q in interruptions),
            'stage_gap': stats(g.get('gap_ms') for g in gaps), 'stage_gap_denominator': len(gaps),
            'boundary': 'J01/J02 from first harness and J03–J08 from revised harness. Same production hash receipt attached. No unchanged-all-source claim, no repeated successful model calls for hash alignment, no overwritten failure.',
            'model_calls': 0, 'production_writes': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--first', type=Path, required=True)
    parser.add_argument('--second', type=Path, required=True)
    parser.add_argument('--first-report', type=Path)
    parser.add_argument('--second-report', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Preserve prior output')
    if bool(args.first_report) != bool(args.second_report):
        parser.error('Supply both collector report directories for merge')
    result = compare(args.first.resolve(), args.second.resolve())
    if args.first_report:
        result = merge(result, args.first_report.resolve(), args.second_report.resolve())
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'output': str(args.output.resolve())}))
