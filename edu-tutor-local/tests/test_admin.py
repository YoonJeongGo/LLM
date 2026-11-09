"""T0 admin contracts. Fake adapter bytes and fake training are never GPU evidence."""
import copy
import json
import shutil
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from edu_tutor.api import create_app
from edu_tutor.jobs.lease import GPULease
from edu_tutor.training.data import load_records

SOURCE = Path(__file__).resolve().parents[1]


@pytest.fixture
def admin(tmp_path):
    shutil.copytree(SOURCE / "data/demo", tmp_path / "data/demo")
    app = create_app(tmp_path)
    token = (tmp_path / ".local/auth-token").read_text()
    with TestClient(app, base_url="http://127.0.0.1:8000", headers={"Authorization":f"Bearer {token}"}) as client:
        yield client, tmp_path


def _record():
    return copy.deepcopy(load_records([SOURCE / "data/demo/train.jsonl"])[0])


def _upload(client, records):
    content = "\n".join(json.dumps(r, ensure_ascii=False) for r in records).encode("utf-8")
    return client.post("/api/datasets", files={"file":("../../outside.jsonl",content,"application/jsonl")}, data={"title":"검토 전 데모"})


def _adapter(root, identity="candidate-a", revision="a"*40, model_id="Qwen/Qwen3-1.7B", tier="T2", eligible=True):
    path = root / "runs" / identity / "adapter"
    path.mkdir(parents=True)
    # Registry fixture only: no loader is called by these tests.
    (path / "adapter_model.safetensors").write_bytes(b"T0-registry-fixture-not-real-weights")
    (path / "adapter-manifest.json").write_text(json.dumps({
        "tier":tier, "base_revision":revision, "base_model_id":model_id}), encoding="utf-8")
    (path.parent / "manifest.json").write_text(json.dumps({
        "fixture_only":True, "status":"passed" if eligible else "bounded_partial",
        "reload":{"status":"passed" if eligible else "not_run"}}), encoding="utf-8")
    return identity


def _base(root):
    folder = root / ".local/models/text"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "model-manifest.json").write_text(json.dumps({"model_id":"Qwen/Qwen3-1.7B", "revision":"a"*40}))


def _wait_job(client, identity):
    for _ in range(200):
        result = client.get(f"/api/jobs/{identity}").json()
        if result["state"] in {"succeeded","failed","cancelled","blocked","interrupted"}:
            return result
        time.sleep(.01)
    raise AssertionError("T0 job fixture did not finish")


def test_upload_roundtrip_validation_and_unreviewed_audit(admin):
    client, root = admin
    result = _upload(client, [_record()])
    assert result.status_code == 201, result.text
    value = result.json()
    assert value["review_status"] == "uploaded_unreviewed"
    assert value["human_review"] == "not_reviewed"
    assert value["record_count"] == 1
    assert (root / ".local/datasets" / f"{value['id']}.jsonl").is_file()
    assert not (root / "outside.jsonl").exists()
    validated = client.post(f"/api/datasets/{value['id']}/validate")
    assert validated.status_code == 200
    assert validated.json()["sha256"] == value["sha256"]
    assert len(client.app.state.store.list("datasets")) == 1
    audit = client.app.state.store.list("audit")
    assert any(a["action"] == "dataset_upload" and a["entity_id"] == value["id"] for a in audit)


@pytest.mark.parametrize("kind", ["bad_json", "bad_utf8", "empty", "missing_rights", "duplicate", "false_production"])
def test_invalid_upload_has_no_persisted_dataset(admin, kind):
    client, root = admin
    record = _record()
    if kind == "bad_json":
        result = client.post("/api/datasets", files={"file":("data.jsonl",b"{broken")})
    elif kind == "bad_utf8":
        result = client.post("/api/datasets", files={"file":("data.jsonl",b"\xff\xfe")})
    else:
        if kind == "missing_rights":
            del record["source"]["rights_note"]
        if kind == "false_production":
            record["demo_only"] = False
        records = [] if kind == "empty" else [record,record] if kind == "duplicate" else [record]
        result = _upload(client, records)
    assert result.status_code == 422, result.text
    assert client.app.state.store.list("datasets") == []
    assert client.app.state.store.list("audit") == []


def test_upload_size_cap_and_unknown_validation(admin):
    client, root = admin
    response = client.post("/api/datasets", files={"file":("large.jsonl",b"x"*(5*1024*1024+1))})
    assert response.status_code == 413
    assert client.post("/api/datasets/unknown/validate").status_code == 404


def test_empty_runs_admin_endpoints_are_valid(admin):
    client, root = admin
    assert not (root / "runs").exists()
    assert client.get("/api/adapters").json() == {"adapters":[],"active_adapter":None,"history":[]}
    assert client.get("/api/evaluations").json()["reports"] == []
    dataset = client.get("/api/datasets").json()["datasets"][0]
    assert dataset["counts"] == {"test":12,"train":25,"validation":8}


def test_real_admin_selection_preserves_history_and_rolls_back(admin):
    client, root = admin
    _base(root)
    first, second = _adapter(root), _adapter(root, "candidate-b")
    assert client.post("/api/adapters/select", json={"adapter_id":first}).json()["active_adapter"] == first
    assert client.post("/api/adapters/select", json={"adapter_id":second}).json()["active_adapter"] == second
    rolled = client.post("/api/adapters/rollback")
    assert rolled.status_code == 200
    assert rolled.json()["active_adapter"] == first
    persisted = json.loads((root / ".local/model-selection.json").read_text())
    assert persisted["active_adapter"] == first
    assert len(client.app.state.store.list("audit")) == 3
    assert client.post("/api/adapters/select", json={"adapter_id":None}).json()["active_adapter"] is None


def test_selection_rejects_unknown_tiny_and_revision_mismatch(admin):
    client, root = admin
    _base(root)
    tiny = _adapter(root, "tiny", tier="T1")
    incompatible = _adapter(root, "other-revision", revision="b"*40)
    assert client.post("/api/adapters/select", json={"adapter_id":"../../unsafe"}).status_code == 404
    assert client.post("/api/adapters/select", json={"adapter_id":tiny}).status_code == 404
    assert client.post("/api/adapters/select", json={"adapter_id":incompatible}).status_code == 409
    assert not (root / ".local/model-selection.json").exists()


def test_selection_rejects_wrong_base_model_identity(admin):
    client, root = admin
    _base(root)
    incompatible = _adapter(root, "wrong-model", model_id="Another/Model")
    assert client.post("/api/adapters/select", json={"adapter_id":incompatible}).status_code == 409
    assert not (root / ".local/model-selection.json").exists()


def test_partial_training_adapter_cannot_be_selected(admin):
    client, root = admin
    _base(root)
    incomplete = _adapter(root, "unfinished", eligible=False)
    assert client.post("/api/adapters/select", json={"adapter_id":incomplete}).status_code == 409
    assert not (root / ".local/model-selection.json").exists()


def test_selection_conflicts_with_gpu_lease(admin):
    client, root = admin
    with GPULease(root / ".local", "test-existing-owner"):
        assert client.post("/api/adapters/select", json={"adapter_id":None}).status_code == 409
    assert not (root / ".local/model-selection.json").exists()


def test_training_is_idempotent_while_active_and_blocks_model_swap(admin, monkeypatch):
    client, root = admin
    import edu_tutor.models.runtime as runtime
    import edu_tutor.training.runner as runner
    entered, release = threading.Event(), threading.Event()
    calls = []

    def fake_training(config_path, model_path, output_dir, **kwargs):
        # T0 application contract only, explicitly not QLoRA evidence.
        calls.append(kwargs)
        entered.set()
        assert release.wait(4)
        return {"status":"passed","tier":"T0","fixture_only":True}

    monkeypatch.setattr(runtime, "model_status", lambda root: {"ready":True})
    monkeypatch.setattr(runner, "run_gpu_training", fake_training)
    body = {"profile":"smoke","request_id":"same-training-request","dataset_id":"demo"}
    first = client.post("/api/train", json=body)
    assert first.status_code == 202
    assert entered.wait(2)
    try:
        repeated = client.post("/api/train", json=body)
        assert repeated.status_code == 202
        assert repeated.json()["id"] == first.json()["id"]
        assert len(client.app.state.store.list("jobs")) == 1
        assert client.post("/api/train", json={**body,"request_id":"another-training-request"}).status_code == 409
        assert client.post("/api/adapters/select", json={"adapter_id":None}).status_code == 409
    finally:
        release.set()
    job = _wait_job(client, first.json()["id"])
    assert job["state"] == "succeeded" and job["result"]["tier"] == "T0"
    assert len(calls) == 1
    assert calls[0]["mode"] == "smoke" and calls[0]["cancel_event"] is not None


def test_training_requires_ready_local_model(admin, monkeypatch):
    client, root = admin
    import edu_tutor.models.runtime as runtime
    monkeypatch.setattr(runtime, "model_status", lambda root: {"ready":False})
    response = client.post("/api/train", json={"profile":"smoke","request_id":"missing-model-request"})
    assert response.status_code == 409
    assert client.app.state.store.list("jobs") == []


def test_evaluation_queued_once_cancellable_and_preserves_selection(admin, monkeypatch):
    client, root = admin
    import edu_tutor.models.runtime as runtime
    import edu_tutor.models.evaluate as evaluator
    entered = threading.Event()
    calls = []
    def fake_evaluation(root, output, adapter, *, cancel_event, job_id):
        calls.append((adapter, job_id))
        entered.set()
        assert cancel_event.wait(4)
        return {"status":"cancelled", "tier":"T0", "fixture_only":True}
    monkeypatch.setattr(runtime, "model_status", lambda root: {"ready":True})
    monkeypatch.setattr(evaluator, "run_evaluation", fake_evaluation)
    body = {"run_id":"base", "request_id":"frozen-evaluation-request"}
    first = client.post("/api/evaluations", json=body)
    assert first.status_code == 202
    identity = first.json()["id"]
    assert entered.wait(2)
    try:
        assert client.post("/api/evaluations", json=body).json()["id"] == identity
        assert client.post("/api/evaluations", json={**body,"request_id":"second-evaluation-request"}).status_code == 409
        assert client.post("/api/adapters/select", json={"adapter_id":None}).status_code == 409
    finally:
        assert client.post(f"/api/jobs/{identity}/cancel").status_code == 200
    assert _wait_job(client, identity)["state"] == "cancelled"
    assert calls == [(None, identity)]
    assert not (root / ".local/model-selection.json").exists()


def test_evaluation_rejects_unregistered_and_incomplete_adapter(admin, monkeypatch):
    client, root = admin
    import edu_tutor.models.runtime as runtime
    monkeypatch.setattr(runtime, "model_status", lambda root: {"ready":True})
    incomplete = _adapter(root, "unfinished-eval", eligible=False)
    for identity in ["../../outside", incomplete]:
        response = client.post("/api/evaluations", json={"run_id":identity,"request_id":"rejected-eval-request"})
        assert response.status_code == 422
    assert client.app.state.store.list("jobs") == []


def test_rubric_is_append_only_and_bound_to_actual_report_item(admin):
    client, root = admin
    report_path = root / "runs/eval-fixture/evaluation.json"
    report_path.parent.mkdir(parents=True)
    raw = json.dumps({"status":"completed", "items":[{"id":"test-1","text":"T0 fixture answer"}]}).encode()
    report_path.write_bytes(raw)
    body = {"run_id":"eval-fixture","item_id":"test-1", "scores":{"correctness":1,"clarity":2,"grounding":3},"comment":"T0 test input, not a human review"}
    for comment in ["first T0 test input", "second T0 test input"]:
        response = client.post("/api/evaluations/reviews", json={**body,"comment":comment})
        assert response.status_code == 201
        assert response.json()["scope"] == "user_rubric_not_expert_certification"
    assert len(client.get("/api/evaluations/reviews").json()["reviews"]) == 2
    assert report_path.read_bytes() == raw
    assert client.post("/api/evaluations/reviews", json={**body,"item_id":"missing"}).status_code == 409
    assert client.post("/api/evaluations/reviews", json={**body,"run_id":"../outside"}).status_code == 422
    assert client.post("/api/evaluations/reviews", json={**body,"scores":{"correctness":6,"clarity":2,"grounding":3}}).status_code == 422


def test_report_questions_require_exact_dataset_hash(admin):
    import hashlib
    client, root = admin
    test_path = root / "data/demo/test.jsonl"
    record = json.loads(test_path.read_text(encoding="utf-8").splitlines()[0])
    for ident, digest in [("matching",hashlib.sha256(test_path.read_bytes()).hexdigest()),("stale","0"*64)]:
        path = root / "runs" / ident / "evaluation.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"dataset_sha256":digest,"items":[{"id":record["id"],"text":"T0 fixture"}]}))
    reports = {item["run_id"]:item["report"] for item in client.get("/api/evaluations").json()["reports"]}
    assert reports["matching"]["items"][0]["question"] == next(m["content"] for m in record["messages"] if m["role"] == "user")
    assert "question" not in reports["stale"]["items"][0]
    assert "question" not in json.loads((root / "runs/matching/evaluation.json").read_text())["items"][0]
