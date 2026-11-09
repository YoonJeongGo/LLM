"""Independent CPU regression for coalesced-write failures. Never a real model."""
import threading
import time

from fastapi.testclient import TestClient

from edu_tutor.api import create_app
from edu_tutor.jobs.manager import JobManager, TERMINAL
from edu_tutor.storage.db import Store


FAILURE = "review fixture partial flush failure"


def fail_background_flush(manager, ident, monkeypatch):
    manager.update_partial(ident, 1, partial_text="first", raw_partial_text="first")
    manager.update_partial(ident, 1, partial_text="first tail", raw_partial_text="first tail")
    pending = manager.partials[ident]
    if pending["timer"] is not None:
        pending["timer"].cancel()
    original = manager.store.put
    def broken(*args, **kwargs):
        raise OSError(FAILURE)
    with monkeypatch.context() as patch:
        patch.setattr(manager.store, "put", broken)
        manager._partial_timer(ident, pending)
    assert manager.store.put == original
    assert manager.cancels[ident].is_set()
    assert FAILURE in pending["error"]


def test_background_failure_survives_target_cooperative_return(tmp_path, monkeypatch):
    manager = JobManager(Store(tmp_path))
    try:
        def target(ident, cancel):
            fail_background_flush(manager, ident, monkeypatch)
            return {"discarded": True}
        job = manager.submit("chat", target, generation_epoch=1)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            saved = manager.store.get("jobs", job["id"])
            if saved["state"] in TERMINAL:
                break
            time.sleep(.01)
        assert saved["state"] != "succeeded"
        assert saved["state"] in {"failed", "cancelled"}
        assert FAILURE in saved.get("error", "")
        assert FAILURE in saved["partial_persistence_error"]
        assert saved["raw_partial_text"] == "first tail"
    finally:
        manager.close()


def test_cancel_api_after_background_failure_preserves_diagnostic(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    manager = app.state.jobs
    token = (tmp_path / ".local/auth-token").read_text().strip()
    with TestClient(app, base_url="http://127.0.0.1:8000", headers={"Authorization": "Bearer " + token}) as client:
        session = client.post("/api/sessions", json={}).json()
        session["generation_epoch"] = 1
        manager.store.put("sessions", session)
        ident = "review-failure-owned"
        manager.store.put("jobs", {"id": ident, "kind": "chat", "state": "running", "generation_epoch": 1,
            "owner_instance": manager.instance, "session_id": session["id"], "cancel_requested": False})
        manager.cancels[ident] = threading.Event()
        fail_background_flush(manager, ident, monkeypatch)
        response = client.post(f"/api/jobs/{ident}/cancel")
        assert response.status_code == 200, response.text
        value = response.json()
        assert value["cancel_requested"]
        assert FAILURE in value["partial_persistence_error"]
        assert manager.store.get("sessions", session["id"])["generation_epoch"] == 2
        manager.update(ident, state="cancelled")
        terminal = client.get(f"/api/jobs/{ident}").json()
        assert FAILURE in terminal["error"]
        assert terminal["raw_partial_text"] == "first tail"


def test_persistence_failure_never_permits_success_even_after_cancel_ack(tmp_path, monkeypatch):
    manager = JobManager(Store(tmp_path))
    try:
        ident = "review-no-success"
        manager.store.put("jobs", {"id": ident, "kind": "chat", "state": "running", "generation_epoch": 1,
            "owner_instance": manager.instance, "cancel_requested": False})
        manager.cancels[ident] = threading.Event()
        fail_background_flush(manager, ident, monkeypatch)
        manager.cancel(ident)
        try:
            manager.update(ident, state="succeeded", result={"unsafe": True})
        except RuntimeError as exc:
            assert "persistence failed" in str(exc)
        else:
            raise AssertionError("A cancelled persistence failure was allowed to succeed")
        assert manager.store.get("jobs", ident)["state"] != "succeeded"
        manager.update(ident, state="failed", error="later independent error")
        saved = manager.store.get("jobs", ident)
        assert saved["error"] == "later independent error"
        assert FAILURE in saved["partial_persistence_error"]
    finally:
        manager.close()


def test_shutdown_preserves_background_failure_diagnostic(tmp_path, monkeypatch):
    manager = JobManager(Store(tmp_path))
    ident = "review-shutdown-failure"
    manager.store.put("jobs", {"id": ident, "kind": "chat", "state": "running", "generation_epoch": 1,
        "owner_instance": manager.instance, "cancel_requested": False})
    manager.cancels[ident] = threading.Event()
    fail_background_flush(manager, ident, monkeypatch)
    manager.close()
    restored = JobManager(Store(tmp_path))
    try:
        saved = restored.store.get("jobs", ident)
        assert saved["state"] == "interrupted"
        assert saved["raw_partial_text"] == "first tail"
        assert FAILURE in saved["partial_persistence_error"]
    finally:
        restored.close()
