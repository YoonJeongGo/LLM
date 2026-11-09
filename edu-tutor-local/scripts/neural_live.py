"""At most eight bounded real inferences for the neural-view acceptance check.

Synthetic QA questions and real events are explicitly retained for this requested
acceptance record. Product requests remain ephemeral unless Save is chosen.
Failures/reservations count too; this ledger is never automatically reset.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
import time
from uuid import uuid4

from filelock import FileLock
import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/neural/current/gpu'
QUESTIONS = {
    'a': '토큰과 Transformer 층이 각각 무엇인지 한국어로 세 문장으로 설명해 주세요.',
    'b': 'SQL에서 WHERE와 HAVING의 차이를 짧은 예시와 함께 한국어로 설명해 주세요.',
    'long': 'Transformer의 임베딩, attention, MLP, 정규화, residual, 출력 토큰 선택을 각각 번호를 붙여 자세히 설명해 주세요.',
}


def save(path, value):
    raw = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
    if len(raw) > 20_000_000:
        raise RuntimeError('Acceptance record exceeds 20 MB; not saved')
    usage = sum(p.stat().st_size for p in (ROOT / 'runs/neural').rglob('*') if p.is_file())
    if usage + len(raw) > 200_000_000:
        raise RuntimeError('Neural acceptance artifacts reached the 200 MB ceiling')
    path.write_bytes(raw)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['off', 'light', 'detail'], required=True)
    parser.add_argument('--question', choices=list(QUESTIONS), default='a')
    parser.add_argument('--adapter', default='base')
    parser.add_argument('--name', required=True)
    parser.add_argument('--cancel-after', type=float)
    parser.add_argument('--toggle', action='store_true')
    parser.add_argument('--reconnect', action='store_true')
    args = parser.parse_args()
    if not args.name.replace('-', '').replace('_', '').isalnum():
        raise ValueError('Invalid record name')
    OUT.mkdir(parents=True, exist_ok=True)
    ledger_path = OUT / 'attempts.json'
    with FileLock(str(OUT / 'attempts.lock')):
        ledger = json.loads(ledger_path.read_text(encoding='utf-8')) if ledger_path.exists() else []
        if len(ledger) >= 8:
            raise RuntimeError('Eight-request acceptance limit reached; no request sent')
        if any(r['name'] == args.name for r in ledger):
            raise RuntimeError('An existing acceptance attempt cannot be repeated implicitly')
        entry = {'name': args.name, 'reserved_at': datetime.now(timezone.utc).isoformat(), 'state': 'reserved'}
        ledger.append(entry)
        save(ledger_path, ledger)

    token = (ROOT / '.local/auth-token').read_text(encoding='utf-8').strip()
    headers = {'Authorization': 'Bearer ' + token}
    result = {'name': args.name, 'source': 'actual_local_gpu_and_authenticated_sse',
              'raw_retention_authorization': 'Synthetic QA question and events explicitly retained for requested acceptance evidence',
              'started_at': entry['reserved_at'], 'events': [], 'stream_errors': [], 'control_actions': [],
              'cold_worker': True, 'separate_warmup_inference': False}
    result['worker_source_sha256'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
        'src/edu_tutor/models/worker.py', 'src/edu_tutor/models/observation.py', 'src/edu_tutor/models/runtime.py')}
    began = time.monotonic()
    runtime_before = {p.name for p in (ROOT / 'runs').glob('runtime-*') if p.is_dir()}
    with httpx.Client(base_url='http://127.0.0.1:8000', headers=headers, timeout=30, trust_env=False) as client:
        def call(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
        try:
            result['budget_before'] = call('GET', '/api/resources/budget')
            state = call('GET', '/api/neural/state')
            structure = state.get('structure') or {}
            layers = [n.get('path', n.get('module_path')) for n in structure.get('nodes', []) if n.get('role') == 'block']
            body = {'text': QUESTIONS[args.question], 'observation_mode': args.mode,
                    'selected_layers': ([layers[0], layers[-1]] if layers else []) if args.mode == 'detail' else [],
                    'sample_every_steps': 16, 'max_new_tokens': 128, 'request_id': 'neural-qa-' + uuid4().hex,
                    'generation_epoch': len(ledger), 'update_interval_ms': 250, 'adapter_id': args.adapter}
            if args.mode == 'detail' and not body['selected_layers']:
                raise RuntimeError('Detail acceptance needs a previously measured structure')
            result['request'] = body
            run = call('POST', '/api/neural/runs', json=body)
            ident = run['run_id']
            result['run_id'], result['job_id'] = ident, run['job_id']
            print(json.dumps({'name': args.name, 'run_id': ident, 'job_id': run['job_id'], 'mode': args.mode}), flush=True)
            done = threading.Event()
            observed_running_at = None
            stream_bytes = [0]

            def listen():
                try:
                    cursor = 0
                    reconnect_done = False
                    while True:
                        reconnect_now = False
                        with httpx.stream('GET', f'http://127.0.0.1:8000/api/neural/runs/{ident}/events?after={cursor}',
                                          headers=headers, timeout=330, trust_env=False) as response:
                            response.raise_for_status()
                            for line in response.iter_lines():
                                if line.startswith('data:'):
                                    event = json.loads(line[5:].strip())
                                    item = {'received_at': datetime.now(timezone.utc).isoformat(), 'event': event}
                                    stream_bytes[0] += len(json.dumps(item, ensure_ascii=False).encode())
                                    if stream_bytes[0] < 16_000_000:
                                        result['events'].append(item)
                                    else:
                                        result['stream_capture_limit_reached'] = True
                                    if event.get('event_type') not in {'snapshot', 'gap'}:
                                        cursor = max(cursor, event.get('sequence_no', 0))
                                    if args.reconnect and not reconnect_done and event.get('event_type') == 'token' and event.get('payload', {}).get('step', 0) >= 32:
                                        reconnect_now = True
                                        break
                                if done.is_set():
                                    break
                        if not reconnect_now or done.is_set():
                            break
                        result['control_actions'].append({'action': 'last_sse_subscriber_disconnect', 'after_sequence': cursor,
                                                         'at': datetime.now(timezone.utc).isoformat()})
                        time.sleep(1)  # slow/closed observer simulation; never sleeps the worker
                        reconnect_done = True
                        result['control_actions'].append({'action': 'sse_reconnect_same_run', 'after_sequence': cursor,
                                                         'at': datetime.now(timezone.utc).isoformat()})
                except Exception as exc:
                    result['stream_errors'].append(type(exc).__name__ + ': ' + str(exc)[:300])

            reader = threading.Thread(target=listen, daemon=True)
            reader.start()
            cancelled = False
            disabled = False
            reenabled = False
            while time.monotonic() - began < 330:
                current = call('GET', '/api/neural/runs/' + ident)
                result['run'] = current
                phase = current.get('state') or current.get('status')
                if phase in {'running', 'generating', 'inference'} and observed_running_at is None:
                    observed_running_at = time.monotonic()
                elapsed_run = time.monotonic() - observed_running_at if observed_running_at else 0
                if args.toggle and elapsed_run > 1 and not disabled:
                    result['control_actions'].append(call('POST', f'/api/neural/runs/{ident}/observation', json={'enabled': False, 'generation_epoch': body['generation_epoch']}))
                    disabled = True
                if args.toggle and elapsed_run > 2 and not reenabled:
                    result['control_actions'].append(call('POST', f'/api/neural/runs/{ident}/observation', json={'enabled': True, 'generation_epoch': body['generation_epoch'], 'mode': args.mode, 'selected_layers': body['selected_layers']}))
                    reenabled = True
                if args.cancel_after and elapsed_run > args.cancel_after and not cancelled:
                    result['control_actions'].append(call('POST', f'/api/neural/runs/{ident}/cancel', json={'generation_epoch': body['generation_epoch']}))
                    cancelled = True
                if phase in {'succeeded', 'completed', 'failed', 'cancelled', 'interrupted', 'blocked', 'error'}:
                    break
                time.sleep(.2)
            else:
                call('POST', f'/api/neural/runs/{ident}/cancel', json={'generation_epoch': body['generation_epoch']})
                raise TimeoutError('Acceptance requested cancellation after 330 seconds')
            reader.join(timeout=3)
            done.set()
            result['wall_seconds'] = time.monotonic() - began
            result['event_counts'] = dict(Counter(x['event'].get('event_type') for x in result['events']))
            result['budget_after'] = call('GET', '/api/resources/budget')
            # The full SSE capture above is the explicitly retained evidence;
            # avoid duplicating sensitive traces through the product Save API.
            entry['state'] = 'completed'
        except Exception as exc:
            result['error'] = type(exc).__name__ + ': ' + str(exc)[:700]
            entry['state'] = 'failed'
            raise
        finally:
            result['finished_at'] = datetime.now(timezone.utc).isoformat()
            result['runtime_records'] = []
            for folder in (ROOT / 'runs').glob('runtime-*'):
                if not folder.is_dir() or folder.name in runtime_before:
                    continue
                report = folder / 'result.json'
                value = json.loads(report.read_text(encoding='utf-8')) if report.exists() else None
                result['runtime_records'].append({'path': str(folder.relative_to(ROOT)),
                    'result_sha256': hashlib.sha256(report.read_bytes()).hexdigest() if report.exists() else None,
                    'redacted_result': value,
                    'no_raw_fields_persisted': not any(k in (value or {}) for k in ('text', 'input_token_ids', 'output_token_ids', 'activations'))})
            save(OUT / (args.name + '.json'), result)
            with FileLock(str(OUT / 'attempts.lock')):
                ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
                next(r for r in ledger if r['name'] == args.name).update(entry, run_id=result.get('run_id'))
                save(ledger_path, ledger)
            print(json.dumps({'name': args.name, 'state': entry['state'], 'wall_seconds': result.get('wall_seconds'),
                              'event_counts': result.get('event_counts'), 'error': result.get('error')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
