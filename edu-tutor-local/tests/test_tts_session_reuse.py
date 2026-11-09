"""Resident transport contracts using a tiny CPU child, never torch or TTS.

The child uses the actual project GPU *OS lock* while its synthetic model is
resident. Object identities and output files here are fixtures, not inference.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from edu_tutor.jobs.lease import GPULease, LeaseBusy
from edu_tutor.models import budget, runtime
from edu_tutor.speech import session


MOCK_CHILD = r'''
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from edu_tutor.jobs.lease import GPULease
model = None
loads = 0
lease = None
try:
    for line in sys.stdin:
        command = json.loads(line)
        if command.get('command') in ('shutdown', 'close'):
            break
        assert command['command'] == 'synthesize'
        payload = command['payload']
        instance = command['instance_id']
        request = command['request_id']
        def emit(kind, **value):
            print(json.dumps({'type':kind, 'instance_id':instance, 'worker_pid':os.getpid(),
                              'request_id':request, **value}), flush=True)
        if lease is None:
            lease = GPULease(Path(payload['root'])/'.local', instance)
            lease.__enter__()
        if model is None:
            model = object()
            loads += 1
        emit('fixture_started', fixture_pid=os.getpid(), fixture_parent_pid=os.getppid(), fixture_model_id=id(model),
             fixture_load_count=loads, job_id=payload['job_id'])
        mode = payload.get('fixture_mode', 'normal')
        if mode == 'crash':
            os._exit(13)
        if mode == 'delay':
            time.sleep(10)
        if mode == 'stale':
            print(json.dumps({'type':'audio', 'instance_id':'dead-instance',
                              'request_id':'previous-request', 'fixture_foreign':True}), flush=True)
        target = Path(payload['run_dir'])/'fixture-output.json'
        target.write_text(json.dumps({'job_id':payload['job_id'], 'request_id':request}), encoding='utf8')
        emit('audio', audio_id=payload['items'][0]['audio_id'],
             fixture_pid=os.getpid(), fixture_parent_pid=os.getppid(), fixture_model_id=id(model), fixture_load_count=loads,
             job_id=payload['job_id'], fixture_output=str(target),
             fixture_cancel_path=payload['cancel_path'])
        emit('done', fixture_load_count=loads)
finally:
    if lease is not None:
        emit('closed', model_resident=False, memory_after_release={'fixture_only':True})
        lease.__exit__(None, None, None)
'''


def write_policy(root, *, mode="session", idle_seconds=30, max_session_seconds=600, clips=2):
    local = root / ".local"
    local.mkdir(parents=True, exist_ok=True)
    (local / "tts-session-policy.json").write_text(json.dumps({
        "mode": mode, "idle_seconds": idle_seconds, "max_session_seconds": max_session_seconds}), encoding="utf8")
    empty_hash = hashlib.sha256(b"[]").hexdigest()
    (local / "phase2-policy.json").write_text(json.dumps({
        "enabled": True, "gpu_seconds": 5400, "new_audio_clips": clips, "vision_requests": 0,
        "min_C_free_bytes": 0, "system_volume": str(root), "per_request_seconds": 300,
        "active_execution_allowance": {"id": "cpu-fixture-only", "baseline_request_count": 0,
            "baseline_requests_sha256": empty_hash,
            "limits": {"text_requests": 0, "new_audio_clips": clips, "vision_requests": 0, "gpu_seconds": 600}}
    }), encoding="utf8")


def payload(job, *, owner="lesson-binding-A", mode="normal"):
    return {"kind": "speech_batch", "job_id": job, "tts_session_key": owner,
            "fixture_mode": mode, "items": [{"audio_id": hashlib.sha256(job.encode()).hexdigest(), "spec": {"text": "CPU fixture"}}]}


@pytest.fixture
def mock_worker(tmp_path, monkeypatch):
    write_policy(tmp_path)
    script = tmp_path / "mock_resident.py"
    script.write_text(MOCK_CHILD, encoding="utf8")
    source = Path(__file__).resolve().parents[1] / "src"
    monkeypatch.setattr(session, "_worker_command", lambda _root: session._python_command(_root, script=script, args=[str(source)]))
    original_popen = subprocess.Popen
    children = []
    def popen(*args, **kwargs):
        child = original_popen(*args, **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(session.subprocess, "Popen", popen)
    value = SimpleNamespace(root=tmp_path, children=children)
    yield value
    session.close(tmp_path, reason="cpu_test_cleanup")
    for child in children:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=5)


def audio(events):
    return next(e for e in events if e["type"] == "audio")


def assert_lease_released(root):
    with GPULease(root / ".local", "independent_cpu_check"):
        pass


def test_two_independent_requests_share_one_mock_model_and_hold_lease_until_close(mock_worker):
    root = mock_worker.root
    first = audio(list(runtime.run_worker(payload("job-one"), root=root, timeout=8)))
    second = audio(list(runtime.run_worker(payload("job-two"), root=root, timeout=8)))
    assert len(mock_worker.children) == 1
    assert first["fixture_pid"] == second["fixture_pid"]
    # The direct-interpreter bootstrap bypasses Windows venv redirectors so the
    # owned Popen handle is now the actual Python process holding the GPU lock.
    assert mock_worker.children[0].pid == first["fixture_pid"] == first["worker_pid"]
    assert first["fixture_model_id"] == second["fixture_model_id"]
    assert first["fixture_load_count"] == second["fixture_load_count"] == 1
    assert first["request_id"] != second["request_id"]
    assert first["job_id"] == "job-one" and second["job_id"] == "job-two"
    assert first["fixture_output"] != second["fixture_output"]
    assert first["fixture_cancel_path"] != second["fixture_cancel_path"]
    assert json.loads(Path(first["fixture_output"]).read_text())["job_id"] == "job-one"
    assert json.loads(Path(second["fixture_output"]).read_text())["job_id"] == "job-two"
    rows = json.loads((root / "runs/phase2/current/resource-budget.json").read_text())["requests"]
    assert [r["job_id"] for r in rows] == ["job-one", "job-two"]
    assert all(r["new_audio_clips"] == 1 and r["status"] == "completed" for r in rows)
    with pytest.raises(LeaseBusy):
        with GPULease(root / ".local", "other_model"):
            pass
    closed = session.close(root, session_key="lesson-binding-A", reason="lesson_complete")
    assert mock_worker.children[0].poll() is not None
    assert closed["child_release_report"]["model_resident"] is False
    assert closed["child_release_report"]["memory_after_release"]["fixture_only"]
    assert_lease_released(root)


def test_budget_refusal_does_not_spawn_or_reset_resident(mock_worker):
    root = mock_worker.root
    write_policy(root, clips=0)
    with pytest.raises(budget.ResourceBudgetExceeded):
        list(runtime.run_worker(payload("denied"), root=root, timeout=8))
    assert mock_worker.children == []
    assert_lease_released(root)


def test_late_completed_job_cancel_cannot_close_new_request_in_same_lesson(mock_worker):
    root = mock_worker.root
    first = audio(list(runtime.run_worker(payload("old-completed"), root=root, timeout=8)))
    second = audio(list(runtime.run_worker(payload("new-completed"), root=root, timeout=8)))
    assert first["fixture_pid"] == second["fixture_pid"]
    stale = session.close(root, session_key="lesson-binding-A", job_id="old-completed", reason="late_cancel")
    assert stale == {"closed": False, "reason": "no_matching_owned_job"}
    assert session.status(root)["resident"] and session.status(root)["latest_job_id"] == "new-completed"
    closed = session.close(root, session_key="lesson-binding-A", job_id="new-completed", reason="student_stop")
    assert closed["closed"] and mock_worker.children[0].poll() is not None
    assert_lease_released(root)


def test_exited_child_pipe_close_error_keeps_confirmed_exit_and_releases_registry(mock_worker):
    root = mock_worker.root
    list(runtime.run_worker(payload("pipe-close-owner"), root=root, timeout=8))
    child = mock_worker.children[0]
    child.terminate()
    child.wait(timeout=2)
    original_stdin = child.stdin
    class ClosedChildPipe:
        closed = False
        def close(self):
            try:
                original_stdin.close()
            except OSError:
                pass
            raise OSError(22, "fixture exited Windows pipe")
    child.stdin = ClosedChildPipe()
    closed = session.close(root, session_key="lesson-binding-A", job_id="pipe-close-owner")
    assert closed["closed"] and closed["process_exit_confirmed"]
    assert closed["stream_cleanup_errors"][0]["stream"] == "stdin"
    assert not session.status(root)["resident"]
    assert_lease_released(root)


def test_required_warm_instance_cannot_silently_load_a_replacement(mock_worker):
    request = {**payload("warm-missing"), "expected_instance_id": "expired-worker-instance"}
    with pytest.raises(session.SessionUnavailable, match="warm"):
        list(runtime.run_worker(request, root=mock_worker.root, timeout=8))
    assert mock_worker.children == []
    assert_lease_released(mock_worker.root)


def test_missing_opt_in_uses_existing_per_request_path(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(runtime, "_run_worker", lambda p, **kw: iter([seen.append(p) or {"type": "done"}]))
    monkeypatch.setattr(session, "run", lambda *a, **kw: pytest.fail("Resident path must remain opt-in"))
    assert list(runtime.run_worker(payload("ordinary"), root=tmp_path))[-1]["type"] == "done"
    assert len(seen) == 1


@pytest.mark.parametrize("failure", ["cancel", "timeout", "crash"])
def test_failure_closes_exact_child_without_retry_and_releases_lease(mock_worker, failure):
    root = mock_worker.root
    cancel = threading.Event()
    events = []
    work = runtime.run_worker(payload("failed-job", mode="crash" if failure == "crash" else "delay"),
                              root=root, cancel_event=cancel, timeout=8)
    try:
        for event in work:
            events.append(event)
            if failure == "cancel" and event["type"] == "fixture_started":
                cancel.set()
    except (RuntimeError, TimeoutError):
        pass
    assert not any(e["type"] == "audio" for e in events)
    assert len(mock_worker.children) == 1 and mock_worker.children[0].poll() is not None
    rows = json.loads((root / "runs/phase2/current/resource-budget.json").read_text())["requests"]
    assert len(rows) == 1 and rows[0]["status"] == "failed_or_cancelled" and rows[0]["new_audio_clips"] == 1
    assert_lease_released(root)


def test_foreign_response_is_never_published_or_attached(mock_worker):
    events = []
    try:
        events = list(runtime.run_worker(payload("current-job", mode="stale"), root=mock_worker.root, timeout=8))
    except RuntimeError:
        pass  # Rejecting the whole compromised request is also safe.
    assert not any(e.get("fixture_foreign") for e in events)
    assert all(e.get("job_id", "current-job") == "current-job" for e in events)
    assert len(mock_worker.children) == 1


def test_lesson_switch_closes_old_owner_and_stale_close_cannot_kill_new_owner(mock_worker):
    root = mock_worker.root
    first = audio(list(runtime.run_worker(payload("A"), root=root, timeout=8)))
    second = audio(list(runtime.run_worker(payload("B", owner="lesson-binding-B"), root=root, timeout=8)))
    assert len(mock_worker.children) == 2 and mock_worker.children[0].poll() is not None
    assert first["instance_id"] != second["instance_id"]
    session.close(root, session_key="lesson-binding-A", reason="late_old_lesson_cleanup")
    assert mock_worker.children[1].poll() is None
    session.close(root, session_key="lesson-binding-B", reason="new_lesson_complete")
    assert mock_worker.children[1].poll() is not None
    assert_lease_released(root)


def test_idle_expiry_releases_resident_memory_ownership(mock_worker):
    root = mock_worker.root
    write_policy(root, idle_seconds=1)
    list(runtime.run_worker(payload("idle"), root=root, timeout=8))
    deadline = time.monotonic() + 5
    while mock_worker.children[0].poll() is None and time.monotonic() < deadline:
        time.sleep(.05)
    assert mock_worker.children[0].poll() is not None
    assert_lease_released(root)


def test_session_lifetime_also_bounds_an_active_request(mock_worker):
    root = mock_worker.root
    write_policy(root, max_session_seconds=1)
    events = []
    started = time.monotonic()
    try:
        events = list(runtime.run_worker(payload("session-expiry", mode="delay"), root=root, timeout=8))
    except (RuntimeError, TimeoutError):
        pass
    assert time.monotonic() - started < 6
    assert not any(e["type"] == "audio" for e in events)
    assert len(mock_worker.children) == 1 and mock_worker.children[0].poll() is not None
    assert_lease_released(root)


def test_cancelled_queue_waiter_never_reserves_or_starts_worker(mock_worker):
    root = mock_worker.root
    cancel = threading.Event()
    entered = threading.Event()
    failures = []
    def waiting():
        entered.set()
        try:
            list(runtime.run_worker(payload("queued-cancel"), root=root, cancel_event=cancel, timeout=8))
        except (RuntimeError, TimeoutError) as exc:
            failures.append(type(exc).__name__)
    with session.execution_slot(root, timeout=8):
        thread = threading.Thread(target=waiting)
        thread.start()
        assert entered.wait(1)
        cancel.set()
        thread.join(timeout=2)
        assert not thread.is_alive(), "Queued cancellation must not wait for the active owner"
    assert mock_worker.children == []
    ledger = root / "runs/phase2/current/resource-budget.json"
    assert not ledger.exists() or not json.loads(ledger.read_text())["requests"]


def test_transition_releases_resident_before_other_model_can_acquire_gpu(mock_worker, monkeypatch):
    root = mock_worker.root
    list(runtime.run_worker(payload("resident"), root=root, timeout=8))
    observed = []
    def other_worker(p, **kwargs):
        assert mock_worker.children[0].poll() is not None
        with GPULease(root / ".local", "other_model_fixture"):
            observed.append(p["kind"])
            yield {"type": "done"}
    monkeypatch.setattr(runtime, "_run_worker", other_worker)
    # Budget behavior is independently exercised above and in the existing suite.
    # This transition fixture must never reserve an actual text/model request.
    monkeypatch.setattr(budget, "reserve", lambda *a, **kw: (None, 20))
    list(runtime.run_worker({"kind": "text", "job_id": "other-model"}, root=root, timeout=20))
    assert observed == ["text"] and len(mock_worker.children) == 1
    assert_lease_released(root)


def test_child_engine_reuses_model_processor_decoder_and_releases_model(tmp_path, monkeypatch):
    """Exercise the real child engine with injected objects, not the transport mock."""
    from edu_tutor.speech import provider, session_worker
    cuda_calls, loads, calls = [], [], []
    model = SimpleNamespace(processor=object(), decoder=object())
    fake_torch = SimpleNamespace(cuda=SimpleNamespace(
        synchronize=lambda: cuda_calls.append("sync"), empty_cache=lambda: cuda_calls.append("empty")))
    def loader(root):
        loads.append(root)
        return fake_torch, model, {"model_load_seconds": 2.0, "worker_heavy_import_seconds": 1.0}
    monkeypatch.setattr(session_worker, "placement", lambda m: {
        "model": id(m), "processor": id(m.processor), "decoder": id(m.decoder)})
    monkeypatch.setattr(session_worker, "memory_snapshot", lambda _torch: {"fixture_only": True})
    def speech(request, emit, **kwargs):
        calls.append({"model": kwargs["model"], "info": dict(kwargs["session_info"]),
                      "load_count": kwargs["model_load_count"], "load_seconds": kwargs["model_load_seconds"]})
        emit("audio", audio_id=request["audio_id"])
        return {"audio_id": request["audio_id"]}
    monkeypatch.setattr(provider, "speech_job", speech)
    engine = session_worker.SessionEngine(tmp_path, "fixture-instance", model_loader=loader)
    assert loads == [] and engine.model is None
    request = {**payload("engine-one"), "root": str(tmp_path), "cancel_path": str(tmp_path / "not-cancelled")}
    events = []
    one = engine.process(request, "request-one", lambda kind, **v: events.append((kind, v)))
    two = engine.process({**request, "job_id": "engine-two"}, "request-two", lambda kind, **v: events.append((kind, v)))
    assert loads == [tmp_path.resolve()] and len(calls) == 2
    assert calls[0]["model"] is calls[1]["model"] is model
    assert [c["load_count"] for c in calls] == [1, 0]
    assert [c["load_seconds"] for c in calls] == [2.0, 0.0]
    assert calls[0]["info"]["model_placement"] == calls[1]["info"]["model_placement"]
    assert one["model_instance_id"] == two["model_instance_id"]
    assert one["worker_pid"] == two["worker_pid"]
    assert [c["info"]["request_id"] for c in calls] == ["request-one", "request-two"]
    assert len(events) == 2
    released = engine.close()
    assert engine.model is None and not released["model_resident"]
    assert cuda_calls == ["sync", "empty", "sync"]


@pytest.mark.parametrize("invalid", ["cancelled", "outside_output"])
def test_child_engine_rejects_invalid_work_before_loading(tmp_path, invalid):
    from edu_tutor.speech import session_worker
    def loader(_root):
        pytest.fail("Invalid or cancelled work must not load a model")
    engine = session_worker.SessionEngine(tmp_path, "fixture-instance", model_loader=loader)
    cancel = tmp_path / "cancel"
    request = {**payload("invalid"), "root": str(tmp_path), "cancel_path": str(cancel)}
    if invalid == "cancelled":
        cancel.touch()
    else:
        request.update(tts_benchmark=True, output_dir=str(tmp_path.parent / "outside"))
    with pytest.raises((ValueError, RuntimeError)):
        engine.process(request, "rejected", lambda *a, **kw: pytest.fail("Invalid work emitted output"))
    assert engine.load_count == 0 and engine.model is None
