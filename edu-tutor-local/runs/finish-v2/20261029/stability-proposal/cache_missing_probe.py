"""Prepared GET-only cache guard and restart snapshots. No model/voice submission.

No work occurs on import. --execute is necessary for the single-file rename.
Output always stays in a new directory under project runs; token never exported.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parents[4]
TERMINAL = {'succeeded', 'failed', 'cancelled', 'interrupted', 'blocked'}
TABLES = ('sessions', 'messages', 'jobs', 'documents', 'chunks', 'photos', 'lessons', 'datasets', 'audit', 'evaluation_reviews')
POLICIES = ('.local/phase2-policy.json', '.local/speech-provider.json', '.local/model-selection.json',
            '.local/text-inference-policy.json', '.local/text-session-policy.json', 'runs/phase2/current/resource-budget.json')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def safe_child(path, folder):
    value = path.resolve()
    if not value.is_relative_to(folder.resolve()) or value == folder.resolve():
        raise ValueError('Resolved path escaped its exact owned folder')
    return value


def frozen(path):
    record = read(safe_child(path, ROOT / 'runs'))
    expected = record['source_hashes']
    for name, digest in expected.items():
        file = safe_child(ROOT / name, ROOT)
        actual = sha(file) if file.is_file() else None
        if actual != digest:
            raise RuntimeError('Frozen source changed: ' + name)
    if read(ROOT / '.local/text-inference-policy.json') != {'precision': 'bf16'}:
        raise RuntimeError('This proposal is for the chosen BF16 build only')
    provider = read(ROOT / '.local/speech-provider.json')
    if provider.get('provider') != 'windows_sapi_local' or 'HEAMI' not in provider.get('windows_sapi', {}).get('voice_id', ''):
        raise RuntimeError('This proposal is for the chosen Heami provider only')
    return record


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('Redirect forbidden in local GET-only probe')


def get(path, *, binary=False):
    parsed = urllib.parse.urlsplit(path)
    if parsed.scheme or parsed.netloc or not path.startswith('/api/'):
        raise ValueError('Only local relative API reads are allowed')
    token = (ROOT / '.local/auth-token').read_text(encoding='utf-8').strip()
    request = urllib.request.Request('http://127.0.0.1:8000' + path, headers={'Authorization': 'Bearer ' + token}, method='GET')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=15) as response:
            payload, status = response.read(), response.status
    except urllib.error.HTTPError as exc:
        payload, status = exc.read(), exc.code
    return status, payload if binary else json.loads(payload)


def require_get(path):
    status, data = get(path)
    if status != 200:
        raise RuntimeError('GET failed: ' + path + ' status=' + str(status))
    return data


def quiescent():
    jobs = require_get('/api/jobs')
    if any(j['state'] not in TERMINAL for j in jobs):
        raise RuntimeError('Active job exists; no cache mutation or restart snapshot')


def snapshot():
    quiescent()
    rows = {}
    with sqlite3.connect((ROOT / '.local/tutor.sqlite3').as_uri() + '?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        for table in TABLES:
            values = db.execute('SELECT * FROM ' + table + ' ORDER BY id').fetchall()
            rows[table] = {str(row[0]): hashlib.sha256(json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest() for row in values}
    audio = safe_child(ROOT / '.local/audio', ROOT)
    files = {p.name: sha(safe_child(p, audio)) for p in sorted(audio.iterdir()) if p.is_file()}
    return {'at': datetime.now(timezone.utc).isoformat(), 'model_calls': 0, 'tts_calls': 0,
            'preservation': {'database_rows': rows, 'audio_files': files,
                             'files': {name: sha(ROOT / name) if (ROOT / name).is_file() else None for name in POLICIES}},
            'api_lease': read(ROOT / '.local/api-lease.json'), 'health': require_get('/api/health')}


def cache_probe(lesson_id, step_id, out):
    if not re.fullmatch(r'[a-f0-9]{32}', lesson_id) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', step_id):
        raise ValueError('Unexpected lesson/step ID format')
    report = {'status': 'PREPARING', 'scope': 'GET-only bound cache endpoint, no UI/listening claim',
              'model_calls': 0, 'tts_calls': 0, 'ocr_calls': 0, 'human_review': 'H_PENDING'}
    journal = out / 'result.json'
    def save():
        temporary = out / 'result.next.json'
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temporary.replace(journal)
    report['before'] = snapshot()
    path = '/api/lessons/' + lesson_id + '/speech?' + urllib.parse.urlencode({'step_id': step_id, 'voice': 'default'})
    manifest = require_get(path)
    clip = next((c for c in manifest.get('steps', []) if c.get('step_id') == step_id), None)
    if not clip or clip.get('provider') != 'windows_sapi_local' or 'HEAMI' not in clip.get('voice', '').upper() or not re.fullmatch(r'[a-f0-9]{64}', clip.get('audio_id', '')):
        raise RuntimeError('Select a previously verified Heami step with attached actual audio')
    if clip.get('cache_source') != 'attached':
        raise RuntimeError('Select an attached lesson cache, not an unrelated global cache')
    audio = safe_child(ROOT / '.local/audio', ROOT)
    source = safe_child(audio / (clip['audio_id'] + '.wav'), audio)
    backup = safe_child(audio / ('.finish-stability-' + uuid.uuid4().hex + '-' + source.name + '.backup'), audio)
    digest = sha(source)
    status, before_bytes = get(clip['audio_url'], binary=True)
    if status != 200 or hashlib.sha256(before_bytes).hexdigest() != digest or digest != clip.get('checksum'):
        raise RuntimeError('Bound bytes, stored WAV and clip checksum differ')
    if backup.exists():
        raise RuntimeError('Unique backup already exists')
    report.update(status='READY_TO_RENAME', manifest_before=manifest,
                  ownership={'source_absolute': str(source), 'backup_absolute': str(backup), 'sha256': digest,
                             'recovery': 'If interrupted, verify backup SHA then rename only this backup to absent source. Never overwrite a conflicting source.'})
    save()  # Persistent exact-path recovery journal precedes mutation.
    moved = False
    try:
        quiescent()
        source.rename(backup)
        moved = True
        if source.exists() or sha(backup) != digest:
            raise RuntimeError('Owned rename/hash validation failed')
        missing = require_get(path)
        missing_status, missing_bytes = get(clip['audio_url'], binary=True)
        report.update(status='MISSING_OBSERVED', manifest_missing=missing, missing_bound_http_status=missing_status,
                      missing_bound_response_sha256=hashlib.sha256(missing_bytes).hexdigest())
        if any(c.get('step_id') == step_id for c in missing.get('steps', [])) or not any(
                c.get('step_id') == step_id and c.get('code') == 'cache_missing' for c in missing.get('cache_misses', [])) or missing_status != 409:
            raise RuntimeError('Missing cache was not safely rejected')
    except BaseException as exc:
        report['error'] = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        if moved:
            if source.exists() or not backup.is_file() or sha(backup) != digest:
                report['status'] = 'RESTORE_BLOCKED_PRESERVE_BACKUP'
                save()
                raise RuntimeError('Do not overwrite changed files; exact recovery journal retained')
            backup.rename(source)
            report['restored_hash_matches'] = sha(source) == digest
        report['status'] = ('FAILED_GUARD_RESTORED' if report.get('error') else 'RESTORED_REQUIRES_FINAL_CHECK') if moved else 'FAILED_BEFORE_MOVE'
        save()
    status, after_bytes = get(clip['audio_url'], binary=True)
    report['after'] = snapshot()
    report['restored_bound_bytes_match'] = status == 200 and hashlib.sha256(after_bytes).hexdigest() == digest
    report['preservation_unchanged'] = report['before']['preservation'] == report['after']['preservation']
    report['status'] = 'PASS_API_CACHE_MISSING_GUARD' if report['restored_hash_matches'] and report['restored_bound_bytes_match'] and report['preservation_unchanged'] else 'FAILED_FINAL_CHECK'
    save()
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', action='store_true')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--lesson-id')
    parser.add_argument('--step-id')
    parser.add_argument('--freeze', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = safe_child(safe_child(args.output, ROOT), ROOT / 'runs')
    if out.exists():
        parser.error('Use a new output directory; no overwrite/retry')
    frozen(args.freeze)
    if not args.snapshot and (not args.execute or not args.lesson_id or not args.step_id):
        parser.error('Cache mutation requires explicit --execute, --lesson-id and --step-id after coordinator GO')
    out.mkdir(parents=True)
    if args.snapshot:
        result = snapshot()
        (out / 'snapshot.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        result = {'status': 'SNAPSHOT_ONLY_NOT_A_RESTART_RESULT'}
    else:
        result = cache_probe(args.lesson_id, args.step_id, out)
    print(json.dumps({'status': result['status'], 'output': str(out)}))


if __name__ == '__main__':
    main()
