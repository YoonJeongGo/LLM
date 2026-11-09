"""CPU transport contracts; all workers are fakes and all state is temporary."""
import hashlib
import json
import time

import pytest
from fastapi.testclient import TestClient

from edu_tutor.api import create_app
from edu_tutor.models import budget, runtime


SCOPE = "fixture-explicit-scope"


def policy_file(root, *, text_limit=2):
    local = root / ".local"
    local.mkdir(exist_ok=True)
    value = {"enabled": True, "gpu_seconds": 5400, "new_audio_clips": 23,
             "vision_requests": 6, "min_C_free_bytes": 0, "system_volume": str(root),
             "active_execution_allowance": {"id": SCOPE, "baseline_request_count": 0,
                 "baseline_requests_sha256": hashlib.sha256(b"[]").hexdigest(),
                 "limits": {"text_requests": text_limit, "new_audio_clips": 1,
                            "vision_requests": 0, "gpu_seconds": 600}}}
    (local / "phase2-policy.json").write_text(json.dumps(value), encoding="utf-8")


def make_client(root):
    app = create_app(root)

    @app.post("/api/fixture-scope-job")
    def create_fixture_job():
        def target(ident, cancel):
            return list(runtime.run_worker({"kind": "text", "job_id": ident}, root=root,
                                           cancel_event=cancel, timeout=20))
        return app.state.jobs.submit("speech", target)

    token = (root / ".local/auth-token").read_text().strip()
    return TestClient(app, base_url="http://127.0.0.1:8000",
                      headers={"Authorization": "Bearer " + token})


def completed(client, ident):
    for _ in range(100):
        value = client.get("/api/jobs/" + ident).json()
        if value["state"] in {"succeeded", "failed", "blocked", "cancelled"}:
            return value
        time.sleep(.01)
    raise AssertionError("In-memory CPU job did not finish")


def test_explicit_header_reaches_budget_through_api_and_job_thread(tmp_path, monkeypatch):
    policy_file(tmp_path)
    seen = []

    def reserve(root, payload, timeout, **_kwargs):
        seen.append(dict(payload))
        if payload.get("execution_allowance_id") != SCOPE:
            raise budget.ResourceBudgetExceeded("Fixture explicit scope is required")
        return None, timeout

    monkeypatch.setattr(budget, "reserve", reserve)
    monkeypatch.setattr(budget, "finish", lambda *_args: None)
    monkeypatch.setattr(runtime, "_run_worker", lambda *_args, **_kwargs: iter([{"type": "done", "fixture": True}]))
    with make_client(tmp_path) as client:
        first = client.post("/api/fixture-scope-job", headers={"X-Execution-Allowance": SCOPE})
        assert first.status_code == 200
        assert completed(client, first.json()["id"])["state"] == "succeeded"
        # A subsequent request without the header must not inherit the prior
        # request's authorization through a reused worker thread or middleware.
        second = client.post("/api/fixture-scope-job")
        assert completed(client, second.json()["id"])["state"] == "blocked"
    assert seen[0]["execution_allowance_id"] == SCOPE
    assert "execution_allowance_id" not in seen[1]


def test_mismatched_header_is_rejected_before_a_job_is_created(tmp_path, monkeypatch):
    policy_file(tmp_path)
    monkeypatch.setattr(runtime, "_run_worker", lambda *_args, **_kwargs: pytest.fail("No worker allowed"))
    with make_client(tmp_path) as client:
        before = client.app.state.store.list("jobs")
        response = client.post("/api/fixture-scope-job", headers={"X-Execution-Allowance": "not-approved"})
        assert response.status_code == 409
        assert client.app.state.store.list("jobs") == before


def test_missing_header_cannot_create_text_work_under_old_zero_text_grant(tmp_path, monkeypatch):
    policy_file(tmp_path, text_limit=0)
    monkeypatch.setattr(runtime, "_run_worker", lambda *_args, **_kwargs: pytest.fail("Old grant denies text"))
    with make_client(tmp_path) as client:
        job = client.post("/api/fixture-scope-job").json()
        result = completed(client, job["id"])
        assert result["state"] == "blocked"
        assert "추가 승인" in result["error"]
    ledger = tmp_path / "runs/phase2/current/resource-budget.json"
    assert not ledger.exists() or json.loads(ledger.read_text())["requests"] == []


def test_bind_scope_does_not_replace_an_explicit_conflicting_payload():
    from edu_tutor.models.execution_context import bind_scope, execution_allowance
    token = execution_allowance.set(SCOPE)
    try:
        assert bind_scope({"kind": "text"})["execution_allowance_id"] == SCOPE
        assert bind_scope({"kind": "text", "execution_allowance_id": "wrong"})["execution_allowance_id"] == "wrong"
    finally:
        execution_allowance.reset(token)
