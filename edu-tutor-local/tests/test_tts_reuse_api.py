"""Grant and lesson binding tests for the authenticated lifecycle comparison."""
import hashlib
import json
import pytest
from test_phase2_backend import client, wait

GRANT = "20261027-tts-worker-reuse-2calls"
COMPARISON = "a"*32


def setup(client, monkeypatch, *, authorized=True, mode="good"):
    from edu_tutor.models import runtime
    from edu_tutor.speech import session
    store = client.app.state.store
    model = store.root / ".local/models/tts"
    model.mkdir(parents=True)
    configs = []
    for name in ("config.json", "generation_config.json"):
        (model/name).write_text("{}")
        configs.append({"path": name, "sha256": hashlib.sha256(b"{}").hexdigest()})
    (model / "model-manifest.json").write_text(json.dumps({"revision": "test-revision", "files": configs}))
    empty_hash = hashlib.sha256(b"[]").hexdigest()
    limits = {"enabled": True, "gpu_seconds": 5400, "new_audio_clips": 2, "vision_requests": 0,
        "min_C_free_bytes": 0, "system_volume": str(store.root),
        "active_execution_allowance": {"id": GRANT if authorized else "old-grant", "baseline_request_count": 0,
            "baseline_requests_sha256": empty_hash, "runtime_scope": "tts_session_benchmark",
            "limits": {"text_requests": 0, "new_audio_clips": 2, "vision_requests": 0, "gpu_seconds": 600}}}
    (store.root / ".local/phase2-policy.json").write_text(json.dumps(limits))
    lesson = {"id": "verified-source", "is_demo": False, "problem": {"source": {"kind": "text"}},
        "source_message_id": "historical-answer", "generation_epoch": 0, "valid": True, "speech_allowed": True,
        "plan": {"steps": [{"id": "s1", "speech": "전체 행 수는 NULL도 포함해 5입니다."}]}}
    store.put("lessons", lesson)
    calls, closes = [], []
    def fake(payload, **kwargs):
        calls.append({**payload, "test_parent_timeout": kwargs["timeout"]})
        if mode == "fail_cold":
            raise RuntimeError("test first synthesis failed")
        warm = payload.get("expected_instance_id") is not None
        if mode == "source_changed":
            changed = store.get("lessons", lesson["id"])
            changed["plan"]["steps"][0]["speech"] = "변경된 대사"
            store.put("lessons", changed)
        info = {"worker_instance_id": "worker-one", "model_instance_id": "model-one", "model_object_id": 123,
                "load_count_total": 1, "load_count_this_request": 0 if warm else 1}
        if mode == "reload" and warm:
            info.update(model_instance_id="model-two", model_object_id=456, load_count_total=2, load_count_this_request=1)
        yield {"type": "audio", "audio_id": payload["items"][0]["audio_id"], "cache_hit": False, "session_info": info}
        yield {"type": "done"}
    monkeypatch.setattr(runtime, "run_worker", fake)
    monkeypatch.setattr(session, "close", lambda *a, **k: closes.append(k) or {"closed": True})
    return store, lesson, calls, closes


def submit(client, phase="cold", **overrides):
    body = {"comparison_id": COMPARISON, "phase": phase, "lesson_id": "verified-source", "step_id": "s1", "request_id": phase+"-request"}
    return client.post("/api/tts/reuse-benchmark", json={**body, **overrides})


def test_two_independent_syntheses_same_saved_spec_cache_bypass_and_finish_close(client, monkeypatch):
    store, original, calls, closes = setup(client, monkeypatch)
    response = submit(client)
    assert response.status_code == 202, response.text
    first = wait(client, response.json()["job_id"])
    assert first["state"] == "succeeded", first
    repeat = submit(client)
    assert repeat.json()["job_id"] == first["id"] and len(calls) == 1
    second = submit(client, "warm")
    assert second.status_code == 202, second.text
    assert wait(client, second.json()["job_id"])["state"] == "succeeded"
    assert len(calls) == 2 and all(c["tts_benchmark"] and c["seed"] == 20261027 for c in calls)
    assert calls[0]["items"][0]["spec"] == calls[1]["items"][0]["spec"]
    assert calls[0]["items"][0]["audio_id"] != calls[1]["items"][0]["audio_id"]
    assert calls[0]["output_dir"] != calls[1]["output_dir"]
    assert calls[1]["expected_instance_id"] == "worker-one"
    assert closes[-1]["reason"] == "benchmark_complete"
    assert store.get("lessons", original["id"]) == original
    assert submit(client, "warm", request_id="another-retry").status_code == 409


@pytest.mark.parametrize("mode", ["fail_cold", "source_changed", "reload"])
def test_failure_or_changed_source_never_becomes_warm_success(client, monkeypatch, mode):
    _, _, calls, closes = setup(client, monkeypatch, mode=mode)
    first = wait(client, submit(client).json()["job_id"])
    if mode == "reload":
        assert first["state"] == "succeeded"
        second = wait(client, submit(client, "warm").json()["job_id"])
        assert second["state"] == "failed" and "warm" in second["error"]
    else:
        assert first["state"] == "failed"
        assert submit(client, "warm").status_code == 409 and len(calls) == 1
    assert closes[-1]["reason"] == "benchmark_failed"


def test_unapproved_or_injected_text_is_denied_before_worker(client, monkeypatch):
    _, _, calls, _ = setup(client, monkeypatch, authorized=False)
    r = submit(client)
    assert r.status_code >= 400 and not calls
    assert submit(client, text="arbitrary new text").status_code == 422
    assert client.post("/api/tts/reuse-benchmark", json={}, headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_warm_without_cold_and_same_request_id_are_denied(client, monkeypatch):
    _, _, calls, _ = setup(client, monkeypatch)
    assert submit(client, "warm").status_code == 409 and not calls
    first = wait(client, submit(client).json()["job_id"])
    assert first["state"] == "succeeded"
    assert submit(client, "warm", request_id="cold-request").status_code == 422
    assert len(calls) == 1


def test_runtime_budget_requires_grant_and_single_benchmark_clip(tmp_path):
    from edu_tutor.models.budget import reserve, ResourceBudgetExceeded
    payload = {"kind": "speech_batch", "items": [{}], "tts_benchmark": True}
    with pytest.raises(ResourceBudgetExceeded, match="명시"):
        reserve(tmp_path, payload, 300)


def test_short_remaining_time_is_split_before_first_synthesis(client, monkeypatch):
    store, _, calls, _ = setup(client, monkeypatch)
    p = store.root / ".local/phase2-policy.json"
    limits = json.loads(p.read_text())
    limits["active_execution_allowance"]["limits"]["gpu_seconds"] = 14
    p.write_text(json.dumps(limits))
    first = wait(client, submit(client).json()["job_id"])
    assert first["state"] == "succeeded"
    second = wait(client, submit(client, "warm").json()["job_id"])
    assert second["state"] == "succeeded"
    assert [call["test_parent_timeout"] for call in calls] == [7, 7]


@pytest.mark.parametrize("change_binding", [False, True])
def test_normal_opt_in_path_keeps_fingerprint_guard_and_releases_last_step(client, monkeypatch, change_binding):
    from edu_tutor.speech import provider
    store, lesson, _, closes = setup(client, monkeypatch)
    (store.root / ".local/tts-session-policy.json").write_text(json.dumps({"mode": "session"}))
    received = []
    def prepare(text, **kwargs):
        received.append(kwargs["session_key"])
        if change_binding:
            changed = store.get("lessons", lesson["id"])
            changed["plan"]["steps"][0]["speech"] = "다른 판서 설명"
            store.put("lessons", changed)
        return {"audio_id": "b"*64, "url": "/api/audio/"+"b"*64}
    monkeypatch.setattr(provider, "prepare", prepare)
    response = client.post("/api/lessons/verified-source/speech", json={"step_id": "s1", "request_id": "normal"})
    assert response.status_code == 202
    job = wait(client, response.json()["job_id"])
    assert received[0].startswith("lesson:verified-source:")
    assert closes[-1]["session_key"] == received[0]
    assert closes[-1]["reason"] == "lesson_complete_or_cancelled"
    current = store.get("lessons", lesson["id"])
    if change_binding:
        assert job["state"] == "cancelled" and not current.get("audio_steps")
    else:
        assert job["state"] == "succeeded" and len(current["audio_steps"]) == 1
