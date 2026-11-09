"""Inspect existing normalized responses only; no fixtures or model calls."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from edu_tutor.training.finish_claims import check_explicit_result_claim, PROTOCOL


def grade(folder):
    folder = Path(folder).resolve()
    if not folder.is_relative_to(ROOT / 'runs/finish-v2/20261029/education'):
        raise ValueError('Current saved evidence required')
    source = folder / 'result-normalized.json'
    original = json.loads(source.read_text(encoding='utf-8'))
    if original.get('status') != 'completed':
        raise ValueError('Completed saved normalized results required')
    items = []
    for item in original['items']:
        checked = check_explicit_result_claim(item)
        checked.update(question=item['question'], actual_answer=item['actual_answer'],
                       original_fixture_result_match=item['sql_result_correct'])
        items.append(checked)
    summary = {'total': len(items), 'explicit_result_claim_items': sum(bool(i['claims']) for i in items),
        'parseable_result_claim_items': sum(any(c['matches_sql_execution'] is not None for c in i['claims']) for i in items),
        'explicit_result_claim_mismatches': sum(i['explicit_numeric_mismatch'] for i in items),
        'original_sql_matches_with_contradictory_prose': sum(i['original_fixture_result_match'] is True and i['explicit_numeric_mismatch'] for i in items),
        'full_explanation_quality': 'H_PENDING', 'human_review': 'H_PENDING'}
    value = {'protocol': PROTOCOL, 'created_at': datetime.now(timezone.utc).isoformat(), 'items': items, 'summary': summary,
             'source_result_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
             'grader_sha256': hashlib.sha256((ROOT / 'src/edu_tutor/training/finish_claims.py').read_bytes()).hexdigest(),
             'new_model_calls': 0}
    path = folder / 'result-explicit-claims-v1.json'
    if path.exists():
        old = json.loads(path.read_text(encoding='utf-8'))
        if any(old[k] != value[k] for k in ['source_result_sha256', 'grader_sha256', 'items']):
            raise ValueError('Preserve existing claims evidence; use a new explicit version for changes')
        return old
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('folder'); args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(grade(args.folder)['summary'], ensure_ascii=False))
