"""Appraise preserved raw answers with no model calls, retries, RAG or speech."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from edu_tutor.training.data import load_records
from edu_tutor.training.finish_app_score import app_score_response, summarize_app
from finish_education_live import check_selection_freeze, protocol_precision


def grade(folder, *, version=None):
    if version is not None and (not version or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in version)):
        raise ValueError('Grading version must be an explicit letters/numbers/hyphen/underscore name')
    folder = Path(folder).resolve()
    if not folder.is_relative_to(ROOT / 'runs/finish-v2/20261029/education'):
        raise ValueError('Only current education evidence is supported')
    source = folder / 'result.json'
    original = json.loads(source.read_text(encoding='utf-8'))
    if original['status'] != 'completed':
        raise ValueError('Completed saved measurement required')
    final = original['protocol'].get('final_holdout_read') is True
    if final:
        reference = original['protocol'].get('selection_freeze') or {}
        selection = check_selection_freeze(ROOT / reference.get('path', ''), original['protocol']['adapter'],
            precision=protocol_precision(original['protocol'], require_explicit=True))
        if selection['reference'] != reference:
            raise ValueError('Frozen selection changed after model outputs')
    dataset = ROOT / original['protocol']['dataset']
    expected = ROOT / ('runs/finish-v2/20261028/education/final/test.jsonl' if final else
                       'runs/finish-v2/20261028/education/development/validation.jsonl')
    if dataset.resolve() != expected or hashlib.sha256(dataset.read_bytes()).hexdigest() != original['protocol']['dataset_sha256']:
        raise ValueError('Frozen dataset path or hash changed')
    records = {r['id']: r for r in load_records([dataset])}
    if len(original['items']) != (80 if final else 40) or set(records) != {i['id'] for i in original['items']}:
        raise ValueError('Complete saved measurement required')
    items = []
    for raw in original['items']:
        score = app_score_response(records[raw['id']], raw.get('actual_answer') or '', raw['finish_reason'])
        score.update(question=raw['question'], actual_answer=raw.get('actual_answer'), job_id=raw.get('job_id'))
        items.append(score)
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in [
        'src/edu_tutor/training/finish_app_score.py', 'src/edu_tutor/problems/evidence.py',
        'src/edu_tutor/problems/app_correction.py',
        'src/edu_tutor/problems/models.py', 'src/edu_tutor/problems/sql_response.py',
        'src/edu_tutor/lessons/verified.py']}
    result = {'mode': 'offline_app_reprocessing_only', 'graded_at': datetime.now(timezone.utc).isoformat(),
              'grading_version': version or 'initial',
              'source_result_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'protocol': original['protocol'], 'items': items, 'summary': summarize_app(items),
              'source_hashes': hashes, 'new_inference': False, 'fixture_provenance': 'procedural_development_test_not_user_upload'}
    target = folder / ('result-app-offline.json' if version is None else f'result-app-offline-{version}.json')
    if target.exists():
        prior = json.loads(target.read_text(encoding='utf-8'))
        if prior['source_result_sha256'] != result['source_result_sha256'] or prior['source_hashes'] != hashes or prior['items'] != items:
            raise ValueError('Existing app evidence differs; preserve it and use a new explicit grading version')
        return prior
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder')
    parser.add_argument('--version')
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(grade(args.folder, version=args.version)['summary'], ensure_ascii=False))
