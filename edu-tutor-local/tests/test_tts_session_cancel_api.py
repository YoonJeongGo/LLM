"""CPU fixtures only: normal lesson completion/cancel ownership, never synthesis."""
import json

from test_phase2_backend import client, wait
from test_tts_reuse_api import setup


def test_terminal_speech_cancel_keeps_its_original_owner_key(client, monkeypatch):
    from edu_tutor.speech import provider
    store, lesson, _, closes = setup(client, monkeypatch)
    (store.root / ".local/tts-session-policy.json").write_text(json.dumps({"mode": "session"}))
    lesson["plan"]["steps"].append({"id": "s2", "speech": "다음 검증 단계"})
    store.put("lessons", lesson)
    monkeypatch.setattr(provider, "prepare", lambda *a, **kw: {"audio_id": "b"*64, "url": "/api/audio/"+"b"*64})
    response = client.post("/api/lessons/verified-source/speech", json={"step_id": "s1", "request_id": "normal-stop"})
    assert response.status_code == 202
    job = wait(client, response.json()["job_id"])
    assert job["state"] == "succeeded" and job["speech_session_key"].startswith("lesson:verified-source:")
    assert not closes, "A non-final successful step may retain its worker"
    changed = store.get("lessons", lesson["id"])
    changed["plan"]["steps"][0]["speech"] = "현재 대사는 변경됨"
    store.put("lessons", changed)
    response = client.post(f"/api/jobs/{job['id']}/cancel", json={})
    assert response.status_code == 200 and response.json()["state"] == "succeeded"
    assert closes[-1] == {"session_key": job["speech_session_key"], "job_id": job["id"], "reason": "speech_job_cancelled"}


def test_allowed_fallback_completes_and_releases_its_exact_job(client, monkeypatch):
    from edu_tutor.speech import provider
    store, lesson, _, closes = setup(client, monkeypatch)
    (store.root / ".local/tts-session-policy.json").write_text(json.dumps({"mode": "session"}))
    lesson.update(plan=None, fallback_text="CPU 검증용 허용된 이전 텍스트 설명")
    store.put("lessons", lesson)
    monkeypatch.setattr(provider, "prepare", lambda *a, **kw: {"audio_id": "b"*64, "url": "/api/audio/"+"b"*64})
    response = client.post("/api/lessons/verified-source/speech", json={"request_id": "fallback-stop"})
    assert response.status_code == 202
    job = wait(client, response.json()["job_id"])
    assert job["state"] == "succeeded" and job["result"]["complete"], job
    assert closes[-1]["job_id"] == job["id"] and closes[-1]["reason"] == "lesson_complete_or_cancelled"


def test_old_unowned_terminal_job_cancel_does_not_close_any_worker(client, monkeypatch):
    store, _, _, closes = setup(client, monkeypatch)
    store.put("jobs", {"id": "legacy-unowned", "kind": "speech", "state": "succeeded", "result": {}})
    response = client.post("/api/jobs/legacy-unowned/cancel", json={})
    assert response.status_code == 200 and not closes
