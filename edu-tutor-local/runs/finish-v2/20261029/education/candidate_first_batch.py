"""First four validation inputs only; never starts the remaining 36 automatically."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'scripts'))
from finish_education_live import Client, submit_once, await_job, result_of, save, stamp
from edu_tutor.models.text_candidate import CANDIDATE, MODEL_ID, REVISION
from edu_tutor.training.data import load_records
from edu_tutor.training.finish_score import public_item, score_response, summarize
from edu_tutor.problems.sql_response import extract_sql_candidate

RUN = 'validation-candidate4b-nf4-v1'


def main(execute=False):
    records = load_records([ROOT / 'runs/finish-v2/20261028/education/development/validation.jsonl'])
    assert len(records) == 40 and all(r['split'] == 'validation' for r in records)
    selected = records[:4]
    folder = ROOT / 'runs/finish-v2/20261029/education' / RUN
    batch = folder / 'batch-01'
    body = {'adapter': 'base', 'precision': 'nf4', 'max_new_tokens': 256,
            'items': [public_item(r) for r in selected], 'model_ref': CANDIDATE}
    client = Client() if execute else None
    journal_path = batch / 'submission.json'
    submitted = journal_path.exists() and json.loads(journal_path.read_text(encoding='utf-8')).get('job_id')
    if execute and not submitted:
        save(folder / 'first-batch-budget-before.json', client.preflight('text', 4))
    journal = submit_once(client, batch, '/api/evaluations/text-batch', body, 'evaluation', execute=execute)
    if not execute:
        print(json.dumps({'status': 'prepared_only', 'run': RUN, 'request_id': journal['request_id'],
                          'new_calls': 0, 'next_36_automatically_started': False}))
        return
    job = await_job(client, batch, journal, 365)
    raw = result_of(job)
    save(batch / 'raw-result.json', raw)
    events = raw.get('items', [])
    by_id = {x['id']: x for x in events}
    runtime_ok = job['state'] == 'succeeded' and len(events) == 4 and set(by_id) == {x['id'] for x in selected}
    failures = []
    scores = []
    for record in selected:
        event = by_id.get(record['id'], {})
        checks = {
            'pinned_identity': event.get('model_ref') == CANDIDATE and event.get('model_id') == MODEL_ID and event.get('revision') == REVISION,
            'actual_nf4': event.get('precision') == 'nf4' and event.get('inference', {}).get('actual_is_loaded_in_4bit') is True,
            'reviewed_eos_list': set(event.get('eos_token_ids', [])) == {151645, 151643},
            'complete_nonempty': event.get('finish_reason') == 'eos' and bool(event.get('text', '').strip()),
        }
        failures.extend({'id': record['id'], 'check': k} for k, ok in checks.items() if not ok)
        score = score_response(record, event.get('text', ''), event.get('finish_reason', 'missing'), extractor=extract_sql_candidate)
        score.update(question=next(m['content'] for m in record['messages'] if m['role'] == 'user'),
                     actual_answer=event.get('text'), raw_model_event=event, job_id=job['id'])
        scores.append(score)
    runtime_ok = runtime_ok and not failures
    report = {'recorded_at': stamp(), 'run': RUN, 'job_id': job['id'], 'job_state': job['state'],
              'runtime_gate_passed': runtime_ok, 'failures': failures, 'items': scores, 'summary': summarize(scores),
              'next_36_automatically_started': False, 'final_holdout_read': False,
              'notice': 'First four inputs are part of the same frozen validation40. Full CLI will read this existing job without a second POST. Runtime success is not educational approval; inspect actual answers before continuing.'}
    save(folder / 'first-batch-review.json', report)
    print(json.dumps({k: report[k] for k in ['job_id', 'job_state', 'runtime_gate_passed', 'failures', 'summary', 'next_36_automatically_started']}, ensure_ascii=False))
    if not runtime_ok:
        raise RuntimeError('First candidate batch failed; preserve evidence and do not continue/retry automatically')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--execute', action='store_true'); args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    main(args.execute)
