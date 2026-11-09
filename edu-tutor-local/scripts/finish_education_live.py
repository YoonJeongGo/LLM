"""Explicit authenticated local experiments; no auto retry or adapter promotion.

Prepare is the default. --execute is required to submit work. Interrupted POSTs
are recovered only by reading an already-created request ID, never reposted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from edu_tutor.training.finish_score import public_item, score_response, summarize
from edu_tutor.training.data import load_records, validate_dataset

SCOPE = 'finish-local-tutor-20261028-v1'
TERMINAL = {'succeeded', 'failed', 'cancelled', 'interrupted', 'blocked'}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def save(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


class Client:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.token = (self.root / '.local/auth-token').read_text(encoding='utf-8').strip()

    def call(self, path, body=None):
        request = Request('http://127.0.0.1:8000' + path,
            data=None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json',
                     'X-Execution-Allowance': SCOPE}, method='GET' if body is None else 'POST')
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read())

    def preflight(self, kind, needed):
        budget = self.call('/api/resources/budget')
        grant = budget.get('active_execution_allowance') or {}
        if grant.get('id') != SCOPE:
            raise RuntimeError('The intended execution allowance is not active')
        field = 'training_remaining' if kind == 'training' else 'text_remaining'
        if int(grant.get(field, 0)) < needed:
            raise RuntimeError('Insufficient explicit scope remaining: ' + field)
        jobs = self.call('/api/jobs')
        active = [j for j in jobs if j['state'] not in TERMINAL]
        if active:
            raise RuntimeError('Other jobs are active; do not overlap model work')
        return budget


def submit_once(client, folder, path, body, kind, *, execute=False):
    """Write intent before POST and never silently recreate an ambiguous request."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    journal_path = folder / 'submission.json'
    wanted = {k: v for k, v in body.items() if k != 'request_id'}
    identity = digest({'path': path, 'body': wanted})
    if journal_path.exists():
        journal = json.loads(journal_path.read_text(encoding='utf-8'))
        if journal['payload_sha256'] != identity:
            raise ValueError('Existing experiment input differs; never overwrite prior evidence')
        if journal.get('job_id'):
            return journal
        if journal['status'] == 'prepared' and not execute:
            return journal
        if journal['status'] != 'prepared':
            matching = [j for j in client.call('/api/jobs') if j.get('request_id') == journal['request_id'] and j['kind'] == kind]
            if len(matching) != 1:
                raise RuntimeError('POST outcome is unresolved; no automatic retry. Inspect submission.json and API jobs.')
            journal.update(job_id=matching[0]['id'], status='recovered_existing_job', recovered_at=stamp())
            save(journal_path, journal)
            return journal
    else:
        journal = {'created_at': stamp(), 'request_id': 'finish-' + uuid4().hex,
                   'path': path, 'payload_sha256': identity, 'body': wanted, 'status': 'prepared'}
        save(journal_path, journal)
    if not execute:
        return journal
    journal.update(status='submitting', submitted_at=stamp())
    save(journal_path, journal)
    try:
        job = client.call(path, {**wanted, 'request_id': journal['request_id']})
        journal.update(status='submitted', job_id=job['id'], initial_job_state=job['state'])
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        journal.update(status='submission_failed_or_unknown', error_type=type(exc).__name__, error=str(exc))
        save(journal_path, journal)
        raise
    save(journal_path, journal)
    return journal


def await_job(client, folder, journal, maximum):
    folder = Path(folder)
    job_id = journal['job_id']
    started = time.monotonic()
    last_print = 0
    try:
        while True:
            job = client.call('/api/jobs/' + job_id)
            save(folder / 'job.json', job)
            if time.monotonic() - last_print > 15 or job['state'] in TERMINAL:
                print(json.dumps({'at': stamp(), 'job_id': job_id, 'state': job['state'],
                                  'progress': job.get('progress'), 'error': job.get('error')}, ensure_ascii=False), flush=True)
                last_print = time.monotonic()
            if job['state'] in TERMINAL:
                return job
            if time.monotonic() - started > maximum:
                raise TimeoutError('Client observation deadline reached; cancel only this owned job')
            time.sleep(2)
    except (KeyboardInterrupt, TimeoutError):
        response = client.call('/api/jobs/' + job_id + '/cancel', {})
        save(folder / 'client-cancel.json', {'at': stamp(), 'job_id': job_id, 'response': response})
        raise


def result_of(job, root=ROOT):
    if isinstance(job.get('result'), dict):
        return job['result']
    artifact = job.get('artifact')
    if artifact:
        folder = (Path(root) / artifact).resolve()
        if not folder.is_relative_to((Path(root) / 'runs').resolve()):
            raise ValueError('API artifact is outside runs')
        candidate = folder / 'result.json'
        if candidate.exists():
            return json.loads(candidate.read_text(encoding='utf-8'))
    return {}


def evaluate(args, client):
    split = getattr(args, 'split', 'validation')
    precision = getattr(args, 'precision', 'nf4')
    model_ref = getattr(args, 'model_ref', 'installed')
    if model_ref != 'installed':
        from edu_tutor.models.text_candidate import CANDIDATE, MODEL_ID, REVISION
        if (model_ref != CANDIDATE or args.adapter != 'base' or precision != 'nf4'
                or split != 'validation'):
            raise ValueError('Candidate screening is base/NF4/validation only; no implicit final selection')
    if precision not in {'nf4', 'bf16'}:
        raise ValueError('Evaluation precision must be explicitly nf4 or bf16')
    selection = None
    if split == 'final':
        selection = check_selection_freeze(getattr(args, 'selection_freeze', None), args.adapter, precision=precision)
    dataset = ROOT / ('runs/finish-v2/20261028/education/final/test.jsonl' if split == 'final'
                      else 'runs/finish-v2/20261028/education/development/validation.jsonl')
    if selection and hashlib.sha256(dataset.read_bytes()).hexdigest() != selection['final_dataset_sha256']:
        raise ValueError('Final dataset differs from the frozen selection manifest')
    records = load_records([dataset])
    validate_dataset(records=records, profile='demo', enforce_minimums=False)
    assert len(records) == (80 if split == 'final' else 40) and all(r['split'] == ('test' if split == 'final' else 'validation') for r in records)
    folder = ROOT / 'runs/finish-v2/20261029/education' / args.run
    folder.mkdir(parents=True, exist_ok=True)
    protocol = {'scope': SCOPE, 'dataset': str(dataset.relative_to(ROOT)),
        'dataset_sha256': hashlib.sha256(dataset.read_bytes()).hexdigest(), 'adapter': args.adapter,
        'precision': precision,
        'max_new_tokens': 256, 'do_sample': False, 'batch_size': 4, 'rag': False,
        'input_roles': ['system', 'user'], 'final_holdout_read': False}
    if model_ref != 'installed':
        protocol.update(model_ref=model_ref, model_id=MODEL_ID, model_revision=REVISION)
    if selection:
        protocol.update(final_holdout_read=True, selection_freeze=selection['reference'],
                        selected_adapter=selection['selected_adapter'], selection_was_frozen_before_final=True)
    protocol_path = folder / 'protocol.json'
    if protocol_path.exists() and json.loads(protocol_path.read_text(encoding='utf-8')) != protocol:
        raise ValueError('Existing protocol differs; choose a new explicitly reviewed run')
    if not protocol_path.exists():
        save(protocol_path, protocol)
    result_path = folder / 'result.json'
    if result_path.exists():
        existing = json.loads(result_path.read_text(encoding='utf-8'))
        if existing.get('status') == 'completed':
            if existing.get('protocol') != protocol:
                raise ValueError('Completed result protocol differs')
            print(json.dumps({'run': args.run, 'status': 'already_completed_no_new_calls',
                              'summary': existing.get('summary')}, ensure_ascii=False), flush=True)
            return existing
    report = {'status': 'prepared' if not args.execute else 'running', 'protocol': protocol,
              'items': [], 'batches': [], 'human_review': 'H_PENDING', 'started_at': stamp()}
    for offset in range(0, len(records), 4):
        selected = records[offset:offset + 4]
        batch = folder / f'batch-{offset//4+1:02d}'
        body = {'adapter': args.adapter, 'precision': precision,
                'max_new_tokens': 256, 'items': [public_item(r) for r in selected]}
        journal_path = batch / 'submission.json'
        submitted = journal_path.exists() and json.loads(journal_path.read_text(encoding='utf-8')).get('job_id')
        if args.execute and not submitted:
            report['last_budget_before_batch'] = client.preflight('text', len(selected))
        if model_ref != 'installed':
            body['model_ref'] = model_ref
        journal = submit_once(client, batch, '/api/evaluations/text-batch', body, 'evaluation', execute=args.execute)
        if not args.execute:
            continue
        job = await_job(client, batch, journal, 365)
        raw = result_of(job)
        save(batch / 'raw-result.json', raw)
        if model_ref != 'installed' and any(item.get('model_ref') != model_ref or item.get('model_id') != MODEL_ID
                or item.get('revision') != REVISION for item in raw.get('items', [])):
            raise RuntimeError('Actual candidate identity differs; do not grade an implicit fallback')
        by_id = {item['id']: item for item in raw.get('items', [])}
        scores = []
        for record in selected:
            output = by_id.get(record['id'])
            score = score_response(record, output.get('text', '') if output else '',
                                   output.get('finish_reason', 'missing') if output else 'missing')
            score.update(question=next(m['content'] for m in record['messages'] if m['role'] == 'user'),
                         actual_answer=output.get('text') if output else None,
                         raw_model_event=output, job_id=job['id'], batch=offset//4+1)
            scores.append(score)
        save(batch / 'scores.json', scores)
        report['items'].extend(scores)
        report['batches'].append({'job_id': job['id'], 'state': job['state'], 'folder': str(batch.relative_to(ROOT))})
        report['summary'] = summarize(report['items'])
        if job['state'] != 'succeeded':
            report.update(status='stopped_after_failed_batch', failure=job.get('error'), finished_at=stamp())
            save(folder / 'result.json', report)
            raise RuntimeError('Batch failed. Partial outputs retained; no automatic retry or next batch.')
        save(folder / 'result.json', report)
    report.update(status='completed' if args.execute else 'prepared', finished_at=stamp())
    save(folder / 'result.json', report)
    print(json.dumps({'run': args.run, 'status': report['status'], 'summary': report.get('summary')}, ensure_ascii=False), flush=True)
    return report


def protocol_precision(protocol, *, require_explicit=False):
    """Historical validation lacked this field and used the fixed NF4 worker."""
    if 'precision' not in protocol:
        if require_explicit or protocol.get('final_holdout_read') is True:
            raise ValueError('New final evidence requires explicit precision')
        return 'nf4'
    precision = protocol['precision']
    if precision not in {'nf4', 'bf16'}:
        raise ValueError('Invalid recorded evaluation precision')
    return precision


def check_selection_freeze(path, adapter, *, root=ROOT, precision='nf4'):
    """Check a reviewed selection manifest before opening any final records.

    A freeze is not adapter promotion. Both a rejected candidate and the selected
    base may be compared, but their identities and validation evidence must be
    fixed before the heldout answers can be used by offline scoring.
    """
    root = Path(root).resolve()
    if not path:
        raise ValueError('Final evaluation requires an explicit selection freeze')
    path = Path(path).resolve()
    if not path.is_relative_to(root / 'runs/finish-v2/20261029/education'):
        raise ValueError('Selection freeze must be in the current education evidence directory')
    raw = path.read_bytes()
    value = json.loads(raw)
    if (value.get('schema_version') != 1 or value.get('status') != 'frozen'
            or value.get('final_evaluation_authorized') is not True
            or value.get('final_answers_used_for_selection') is not False
            or not value.get('frozen_at') or not value.get('selection_basis')):
        raise ValueError('Incomplete or unauthorized selection freeze')
    selected_precision = value.get('selected_precision')
    if selected_precision not in {'nf4', 'bf16'}:
        raise ValueError('Selection freeze requires explicit selected_precision')
    if precision != selected_precision:
        raise ValueError('Requested final precision differs from frozen selected_precision')
    adapters = value.get('evaluation_adapters', [])
    if ('base' not in adapters or len(adapters) != 2 or len(set(adapters)) != 2
            or adapter not in adapters or value.get('selected_adapter') not in adapters):
        raise ValueError('Freeze must identify base and exactly one evaluated candidate')
    seen = set()
    for reference in value.get('validation_evidence', []):
        result_path = (root / reference['path']).resolve()
        if not result_path.is_relative_to(root / 'runs/finish-v2/20261029/education'):
            raise ValueError('Validation evidence must remain in the current run')
        result_raw = result_path.read_bytes()
        if hashlib.sha256(result_raw).hexdigest() != reference['sha256']:
            raise ValueError('Frozen validation evidence changed')
        result = json.loads(result_raw)
        if protocol_precision(result['protocol']) != selected_precision:
            raise ValueError('Validation precision differs from frozen selected_precision')
        if (result.get('status') != 'completed' or len(result.get('items', [])) != 40
                or result['protocol'].get('final_holdout_read') is not False
                or result['protocol'].get('max_new_tokens') != 256
                or result['protocol'].get('do_sample') is not False):
            raise ValueError('Completed comparable validation evidence is required')
        seen.add(result['protocol']['adapter'])
    if seen != set(adapters):
        raise ValueError('Both base and candidate validation evidence must be frozen')
    sha = value.get('final_dataset_sha256', '')
    if len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
        raise ValueError('Frozen final dataset SHA256 is required')
    return {**value, 'reference': {'path': str(path.relative_to(root)),
                                 'sha256': hashlib.sha256(raw).hexdigest()}}


def train(args, client):
    folder = ROOT / 'runs/finish-v2/20261029/education' / args.run
    folder.mkdir(parents=True, exist_ok=True)
    baseline = Path(args.baseline_result).resolve() if args.baseline_result else None
    if not baseline or not baseline.is_relative_to((ROOT / 'runs').resolve()):
        raise ValueError('A local completed validation baseline result is required')
    previous = json.loads(baseline.read_text(encoding='utf-8'))
    if previous['status'] != 'completed' or previous['protocol']['adapter'] != 'base' or len(previous['items']) != 40:
        raise ValueError('The fresh 40-question base validation measurement is not complete')
    link = {'path': str(baseline.relative_to(ROOT)), 'sha256': hashlib.sha256(baseline.read_bytes()).hexdigest()}
    link_path = folder / 'baseline-link.json'
    if link_path.exists() and json.loads(link_path.read_text(encoding='utf-8')) != link:
        raise ValueError('Original baseline evidence changed; do not silently overwrite the experiment link')
    if not link_path.exists():
        save(link_path, link)
    journal_path = folder / 'submission.json'
    submitted = journal_path.exists() and json.loads(journal_path.read_text(encoding='utf-8')).get('job_id')
    if args.execute and not submitted:
        save(folder / 'budget-before.json', client.preflight('training', 1))
    dataset_id = getattr(args, 'dataset_id', 'finish-v2')
    if dataset_id not in {'finish-v2', 'finish-v2-diverse-v2', 'finish-v2-reason-v3'}:
        raise ValueError('Only explicitly prepared education dataset versions are supported')
    journal = submit_once(client, folder, '/api/train', {'profile': 'education', 'dataset_id': dataset_id}, 'training', execute=args.execute)
    if not args.execute:
        return journal
    job = await_job(client, folder, journal, 7270)
    save(folder / 'result.json', {'status': job['state'], 'job_id': job['id'], 'artifact': job.get('artifact'),
        'training_result': job.get('result'), 'error': job.get('error'), 'finished_at': stamp(),
        'automatic_adapter_promotion': False, 'education_quality': 'NOT_YET_EVALUATED', 'human_review': 'H_PENDING'})
    if job['state'] != 'succeeded':
        raise RuntimeError('Actual training did not complete; no automatic experiment retry')
    return job


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['evaluate', 'train'])
    parser.add_argument('--run', required=True)
    parser.add_argument('--adapter', default='base')
    parser.add_argument('--model-ref', choices=['installed', 'qwen3-4b-instruct-2507'], default='installed')
    parser.add_argument('--precision', choices=['nf4', 'bf16'], default='nf4',
                        help='Evaluation precision. Training configuration remains NF4.')
    parser.add_argument('--baseline-result')
    parser.add_argument('--dataset-id', choices=['finish-v2', 'finish-v2-diverse-v2', 'finish-v2-reason-v3'], default='finish-v2')
    parser.add_argument('--split', choices=['validation', 'final'], default='validation')
    parser.add_argument('--selection-freeze')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.mode == 'train' and args.model_ref != 'installed':
        parser.error('Candidate scope is inference comparison only; training is unchanged')
    if args.mode == 'train' and args.precision != 'nf4':
        parser.error('--precision controls evaluation only; the training configuration remains NF4')
    if not args.run or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.run):
        parser.error('run must contain only letters, digits, underscore and hyphen')
    sys.stdout.reconfigure(encoding='utf-8')
    client = Client()
    (evaluate if args.mode == 'evaluate' else train)(args, client)


if __name__ == '__main__':
    main()
