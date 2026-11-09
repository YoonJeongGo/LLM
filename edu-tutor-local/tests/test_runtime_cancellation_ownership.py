"""CPU race fixtures: no models, native voice, project ledger, or downloads."""
from contextlib import contextmanager
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import threading

import pytest

from edu_tutor.models import budget, text_session
from edu_tutor.speech import direct, session


@pytest.fixture
def dispatch_fixture(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "src/edu_tutor/models/runtime.py"
    spec = importlib.util.spec_from_file_location("edu_tutor.models.cancel_ownership_runtime", source)
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    calls, clock, cancel = [], [0.0], threading.Event()
    monkeypatch.setattr(runtime, "time", SimpleNamespace(perf_counter=lambda: clock[0]))
    monkeypatch.setattr(text_session, "enabled", lambda _r, p: p["kind"] == "text")
    monkeypatch.setattr(session, "enabled", lambda *_: False)
    monkeypatch.setattr(session, "close", lambda *_a, **kw: calls.append(("close_tts", kw)))
    monkeypatch.setattr(text_session, "close", lambda *_a, **kw: calls.append(("close_text", kw)))
    monkeypatch.setattr(text_session, "status", lambda *_: {
        "resident": True, "session": {"instance_id": "retained-text", "latest_job_id": "old-text"}})
    monkeypatch.setattr(session, "status", lambda *_: {
        "resident": True, "session_key": "retained-tts", "latest_job_id": "old-tts", "instance_id": "old-tts-instance"})
    monkeypatch.setattr(budget, "finish", lambda ident, success: calls.append(("finish", ident, success)))

    def worker(name):
        def run(_p, **kwargs):
            calls.append(("worker", name, kwargs["timeout"]))
            yield {"type": "done"}
        return run
    monkeypatch.setattr(text_session, "run", worker("text"))
    monkeypatch.setattr(direct, "run", worker("sapi"))
    monkeypatch.setattr(runtime, "_run_worker", worker("gpu"))
    return SimpleNamespace(root=tmp_path, runtime=runtime, calls=calls, clock=clock, cancel=cancel)


@pytest.mark.parametrize("kind", ["speech", "speech_batch", "text", "vision"])
@pytest.mark.parametrize("interruption", ["cancel", "deadline", "denied"])
def test_unstarted_request_never_closes_unrelated_model(dispatch_fixture, monkeypatch, kind, interruption):
    f = dispatch_fixture
    payload = {"kind": kind, "job_id": "never-dispatched", "spec": {"provider": "windows_sapi_local"},
               "speech_provider": "windows_sapi_local", "items": [{"spec": {"provider": "windows_sapi_local"}}]}
    def reserve(*_a, **_kw):
        f.calls.append(("reserve",))
        if interruption == "denied":
            raise RuntimeError("fixture budget denied")
        if interruption == "cancel":
            f.cancel.set()
        else:
            f.clock[0] = 301
        return "owned-reservation", 300
    monkeypatch.setattr(budget, "reserve", reserve)
    with pytest.raises((RuntimeError, TimeoutError)):
        list(f.runtime.run_worker(payload, root=f.root, cancel_event=f.cancel, timeout=300))
    assert not [c for c in f.calls if c[0].startswith("close_")], f.calls
    assert not [c for c in f.calls if c[0] == "worker"], f.calls
    assert [c for c in f.calls if c[0] == "finish"] == ([] if interruption == "denied" else [("finish", "owned-reservation", False)])


def test_cancelled_after_slot_but_before_reservation_does_not_transition(dispatch_fixture, monkeypatch):
    f = dispatch_fixture
    @contextmanager
    def interleaving_slot(*_a, **_kw):
        f.cancel.set()
        yield {"remaining_seconds": 300, "queue_wait_seconds": 0}
    monkeypatch.setattr(session, "execution_slot", interleaving_slot)
    monkeypatch.setattr(budget, "reserve", lambda *_a, **_kw: pytest.fail("cancelled request reserved"))
    with pytest.raises(RuntimeError, match="cancelled"):
        list(f.runtime.run_worker({"kind": "vision"}, root=f.root, cancel_event=f.cancel))
    assert f.calls == []


def test_heami_keeps_unrelated_idle_gpu_owner_even_when_successful(dispatch_fixture, monkeypatch):
    f = dispatch_fixture
    monkeypatch.setattr(budget, "reserve", lambda *_a, **_kw: ("sapi-reservation", 300))
    assert list(f.runtime.run_worker({"kind": "speech", "spec": {"provider": "windows_sapi_local"}}, root=f.root)) == [{"type": "done"}]
    assert not [c for c in f.calls if c[0].startswith("close_")]
    assert f.calls[-1] == ("finish", "sapi-reservation", True)


def test_gpu_transition_is_after_reservation_and_targets_observed_text_owner(dispatch_fixture, monkeypatch):
    f = dispatch_fixture
    def reserve(*_a, **_kw):
        f.calls.append(("reserve",))
        return "vision-reservation", 300
    monkeypatch.setattr(budget, "reserve", reserve)
    list(f.runtime.run_worker({"kind": "vision"}, root=f.root))
    assert f.calls[0] == ("reserve",)
    text_close = next(c for c in f.calls if c[0] == "close_text")
    assert text_close[1]["instance_id"] == "retained-text"
    assert next(c for c in f.calls if c[0] == "worker")[1] == "gpu"
    assert f.calls[-1] == ("finish", "vision-reservation", True)


def test_transition_time_is_inside_request_deadline(dispatch_fixture, monkeypatch):
    f = dispatch_fixture
    monkeypatch.setattr(budget, "reserve", lambda *_a, **_kw: ("reservation", 300))
    def close_text(*_a, **_kw):
        f.calls.append(("close_text",))
        f.clock[0] = 301
    monkeypatch.setattr(text_session, "close", close_text)
    with pytest.raises(TimeoutError):
        list(f.runtime.run_worker({"kind": "vision"}, root=f.root))
    assert not [c for c in f.calls if c[0] in {"worker", "close_tts"}]
    assert f.calls[-1] == ("finish", "reservation", False)


def test_late_idle_callback_cannot_expire_a_later_idle_request(tmp_path):
    calls = []
    child = SimpleNamespace(instance_id="same-worker", active=False, idle_generation=2,
                            stop=lambda reason: calls.append(reason), record={})
    key = str(tmp_path.resolve())
    with text_session._LOCK:
        text_session._CURRENT[key] = child
    try:
        text_session._expire(tmp_path, "same-worker", "idle_expired", idle_generation=1)
        assert calls == []
        assert text_session._CURRENT[key] is child
        text_session._expire(tmp_path, "same-worker", "idle_expired", idle_generation=2)
        assert calls == ["idle_expired"]
    finally:
        with text_session._LOCK:
            text_session._CURRENT.pop(key, None)
            text_session._LAST.pop(key, None)


@pytest.mark.parametrize("interruption", ["cancel", "deadline"])
def test_event_arriving_during_cancel_or_deadline_is_not_returned(monkeypatch, interruption):
    cancel, clock = threading.Event(), [0.0]
    class QueueRace:
        def get(self, timeout):
            if interruption == "cancel":
                cancel.set()
            else:
                clock[0] = 2
            return ('{"type":"delta","text":"late"}', 0.0, 0.0, 0.0)
    child = SimpleNamespace(closed=False, events=QueueRace())
    monkeypatch.setattr(text_session, "time", SimpleNamespace(perf_counter=lambda: clock[0]))
    with pytest.raises((RuntimeError, TimeoutError)):
        text_session._Child.receive(child, 1, cancel)


def test_stale_same_job_request_cleanup_cannot_close_its_repair_request(tmp_path):
    calls = []
    child = SimpleNamespace(instance_id="worker", job_id="same-chat-job", request_id="repair-request",
                            stop=lambda reason: calls.append(reason), record={})
    key = str(tmp_path.resolve())
    text_session._CURRENT[key] = child
    try:
        result = text_session.close(tmp_path, "old-request-failure", job_id="same-chat-job",
                                    instance_id="worker", request_id="first-request")
        assert not result["closed"] and calls == []
        assert text_session._CURRENT[key] is child
    finally:
        text_session._CURRENT.pop(key, None)
