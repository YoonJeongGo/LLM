"""CPU evidence aggregation only; reads completed validation outputs, never final data."""
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import hashlib
import json
import sqlite3
import statistics

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
NAMES = ['validation-base-v1', 'validation-adapter-v1',
         'validation-base-bf16-v1', 'validation-adapter1-bf16-v1']
APP = 'result-app-offline-app-bounded-correction-v3.json'
FILES = ['result-normalized.json', 'result-sql-counterexamples-v1.json',
         'result-explicit-claims-v1.json', APP]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def public_inputs(folder):
    return [item for i in range(1, 11)
            for item in read(folder / f'batch-{i:02d}' / 'submission.json')['body']['items']]


def main():
    target = HERE / 'validation-comparison-precision-and-app-v3.json'
    if target.exists():
        raise ValueError('Preserve the existing comparison; use a new version for new evidence')
    ledger = read(ROOT / 'runs/phase2/current/resource-budget.json')['requests']
    result = {'created_at': datetime.now(timezone.utc).isoformat(),
              'mode': 'saved_validation_evidence_aggregation_only',
              'new_model_calls_in_this_report': 0, 'final_holdout_read': False,
              'comparison_basis': 'same validation40/public messages/max256/deterministic batch4; precision and trained adapter are separate factors',
              'results': {}}
    first_inputs = public_inputs(HERE / NAMES[0])
    first = read(HERE / NAMES[0] / FILES[0])
    first_input_tokens = {i['id']: i['raw_model_event']['input_tokens'] for i in first['items']}
    first_app_hashes = read(HERE / NAMES[0] / APP)['source_hashes']
    dataset_hash = first['protocol']['dataset_sha256']
    for name in NAMES:
        folder = HERE / name
        docs = {f: read(folder / f) for f in FILES}
        raw = docs[FILES[0]]
        protocol = raw['protocol']
        assert raw['status'] == 'completed' and len(raw['items']) == 40
        assert protocol['final_holdout_read'] is False
        assert protocol['dataset_sha256'] == dataset_hash
        assert protocol['max_new_tokens'] == 256 and protocol['do_sample'] is False
        assert protocol['batch_size'] == 4 and protocol['rag'] is False
        assert public_inputs(folder) == first_inputs
        assert docs[APP]['source_hashes'] == first_app_hashes
        events = [i['raw_model_event'] for i in raw['items']]
        assert {i['id']: i['raw_model_event']['input_tokens'] for i in raw['items']} == first_input_tokens
        assert {e['revision'] for e in events} == {'70d244cc86ccca08cf5af4e1e306ecf908b1ad5e'}
        generations = [e['latency_seconds'] for e in events]
        loads = [e['model_load_seconds'] for e in events if e.get('model_load_count') == 1]
        ids = {b['job_id'] for b in raw['batches']}
        charged = [x for x in ledger if x.get('job_id') in ids]
        families = {}
        for item in raw['items']:
            family = item['id'].rsplit('_', 1)[0]
            f = families.setdefault(family, {'total': 0, 'original_fixture_result_match': 0,
                                            'concept_pending': 0, 'incomplete': 0})
            f['total'] += 1
            f['original_fixture_result_match'] += item['sql_result_correct'] is True
            f['concept_pending'] += item['sql_result_correct'] is None
            f['incomplete'] += item['finish_reason'] != 'eos'
        result['results'][name] = {
            'adapter': protocol['adapter'], 'precision': protocol.get('precision', 'historical_nf4'),
            'actual_inference_first_event': events[0].get('inference'),
            'normalized_parser': raw['grading_protocol'], 'summary': raw['summary'],
            'finish_reasons': dict(Counter(i['finish_reason'] for i in raw['items'])),
            'executable_sql_outputs': sum(i.get('actual', {}).get('status') == 'executed' for i in raw['items']),
            'complete_nonempty_raw_responses': sum(i['finish_reason'] == 'eos' and bool(i.get('actual_answer', '').strip()) for i in raw['items']),
            'families': families,
            'counterexamples': docs[FILES[1]]['summary'],
            'explicit_claims': docs[FILES[2]]['summary'], 'offline_app': docs[APP]['summary'],
            'time': {'generation_median_seconds': statistics.median(generations),
                     'generation_max_seconds': max(generations), 'generation_total_seconds': sum(generations),
                     'generated_token_total': sum(e['output_tokens'] for e in events),
                     'load_count': len(loads), 'load_median_seconds': statistics.median(loads),
                     'load_max_seconds': max(loads), 'load_total_seconds': sum(loads),
                     'ledger_charged_seconds': sum(x['charged_seconds'] for x in charged),
                     'ledger_text_attempts': sum(x.get('text_requests', 1) for x in charged),
                     'peak_vram_bytes': max(e['peak_vram_bytes'] for e in events)},
            'measurement_dates_utc': {'started': raw['started_at'], 'finished': raw['finished_at']},
            'evidence_hashes': {f: sha(folder / f) for f in FILES},
            'source_hashes_app': first_app_hashes,
            'concept_answers_for_review': [{'id': i['id'], 'question': i['question'], 'actual_answer': i['actual_answer']}
                                          for i in raw['items'] if i['sql_result_correct'] is None]}
    result['protocol_checks'] = {'same_validation_sha256': dataset_hash,
        'exact_public_model_inputs_equal_all_four_runs': True, 'same_current_app_grader_hashes': True,
        'same_per_question_input_tokens': True, 'same_pinned_base_revision': True,
        'private_answers_added_to_model_or_app_input': False}
    # Independent tiny SQLite control, not fed to any model or product prompt.
    con = sqlite3.connect(':memory:')
    con.execute('CREATE TABLE evidence_check (id INTEGER, val INTEGER NOT NULL)')
    probes = []
    for row_id, value in [(1, None), (2, 0), (3, '')]:
        try:
            con.execute('INSERT INTO evidence_check (id,val) VALUES (?,?)', (row_id, value))
            probes.append({'value': value, 'status': 'inserted'})
        except sqlite3.IntegrityError as exc:
            probes.append({'value': value, 'status': 'rejected', 'error': str(exc)})
    result['not_null_sqlite_control'] = {'sqlite_version': sqlite3.sqlite_version, 'probes': probes,
        'rows': con.execute('SELECT id,val FROM evidence_check ORDER BY id').fetchall(),
        'interpretation': 'NOT NULL rejects NULL. Numeric zero and empty text are not NULL in SQLite. This check does not automatically grade full prose or replace human review.'}
    con.close()
    result['concept_failure_reading'] = {
        'review_type': 'agent reading of saved answers against independent SQLite NOT NULL control; not human review and not a new automatic pass metric',
        'critical_wrong_or_self_contradictory_ids': {
            'validation-base-v1': [f'finish_v2_notnull_constraint_{i:02d}' for i in range(1, 6)],
            'validation-base-bf16-v1': ['finish_v2_notnull_constraint_01', 'finish_v2_notnull_constraint_03'],
            'validation-adapter-v1': [f'finish_v2_notnull_constraint_{i:02d}' for i in range(1, 6)],
            'validation-adapter1-bf16-v1': [f'finish_v2_notnull_constraint_{i:02d}' for i in range(1, 6)]},
        'remaining_concept_items_not_approved_for_human_quality': True,
        'adapter1_promotion': 'TRAINED_NOT_PROMOTED; core concept errors persist in NF4 and BF16',
        'base_readiness': 'NOT_READY; BF16 also emits critical NOT NULL errors'}
    result['limitations'] = [
        'Original-fixture output equality is not semantic correctness. Counterexamples disprove some coincidental matches; absence of a counterexample is not proof.',
        'All five concept answers remain excluded from automatic pass counts. Stored original answers include critical NOT NULL errors; human review is pending.',
        'Explicit-array claim checking covers only parseable result-array statements. Fewer such statements does not mean fewer prose errors.',
        'App results are CPU reprocessing of saved model answers with public original fixtures. They are not fresh conversations or browser/audio validation.',
        'Historical NF4 and BF16 runs use different server revisions/telemetry. Adapter1 BF16 ran alongside CPU/browser regression. Timings are reference only, not an isolated speed benchmark or student first-explanation latency.',
        'Training2 was interrupted with no completed adapter evidence; it is not one of the compared adapters. Reserved 7200 seconds remains deducted, not asserted as measured training runtime.',
        'No final80 contents were read. No adapter is promoted by this report. NOT_READY and H_PENDING remain.'
    ]
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(str(target))
    for name, value in result['results'].items():
        print(name, value['summary'], value['offline_app'], value['counterexamples'])


if __name__ == '__main__':
    main()
