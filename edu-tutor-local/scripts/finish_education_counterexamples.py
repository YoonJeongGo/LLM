"""CPU-only counterexamples for saved model SQL, preserving original grades."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from edu_tutor.training.data import load_records
from edu_tutor.training.finish_counterexamples import check_saved_sql, PROTOCOL
from finish_education_live import check_selection_freeze, protocol_precision


def grade(folder):
    folder = Path(folder).resolve()
    if not folder.is_relative_to(ROOT / 'runs/finish-v2/20261029/education'):
        raise ValueError('Current run evidence required')
    source = folder / 'result-normalized.json'
    original = json.loads(source.read_text(encoding='utf-8'))
    if original['status'] != 'completed':
        raise ValueError('Completed normalized saved result required')
    final = original['protocol'].get('final_holdout_read') is True
    if final:
        reference = original['protocol'].get('selection_freeze') or {}
        selection = check_selection_freeze(ROOT / reference.get('path', ''), original['protocol']['adapter'],
            precision=protocol_precision(original['protocol'], require_explicit=True))
        if selection['reference'] != reference:
            raise ValueError('Selection freeze changed')
    dataset = ROOT / original['protocol']['dataset']
    allowed = ROOT / ('runs/finish-v2/20261028/education/final/test.jsonl' if final else 'runs/finish-v2/20261028/education/development/validation.jsonl')
    if dataset.resolve() != allowed or hashlib.sha256(dataset.read_bytes()).hexdigest() != original['protocol']['dataset_sha256']:
        raise ValueError('Dataset path or hash changed')
    records = {r['id']: r for r in load_records([dataset])}
    if len(original['items']) != (80 if final else 40) or set(records) != {i['id'] for i in original['items']}:
        raise ValueError('Complete saved measurement required')
    items = []
    for old in original['items']:
        score = check_saved_sql(records[old['id']], old.get('actual_answer') or '', old['finish_reason'])
        score.update(original_fixture_result_match=old['sql_result_correct'],
                     question=old['question'], actual_answer=old.get('actual_answer'))
        items.append(score)
    summary = {'total': len(items), 'original_fixture_result_matches': sum(i['original_fixture_result_match'] is True for i in items),
        'counterexample_found': sum(i['counterexample_found'] is True for i in items),
        'original_matches_disproved_by_counterexample': sum(i['original_fixture_result_match'] is True and i['counterexample_found'] is True for i in items),
        'semantic_pass_count': None, 'human_review': 'H_PENDING', 'new_model_calls': 0}
    value = {'protocol': PROTOCOL, 'created_at': datetime.now(timezone.utc).isoformat(), 'summary': summary,
        'source_result_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'grader_sha256': hashlib.sha256((ROOT / 'src/edu_tutor/training/finish_counterexamples.py').read_bytes()).hexdigest(),
        'items': items}
    target = folder / 'result-sql-counterexamples-v1.json'
    if target.exists():
        prior = json.loads(target.read_text(encoding='utf-8'))
        if any(prior[k] != value[k] for k in ['source_result_sha256', 'grader_sha256', 'items']):
            raise ValueError('Existing counterexample evidence changed; do not overwrite')
        return prior
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('folder'); args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(grade(args.folder)['summary'], ensure_ascii=False))
