from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import v021_eval_live as live


class FakeClient:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def call(self, path, body):
        self.calls.append((path, body))
        if self.error:
            raise self.error
        return {"job_id": "saved-job"}


def test_completed_submission_is_read_not_reposted(tmp_path):
    client = FakeClient()
    body = {"content": "new question", "request_id": "fixed"}
    first = live.submit_once(client, tmp_path, "chat", "/api/example", body)
    assert live.submit_once(client, tmp_path, "chat", "/api/example", body) == first
    assert len(client.calls) == 1
    with pytest.raises(RuntimeError, match="differs"):
        live.submit_once(client, tmp_path, "chat", "/api/example", {**body, "content": "changed"})
    assert len(client.calls) == 1


def test_unknown_post_outcome_stops_instead_of_retrying(tmp_path):
    client = FakeClient(TimeoutError("outcome unknown"))
    with pytest.raises(TimeoutError):
        live.submit_once(client, tmp_path, "chat", "/api/example", {})
    client.error = None
    with pytest.raises(RuntimeError, match="no automatic retry"):
        live.submit_once(client, tmp_path, "chat", "/api/example", {})
    assert len(client.calls) == 1
    assert live.read(tmp_path / "chat-submission.json")["status"] == "failed_or_unknown_no_retry"


def test_source_change_after_freeze_blocks_evaluation(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "BASE", tmp_path)
    monkeypatch.setattr(live, "current_hashes", lambda: {"src/a.py": "initial"})
    live.save(tmp_path / "code-freeze.json", {"source_hashes": {"src/a.py": "initial"}})
    assert live.check_code()["source_hashes"] == {"src/a.py": "initial"}
    monkeypatch.setattr(live, "current_hashes", lambda: {"src/a.py": "edited"})
    with pytest.raises(RuntimeError, match="changed after code freeze"):
        live.check_code()


def test_private_query_or_intent_cannot_be_added_to_public_problem(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "BASE", tmp_path)
    import json
    rows = [{"id": str(i), "problem": {"raw_text": "fixture", "query": "private SQL"}} for i in range(28)]
    data = "".join(json.dumps(row) + "\n" for row in rows).encode()
    (tmp_path / "public.jsonl").write_bytes(data)
    live.save(tmp_path / "freeze.json", {"public_sha256": live.sha(data)})
    with pytest.raises(RuntimeError, match="Private or candidate-derived"):
        live.check_corpus()


def test_second_frozen_corpus_is_explicit_and_cannot_escape_project(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "ROOT", tmp_path)
    monkeypatch.setattr(live, "BASE", tmp_path / "original")
    target = tmp_path / "runs/v021-support/20261029/independent-eval-r2"
    target.mkdir(parents=True)
    (target / "freeze.json").write_text("{}")
    assert live.use_corpus("independent-eval-r2") == target.resolve()
    with pytest.raises(ValueError, match="directory required"):
        live.use_corpus(str(tmp_path / "elsewhere"))
    with pytest.raises(ValueError, match="frozen"):
        live.use_corpus("independent-eval-r3")


def test_failed_lesson_stops_after_persisting_actual_case(tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(live, "ROOT", tmp_path)
    monkeypatch.setattr(live, "BASE", tmp_path)
    rows = [{"id": str(i), "problem": {"raw_text": "fixture"}} for i in range(28)]
    monkeypatch.setattr(live, "check_corpus", lambda: ({"public_sha256": "fixed"}, rows))
    monkeypatch.setattr(live, "check_code", lambda: {})
    monkeypatch.setattr(live, "prepare", lambda args: None)
    (tmp_path / "code-freeze.json").write_text("{}")
    prepared = tmp_path / "prepared-public-requests"
    prepared.mkdir()
    live.save(prepared / "0.json", {"request_id": "first"})
    posts = []
    grant = {"text_remaining": 100, "seconds_remaining": 1000}

    class Service:
        def budget(self):
            return {"active_execution_allowance": grant.copy()}

        def call(self, path, body=None):
            if path == "/api/jobs":
                return []
            if path == "/api/models":
                return []
            if path.endswith("/messages"):
                return [{"id": "message", "role": "assistant", "request_id": "first", "model_attempts": []}]
            if path == "/api/lessons/lesson":
                return {"id": "lesson", "status": "failed", "plan": None}
            raise AssertionError(path)

    def submit(client, folder, name, path, body):
        posts.append(name)
        if name == "session":
            return {"id": "session"}
        if name == "lesson":
            return {"id": "lesson"}
        return {"job_id": name}

    def job(client, folder, kind, job_id, session_id):
        return {"id": job_id, "state": "succeeded" if kind == "chat" else "failed", "error": "test failure"}

    monkeypatch.setattr(live, "Client", Service)
    monkeypatch.setattr(live, "submit_once", submit)
    monkeypatch.setattr(live, "await_job", job)
    with pytest.raises(RuntimeError, match="Actual lesson job failed"):
        live.execute(SimpleNamespace(go="ROOT_APPROVED_FINAL_FROZEN_V021"))
    report = live.read(tmp_path / "live-app-v1/result.json")
    assert report["status"] == "stopped_no_retry"
    assert len(report["items"]) == 1
    assert report["items"][0]["lesson_job_state"] == "failed"
    assert posts == ["session", "chat", "lesson", "lesson-generate"]
