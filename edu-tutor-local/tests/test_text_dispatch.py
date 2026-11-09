"""Runtime integration CPU boundary checks; model and ledger seams are fixtures."""
import importlib.util
from pathlib import Path

import pytest

from edu_tutor.models import budget, registry, text_session
from edu_tutor.speech import direct, session


@pytest.fixture
def runtime(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "src/edu_tutor/models/runtime.py"
    spec = importlib.util.spec_from_file_location("edu_tutor.models.resident_proposal_runtime", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(session, "enabled", lambda *_: False)
    return module


@pytest.mark.parametrize("kind,provider,expected,closes_text", [
    ("text", None, "resident", False),
    ("speech", "windows_sapi_local", "cpu", False),
    ("vision", None, "legacy", True),
    ("speech", "qwen", "legacy", True),
])
def test_dispatch_and_one_reservation(runtime, tmp_path, monkeypatch, kind, provider, expected, closes_text):
    calls = []
    monkeypatch.setattr(text_session, "enabled", lambda _root, payload: payload["kind"] == "text")
    monkeypatch.setattr(session, "close", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(text_session, "close", lambda *_args, **_kwargs: calls.append("close_text"))
    monkeypatch.setattr(text_session, "status", lambda *_: {"session": {"instance_id": "owned-text"}})
    monkeypatch.setattr(budget, "reserve", lambda *_args, **_kwargs: (calls.append("reserve") or "reservation", 20))
    monkeypatch.setattr(budget, "finish", lambda ident, success: calls.append((ident, success)))
    def run(name):
        def inner(*_args, **_kwargs):
            calls.append(name)
            yield {"type": "done"}
        return inner
    monkeypatch.setattr(text_session, "run", run("resident"))
    monkeypatch.setattr(direct, "run", run("cpu"))
    monkeypatch.setattr(runtime, "_run_worker", run("legacy"))
    assert list(runtime.run_worker({"kind": kind, "spec": {"provider": provider}}, root=tmp_path)) == [{"type": "done"}]
    assert calls == ["reserve"] + (["close_text"] if closes_text else []) + [expected, ("reservation", True)]


def test_reservation_denial_preserves_unrelated_idle_owner_and_never_dispatches(runtime, tmp_path, monkeypatch):
    closed = []
    monkeypatch.setattr(text_session, "enabled", lambda *_: True)
    monkeypatch.setattr(text_session, "run", lambda *_args, **_kwargs: pytest.fail("unreserved work"))
    monkeypatch.setattr(session, "close", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(text_session, "close", lambda *_args, **_kwargs: closed.append(True))
    def denied(*_args, **_kwargs):
        raise RuntimeError("budget fixture denied")
    monkeypatch.setattr(budget, "reserve", denied)
    with pytest.raises(RuntimeError, match="budget fixture"):
        list(runtime.run_worker({"kind": "text"}, root=tmp_path))
    assert closed == []


def test_message_metadata_keeps_real_residency_identity(runtime, tmp_path, monkeypatch, nf4_inference_fixture):
    monkeypatch.setattr(runtime, "model_status", lambda *_: {"ready": True})
    monkeypatch.setattr(registry, "resolve_adapter", lambda *_: None)
    identity = {"worker_pid": 123, "instance_id": "process", "model_instance_id": "weights", "model_python_id": 456,
        "cumulative_model_load_count": 1, "request_model_load_count": 0, "model_load_count": 0,
        "model_resident": True, "parent_timing": {"clock": "perf_counter"}}
    monkeypatch.setattr(runtime, "run_worker", lambda *_args, **_kwargs: iter([
        {"type": "delta", "text": "CPU fixture"}, {"type": "metadata", "finish_reason": "eos", "adapter": None,
         "requested_precision": "nf4", "inference": nf4_inference_fixture, **identity}]))
    target = {}
    assert list(runtime.generate([{"role": "user", "content": "fixture"}], root=tmp_path, metadata_out=target)) == ["CPU fixture"]
    assert all(target[key] == value for key, value in identity.items())


def test_live_state_overrides_saved_runtime_structure(runtime, tmp_path, monkeypatch):
    import json
    folder = tmp_path / ".local/models/text"
    folder.mkdir(parents=True)
    (folder / "runtime-structure.json").write_text(json.dumps({"resident": True, "structure_notice": "stale per-request"}))
    monkeypatch.setattr(registry, "selection", lambda *_: {"active_adapter": "base"})
    monkeypatch.setattr(text_session, "status", lambda *_: {"resident": False})
    assert runtime.model_status(tmp_path)["resident"] is False


def test_reservation_cpu_time_reduces_worker_deadline_and_is_reported(runtime, tmp_path, monkeypatch):
    from types import SimpleNamespace
    clock, captured, finished = [0.0], {}, []
    monkeypatch.setattr(runtime, "time", SimpleNamespace(perf_counter=lambda: clock[0]))
    monkeypatch.setattr(text_session, "enabled", lambda *_: True)
    monkeypatch.setattr(session, "close", lambda *_args, **_kwargs: None)
    def reserve(_root, _payload, timeout, *, timing, on_admitted=None):
        assert on_admitted is None  # No student request in this fixture.
        assert timeout <= 300
        clock[0] += 5
        timing["storage_check_seconds"] = 4
        return "fixture", 300
    monkeypatch.setattr(budget, "reserve", reserve)
    monkeypatch.setattr(budget, "finish", lambda ident, success: finished.append((ident, success)))
    def worker(payload, **kwargs):
        captured.update(kwargs)
        yield {"type": "metadata", "kind": "text"}
        yield {"type": "done"}
    monkeypatch.setattr(text_session, "run", worker)
    result = list(runtime.run_worker({"kind": "text"}, root=tmp_path, timeout=300))
    assert captured["timeout"] == 295
    assert result[0]["dispatch_timing"]["storage_check_seconds"] == 4
    assert result[0]["dispatch_timing"]["total_preflight_seconds"] == 5
    assert finished == [("fixture", True)]


@pytest.mark.parametrize("interruption", ["deadline", "cancel"])
def test_preflight_timeout_or_cancel_never_launches_worker(runtime, tmp_path, monkeypatch, interruption):
    from types import SimpleNamespace
    import threading
    clock, finished, cancel = [0.0], [], threading.Event()
    monkeypatch.setattr(runtime, "time", SimpleNamespace(perf_counter=lambda: clock[0]))
    monkeypatch.setattr(text_session, "enabled", lambda *_: True)
    monkeypatch.setattr(session, "close", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(text_session, "close", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(text_session, "run", lambda *_args, **_kwargs: pytest.fail("worker started after preflight interruption"))
    def reserve(*_args, **_kwargs):
        if interruption == "deadline": clock[0] = 11
        else: cancel.set()
        return "fixture", 10
    monkeypatch.setattr(budget, "reserve", reserve)
    monkeypatch.setattr(budget, "finish", lambda ident, success: finished.append((ident, success)))
    with pytest.raises((TimeoutError, RuntimeError), match="no model worker started"):
        list(runtime.run_worker({"kind": "text"}, root=tmp_path, timeout=10, cancel_event=cancel))
    assert finished == [("fixture", False)]
