"""CPU-only cache safety. Synthetic PCM fixtures are never model/voice evidence."""
import hashlib
import json
import sys
import wave
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from edu_tutor.api import create_app
from edu_tutor.jobs.lease import GPULease, LeaseBusy
from edu_tutor.models import budget, runtime
from edu_tutor.speech import provider


TEXT = "검증용 문장입니다."
PREPARE_BATCH = provider.prepare_batch


def make_cache(root, text=TEXT, voice="Sohee"):
    folder = root / ".local/models/tts"
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    for name, data in (("config.json", {"talker_config": {"codec_eos_token_id": 99}}),
                       ("generation_config.json", {"subtalker_dosample": True})):
        raw = json.dumps(data).encode()
        (folder / name).write_bytes(raw)
        files.append({"path": name, "sha256": hashlib.sha256(raw).hexdigest()})
    (folder / "model-manifest.json").write_text(json.dumps({"revision": "fixture-pinned", "files": files}))
    key, spec = provider._spec(text, root, voice)
    audio = root / ".local/audio"
    audio.mkdir(exist_ok=True)
    wav = audio / (key + ".wav")
    with wave.open(str(wav), "wb") as stream:
        stream.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\x10\x00" * 12000)
    meta = {"audio_id": key, "checksum": hashlib.sha256(wav.read_bytes()).hexdigest(),
            "provider": "qwen3_tts_local", "voice": voice, "revision": "fixture-pinned",
            "text_hash": hashlib.sha256(spec["text"].encode()).hexdigest(), "duration": .5, "sample_rate": 24000,
            "generation_settings": {"language": "Korean", "do_sample": False, "max_new_tokens": 768,
                                    "dictionary_version": 1, "completion_check_version": 2},
            "completion": {"finish_reason": "eos", "completion_check_version": 2,
                           "observed_eos_token_id": 99, "last_generated_tokens": [4, 99], "output_code_frames": 2}}
    wav.with_suffix(".json").write_text(json.dumps(meta))
    return wav, meta


def forbid_inference(*args, **kwargs):
    raise AssertionError("cache reads must never execute or reserve model work")


@pytest.fixture(autouse=True)
def no_inference(monkeypatch):
    monkeypatch.setattr(runtime, "run_worker", forbid_inference)
    monkeypatch.setattr(budget, "reserve", forbid_inference)
    monkeypatch.setattr(provider, "prepare", forbid_inference)
    monkeypatch.setattr(provider, "prepare_batch", forbid_inference)


def test_missing_cache_does_not_initialize_or_write(tmp_path):
    assert not provider.cached_audio(TEXT, root=tmp_path)["hit"]
    assert list(tmp_path.iterdir()) == []


def test_exact_cache_works_without_tts_package_or_ready_status(tmp_path, monkeypatch):
    wav, _ = make_cache(tmp_path)
    monkeypatch.setattr(provider, "status", forbid_inference)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = provider.cached_audio(TEXT, root=tmp_path)
    assert result["hit"] and result["path"] == wav and result["audio"]["cache_hit"]
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert not provider.cached_audio(TEXT + " 바뀜", root=tmp_path)["hit"]
    assert not provider.cached_audio(TEXT, root=tmp_path, voice="Vivian")["hit"]


@pytest.mark.parametrize("field,value", [
    ("revision", "other"), ("voice", "Vivian"), ("audio_id", "0" * 64), ("text_hash", "wrong"),
    ("provider", "other"), ("duration", 2), ("sample_rate", 22050),
    ("generation_settings", {}), ("completion", {}), ("completion", {"finish_reason": "length_or_timeout"}),
])
def test_wrong_metadata_stops_without_regeneration(tmp_path, field, value):
    wav, meta = make_cache(tmp_path)
    meta[field] = value
    wav.with_suffix(".json").write_text(json.dumps(meta))
    assert not provider.cached_audio(TEXT, root=tmp_path)["hit"]


@pytest.mark.parametrize("mutation", ["checksum", "wave_header", "bad_json", "list_json", "settings", "revision", "no_eos"])
def test_corrupt_or_changed_cache_is_miss(tmp_path, mutation):
    wav, meta = make_cache(tmp_path)
    if mutation in {"checksum", "wave_header"}:
        wav.write_bytes(b"not-wave")
        if mutation == "wave_header":
            meta["checksum"] = hashlib.sha256(wav.read_bytes()).hexdigest()
    elif mutation == "settings":
        (tmp_path / ".local/models/tts/generation_config.json").write_text("{}")
    elif mutation == "revision":
        path = tmp_path / ".local/models/tts/model-manifest.json"
        content = json.loads(path.read_text()); content["revision"] = "changed"
        path.write_text(json.dumps(content))
    elif mutation == "no_eos":
        meta["completion"]["last_generated_tokens"] = [4, 5]
    wav.with_suffix(".json").write_text("{" if mutation == "bad_json" else "[]" if mutation == "list_json" else json.dumps(meta))
    assert not provider.cached_audio(TEXT, root=tmp_path)["hit"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    make_cache(tmp_path)
    app = create_app(tmp_path)
    monkeypatch.setattr(app.state.jobs, "submit", forbid_inference)
    lesson = {"id": "cache-lesson", "is_demo": False, "valid": True, "speech_allowed": True,
              "generation_epoch": 1, "problem": {"revision": 1, "source": {}},
              "plan": {"steps": [{"id": "s1", "speech": TEXT, "board": {"value": 1}}]}, "audio_steps": []}
    app.state.store.put("lessons", lesson)
    token = (tmp_path / ".local/auth-token").read_text().strip()
    with TestClient(app, base_url="http://127.0.0.1:8000", headers={"Authorization": "Bearer " + token}) as value:
        yield value


def test_global_cached_replay_is_read_only_and_budget_independent(client):
    store = client.app.state.store
    before = {table: store.list(table) for table in ("lessons", "jobs", "audit")}
    result = client.get("/api/lessons/cache-lesson/speech?step_id=s1").json()
    assert result["replay_only"] and not result["cache_misses"]
    step = result["steps"][0]
    assert step["cache_source"] == "global" and step["binding_fingerprint"] == result["binding_fingerprint"]
    response = client.get(step["audio_url"])
    assert response.status_code == 200 and response.content.startswith(b"RIFF")
    assert {table: store.list(table) for table in before} == before
    assert not (store.root / "runs/phase2/current/resource-budget.json").exists()


@pytest.mark.parametrize("mutation", ["board", "script", "epoch", "problem_revision", "unverified", "invalid"])
def test_prefetched_binding_is_rechecked_before_serving(client, mutation):
    old = client.get("/api/lessons/cache-lesson/speech?step_id=s1").json()["steps"][0]
    store = client.app.state.store
    lesson = store.get("lessons", "cache-lesson")
    if mutation == "board": lesson["plan"]["steps"][0]["board"]["value"] = 2
    if mutation == "script": lesson["plan"]["steps"][0]["speech"] = "변경된 대사입니다."
    if mutation == "epoch": lesson["generation_epoch"] += 1
    if mutation == "problem_revision": lesson["problem"]["revision"] += 1
    if mutation == "unverified": lesson["speech_allowed"] = False
    if mutation == "invalid": lesson["valid"] = False; lesson["invalidated_reason"] = "invalid fixture"
    store.put("lessons", lesson)
    assert client.get(old["audio_url"]).status_code == 409


def test_photo_revision_and_legacy_attachment_cannot_bypass_checks(client):
    store = client.app.state.store
    step = client.get("/api/lessons/cache-lesson/speech?step_id=s1").json()["steps"][0]
    lesson = store.get("lessons", "cache-lesson")
    lesson["audio_steps"] = [step]
    store.put("lessons", lesson)
    assert client.get("/api/audio/" + step["audio_id"]).status_code == 200
    lesson["problem"]["source"] = {"photo_id": "photo"}
    store.put("photos", {"id": "photo", "revision": 2, "confirmed": True})
    store.put("lessons", lesson)
    assert client.get(step["audio_url"]).status_code == 409
    assert client.get("/api/audio/" + step["audio_id"]).status_code == 409


def test_cache_miss_and_corruption_stop_without_job(client):
    store = client.app.state.store
    step = client.get("/api/lessons/cache-lesson/speech?step_id=s1").json()["steps"][0]
    (store.local / "audio" / (step["audio_id"] + ".wav")).write_bytes(b"corrupt")
    result = client.get("/api/lessons/cache-lesson/speech?step_id=s1").json()
    assert result["steps"] == [] and result["cache_misses"][0]["code"] == "cache_checksum_mismatch"
    assert client.get(step["audio_url"]).status_code == 409
    assert client.get("/api/lessons/cache-lesson/speech?step_id=unknown").status_code == 404
    assert not store.list("jobs")


def test_served_bytes_remain_the_bytes_that_passed_checksum(client, monkeypatch):
    store = client.app.state.store
    step = client.get("/api/lessons/cache-lesson/speech?step_id=s1").json()["steps"][0]
    wav = store.local / "audio" / (step["audio_id"] + ".wav")
    validated_bytes = wav.read_bytes()
    lookup = provider.cached_audio
    def concurrent_replace(*args, **kwargs):
        result = lookup(*args, **kwargs)
        wav.write_bytes(b"replaced after validation")
        return result
    monkeypatch.setattr(provider, "cached_audio", concurrent_replace)
    response = client.get(step["audio_url"])
    assert response.status_code == 200 and response.content == validated_bytes


def test_oversized_cache_stops_before_serving(tmp_path):
    wav, _ = make_cache(tmp_path)
    wav.write_bytes(b"x" * (4 * 1024 * 1024 + 1))
    result = provider.cached_audio(TEXT, root=tmp_path)
    assert not result["hit"] and result["code"] == "cache_wave_oversized"


def test_missing_cache_does_not_hide_explicit_generation_capability(client, monkeypatch):
    store = client.app.state.store
    lesson = store.get("lessons", "cache-lesson")
    lesson["plan"]["steps"][0]["speech"] += " 다른 문장"
    store.put("lessons", lesson)
    monkeypatch.setattr(provider, "status", lambda root: {"ready": True, "reason": None})
    result = client.get("/api/lessons/cache-lesson/speech?step_id=s1").json()
    assert result["available"] and result["generation_available"] and not result["cached_available"]
    assert result["steps"] == [] and result["cache_misses"] and not store.list("jobs")


def test_cached_replay_remains_available_when_generation_engine_unavailable(client, monkeypatch):
    monkeypatch.setattr(provider, "status", lambda root: {"ready": False, "reason": "fixture unavailable"})
    result = client.get("/api/lessons/cache-lesson/speech?step_id=s1").json()
    assert result["available"] and result["cached_available"] and not result["generation_available"]
    assert client.get(result["steps"][0]["audio_url"]).status_code == 200


def test_cache_endpoints_keep_authentication(client):
    step = client.get("/api/lessons/cache-lesson/speech?step_id=s1").json()["steps"][0]
    client.headers.pop("Authorization")
    assert client.get("/api/lessons/cache-lesson/speech?step_id=s1").status_code == 401
    assert client.get(step["audio_url"]).status_code == 401


def test_source_context_is_a_minimal_read_only_projection(client):
    store = client.app.state.store
    store.put("sessions", {"id": "fixture-session"})
    source = {"id": "source", "session_id": "fixture-session", "role": "assistant",
              "lesson_context": {"lesson_id": "original-plan", "problem_revision": 4,
                                 "board_snapshot": {"large": "omitted"}}}
    store.put("messages", source)
    lesson = store.get("lessons", "cache-lesson")
    lesson["source_message_id"] = "source"
    store.put("lessons", lesson)
    result = client.get("/api/lessons/cache-lesson").json()
    assert result["source_session_id"] == "fixture-session"
    assert result["source_lesson_context"] == {"lesson_id": "original-plan", "problem_revision": 4}
    assert store.get("lessons", "cache-lesson") == lesson and store.get("messages", "source") == source


def test_lesson_projection_and_audio_manifest_share_same_binding(client):
    store = client.app.state.store
    original = store.get("lessons", "cache-lesson")
    lesson = client.get("/api/lessons/cache-lesson").json()
    manifest = client.get("/api/lessons/cache-lesson/speech?step_id=s1").json()
    assert lesson["speech_binding_fingerprint"] == manifest["binding_fingerprint"]
    assert manifest["steps"][0]["binding_fingerprint"] == lesson["speech_binding_fingerprint"]
    assert store.get("lessons", "cache-lesson") == original
    assert "speech_binding_fingerprint" not in original
    # The existing demo alias must project the same binding too; otherwise a
    # fresh student's demo would fail the new visible-board check.
    demo = client.get("/api/lessons/demo-count-null").json()
    demo_manifest = client.get("/api/lessons/demo-count-null/speech").json()
    assert demo["speech_binding_fingerprint"] == demo_manifest["binding_fingerprint"]


def test_changed_board_projects_new_binding_without_changing_cached_voice(client):
    before = client.get("/api/lessons/cache-lesson").json()
    first = client.get("/api/lessons/cache-lesson/speech?step_id=s1").json()["steps"][0]
    store = client.app.state.store
    changed = store.get("lessons", "cache-lesson")
    changed["plan"]["steps"][0]["board"]["value"] = 2
    store.put("lessons", changed)
    current = client.get("/api/lessons/cache-lesson").json()
    next_audio = client.get("/api/lessons/cache-lesson/speech?step_id=s1").json()["steps"][0]
    assert current["speech_binding_fingerprint"] != before["speech_binding_fingerprint"]
    assert current["speech_binding_fingerprint"] == next_audio["binding_fingerprint"]
    assert next_audio["audio_id"] == first["audio_id"]  # Same script, separate current-board binding.
    assert client.get(first["audio_url"]).status_code == 409
    assert client.get(next_audio["audio_url"]).status_code == 200
    assert store.get("lessons", "cache-lesson") == changed


def test_saturated_budget_and_busy_job_do_not_block_cache_read(client):
    store = client.app.state.store
    (store.local / "phase2-policy.json").write_text(json.dumps({"enabled": True, "gpu_seconds": 0,
        "new_audio_clips": 0, "vision_requests": 0, "min_C_free_bytes": 0}))
    ledger = store.root / "runs/phase2/current/resource-budget.json"
    ledger.parent.mkdir(parents=True)
    raw = b'{"used_seconds":5400,"new_audio_clips":19,"vision_requests":6,"requests":[]}'
    ledger.write_bytes(raw)
    job = {"id": "busy-fixture", "kind": "text", "state": "running"}
    store.put("jobs", job)
    # This is only the filesystem lease in an isolated test root, no GPU use.
    with GPULease(store.local, "cpu-lease-fixture"):
        with pytest.raises(LeaseBusy):
            with GPULease(store.local, "second-fixture"):
                pass
        result = client.get("/api/lessons/cache-lesson/speech?step_id=s1").json()
        assert result["steps"] and client.get(result["steps"][0]["audio_url"]).status_code == 200
    assert ledger.read_bytes() == raw and store.list("jobs") == [job]


def test_explicit_prepare_and_replay_share_strict_cache_checks(tmp_path, monkeypatch):
    # Call the original function despite the default no-inference tripwire.
    wav, meta = make_cache(tmp_path)
    monkeypatch.setattr(provider, "status", lambda root: {"ready": True})
    assert PREPARE_BATCH([{"id": "s1", "text": TEXT}], root=tmp_path)[0]["audio"]["cache_hit"]
    meta["completion"]["finish_reason"] = "length_or_timeout"
    wav.with_suffix(".json").write_text(json.dumps(meta))
    assert not provider.cached_audio(TEXT, root=tmp_path)["hit"]
    # An explicit generation request can only proceed through the normal worker
    # budget path. The tripwire proves the invalid cache was not published.
    with pytest.raises(AssertionError, match="cache reads"):
        PREPARE_BATCH([{"id": "s1", "text": TEXT}], root=tmp_path)


@pytest.mark.parametrize("shared", [False, True])
def test_new_host_timing_uses_cpu_test_doubles_only(tmp_path, monkeypatch, shared):
    """No real torch/qwen import, weights, GPU, speech inference or optimizer."""
    import numpy as np
    wav, meta = make_cache(tmp_path)
    key, spec = provider._spec(TEXT, tmp_path, "Sohee")
    expected_settings = {"do_sample": False, "max_new_tokens": 768, "subtalker_dosample": True}
    model = SimpleNamespace(_merge_generate_kwargs=lambda **kwargs: {**expected_settings, **kwargs})
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(float16="fixture", bfloat16="fixture",
        cuda=SimpleNamespace(is_available=lambda: True, is_bf16_supported=lambda: False,
                             max_memory_allocated=lambda: 0)))
    monkeypatch.setitem(sys.modules, "qwen_tts", SimpleNamespace(Qwen3TTSModel=SimpleNamespace(
        from_pretrained=lambda *args, **kwargs: model)))
    monkeypatch.setattr(provider, "_checked_custom_voice", lambda *args: (
        [np.full(12000, .1)], 24000, meta["completion"]))
    run = tmp_path / "cpu-test-double"
    run.mkdir()
    emitted = []
    provider.speech_job({"root": str(tmp_path), "run_dir": str(run), "spec": spec,
                         "cancel_path": str(run / "cancel"), "audio_id": key},
                        lambda kind, **value: emitted.append(value),
                        model=model if shared else None, model_load_seconds=9 if shared else 0)
    result = emitted[0]
    timing = result["host_timing"]
    assert result["effective_tts_generation_settings"] == expected_settings
    assert timing["not_gpu_kernel_time"] and timing["clock"] == "worker_monotonic"
    assert timing["voice_api_finished_offset_seconds"] >= timing["voice_api_started_offset_seconds"]
    assert timing["voice_api_seconds"] >= 0 and timing["wave_write_seconds"] >= 0
    assert timing["voice_api_to_audio_duration_ratio"] == timing["voice_api_seconds"] / .5
    assert timing["metadata_write_seconds"] is None
    if shared:
        assert result["model_load_seconds"] == 9
        assert timing["model_load_scope"] == "before_clip_entry_shared_batch"
    else:
        assert timing["model_load_scope"] == "within_clip_entry"
    assert provider.cached_audio(TEXT, root=tmp_path)["hit"]
