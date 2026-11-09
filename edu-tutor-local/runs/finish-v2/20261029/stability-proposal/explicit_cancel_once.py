"""Prepared, opt-in ONE text submission/ONE cancel. Never synthesize or retry.

Coordinator GO is required before --execute. Uses one completed J01 question,
the same frozen base/BF16 build, no RAG/tools repair, and the existing scope.
"""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request
import uuid

from cache_missing_probe import ROOT, TERMINAL, NoRedirect, frozen, get, require_get, read, safe_child, sha

SCOPE = 'finish-local-tutor-20261028-v1'


def native_diagnostic(path, exit_code):
    value = {'path': str(path), 'exit_code': exit_code, 'scan_complete': False, 'fatal_lines': []}
    if path.is_file() and path.stat().st_size <= 2 * 1024 * 1024:
        data = path.read_bytes()
        pattern = re.compile(r'Windows fatal exception|Fatal Python error|access[- ]violation|0x[cC]0000005', re.I)
        value.update(scan_complete=True, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
            fatal_lines=[line[:700] for line in data.decode('utf-8', errors='replace').splitlines() if pattern.search(line)][:20])
    value['native_fatal_diagnostic'] = bool(value['fatal_lines']) or (isinstance(exit_code, int) and exit_code & 0xffffffff == 0xC0000005)
    return value


def ready_owned_request(job, session, job_id):
    ownership = session.get('ownership') or {}
    info = session.get('inference') or {}
    return (job.get('id') == job_id and job.get('state') == 'running' and bool(job.get('raw_partial_text'))
            and session.get('latest_job_id') == job_id and session.get('active_request') is True
            and bool(session.get('model_instance_id')) and re.fullmatch(r'[a-f0-9]{32}', session.get('instance_id', ''))
            and ownership.get('ancestry_verified') is True and ownership.get('job_assigned') is True
            and ownership.get('pid') == session.get('worker_pid') and isinstance(session.get('process_start_time'), (int, float))
            and session.get('requested_precision') == 'bf16' and info.get('requested_precision') == 'bf16'
            and info.get('actual_is_loaded_in_4bit') is False and info.get('quantization') == 'none'
            and info.get('actual_parameter_devices') == ['cuda:0']
            and info.get('load_dtype') == 'torch.bfloat16'
            and set(info.get('actual_parameter_dtypes_elements', {})) == {'torch.bfloat16'}
            and all(type(n) is int and n > 0 for n in info['actual_parameter_dtypes_elements'].values()))


class ExactProcess:
    """Read/synchronize-only stable Windows handle. No termination permission."""
    def __init__(self, pid, birth):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        self.kernel.GetProcessTimes.restype = wintypes.BOOL
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.GetExitCodeProcess.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.handle = self.kernel.OpenProcess(0x1000 | 0x00100000, False, int(pid))
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            clocks = [wintypes.FILETIME() for _ in range(4)]
            if not self.kernel.GetProcessTimes(self.handle, *[ctypes.byref(c) for c in clocks]):
                raise ctypes.WinError(ctypes.get_last_error())
            self.birth = ((clocks[0].dwHighDateTime << 32) | clocks[0].dwLowDateTime) / 10_000_000 - 11644473600
            if abs(self.birth - birth) > .01 or self.exited():
                raise RuntimeError('Exact worker birth/live-handle verification failed')
        except BaseException:
            self.close()
            raise

    def exited(self):
        result = self.kernel.WaitForSingleObject(self.handle, 0)
        if result not in {0, 258}:
            raise RuntimeError('Process wait state is unknown')
        return result == 0

    def exit_code(self):
        value = wintypes.DWORD()
        if not self.kernel.GetExitCodeProcess(self.handle, ctypes.byref(value)):
            raise ctypes.WinError(ctypes.get_last_error())
        return value.value

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def run(version_dir, out, source_version=None):
    frozen_record = frozen(version_dir / 'execution-version.json')
    cross_receipt = None
    if source_version is not None:
        from cross_version_receipt import compare
        cross_receipt = compare(source_version, version_dir)
    case_path = lambda number: Path(cross_receipt['case_mapping'][f'J{number:02}']) if cross_receipt else version_dir/f'J{number:02}'/'actual.json'
    for number in range(1, 9):
        record = read(case_path(number))
        if record.get('status') == 'RUNNING' or not record.get('completed_at'):
            raise RuntimeError('Wait until all eight browser attempts have ended')
        case_freeze = read(case_path(number).parent.parent/'execution-version.json')
        if (record.get('id') != f'J{number:02}' or record.get('version') != case_freeze['version']
                or record.get('source_hashes') != case_freeze['source_hashes'] or record.get('source_unchanged_at_end') is not True):
            raise RuntimeError('Completed browser artifact does not prove its frozen execution version')
    source = read(case_path(1))
    question = source['spec']['question']
    if not question or source.get('status', '').startswith('FAILED'):
        raise RuntimeError('Use the completed J01 question, no new experimental wording')
    if any(j['state'] not in TERMINAL for j in require_get('/api/jobs')):
        raise RuntimeError('Another app job is active')
    model = require_get('/api/models')
    expected = frozen_record['state']['model']
    if any(model.get(k) != expected[k] for k in ('model_id', 'revision', 'active_adapter')) or model.get('active_adapter') is not None:
        raise RuntimeError('Chosen installed base model differs from freeze')
    if require_get('/api/tts/session').get('resident'):
        raise RuntimeError('An experimental TTS worker is still resident')
    budget = require_get('/api/resources/budget')
    allowance = budget.get('active_execution_allowance') or {}
    if budget.get('accounting_scope') != SCOPE or allowance.get('id') != SCOPE or allowance.get('text_remaining', 0) < 1 or allowance.get('seconds_remaining', 0) < 30:
        raise RuntimeError('Existing approved text/time allowance is insufficient; no request made')
    ledger_path = ROOT / 'runs/phase2/current/resource-budget.json'
    before_rows = read(ledger_path)['requests']
    record = {'status': 'PREPARED_NOT_SUBMITTED', 'started_at': datetime.now(timezone.utc).isoformat(),
        'version': version_dir.name, 'freeze_sha256': sha(version_dir/'execution-version.json'),
        'source_question_sha256': sha(case_path(1)), 'source_question_path': str(case_path(1)),
        'cross_harness_same_product_receipt': cross_receipt, 'question': question, 'scope': SCOPE,
        'text_submission_limit': 1, 'cancel_post_limit': 1, 'tts_calls': 0, 'ocr_calls': 0,
        'api_ui_boundary': 'Explicit API cancel, not a separate student cancel-button validation',
        'request_id': 'stability-cancel-' + uuid.uuid4().hex, 'posts': [], 'before_budget': budget,
        'source_files_unchanged_before': True, 'human_review': 'H_PENDING'}
    def save():
        temp = out/'result.next.json'
        temp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temp.replace(out/'result.json')
    def post(path, body=None):
        allowed = path == '/api/sessions' and not record.get('session_id') or (
            record.get('session_id') and path == '/api/sessions/'+record['session_id']+'/messages' and not record.get('submitted')) or (
            record.get('job_id') and path == '/api/jobs/'+record['job_id']+'/cancel' and not record.get('cancel_sent'))
        if not allowed:
            raise RuntimeError('Unexpected/duplicate POST refused')
        if path.endswith('/messages'):
            record['submitted'] = True  # A failed POST is still an attempt; never resend.
        if path.endswith('/cancel'):
            record['cancel_sent'] = True
            record['cancel_at_monotonic'] = time.monotonic()
        record['posts'].append({'path': path, 'at': datetime.now(timezone.utc).isoformat()})
        save()
        token = (ROOT/'.local/auth-token').read_text().strip()
        request = urllib.request.Request('http://127.0.0.1:8000'+path, data=json.dumps(body or {}).encode(), method='POST',
            headers={'Authorization': 'Bearer '+token, 'X-Execution-Allowance': SCOPE, 'Content-Type': 'application/json'})
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=10) as response:
            return json.loads(response.read())
    exact = None
    save()
    try:
        session = post('/api/sessions', {'title': '개발 검증 · 명시 취소 1회'})
        record['session_id'] = session['id']
        save()
        receipt = post('/api/sessions/'+session['id']+'/messages', {'content': question, 'request_id': record['request_id'],
            'adapter': 'base', 'use_rag': False, 'verification_mode': 'model_only'})
        record.update(job_id=receipt['job_id'], generation_epoch=receipt['generation_epoch'], receipt=receipt)
        save()
        deadline = time.monotonic() + min(270, allowance['seconds_remaining'] - 20)
        while time.monotonic() < deadline:
            job = require_get('/api/jobs/'+record['job_id'])
            record['last_job_before_cancel'] = job
            if job['state'] in TERMINAL:
                record['status'] = 'NOT_EXERCISED_REQUEST_FINISHED_BEFORE_CANCEL'
                break
            active = (require_get('/api/models').get('text_session') or {}).get('session') or {}
            if ready_owned_request(job, active, record['job_id']):
                exact = ExactProcess(active['worker_pid'], active['process_start_time'])
                record['owned_session_before_cancel'] = active
                record['os_handle_birth'] = exact.birth
                record['actual_partial_text_observed'] = True
                record['cancel_receipt'] = post('/api/jobs/'+record['job_id']+'/cancel')
                record['status'] = 'CANCEL_REQUESTED_AFTER_ACTUAL_TEXT_DELTA'
                break
            time.sleep(.1)
        else:
            record['status'] = 'NOT_EXERCISED_NO_OWNED_ACTIVE_TEXT_DELTA'
    except BaseException as exc:
        record['status'] = 'FAILED_NO_RETRY'
        record['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        try:
            # A timed-out submission response can still have created our unique job.
            if record.get('submitted') and not record.get('job_id'):
                found = [j for j in require_get('/api/jobs') if j.get('session_id') == record.get('session_id') and j.get('request_id') == record['request_id']]
                if len(found) == 1:
                    record['job_id'] = found[0]['id']
                elif len(found) > 1:
                    raise RuntimeError('Duplicate jobs for one owned request; do not cancel broadly')
            if record.get('job_id'):
                job = require_get('/api/jobs/'+record['job_id'])
                if job['state'] not in TERMINAL and not record.get('cancel_sent'):
                    record['cleanup_cancel_receipt'] = post('/api/jobs/'+record['job_id']+'/cancel')
                stop = time.monotonic()+30
                while time.monotonic() < stop:
                    job = require_get('/api/jobs/'+record['job_id'])
                    if record.get('cancel_at_monotonic') is not None:
                        if job['state'] in TERMINAL and 'cancel_to_terminal_observed_seconds' not in record:
                            record['cancel_to_terminal_observed_seconds'] = time.monotonic()-record['cancel_at_monotonic']
                        if exact is not None and exact.exited() and 'cancel_to_worker_exit_observed_seconds' not in record:
                            record['cancel_to_worker_exit_observed_seconds'] = time.monotonic()-record['cancel_at_monotonic']
                    if job['state'] in TERMINAL and (exact is None or exact.exited()):
                        break
                    time.sleep(.1)
                record['final_job'] = job
                record['exact_worker_handle_exited'] = exact.exited() if exact else None
                record['exact_worker_exit_code'] = exact.exit_code() if exact else None
                if record.get('owned_session_before_cancel'):
                    instance = record['owned_session_before_cancel']['instance_id']
                    session_path = safe_child(ROOT/'runs'/('text-session-'+instance)/'session.json', ROOT/'runs')
                    record['owned_session_after'] = read(session_path)
                    record['owned_session_path'] = str(session_path)
                    record['owned_session_sha256'] = sha(session_path)
                    stderr = safe_child(session_path.parent/'stderr.log', session_path.parent)
                    record['owned_native_diagnostic'] = native_diagnostic(stderr, record['exact_worker_exit_code'])
                late = []
                late_started = time.monotonic()
                until = late_started+5
                while time.monotonic() < until:
                    late += [m for m in require_get('/api/sessions/'+record['session_id']+'/messages') if m.get('request_id') == record['request_id'] and m.get('role') == 'assistant']
                    time.sleep(.5)
                record['late_observation_seconds'] = time.monotonic()-late_started
                record['late_assistant_messages'] = {m['id']: m for m in late}
                after_rows = read(ledger_path)['requests']
                record['original_ledger_prefix_unchanged'] = after_rows[:len(before_rows)] == before_rows
                record['new_reservations'] = after_rows[len(before_rows):]
                record['only_one_owned_text_reservation'] = len(record['new_reservations']) == 1 and all(
                    r.get('kind') == 'text' and r.get('job_id') == record['job_id'] and r.get('execution_allowance_id') == SCOPE for r in record['new_reservations'])
                record['reservation_settled_within_existing_deadline'] = bool(record['new_reservations']) and all(
                    r.get('status') in {'completed', 'failed_or_cancelled'} and 0 <= r.get('charged_seconds', -1) <= r.get('request_limit_seconds', -1) <= 300
                    for r in record['new_reservations'])
                closed = record.get('owned_session_after') or {}
                record['checks'] = {'actual_text_delta_before_cancel': record.get('actual_partial_text_observed') is True,
                    'cancelled_terminal': job['state'] == 'cancelled', 'actual_worker_exited': record['exact_worker_handle_exited'] is True,
                    'owned_session_closed': closed.get('status') == 'closed' and closed.get('actual_worker_exit_confirmed') is True and closed.get('process_exit_confirmed') is True,
                    'no_native_fatal_cleanup_diagnostic': record.get('owned_native_diagnostic', {}).get('scan_complete') is True
                        and record['owned_native_diagnostic']['native_fatal_diagnostic'] is False,
                    'no_late_answer_saved': not late, 'old_ledger_preserved': record['original_ledger_prefix_unchanged'],
                    'one_owned_text_reservation': record['only_one_owned_text_reservation'],
                    'reservation_settled_within_existing_deadline': record['reservation_settled_within_existing_deadline']}
                if record.get('status') == 'CANCEL_REQUESTED_AFTER_ACTUAL_TEXT_DELTA':
                    record['status'] = 'PASS_ACTUAL_API_TEXT_CANCEL' if all(record['checks'].values()) else 'FAILED_CANCEL_OR_PRESERVATION_CHECK'
            frozen(version_dir/'execution-version.json')
            record['source_files_unchanged_after'] = True
        except BaseException as exc:
            record['finalization_error'] = type(exc).__name__ + ': ' + str(exc)
            record['status'] = 'FAILED_NEEDS_OWNED_JOB_REVIEW_NO_RETRY'
        finally:
            if exact:
                exact.close()
            record['completed_at'] = datetime.now(timezone.utc).isoformat()
            save()
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--version-dir', type=Path, required=True)
    parser.add_argument('--source-version', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.execute:
        parser.error('Actual submission forbidden without explicit coordinator GO and --execute')
    version = safe_child(args.version_dir, ROOT/'runs/finish-v2/20261029/student')
    out = safe_child(safe_child(args.output, ROOT), ROOT/'runs')
    if out.exists():
        parser.error('No overwrite or automatic retry')
    out.mkdir(parents=True)
    source_version = safe_child(args.source_version, ROOT/'runs/finish-v2/20261029/student') if args.source_version else None
    result = run(version, out, source_version)
    print(json.dumps({'status': result['status'], 'output': str(out)}))
    raise SystemExit(0 if result['status'] == 'PASS_ACTUAL_API_TEXT_CANCEL' else 1)
