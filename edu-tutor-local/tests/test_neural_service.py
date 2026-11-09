"""CPU fixture transport/privacy tests; no actual model or GPU is executed."""
from __future__ import annotations

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from edu_tutor.api import create_app
from edu_tutor.jobs.manager import JobManager
from edu_tutor.neural import service as service_module
from edu_tutor.neural.service import NeuralConflict, NeuralRun, NeuralService
from edu_tutor.storage.db import Store


def body(**changes):
    return {"text": "PRIVATE_PROMPT_FIXTURE", "observation_mode": "light", "selected_layers": [],
            "sample_every_steps": 16, "max_new_tokens": 32, "request_id": "fixture-request-1234",
            "generation_epoch": 7, "update_interval_ms": 100, "adapter_id": "base", **changes}


def event(payload, sequence, kind, value):
    observer = payload["observation"]
    return {"run_id": observer["run_id"], "request_id": observer["request_id"],
            "generation_epoch": observer["generation_epoch"], "sequence_no": sequence,
            "event_type": kind, "payload": value, "source": "cpu_fixture",
            "observed_at": "2026-10-26T00:00:00+00:00", "timing_kind": "host_call"}


def fixture_worker(payload, **kwargs):
    assert payload["max_new_tokens"] <= 128
    assert payload["observation"]["save_sensitive"] is False
    yield {"type": "observation_batch", "events": [
        event(payload, 1, "structure", {"nodes": [{"path": "test.layers.0", "role": "block"}],
                                     "source": "cpu_fixture", "resident": True, "layer_count": 1}),
        event(payload, 2, "input_tokens", {"token_ids": [11, 12], "text": "PRIVATE_INPUT_FIXTURE"}),
        event(payload, 3, "block_call", {"input_shape": [1, 2, 4], "gpu_elapsed_ms": None}),
        event(payload, 4, "activation_sample", {"values": [0.125, 0.25], "sample_mean": 0.1875}),
        event(payload, 5, "token", {"token_id": 31, "text": "PRIVATE_TOKEN_FIXTURE"}),
    ], "dropped_events": 0}
    yield {"type": "delta", "text": "PRIVATE_OUTPUT_FIXTURE"}
    yield {"type": "metadata", "model_id": "CPU_FIXTURE_MODEL", "finish_reason": "eos",
           "output_tokens": 1, "output_token_ids": [31], "text": "PRIVATE_REPORT_FIXTURE",
           "generation_seconds": .25, "peak_vram_reserved_bytes": 0}
    yield {"type": "done"}


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr("edu_tutor.models.runtime.model_status", lambda *a, **k: {
        "ready": True, "model_id": "CPU_FIXTURE_MODEL", "revision": "fixture-revision"})
    store = Store(tmp_path)
    jobs = JobManager(store)
    broker = NeuralService(tmp_path, store, jobs, worker=fixture_worker)
    yield broker
    broker.close()
    jobs.close()


def finished(service, ident):
    for _ in range(300):
        run = service.get(ident)
        if run["state"] in {"succeeded", "failed", "cancelled", "blocked", "interrupted"}:
            return run
        time.sleep(.005)
    raise AssertionError("CPU fixture did not finish")


def test_default_memory_only_and_explicit_redacted_vs_sensitive_trace(service):
    run = finished(service, service.start(body())["run_id"])
    assert run["state"] == "succeeded"
    assert run["output_text"] == "PRIVATE_OUTPUT_FIXTURE"
    assert run["metadata"]["output_token_ids"] == [31]
    assert service.records() == []
    for _ in range(100):
        job = service.store.get("jobs", run["job_id"])
        if job["state"] == "succeeded":
            break
        time.sleep(.005)
    persisted = json.dumps(job)
    assert "PRIVATE" not in persisted and "output_token_ids\"" not in persisted
    assert job["result"]["output_tokens"] == 1
    default = service.save(run["run_id"])
    saved = service.record(default["id"])
    assert saved["mode"] == "REPLAY" and saved["run"]["resident"] is False
    serialized = json.dumps(saved)
    assert "PRIVATE" not in serialized and "0.1875" not in serialized
    assert "output_token_ids\"" not in serialized and "token_ids\"" not in serialized
    assert saved["structure"]["resident"] is False
    sensitive = service.record(service.save(run["run_id"], True)["id"])
    assert sensitive["run"]["output_text"] == "PRIVATE_OUTPUT_FIXTURE"
    assert sensitive["run"]["metadata"]["output_token_ids"] == [31]
    assert any(e["payload"].get("values") == [0.125, 0.25] for e in sensitive["events"])
    cache = service.state()
    assert cache["mode"] == "STATIC" and cache["structure_source"] == "cached"
    assert cache["structure"]["resident"] is False and cache["active_run"] is None
    assert not list(service.control_dir.glob("*.json"))


def test_bounded_buffer_retains_critical_lifecycle_and_reports_drops():
    run = NeuralRun(body(), {}, "cpu-fixture")
    run.append("run_state", {"state": "queued"})
    for i in range(6000):
        run.append("block_call", {"index": i, "padding": "a" * 3000})
    run.append("run_state", {"state": "succeeded"})
    assert run.buffer_bytes <= service_module.MAX_BUFFER_BYTES
    assert len(run.events) <= service_module.MAX_EVENTS
    assert run.dropped_events > 0
    events = run.after(0)
    assert events[0]["payload"]["state"] == "queued"
    assert events[-1]["payload"]["state"] == "succeeded"
    assert len({e["sequence_no"] for e in events}) == len(events)


def test_actual_token_ids_survive_module_buffer_pressure():
    run = NeuralRun(body(), {}, "cpu-fixture")
    run.append("input_tokens", {"token_ids": [42]})
    for step in range(128):
        run.append("token", {"token_ids": [step]})
        for _ in range(28):
            run.append("block_call", {"shape": [1, 1, 2048], "padding": "x" * 600})
    events = run.after(0)
    assert len([e for e in events if e["event_type"] == "token"]) == 128
    assert any(e["event_type"] == "input_tokens" for e in events)
    assert run.buffer_bytes <= service_module.MAX_BUFFER_BYTES and run.dropped_events > 0


def test_lifecycle_end_is_retained_when_observer_state_limit_reached():
    run = NeuralRun(body(), {}, "cpu-fixture")
    for _ in range(256):
        run.append("observer_state", {"state": "disabled"})
    with pytest.raises(ValueError):
        run.append("observer_state", {"state": "observing"})
    run.append("run_state", {"state": "failed"})
    assert run.after(0)[-1]["payload"]["state"] == "failed"


def controlled_worker(started, release):
    def worker(payload, **kwargs):
        yield {"type": "observation_batch", "events": [event(payload, 1, "structure", {"nodes": [], "resident": True})]}
        started.set()
        release.wait(2)
        yield {"type": "done"}
    return worker


def test_multiple_subscribers_reconnect_and_stale_controls(service):
    started, release = threading.Event(), threading.Event()
    service.worker = controlled_worker(started, release)
    run = service.start(body())
    assert started.wait(1)
    first = service.subscribe(run["run_id"])
    second = service.subscribe(run["run_id"])
    service.unsubscribe(run["run_id"], first)
    control = service.control_dir / f"{run['run_id']}.json"
    assert json.loads(control.read_text(encoding="utf-8"))["enabled"] is True
    service.unsubscribe(run["run_id"], second)
    assert json.loads(control.read_text(encoding="utf-8"))["enabled"] is False
    assert service.get(run["run_id"])["mode"] == "STALE"
    third = service.subscribe(run["run_id"])
    assert json.loads(control.read_text(encoding="utf-8"))["enabled"] is True
    with pytest.raises(NeuralConflict):
        service.observation(run["run_id"], {"enabled": True, "generation_epoch": 6})
    with pytest.raises(NeuralConflict):
        service.cancel(run["run_id"], 6)
    service.observation(run["run_id"], {"enabled": False, "generation_epoch": 7})
    service.unsubscribe(run["run_id"], third)
    fourth = service.subscribe(run["run_id"])
    assert json.loads(control.read_text(encoding="utf-8"))["enabled"] is False
    service.unsubscribe(run["run_id"], fourth)
    release.set()
    assert finished(service, run["run_id"])["observer_enabled"] is False


def test_stale_epoch_duplicate_worker_events_are_rejected(service):
    run = NeuralRun(body(), {}, "cpu-fixture")
    payload = {"observation": {"run_id": run.run_id, "request_id": run.request_id, "generation_epoch": 7}}
    current = event(payload, 1, "block_call", {"call": 1})
    stale = {**current, "generation_epoch": 6, "sequence_no": 2}
    service._ingest_safe(run, {"events": [current, stale, current]})
    assert run.rejected_stale_events == 2 and len(run.events) == 1


def test_intentional_aggregation_remains_separate_from_queue_drops(service):
    run = NeuralRun(body(), {}, "cpu-fixture")
    service._ingest_safe(run, {"events": [], "dropped_events": 3, "aggregated_events": 84})
    service._ingest_safe(run, {"events": [], "dropped_events": 1, "aggregated_events": 28})
    view = run.view()
    assert view["aggregated_events"] == 84 and view["worker_dropped_events"] == 3
    assert view["dropped_events"] == 0


def test_first_token_host_metrics_are_scalar_only():
    metrics = service_module._metrics({
        "first_token_latency_seconds": 1.2, "first_token_latency_status": "measured_host_stopping_callback",
        "first_token_latency_kind": "generation_start_to_first_existing_stopping_callback_after_streamer",
        "generation_remaining_seconds": .8, "remaining_output_tokens": 7, "warmup_seconds": None,
        "output_token_ids": [1, 2, 3], "text": "PRIVATE",
    })
    assert metrics["first_token_latency_seconds"] == 1.2
    assert metrics["remaining_output_tokens"] == 7 and metrics["warmup_seconds"] is None
    assert "output_token_ids" not in metrics and "text" not in metrics


def test_observation_failure_does_not_abort_worker_and_cancel_stops_live(service):
    def bad_observer(payload, **kwargs):
        yield {"type": "observation_batch", "events": [event(payload, 1, "structure", "invalid") ]}
        yield {"type": "delta", "text": "continues"}
        yield {"type": "done"}
    service.worker = bad_observer
    run = finished(service, service.start(body())["run_id"])
    assert run["state"] == "succeeded" and run["output_text"] == "continues"
    assert run["observation_error"] and run["observer_enabled"] is False
    started, release = threading.Event(), threading.Event()
    service.worker = controlled_worker(started, release)
    # Wait for JobManager's terminal store update after the target return.
    for _ in range(100):
        if service.store.get("jobs", run["job_id"])["state"] == "succeeded":
            break
        time.sleep(.005)
    second = service.start(body(request_id="cancel-fixture-1234"))
    assert started.wait(1)
    service.cancel(second["run_id"], 7)
    release.set()
    assert finished(service, second["run_id"])["state"] == "cancelled"


def test_trace_quotas_never_delete_existing_files(service, monkeypatch):
    run = finished(service, service.start(body())["run_id"])
    first = service.save(run["run_id"])
    path = service.records_dir / f"{first['id']}.json"
    original = path.read_bytes()
    monkeypatch.setattr(service_module, "MAX_TOTAL_TRACE_BYTES", len(original) + 1)
    with pytest.raises(NeuralConflict, match="200MB"):
        service.save(run["run_id"])
    assert path.read_bytes() == original and len(list(service.records_dir.glob("*.json"))) == 1
    assert service.get(run["run_id"])["save_status"] == "limit_reached"


def test_repeated_saves_share_one_run_allowance(service, monkeypatch):
    run = finished(service, service.start(body())["run_id"])
    first = service.save(run["run_id"])
    monkeypatch.setattr(service_module, "MAX_TRACE_BYTES", first["bytes"] + 100)
    with pytest.raises(NeuralConflict, match="20MB"):
        service.save(run["run_id"])
    assert len(service.records()) == 1


def test_slow_save_scan_does_not_block_event_ingestion(service, monkeypatch):
    run = finished(service, service.start(body())["run_id"])
    scan_started, finish_scan = threading.Event(), threading.Event()
    original_records = service.records
    def slow_records():
        scan_started.set()
        assert finish_scan.wait(2)
        return original_records()
    monkeypatch.setattr(service, "records", slow_records)
    errors = []
    def save():
        try:
            service.save(run["run_id"])
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=save)
    thread.start()
    assert scan_started.wait(1)
    # Access and event collection must remain possible while quota I/O waits.
    start = time.monotonic()
    assert service.get(run["run_id"])["state"] == "succeeded"
    service.events_after(run["run_id"], 0)
    assert time.monotonic() - start < .25
    finish_scan.set()
    thread.join(2)
    assert not thread.is_alive() and errors == []


def test_concurrent_start_and_ingest_do_not_deadlock(service):
    started, release = threading.Event(), threading.Event()
    service.worker = controlled_worker(started, release)
    first = service.start(body())
    assert started.wait(1)
    result = []
    def conflicting_start():
        try:
            service.start(body(request_id="concurrent-fixture-1234"))
        except NeuralConflict:
            result.append("busy")
    thread = threading.Thread(target=conflicting_start)
    thread.start()
    thread.join(1)
    assert not thread.is_alive() and result == ["busy"]
    assert service.start(body())["run_id"] == first["run_id"]
    release.set()
    finished(service, first["run_id"])


def test_restart_does_not_reuse_old_request_or_live_memory(service):
    run = finished(service, service.start(body())["run_id"])
    service.close()
    new = NeuralService(service.root, service.store, service.jobs, worker=fixture_worker)
    try:
        assert new.state()["active_run"] is None
        assert new.state()["mode"] == "STATIC"
        with pytest.raises(KeyError):
            new.get(run["run_id"])
        with pytest.raises(NeuralConflict, match="이전 서버"):
            new.start(body())
    finally:
        new.close()


def test_api_sse_auth_host_origin_limits_and_completed_reconnect(tmp_path, monkeypatch):
    monkeypatch.setattr("edu_tutor.models.runtime.model_status", lambda *a, **k: {"ready": True})
    app = create_app(tmp_path)
    app.state.neural.worker = fixture_worker
    token = (tmp_path / ".local/auth-token").read_text(encoding="utf-8")
    with TestClient(app, base_url="http://127.0.0.1:8000", headers={"Authorization": "Bearer " + token}) as client:
        for path in ("/api/neural/state", "/api/neural/records", "/api/neural/runs/none/events"):
            assert client.get(path, headers={"Authorization": ""}).status_code == 401
        assert client.get("/api/neural/state", headers={"Host": "evil.example"}).status_code == 400
        assert client.get("/api/neural/state", headers={"Origin": "https://evil.example"}).status_code == 403
        assert client.get("/api/neural/state?token=" + token, headers={"Authorization": ""}).status_code == 401
        assert client.post("/api/neural/runs", json=body(max_new_tokens=129)).status_code == 422
        assert client.post("/api/neural/runs", json=body(selected_layers=["a", "b", "c"])).status_code == 422
        response = client.post("/api/neural/runs", json=body())
        assert response.status_code == 202
        run = finished(app.state.neural, response.json()["run_id"])
        sse = client.get(f"/api/neural/runs/{run['run_id']}/events").text
        data = [json.loads(line[6:]) for line in sse.splitlines() if line.startswith("data: ")]
        assert data[0]["event_type"] == "snapshot"
        assert data[0]["payload"]["run"]["state"] == "succeeded"
        actual = [e for e in data if e["event_type"] not in {"snapshot", "gap"}]
        assert [e["sequence_no"] for e in actual] == sorted({e["sequence_no"] for e in actual})
        assert all(e["generation_epoch"] == 7 for e in actual)
        after = actual[-1]["sequence_no"]
        reconnect = client.get(f"/api/neural/runs/{run['run_id']}/events?after={after}").text
        assert "event: observation" not in reconnect and "event: snapshot" in reconnect
        assert client.post(f"/api/neural/runs/{run['run_id']}/cancel", json={"generation_epoch": 6}).status_code == 409
        saved = client.post(f"/api/neural/runs/{run['run_id']}/save", json={}).json()
        assert client.get(f"/api/neural/records/{saved['id']}", headers={"Authorization": ""}).status_code == 401


def test_training_history_is_existing_metrics_not_live_reconstruction(service):
    directory = service.root / "runs/cpu-fixture-history"
    directory.mkdir(parents=True)
    (directory / "metrics.jsonl").write_text(json.dumps({"step": 50, "loss": 1.25, "actual_microbatches": 400}) + "\n", encoding="utf-8")
    service.store.put("jobs", {"id": "training-fixture", "kind": "training", "state": "succeeded",
                               "artifact": "runs/cpu-fixture-history"})
    state = service.state()
    assert state["training"]["current"] == []
    history = state["training"]["history"][0]
    assert history["latest_metrics"]["step"] == 50 and history["latest_metrics"]["actual_microbatches"] == 400
    assert "grad_norm" not in history["latest_metrics"]
    assert state["training"]["source"] == "existing_training_callbacks"
