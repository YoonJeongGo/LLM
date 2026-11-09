"""Fake HTTP/clock/handle, temporary ROOT only. No API, model or OS child."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest


def load():
    spec = importlib.util.spec_from_file_location('prepared_explicit_cancel', Path(__file__).with_name('explicit_cancel_once.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    module = load()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    version = tmp_path/'runs/student/final-fixture'
    expected = {'model_id': 'fixture-model', 'revision': 'fixture-revision', 'active_adapter': None}
    frozen = {'version': version.name, 'source_hashes': {'src/core.py': 'CPU-fixture-hash'}, 'state': {'model': expected}}
    write(version/'execution-version.json', frozen)
    for i in range(1, 9):
        write(version/f'J{i:02}'/'actual.json', {'id': f'J{i:02}', 'status': 'COMPLETED_CPU_FIXTURE',
            'completed_at': 'fixture', 'version': version.name, 'source_hashes': frozen['source_hashes'],
            'source_unchanged_at_end': True, 'spec': {'question': 'CPU dummy question, never submitted to a real API'}})
    monkeypatch.setattr(module, 'frozen', lambda _: frozen)
    ledger = tmp_path/'runs/phase2/current/resource-budget.json'
    old = {'id': 'old', 'status': 'completed'}
    write(ledger, {'requests': [old]})
    (tmp_path/'.local').mkdir()
    (tmp_path/'.local/auth-token').write_text('CPU fake token')
    out = tmp_path/'runs/output'
    out.mkdir()
    state = {'cancel': False, 'submitted': False, 'lost': False, 'fast': False, 'posts': [], 'clock': 100.0}
    instance = 'a'*32
    active = {'latest_job_id': 'owned-job', 'active_request': True, 'model_instance_id': 'actual-fixture-instance',
        'instance_id': instance, 'worker_pid': 7, 'process_start_time': 1000.0,
        'ownership': {'pid': 7, 'ancestry_verified': True, 'job_assigned': True}, 'requested_precision': 'bf16',
        'inference': {'requested_precision': 'bf16', 'actual_is_loaded_in_4bit': False, 'quantization': 'none',
                      'load_dtype': 'torch.bfloat16',
                      'actual_parameter_devices': ['cuda:0'], 'actual_parameter_dtypes_elements': {'torch.bfloat16': 100}}}
    session_path = tmp_path/'runs'/('text-session-'+instance)/'session.json'
    write(session_path, active)
    (session_path.parent/'stderr.log').write_text('CPU fixture log; no native execution')
    def job():
        return {'id': 'owned-job', 'session_id': 'owned-session', 'request_id': state.get('request_id'),
                'state': 'cancelled' if state['cancel'] else 'succeeded' if state['fast'] else 'running',
                'raw_partial_text': 'actual fake delta' if state['submitted'] else ''}
    def get(path):
        if path == '/api/jobs':
            return [job()] if state['submitted'] else []
        if path == '/api/jobs/owned-job':
            return job()
        if path == '/api/models':
            return {**expected, 'text_session': {'session': active if state['submitted'] else None}}
        if path == '/api/tts/session':
            return {'resident': False}
        if path == '/api/resources/budget':
            return {'accounting_scope': module.SCOPE, 'active_execution_allowance': {'id': module.SCOPE, 'text_remaining': 10, 'seconds_remaining': 1000}}
        if path == '/api/sessions/owned-session/messages':
            return [{'id': 'ordinary-answer', 'request_id': state['request_id'], 'role': 'assistant'}] if state['fast'] else []
        raise AssertionError('Unexpected GET '+path)
    monkeypatch.setattr(module, 'require_get', get)
    def open(request, timeout):
        path = request.full_url.removeprefix('http://127.0.0.1:8000')
        state['posts'].append(path)
        payload = json.loads(request.data)
        if path == '/api/sessions':
            value = {'id': 'owned-session'}
        elif path == '/api/sessions/owned-session/messages':
            assert payload['verification_mode'] == 'model_only' and payload['adapter'] == 'base' and not payload['use_rag']
            state.update(submitted=True, request_id=payload['request_id'])
            write(ledger, {'requests': [old, {'id': 'owned-reservation', 'kind': 'text', 'job_id': 'owned-job',
                'execution_allowance_id': module.SCOPE, 'status': 'completed' if state['fast'] else 'reserved',
                'charged_seconds': 300, 'request_limit_seconds': 300}]})
            if state['lost']:
                raise TimeoutError('CPU simulated lost response after acceptance')
            value = {'job_id': 'owned-job', 'generation_epoch': 1}
        elif path == '/api/jobs/owned-job/cancel':
            state['cancel'] = True
            write(session_path, {**active, 'status': 'closed', 'actual_worker_exit_confirmed': True, 'process_exit_confirmed': True})
            rows = json.loads(ledger.read_text())
            rows['requests'][-1].update(status='failed_or_cancelled', charged_seconds=3)
            write(ledger, rows)
            value = job()
        else:
            raise AssertionError('Unexpected POST '+path)
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self): return json.dumps(value).encode()
        return Response()
    monkeypatch.setattr(module.urllib.request, 'build_opener', lambda *_: SimpleNamespace(open=open))
    def sleep(seconds): state['clock'] += seconds
    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: state['clock'], sleep=sleep))
    class Handle:
        def __init__(self, pid, birth): assert (pid, birth) == (7, 1000.0); self.birth = birth
        def exited(self): return state['cancel']
        def exit_code(self): return 0 if state['cancel'] else 259
        def close(self): state['handle_closed'] = True
    monkeypatch.setattr(module, 'ExactProcess', Handle)
    return module, version, out, state, active


def test_one_owned_text_cancel_and_ledger_finalization(fixture):
    module, version, out, state, _ = fixture
    result = module.run(version, out)
    assert result['status'] == 'PASS_ACTUAL_API_TEXT_CANCEL'
    assert state['posts'] == ['/api/sessions', '/api/sessions/owned-session/messages', '/api/jobs/owned-job/cancel']
    assert result['exact_worker_handle_exited'] and state['handle_closed']
    assert result['original_ledger_prefix_unchanged'] and result['late_observation_seconds'] >= 5


def test_lost_creation_receipt_only_cancels_matching_owned_request(fixture):
    module, version, out, state, _ = fixture
    state['lost'] = True
    result = module.run(version, out)
    assert result['status'] == 'FAILED_NO_RETRY'
    assert state['posts'].count('/api/sessions/owned-session/messages') == 1
    assert state['posts'].count('/api/jobs/owned-job/cancel') == 1
    assert result['final_job']['state'] == 'cancelled'
    assert result['exact_worker_handle_exited'] is None  # cleanup is not the requested actual-generation proof


def test_fast_completion_is_not_exercised_without_retry(fixture):
    module, version, out, state, _ = fixture
    state['fast'] = True
    result = module.run(version, out)
    assert result['status'] == 'NOT_EXERCISED_REQUEST_FINISHED_BEFORE_CANCEL'
    assert len(state['posts']) == 2 and not state['cancel']


def test_copied_foreign_version_artifact_blocks_before_any_post(fixture):
    module, version, out, state, _ = fixture
    path = version/'J04/actual.json'
    record = json.loads(path.read_text())
    record['version'] = 'older-build'
    write(path, record)
    with pytest.raises(RuntimeError, match='frozen execution version'):
        module.run(version, out)
    assert not state['posts']


def test_native_av_diagnostic_prevents_stability_pass_even_with_zero_exit(fixture):
    module, version, out, state, active = fixture
    path = module.ROOT/'runs'/('text-session-'+active['instance_id'])/'stderr.log'
    path.write_text('Windows fatal exception: access violation\nCPU simulated diagnostic; no native code ran')
    result = module.run(version, out)
    assert result['status'] == 'FAILED_CANCEL_OR_PRESERVATION_CHECK'
    assert result['checks']['cancelled_terminal'] and result['checks']['actual_worker_exited']
    assert not result['checks']['no_native_fatal_cleanup_diagnostic']
    assert result['exact_worker_exit_code'] == 0


@pytest.mark.parametrize('change', [lambda s: s.update(latest_job_id='foreign'),
    lambda s: s['ownership'].update(job_assigned=False), lambda s: s.update(active_request=False),
    lambda s: s['inference'].update(actual_is_loaded_in_4bit=True), lambda s: s.update(model_instance_id=None)])
def test_unowned_or_unloaded_or_wrong_precision_not_accepted(fixture, change):
    module, _, _, _, active = fixture
    value = copy.deepcopy(active)
    change(value)
    job = {'id': 'owned-job', 'state': 'running', 'raw_partial_text': 'CPU delta'}
    assert not module.ready_owned_request(job, value, 'owned-job')
