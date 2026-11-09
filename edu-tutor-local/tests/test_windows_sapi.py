"""CPU contracts with synthetic PCM. No installed voice is synthesized here."""
import array
import builtins
import hashlib
import io
import json
import os
import subprocess
import sys
import time
import wave

import pytest

from edu_tutor.speech import provider, windows_sapi as sapi


@pytest.fixture
def configured(tmp_path):
    config = {"provider": sapi.PROVIDER, "windows_sapi": {
        "voice_id": "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\fixture-Korean",
        "voice_name": "Fixture Korean", "language": "ko-KR", "sapi_binary_sha256": "f"*64,
        "engine_version": "fixture-engine", "os_build": "fixture-build"}}
    (tmp_path / ".local/audio").mkdir(parents=True)
    (tmp_path / ".local/speech-provider.json").write_text(json.dumps(config), encoding="utf-8")
    return tmp_path, config, sapi.VOICE_PREFIX + config["windows_sapi"]["voice_id"]


def pcm(*, silent=False, rate=sapi.SAMPLE_RATE):
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        stream.writeframes(array.array("h", [0 if silent else (100 if n % 2 else -100) for n in range(rate//2)]).tobytes())
    return output.getvalue()


def make_cache(root, voice, text="SQL에서 NULL은 0과 다릅니다."):
    key, value = sapi.spec(text, root, voice)
    data = pcm()
    meta = {"audio_id": key, "provider": sapi.PROVIDER, "voice": value["voice"],
        "revision": value["revision"], "engine_version": value["engine_version"],
        "display_text": text, "spoken_text": value["spoken_text"],
        "text_hash": hashlib.sha256(value["text"].encode()).hexdigest(),
        "generation_settings": sapi.generation_settings(value), **sapi.inspect_pcm(data),
        "completion": {"finish_reason": "sapi_wait_until_done", "exit_code": 0, "completion_check_version": 1}}
    path = root / ".local/audio" / (key+".wav")
    path.write_bytes(data)
    path.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
    return path, meta, text


def test_provider_identity_preserves_display_and_distinguishes_spoken_script(configured):
    root, config, voice = configured
    key, value = provider._spec("SQL에서 NULL은 0과 다릅니다.", root, "default")
    assert value["display_text"] == "SQL에서 NULL은 0과 다릅니다."
    assert value["spoken_text"] == "에스 큐 엘에서 널은 0과 다릅니다."
    assert value["provider"] == sapi.PROVIDER
    assert provider._spec("SQL에서 NULL은 1과 다릅니다.", root, voice)[0] != key
    config["windows_sapi"]["engine_version"] = "changed"
    (root / ".local/speech-provider.json").write_text(json.dumps(config), encoding="utf-8")
    assert provider._spec(value["display_text"], root, voice)[0] != key
    with pytest.raises(ValueError, match="한국어"):
        sapi.spec("시험", root, sapi.VOICE_PREFIX + "unknown-token")


@pytest.mark.parametrize("mutation", ["none", "wrong_text", "no_completion", "wave_changed", "silent"])
def test_system_cache_validates_completion_binding_and_pcm_without_neural_eos(configured, mutation):
    root, _, voice = configured
    path, meta, text = make_cache(root, voice)
    if mutation == "wrong_text":
        meta["spoken_text"] = "다른 문장"
    if mutation == "no_completion":
        meta["completion"] = {"finish_reason": "eos", "exit_code": 0, "completion_check_version": 1}
    if mutation == "wave_changed":
        path.write_bytes(b"invalid")
    if mutation == "silent":
        data = pcm(silent=True)
        path.write_bytes(data)
        meta["checksum"] = hashlib.sha256(data).hexdigest()
    path.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
    result = provider.cached_audio(text, root=root, voice="default")
    assert result["hit"] == (mutation == "none")
    if result["hit"]:
        assert result["wave_bytes"] == path.read_bytes()
        assert result["audio"]["cache_hit"]


def test_system_wave_rejects_wrong_sample_format_and_silence():
    with pytest.raises(ValueError, match="22050"):
        sapi.inspect_pcm(pcm(rate=16000))
    with pytest.raises(ValueError, match="Silent"):
        sapi.inspect_pcm(pcm(silent=True))


def test_system_dispatch_does_not_import_neural_packages(configured, monkeypatch):
    root, _, voice = configured
    key, value = provider._spec("새로운 검증 문장입니다.", root, voice)
    imported = builtins.__import__
    def no_neural(name, *args, **kwargs):
        if name.split(".")[0] in {"torch", "transformers", "qwen_tts", "numpy", "soundfile"}:
            raise AssertionError("System speech imported a neural dependency: " + name)
        return imported(name, *args, **kwargs)
    calls = []
    monkeypatch.setattr(builtins, "__import__", no_neural)
    monkeypatch.setattr(sapi, "speech_job", lambda payload, emit, **kwargs: calls.append(payload))
    provider.speech_batch_job({"speech_provider": sapi.PROVIDER, "items": [{"audio_id": key, "spec": value}]}, lambda *_: None)
    provider.speech_job({"spec": value, "audio_id": key}, lambda *_: None)
    assert len(calls) == 2


def test_system_prepare_uses_existing_budgeted_worker_and_never_experimental_session(configured, monkeypatch):
    from edu_tutor.models import runtime
    root, _, _ = configured
    calls = []
    monkeypatch.setattr(sapi, "status", lambda _: {"ready": True})
    def worker(payload, **kwargs):
        calls.append(payload)
        for item in payload["items"]:
            yield {"type": "audio", "audio_id": item["audio_id"], "provider": sapi.PROVIDER}
        yield {"type": "done"}
    monkeypatch.setattr(runtime, "run_worker", worker)
    result = provider.prepare_batch([{"id": "s1", "text": "세 행입니다."}], root=root,
        voice="default", session_key="existing-lesson-binding")
    assert result[0]["audio"]["provider"] == sapi.PROVIDER
    assert calls[0]["kind"] == "speech_batch"
    assert calls[0]["speech_provider"] == sapi.PROVIDER
    assert "tts_session_key" not in calls[0]


def test_corrupted_system_cache_stops_before_worker_reservation(configured, monkeypatch):
    from edu_tutor.models import runtime
    root, _, voice = configured
    path, _, text = make_cache(root, voice)
    path.write_bytes(b"corrupt preserved fixture")
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Corrupt cache must not consume a synthesis attempt")
    monkeypatch.setattr(runtime, "run_worker", forbidden)
    with pytest.raises(ValueError, match="무결성"):
        provider.prepare_batch([{"id": "s1", "text": text}], root=root, voice="default")
    assert path.read_bytes() == b"corrupt preserved fixture"


@pytest.mark.skipif(os.name != "nt", reason="Windows process ownership contract")
def test_owned_job_close_terminates_exact_sleeping_child_without_speech():
    # Actual OS process-lifetime check. The child only sleeps: no voice, model,
    # fixture WAV, or inference budget is consumed.
    executable = getattr(sys, "_base_executable", sys.executable)
    child = subprocess.Popen([executable, "-c", "import time; time.sleep(30)"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    owner = None
    try:
        owner = sapi._OwnedProcessJob(child)
        assert child.poll() is None
        started = time.monotonic()
        owner.close()
        child.wait(timeout=3)
        assert child.poll() is not None
        assert time.monotonic()-started < 3
    finally:
        if owner is not None:
            owner.close()
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=3)


@pytest.mark.parametrize("completed,published,expected", [
    (False, False, "CANCELLED_DURING_SYNTHESIS_WITH_OWNED_CHILD_EXIT"),
    (True, False, "CANCELLATION_NOT_PROVEN"),
    (False, True, "CANCELLATION_NOT_PROVEN"),
])
def test_live_evidence_does_not_call_late_cancel_actual_synthesis_interruption(completed, published, expected):
    from scripts.finish_voice_live import cancellation_status
    events = [{"stage": "synth_queued"}] + ([{"stage": "synth_finished"}] if completed else [])
    assert cancellation_status(True, "cancelled", events, [], published) == expected
