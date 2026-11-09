"""One-shot saved-answer CPU reprocessing after the independently observed follow-up defect.

No API client, model, retrieval, repair, audio, or budget mutation is used.
Original model outputs and r10 app grades remain immutable.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[4]
EDU = ROOT / 'runs/finish-v2/20261029/education'
VERSION = 'final-source-r14-followup-binding-v1'
RECEIPT = EDU / f'{VERSION}-comparison.json'
RUNS = ('final-base-bf16-v1', 'final-adapter1-bf16-v1')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_hashes():
    paths = sorted((ROOT / 'src').rglob('*.py')) + [ROOT / 'scripts/finish_education_app_grade.py', ROOT / 'scripts/finish_education_live.py']
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in paths}


def protected_hashes():
    paths = [EDU / 'selection-bf16-frozen-v1.json', ROOT / 'runs/finish-v2/20261028/education/final/test.jsonl']
    for run in RUNS:
        paths.extend(EDU / run / name for name in ('result.json', 'result-normalized.json', 'result-app-offline-final-source-r10-v1.json'))
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in paths}


def main():
    if RECEIPT.exists():
        raise RuntimeError('Preserve completed reprocessing; this one-shot script does not overwrite it.')
    for run in RUNS:
        if (EDU / run / f'result-app-offline-{VERSION}.json').exists():
            raise RuntimeError('Target app grade already exists; inspect its evidence instead of rerunning.')
    before_code, before_protected = code_hashes(), protected_hashes()
    started = datetime.now(timezone.utc).isoformat()
    sys.path.insert(0, str(ROOT / 'scripts'))
    from finish_education_app_grade import grade
    comparisons = []
    for run in RUNS:
        old = read(EDU / run / 'result-app-offline-final-source-r10-v1.json')
        new = grade(EDU / run, version=VERSION)
        old_items = {i['id']: i for i in old['items']}
        changed = [i['id'] for i in new['items'] if old_items[i['id']] != i]
        reasons = {}
        for item in new['items']:
            if item.get('accepted_result_correct') is None or item.get('accepted'):
                continue
            evidence = item.get('evidence', {})
            reason = str(evidence.get('reason') or evidence.get('failure') or item.get('failure') or evidence.get('status') or item.get('status'))
            reasons[reason] = reasons.get(reason, 0) + 1
        comparisons.append({'run': run, 'old_summary': old['summary'], 'new_summary': new['summary'],
            'changed_item_ids': changed, 'old_result_sha256': sha(EDU / run / 'result-app-offline-final-source-r10-v1.json'),
            'new_result_sha256': sha(EDU / run / f'result-app-offline-{VERSION}.json'),
            'source_hashes': new['source_hashes'], 'stop_reasons': reasons,
            'conditional_correctness_on_accepted': None if new['summary']['accepted'] == 0 else new['summary']['accepted_result_correct'] / new['summary']['accepted']})
    after_code, after_protected = code_hashes(), protected_hashes()
    stable = before_code == after_code and before_protected == after_protected
    result = {'status': 'PASS_SAVED_RAW_CPU_REPROCESSING_PROVENANCE' if stable else 'INVALID_SOURCE_CHANGED_DURING_REPROCESSING',
        'started_at': started, 'finished_at': datetime.now(timezone.utc).isoformat(), 'grading_version': VERSION,
        'notice': 'Post-fix saved raw CPU app reprocessing, not a new independent model measurement. Fixed selection and held-out raw answers remain unchanged. No lesson context is supplied to these final-answer records.',
        'new_model_calls': 0, 'new_rag_search': 0, 'new_model_repair': 0, 'new_tts': 0, 'actual_live_classroom_runs': 0,
        'human_review': 'H_PENDING', 'readiness': 'NOT_READY', 'conditions': comparisons,
        'code_before': before_code, 'code_after': after_code, 'code_unchanged_during_reprocessing': before_code == after_code,
        'protected_before': before_protected, 'protected_after': after_protected, 'protected_unchanged': before_protected == after_protected}
    RECEIPT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'receipt': str(RECEIPT), 'conditions': comparisons}, ensure_ascii=False, indent=2))
    if not stable:
        raise RuntimeError('Source changed; new grades retained as INVALID, not accepted evidence.')


if __name__ == '__main__':
    main()
