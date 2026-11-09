"""Explicit authenticated one-candidate download. Default only prepares intent."""
from pathlib import Path
import argparse
import json
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from finish_education_live import Client, ROOT, SCOPE, TERMINAL, submit_once, await_job, save, stamp

CANDIDATE = "qwen3-4b-instruct-2507"
EXPECTED_BYTES = 8_060_915_998


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}', args.run):
        parser.error('Use a unique simple run name')
    folder = ROOT / 'runs/finish-v2/20261029' / args.run
    client = Client()
    journal_path = folder / 'submission.json'
    previous = json.loads(journal_path.read_text(encoding='utf-8')) if journal_path.exists() else {}
    # An acknowledged/ambiguous POST is recovered by request ID, never posted
    # again or blocked merely because its own job is still active.
    new_submission = previous.get('status', 'prepared') == 'prepared'
    if args.execute and new_submission:
        budget = client.call('/api/resources/budget')
        grant = budget.get('active_execution_allowance') or {}
        if (grant.get('id') != SCOPE or grant.get('accounting') != 'scope_only_preserve_lifetime'
                or grant.get('download_bytes_remaining', 0) < EXPECTED_BYTES + 2_000_000 + 12*262144):
            raise RuntimeError('Exact integrated scope and remaining download bytes are required')
        if any(j['state'] not in TERMINAL for j in client.call('/api/jobs')):
            raise RuntimeError('Another job is active; no overlapping download')
        schema = client.call('/api/openapi.json')
        if '/api/models/text-candidate/download' not in schema.get('paths', {}):
            raise RuntimeError('Reviewed download API has not been deployed')
        folder.mkdir(parents=True, exist_ok=True)
        if not (folder/'budget-before.json').exists():
            save(folder/'budget-before.json', budget)
    journal = submit_once(client, folder, '/api/models/text-candidate/download',
        {'candidate_id':CANDIDATE}, 'download', execute=args.execute)
    if not args.execute:
        return
    job = await_job(client, folder, journal, 1265)
    save(folder/'result.json', {'at':stamp(), 'job':job,
        'budget_after':client.call('/api/resources/budget'), 'model_calls':0,
        'default_selection_changed':False, 'notice':'Download completion is not runtime or educational validation.'})
    if job['state'] != 'succeeded':
        raise RuntimeError('Candidate download did not complete; no automatic retry')


if __name__ == '__main__':
    main()
