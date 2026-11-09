"""Synthetic cache fixtures only; changing a provider cannot rewrite old audio."""
import json

from fastapi.testclient import TestClient

from edu_tutor.api import create_app
from edu_tutor.models import runtime
from test_speech_cache_replay import make_cache, TEXT


def test_default_engine_change_keeps_attached_historical_voice_and_binding(tmp_path, monkeypatch):
    wav, audio = make_cache(tmp_path)
    # A deliberately unavailable new engine must not disable a valid, attached
    # historical clip or cause an implicit synthesis while reading it.
    (tmp_path / ".local/speech-provider.json").write_text(json.dumps({
        "provider": "windows_sapi_local", "windows_sapi": {"language": "ko-KR"}}))
    monkeypatch.setattr(runtime, "run_worker", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("No worker")))
    app = create_app(tmp_path)
    lesson = {"id": "historical", "valid": True, "speech_allowed": True, "is_demo": False,
              "generation_epoch": 1, "problem": {"revision": 1, "source": {}},
              "plan": {"steps": [{"id": "s1", "speech": TEXT, "board": {"value": 1}}]},
              "audio_steps": [{**audio, "step_id": "s1"}]}
    app.state.store.put("lessons", lesson)
    token = (tmp_path / ".local/auth-token").read_text().strip()
    before = wav.read_bytes()
    with TestClient(app, base_url="http://127.0.0.1:8000", headers={"Authorization": "Bearer " + token}) as client:
        result = client.get("/api/lessons/historical/speech?step_id=s1&voice=default")
        assert result.status_code == 200
        clip = result.json()["steps"][0]
        assert clip["voice"] == "Sohee" and clip["cache_source"] == "attached"
        assert "voice=Sohee" in clip["audio_url"]
        assert client.get(clip["audio_url"]).content == before
        # A changed board must still reject the same formerly valid URL.
        lesson["plan"]["steps"][0]["board"]["value"] = 2
        app.state.store.put("lessons", lesson)
        assert client.get(clip["audio_url"]).status_code == 409
        assert app.state.store.list("jobs") == []
    assert wav.read_bytes() == before
