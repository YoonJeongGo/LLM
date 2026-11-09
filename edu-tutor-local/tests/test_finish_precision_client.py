"""Comparison driver contracts with fake jobs only; no real auth, API or GPU."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("precision_client_test", ROOT / "scripts/finish_precision_live.py")
client_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client_module)


@pytest.fixture
def project(tmp_path):
    folder = tmp_path / client_module.PROPOSAL
    folder.mkdir(parents=True)
    (folder / "protocol.json").write_bytes((ROOT / client_module.PROPOSAL / "protocol.json").read_bytes())
    return tmp_path


def raw_result(body, protocol):
    rows = []
    for index, item in enumerate(body["items"]):
        rows.append({"id": item["id"], "model_load_count": 1 - index, "worker_pid": 51,
                     "model_object_id": 992, "precision": body["precision"],
                     "inference": {"requested_precision": body["precision"],
                         "actual_is_loaded_in_4bit": body["precision"] == "nf4",
                         "actual_parameter_devices": ["cuda:0"], "load_dtype": "torch.bfloat16",
                         "actual_parameter_dtypes_elements": {"torch.bfloat16": 20},
                         "unique_parameter_storage_bytes": 40},
                     "revision": protocol["base_revision"], "max_new_tokens": 128,
                     "output_tokens": 15, "input_tokens": 20, "finish_reason": "eos",
                     "phase_timing": {"generation_seconds": 2, "runtime_import_seconds": 1 - index,
                         "loader_import_seconds": 1 - index, "load_excluding_loader_import_seconds": 1 - index},
                     "latency_seconds": 2, "model_load_seconds": 2 if index == 0 else 0,
                     "text": "test output; not an educational result"})
    return {"status": "completed", "items": rows}


def test_prepare_never_creates_client_or_overwrites(project):
    def forbidden(*args):
        raise AssertionError("Prepare must not touch auth/network/model")
    result = client_module.run("prepare", root=project, client_factory=forbidden)
    assert result["status"] == "prepared" and result["model_calls_submitted"] == 0
    folder = project / "runs/finish-v2/20261029/prepare"
    bodies = [json.loads((folder / (name + "-request.json")).read_text(encoding="utf-8")) for name in ("nf4", "bf16")]
    assert sum(len(body["items"]) for body in bodies) == 4
    assert len({json.dumps(item["messages"]) for body in bodies for item in body["items"]}) == 1
    with pytest.raises(ValueError, match="already exists"):
        client_module.run("prepare", root=project, client_factory=forbidden)


def test_result_requires_actual_precision_and_same_instance(project):
    protocol, bodies = client_module.inputs(project)
    for body in bodies:
        raw = raw_result(body, protocol)
        summary = client_module.check_result({"state": "succeeded"}, raw, body, protocol)
        assert [r["generation_tokens_per_second"] for r in summary] == [7.5, 7.5]
        changed = deepcopy(raw)
        changed["items"][1]["model_object_id"] += 1
        with pytest.raises(RuntimeError, match="identical"):
            client_module.check_result({"state": "succeeded"}, changed, body, protocol)
        changed = deepcopy(raw)
        changed["items"][0]["inference"]["actual_is_loaded_in_4bit"] = body["precision"] != "nf4"
        with pytest.raises(RuntimeError, match="contradict"):
            client_module.check_result({"state": "succeeded"}, changed, body, protocol)


class FakeClient:
    def __init__(self, root):
        self.posts = []

    def call(self, path, body=None):
        if body is not None:
            assert path == "/api/evaluations/text-batch"
            self.posts.append(body)
            return {"id": str(len(self.posts)), "state": "queued"}
        return [] if path == "/api/jobs" else {"fake": True}


@pytest.mark.parametrize("failed", [False, True])
def test_execute_exact_batches_or_stop_after_first_failure(project, monkeypatch, failed):
    protocol, _ = client_module.inputs(project)
    client = FakeClient(project)
    monkeypatch.setattr(client_module, "source_hashes", lambda root: {"fake-source": "unchanged"})
    monkeypatch.setattr(client_module.importlib.metadata, "version", lambda name: "fake")
    monkeypatch.setattr(client_module, "gpu_snapshot", lambda: {"fake": True})
    monkeypatch.setattr(client_module, "preflight", lambda *_: {"budget": {"fake": True}})
    def wait(_client, _folder, journal, maximum):
        assert maximum == 315
        body = client.posts[-1]
        return {"id": journal["job_id"], "state": "failed" if failed else "succeeded",
                "result": raw_result(body, protocol)}
    monkeypatch.setattr(client_module, "await_job", wait)
    if failed:
        with pytest.raises(RuntimeError, match="Batch failed"):
            client_module.run("failure", root=project, execute=True, client_factory=lambda _: client)
        assert [body["precision"] for body in client.posts] == ["nf4"]
        report = json.loads((project / "runs/finish-v2/20261029/failure/result.json").read_text(encoding="utf-8"))
        assert report["status"] == "stopped_preserved_no_retry"
    else:
        report = client_module.run("success", root=project, execute=True, client_factory=lambda _: client)
        assert report["status"] == "completed_screening_only"
        assert [body["precision"] for body in client.posts] == ["nf4", "bf16"]
        assert report["model_calls_submitted"] == 4
    assert all(len(body["items"]) == 2 and body["max_new_tokens"] == 128 for body in client.posts)


def test_ambiguous_post_is_not_retried(project, monkeypatch):
    class BrokenClient(FakeClient):
        def call(self, path, body=None):
            if body is not None:
                self.posts.append(body)
                raise TimeoutError("fake ambiguous submission")
            return super().call(path, body)
    client = BrokenClient(project)
    monkeypatch.setattr(client_module, "source_hashes", lambda root: {})
    monkeypatch.setattr(client_module.importlib.metadata, "version", lambda name: "fake")
    monkeypatch.setattr(client_module, "preflight", lambda *_: {"budget": {}})
    with pytest.raises(TimeoutError):
        client_module.run("ambiguous", root=project, execute=True, client_factory=lambda _: client)
    assert len(client.posts) == 1
    folder = project / "runs/finish-v2/20261029/ambiguous"
    journal = json.loads((folder / "nf4/submission.json").read_text(encoding="utf-8"))
    assert journal["status"] == "submission_failed_or_unknown"
    assert not (folder / "bf16/submission.json").exists()
    report = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    assert report["generation_attempts_requested_upper_bound"] == 2
    assert report["model_calls_submitted"] == 0
