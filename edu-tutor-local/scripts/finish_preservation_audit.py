"""Read-only final preservation audit; new records are allowed, old rows are not changed."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import sqlite3

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(ROOT / 'runs') or output.exists():
        raise ValueError('Use a new output file under runs; preserve prior audits')
    baseline = ROOT / 'runs/finish-v2/20261028'
    report = {'at': datetime.now(timezone.utc).isoformat(), 'model_calls': 0,
              'database': {}, 'baseline': str(baseline.relative_to(ROOT))}
    with sqlite3.connect((baseline / 'before-tutor.sqlite3').as_uri()+'?mode=ro', uri=True) as old, \
            sqlite3.connect((ROOT / '.local/tutor.sqlite3').as_uri()+'?mode=ro', uri=True) as new:
        old.execute('PRAGMA query_only=ON')
        new.execute('PRAGMA query_only=ON')
        for name in ('sessions', 'messages', 'jobs', 'documents', 'chunks', 'photos',
                     'lessons', 'datasets', 'audit', 'evaluation_reviews'):
            before = {row[0]: row for row in old.execute(f'SELECT * FROM {name}')}
            after = {row[0]: row for row in new.execute(f'SELECT * FROM {name}')}
            report['database'][name] = {
                'original_rows': len(before), 'current_rows': len(after),
                'new_rows': len(after.keys()-before.keys()),
                'missing_original_ids': sorted(before.keys()-after.keys()),
                'changed_original_ids': sorted(k for k, v in before.items() if k in after and after[k] != v)}
    ledger = json.loads((ROOT / 'runs/phase2/current/resource-budget.json').read_text(encoding='utf-8'))
    old_ledger = json.loads((baseline / 'before-resource-budget.json').read_text(encoding='utf-8-sig'))
    rows = ledger['requests']
    grant = json.loads((ROOT / '.local/phase2-policy.json').read_text(encoding='utf-8'))['active_execution_allowance']
    approved = json.loads((baseline / 'authorization.json').read_text(encoding='utf-8'))['authorization']
    prefix = json.dumps(rows[:grant['baseline_request_count']], ensure_ascii=False,
                        sort_keys=True, separators=(',', ':')).encode('utf-8')
    report['ledger'] = {'original_count': len(old_ledger['requests']), 'current_count': len(rows),
        'original_prefix_unchanged': rows[:len(old_ledger['requests'])] == old_ledger['requests'],
        'authorization_baseline_hash_matches': hashlib.sha256(prefix).hexdigest() == grant['baseline_requests_sha256'],
        'scope': grant['id'],
        'approved_scope_and_caps_unchanged': all(grant[k] == approved[k]
            for k in ('id', 'limits', 'baseline_request_count', 'baseline_requests_sha256', 'accounting'))}
    report['status'] = 'PASS' if (report['ledger']['original_prefix_unchanged']
        and report['ledger']['authorization_baseline_hash_matches']
        and report['ledger']['approved_scope_and_caps_unchanged']
        and all(not row['missing_original_ids'] and not row['changed_original_ids']
                for row in report['database'].values())) else 'REVIEW_REQUIRED'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'output': str(output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
