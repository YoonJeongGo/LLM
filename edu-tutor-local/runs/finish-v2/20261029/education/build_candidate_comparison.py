"""Aggregate saved five-condition validation evidence; no final/model execution."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import statistics

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NAMES = ['validation-base-v1', 'validation-adapter-v1', 'validation-base-bf16-v1',
         'validation-adapter1-bf16-v1', 'validation-candidate4b-nf4-v1']
APP = 'result-app-offline-app-v4-plan-refresh.json'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    target = HERE / 'candidate-validation-comparison-app-v4.json'
    assert not target.exists(), 'Do not overwrite prior evidence'
    ledger = read(ROOT / 'runs/phase2/current/resource-budget.json')['requests']
    files = ['result-normalized.json', 'result-sql-counterexamples-v1.json', 'result-explicit-claims-v1.json', APP]
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'mode': 'saved_evidence_comparison_only',
              'new_inference_in_report': 0, 'final_holdout_read': False, 'results': {}}
    common_input = None; common_app = None
    for name in NAMES:
        folder = HERE / name
        values = {f: read(folder / f) for f in files}
        result = values['result-normalized.json']; protocol = result['protocol']; items = result['items']
        assert result['status'] == 'completed' and len(items) == 40 and not protocol['final_holdout_read']
        assert protocol['dataset_sha256'] == '99de8bc098caa5426297f30473e32cd3c2a8e3e29fc3531a9d600d2b7b932e34'
        assert protocol['max_new_tokens'] == 256 and protocol['do_sample'] is False and protocol['rag'] is False
        assert protocol['batch_size'] == 4 and len(result['batches']) == 10
        submissions = [read(folder / f'batch-{i:02d}' / 'submission.json') for i in range(1, 11)]
        public = [item for s in submissions for item in s['body']['items']]
        if common_input is None: common_input = public
        assert public == common_input
        app_hashes = values[APP]['source_hashes']
        if common_app is None: common_app = app_hashes
        assert app_hashes == common_app
        events = [i['raw_model_event'] for i in items]
        job_ids = {b['job_id'] for b in result['batches']}
        entries = [r for r in ledger if r.get('job_id') in job_ids]
        generations = [e['latency_seconds'] for e in events]
        loads = [e['model_load_seconds'] for e in events if e['model_load_count'] == 1]
        families = {}
        for item in items:
            f = families.setdefault(item['id'].rsplit('_', 1)[0], {'total': 0, 'fixed_fixture_match': 0, 'incomplete': 0})
            f['total'] += 1; f['fixed_fixture_match'] += item['sql_result_correct'] is True
            f['incomplete'] += item['finish_reason'] != 'eos'
        candidate = protocol.get('model_ref') == 'qwen3-4b-instruct-2507'
        expected_revision = 'cdbee75f17c01a7cc42f958dc650907174af0554' if candidate else '70d244cc86ccca08cf5af4e1e306ecf908b1ad5e'
        assert {e['revision'] for e in events} == {expected_revision}
        if candidate:
            assert all(e['model_ref'] == protocol['model_ref'] and e['model_id'] == protocol['model_id']
                       and e['precision'] == 'nf4' and set(e['eos_token_ids']) == {151645, 151643} for e in events)
        row = {'protocol': protocol, 'summary': result['summary'], 'families': families,
               'finish_reasons_as_historically_recorded': dict(Counter(i['finish_reason'] for i in items)),
               'executable_sql_outputs': sum(i.get('actual', {}).get('status') == 'executed' for i in items),
               'counterexamples': values[files[1]]['summary'], 'explicit_claims': values[files[2]]['summary'],
               'offline_app_v4': values[APP]['summary'], 'source_hashes_app_v4': app_hashes,
               'actual_first_inference': events[0].get('inference'),
               'time': {'first_batch_submitted_at': submissions[0]['submitted_at'], 'main_cli_started_at': result['started_at'],
                        'completed_at': result['finished_at'], 'generation_median_seconds': statistics.median(generations),
                        'generation_max_seconds': max(generations), 'generation_total_seconds': sum(generations),
                        'load_count': len(loads), 'load_median_seconds': statistics.median(loads), 'load_max_seconds': max(loads),
                        'load_total_seconds': sum(loads), 'output_tokens': sum(e['output_tokens'] for e in events),
                        'ledger_charged_seconds': sum(e['charged_seconds'] for e in entries),
                        'ledger_text_attempts': sum(e.get('text_requests', 1) for e in entries),
                        'peak_request_vram_bytes': max(e['peak_vram_bytes'] for e in events)},
               'input_token_lengths': {i['id']: i['raw_model_event']['input_tokens'] for i in items},
               'concept_answers_for_review': [{'id': i['id'], 'question': i['question'], 'answer': i['actual_answer']}
                                              for i in items if i['sql_result_correct'] is None],
               'evidence_hashes': {f: sha(folder / f) for f in files}}
        old = folder / 'result-app-offline-app-bounded-correction-v3.json'
        if old.exists(): row['previous_app_v3_summary_preserved'] = read(old)['summary']
        report['results'][name] = row
    report['comparison_pairs'] = [
        {'left': NAMES[0], 'right': NAMES[1], 'effect': 'training_at_nf4'},
        {'left': NAMES[2], 'right': NAMES[3], 'effect': 'training_at_bf16'},
        {'left': NAMES[0], 'right': NAMES[4], 'effect': 'model_checkpoint_replacement_at_nf4'},
        {'left': NAMES[2], 'right': NAMES[4], 'effect': 'model_and_precision_deployment_bundle_not_pure_model_effect'}]
    report['limits'] = [
        'Same original public messages and scoring data do not guarantee full explanation correctness. SQL fixed-fixture equality, counterexample disproof and explicit prose claims remain separate.',
        'Historical installed generation inherited two EOS IDs but its finish classifier checked only151645. Raw outputs/old grades are unchanged; last generated token was not retained. Candidate explicitly generated and classified both EOS IDs.',
        'Candidate uses its own official nonthinking template; input token lengths can differ despite identical public messages. This compares checkpoint configurations, not parameter count alone.',
        'The first candidate batch was screened once then reused by GET. Main CLI start time is later than first submission. Review gap is not model processing time.',
        'Five conditions include different historical server revisions and concurrent CPU checks. Batch generation/load timing is not student first-explanation latency or a controlled speed benchmark.',
        'App v3 falsely treated the BF16 base COUNT DISTINCT same-column IS NOT NULL condition as needing correction. v4 recognizes equivalence; app acceptance remains5/35 and corrected count changes5 to0. This is grader correction, not model improvement.',
        'The first app-v4 records straddled a verified.py plan change, so their hashes were rejected as a same-version comparison. All five conditions were reprocessed into separate app-v4-plan-refresh files and the full source-hash equality is required here.',
        'App results are saved-answer CPU reprocessing with original public fixtures, not live audio/board sessions. No final80 read, no adapter promotion, no human review performed.'
    ]
    report['same_public_inputs'] = True
    report['same_app_v4_source_hashes'] = True
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(str(target))
    print(json.dumps({n: {'raw': r['summary'], 'app': r['offline_app_v4'], 'counterexamples': r['counterexamples']} for n, r in report['results'].items()}))


if __name__ == '__main__':
    main()
