"""CPU fixtures and actual OS ownership only; no model imports/generation."""
import json
import os
from pathlib import Path
import sys
import threading
import time

import pytest

from edu_tutor.models import text_session
from edu_tutor.speech import direct

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def resident(tmp_path, monkeypatch):
    if os.name != "nt":
        pytest.skip("Windows redirector ownership contract")
    (tmp_path / ".local").mkdir()
    (tmp_path / ".local/text-session-policy.json").write_text(json.dumps({"mode": "session", "idle_seconds": 10, "max_session_seconds": 40}))
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    monkeypatch.setattr(text_session, "_command", lambda root: [sys.executable, "-u", "-m", "scripts.text_resident_cpu_fixture"])
    yield tmp_path
    text_session.close(tmp_path, "fixture_end")


def request(content="normal", job="one", **extra):
    return {"kind": "text", "messages": [{"role": "user", "content": content}], "job_id": job,
        "adapter": None, "max_new_tokens": 16, "execution_allowance_id": "cpu-fixture", **extra}


def test_two_requests_keep_actual_child_and_fixture_object_with_clean_protocol(resident):
    first = list(text_session.run(request(), root=resident, timeout=20))
    first_meta = next(e for e in first if e["type"] == "metadata")
    assert first_meta["kind"] == "text"  # Production report uses kind as payload, not protocol argument.
    state = text_session.status(resident)
    second = list(text_session.run(request(job="two", expected_text_instance_id=state["session"]["instance_id"]), root=resident, timeout=20))
    second_meta = next(e for e in second if e["type"] == "metadata")
    assert first_meta["worker_pid"] == second_meta["worker_pid"]
    assert first_meta["model_python_id"] == second_meta["model_python_id"]
    assert first_meta["model_load_count"] == 1 and second_meta["model_load_count"] == 0
    assert state["session"]["ownership"]["ancestry_verified"]
    assert "CPU fixture library" in next((resident / "runs").glob("text-session-*/stderr.log")).read_text()
    assert not text_session.close(resident, job_id="one")["closed"]
    assert text_session.status(resident)["resident"]
    closed = text_session.close(resident, job_id="two")
    assert closed["actual_worker_exit_confirmed"]


def test_cancellation_discards_late_output_and_releases_owned_child(resident):
    list(text_session.run(request(), root=resident, timeout=20))
    cancel = threading.Event()
    timer = threading.Timer(.15, cancel.set)
    timer.start()
    try:
        with pytest.raises(RuntimeError, match="cancelled"):
            list(text_session.run(request("wait", job="cancel-this"), root=resident, cancel_event=cancel, timeout=20))
    finally:
        timer.cancel()
    state = text_session.status(resident)
    assert not state["resident"] and state["last_session"]["actual_worker_exit_confirmed"]


def test_late_idle_timer_cannot_close_active_request_or_replacement(resident):
    list(text_session.run(request(), root=resident, timeout=20))
    child = text_session._CURRENT[str(resident.resolve())]
    child.active = True
    text_session._expire(resident, child.instance_id, "idle_expired")
    assert not child.closed
    child.active = False
    text_session._expire(resident, "older-instance", "maximum_lifetime")
    assert not child.closed
    text_session._expire(resident, child.instance_id, "idle_expired")
    assert child.closed


def test_foreign_event_fails_closed_and_missing_warm_never_loads(resident):
    with pytest.raises(RuntimeError, match="foreign"):
        list(text_session.run(request("foreign"), root=resident, timeout=20))
    assert not text_session.status(resident)["resident"]
    before = list((resident / "runs").glob("text-session-*"))
    with pytest.raises(RuntimeError, match="cold reload is forbidden"):
        list(text_session.run(request(expected_text_instance_id="missing"), root=resident, timeout=20))
    assert before == list((resident / "runs").glob("text-session-*"))


def test_model_or_scope_change_closes_old_instance(resident):
    first = list(text_session.run(request(), root=resident, timeout=20))
    second = list(text_session.run(request(job="other", execution_allowance_id="other-fixture"), root=resident, timeout=20))
    assert first[0]["instance_id"] != second[0]["instance_id"]
    assert text_session.status(resident)["last_session"]["actual_worker_exit_confirmed"]


def test_precision_change_never_reuses_wrong_fixture_instance(resident):
    first = list(text_session.run(request(precision="nf4"), root=resident, timeout=20))
    state = text_session.status(resident)
    before = list((resident / "runs").glob("text-session-*"))
    with pytest.raises(RuntimeError, match="cold reload is forbidden"):
        list(text_session.run(request(precision="bf16", expected_text_instance_id=state["session"]["instance_id"]),
                              root=resident, timeout=20))
    assert before == list((resident / "runs").glob("text-session-*"))
    second = list(text_session.run(request(job="bf16-fixture", precision="bf16"), root=resident, timeout=20))
    assert first[0]["instance_id"] != second[0]["instance_id"]
    assert text_session.status(resident)["last_session"]["actual_worker_exit_confirmed"]


def test_resident_transport_distinguishes_reader_queue_and_consumer_work(resident):
    events = []
    for event in text_session.run(request(job="timing-fixture"), root=resident, timeout=20):
        events.append(event)
        assert not any(key.startswith("_transport") for key in event)
        if event["type"] == "delta":
            # Deliberate CPU consumer delay, not a DB/model performance claim.
            time.sleep(.06)
    meta = next(e for e in events if e["type"] == "metadata")
    timing = meta["transport_timing"]
    assert timing["clock"] == "parent_perf_counter"
    assert timing["queue_capacity_events"] == 128
    assert timing["delta_event_count"] == 1
    assert timing["consumer_yield_seconds_total"] >= .05
    assert timing["metadata_consumer_elapsed_seconds"] >= timing["metadata_reader_elapsed_seconds"]
    assert timing["queue_wait_seconds_total"] >= .04
    assert timing["reader_log_seconds_total"] >= 0
    result = next((resident / "runs").glob("text-session-*/request-*/request-result.json"))
    stored = json.loads(result.read_text(encoding="utf-8"))
    assert stored["transport_timing"]["observed_through"] == "request finalization"
    assert stored["transport_timing"]["received_event_count"] == timing["received_event_count"] + 1


def test_cancelled_sapi_preflight_retains_same_actual_cpu_fixture_child(resident, monkeypatch):
    from edu_tutor.models import budget, runtime
    first = list(text_session.run(request(job="before-voice"), root=resident, timeout=20))
    first_meta = next(e for e in first if e["type"] == "metadata")
    instance = text_session.status(resident)["session"]["instance_id"]
    cancel, finished = threading.Event(), []
    def reserve(*_args, **_kwargs):
        cancel.set()
        return "cpu-sapi-fixture-only", 20
    monkeypatch.setattr(budget, "reserve", reserve)
    monkeypatch.setattr(budget, "finish", lambda ident, success: finished.append((ident, success)))
    monkeypatch.setattr(direct, "run", lambda *_a, **_kw: pytest.fail("cancelled voice reached actual synthesis"))
    with pytest.raises(RuntimeError, match="cancelled during preflight"):
        list(runtime.run_worker({"kind": "speech", "job_id": "cancelled-voice",
            "spec": {"provider": "windows_sapi_local"}}, root=resident, cancel_event=cancel, timeout=20))
    assert finished == [("cpu-sapi-fixture-only", False)]
    assert text_session.status(resident)["session"]["instance_id"] == instance
    second = list(text_session.run(request(job="after-voice", expected_text_instance_id=instance), root=resident, timeout=20))
    second_meta = next(e for e in second if e["type"] == "metadata")
    assert first_meta["worker_pid"] == second_meta["worker_pid"]
    assert first_meta["model_instance_id"] == second_meta["model_instance_id"]
    assert second_meta["model_load_count"] == 0


def test_direct_cpu_route_rejects_mixed_neural_items():
    assert not direct.enabled({"kind": "text", "speech_provider": "windows_sapi_local"})
    assert not direct.enabled({"kind": "speech_batch", "speech_provider": "windows_sapi_local",
        "items": [{"spec": {"provider": "windows_sapi_local"}}, {"spec": {}}]})


def test_direct_cpu_voice_is_sequential_without_python_worker_or_gpu_lease(tmp_path, monkeypatch):
    from edu_tutor.speech import windows_sapi
    from edu_tutor.jobs import lease
    calls = []
    monkeypatch.setattr(lease, "GPULease", lambda *_args, **_kwargs: pytest.fail("CPU voice must not acquire GPU lease"))
    def speech(payload, emit, **kwargs):
        calls.append(payload)
        emit("audio", fixture_only=True)
    monkeypatch.setattr(windows_sapi, "speech_job", speech)
    payload = {"kind": "speech_batch", "speech_provider": "windows_sapi_local", "items": [{"spec": {"provider": "windows_sapi_local"}}]}
    result = list(direct.run(payload, root=tmp_path, timeout=10))
    assert len(calls) == 1 and [e["type"] for e in result] == ["audio", "done"]
    assert not result[0]["parent_timing"]["gpu_lease_acquired"]


def test_direct_cpu_reserved_timeout_cancels_before_publishing(tmp_path, monkeypatch):
    from edu_tutor.speech import windows_sapi
    def speech(payload, emit, **kwargs):
        while not Path(payload["cancel_path"]).exists():
            time.sleep(.01)
        raise RuntimeError("fixture cancelled")
    monkeypatch.setattr(windows_sapi, "speech_job", speech)
    with pytest.raises(TimeoutError, match="reserved deadline"):
        list(direct.run({"kind": "speech", "spec": {"provider": "windows_sapi_local"}}, root=tmp_path, timeout=6.05))
