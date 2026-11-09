from __future__ import annotations

import copy
import io
import json
import sys
import threading
import time
import types

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from edu_tutor.api import create_app
from edu_tutor.api.app import recorded_validation
from edu_tutor.evaluation.sql_sandbox import compare_results, execute_sql, extract_sql
from edu_tutor.jobs.lease import GPULease, LeaseBusy
from edu_tutor.jobs.manager import JobManager
from edu_tutor.jobs.inspection import active_gpu_lease, job_view
from edu_tutor.lessons.plans import checked_demo_plan, demo_plan, scene_at, validate_plan
from edu_tutor.retrieval.index import DocumentIndex
from edu_tutor.storage.db import Store, new_id, utcnow
from edu_tutor.vision.conditions import check_transcription, missing_condition_warnings


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path)
    token = (tmp_path / ".local" / "auth-token").read_text()
    with TestClient(app, base_url="http://127.0.0.1:8000", headers={"Authorization": f"Bearer {token}"}) as value:
        yield value


def wait_job(client, job_id):
    for _ in range(300):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in {"succeeded", "failed", "cancelled", "interrupted", "blocked"}:
            return job
        time.sleep(.01)
    raise AssertionError("Job did not complete")


def png():
    output = io.BytesIO()
    Image.new("RGB", (50, 30), "white").save(output, "PNG")
    return output.getvalue()


def test_auth_origin_and_host(client):
    assert client.get("/api/health", headers={"Authorization": ""}).status_code == 200
    assert client.get("/api/sessions", headers={"Authorization": ""}).status_code == 401
    assert client.post("/api/sessions", json={}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/sessions", headers={"Host": "evil.example"}).status_code == 400
    assert client.options("/api/sessions", headers={"Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization"}).status_code == 200
    assert client.get("/api/openapi.json", headers={"Authorization": ""}).status_code == 401


def test_static_module_mime_and_strict_csp(tmp_path):
    import mimetypes
    folder = tmp_path / "web/dist/assets"
    folder.mkdir(parents=True)
    (folder / "main.js").write_text("export const value = 1;", encoding="utf-8")
    mimetypes.add_type("text/plain", ".js")
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        result = client.get("/assets/main.js")
        assert result.headers["content-type"].startswith("application/javascript")
        assert "font-src 'self' data:" in result.headers["content-security-policy"]
        assert "unsafe-eval" not in result.headers["content-security-policy"]


def test_capabilities_reads_recorded_stage_evidence_without_global_inference(tmp_path):
    assert recorded_validation(tmp_path)["status"] == "not_recorded"
    path = tmp_path / "STATUS.json"
    path.write_text("invalid", encoding="utf-8")
    assert recorded_validation(tmp_path)["status"] == "not_recorded"
    status = {"overall_status": "PARTIAL", "stages": {"text": {"validation": {"T2": "pass"}},
              "vision": {"validation": {"T2": "not_run"}}}, "evidence": [{"artifact": "runs/test/result.json"}]}
    path.write_text(json.dumps(status), encoding="utf-8")
    reported = recorded_validation(tmp_path)
    assert reported["stages"] == status["stages"] and reported["evidence"] == status["evidence"]
    assert "T2" not in reported and reported["human_review"] == "not_reviewed"
    status["stages"]["vision"]["validation"]["T2"] = "fail"
    path.write_text(json.dumps(status), encoding="utf-8")
    assert recorded_validation(tmp_path)["stages"]["vision"]["validation"]["T2"] == "fail"


def test_store_preservation_restart_and_orphan(tmp_path):
    store = Store(tmp_path)
    session = {"id": new_id(), "title": "기록 보존", "generation_epoch": 0, "created_at": utcnow()}
    store.put("sessions", session)
    store.put("jobs", {"id": "orphan", "state": "running", "kind": "chat"})
    app = create_app(tmp_path)
    assert app.state.store.get("sessions", session["id"]) == session
    assert app.state.store.get("jobs", "orphan")["state"] == "interrupted"
    app.state.jobs.close()


def test_duplicate_api_does_not_interrupt_owner(tmp_path):
    first = create_app(tmp_path)
    store = first.state.store
    store.put("jobs", {"id": "owned-running", "state": "running", "kind": "chat"})
    with pytest.raises(LeaseBusy, match="API 서버"):
        create_app(tmp_path)
    assert store.get("jobs", "owned-running")["state"] == "running"
    first.state.jobs.close()
    second = create_app(tmp_path)
    assert second.state.store.get("jobs", "owned-running")["state"] == "interrupted"
    second.state.jobs.close()


def test_shutdown_blocks_late_worker_state_overwrite(tmp_path):
    store = Store(tmp_path)
    manager = JobManager(store)
    entered, release, exited = threading.Event(), threading.Event(), threading.Event()
    def slow(ident, cancel):
        entered.set()
        release.wait(3)
        manager.update(ident, state="succeeded")
        exited.set()
        return {"late": True}
    job = manager.submit("test_fixture", slow)
    assert entered.wait(2)
    manager.close()
    reopened = JobManager(store)
    release.set()
    assert exited.wait(2)
    assert store.get("jobs", job["id"])["state"] == "interrupted"
    reopened.close()


def test_real_contract_fixture_chat_idempotency(client, monkeypatch):
    # This explicit T0 test double is not model-inference evidence.
    module = types.ModuleType("edu_tutor.models.runtime")
    module.generate = lambda *args, **kwargs: iter(["COUNT(*)는 ", "모든 행을 셉니다."])
    monkeypatch.setitem(sys.modules, "edu_tutor.models.runtime", module)
    session = client.post("/api/sessions", json={"title": "NULL 실습"}).json()
    path = f"/api/sessions/{session['id']}/messages"
    body = {"content": "COUNT(*)?", "request_id": "same-request"}
    first = client.post(path, json=body)
    assert first.status_code == 202
    second = client.post(path, json=body)
    assert first.json() == second.json()
    assert wait_job(client, first.json()["job_id"])["state"] == "succeeded"
    messages = client.get(path).json()
    assert len(messages) == 2
    assert messages[1]["content"] == "COUNT(*)는 모든 행을 셉니다."
    lesson = client.post("/api/lessons", json={"session_id": session["id"], "message_id": messages[1]["id"]}).json()
    assert lesson["status"] == "text_fallback"
    assert lesson["fallback_text"] == messages[1]["content"]
    assert lesson["plan"] is None


def test_chat_preserves_actual_worker_generation_snapshot(client, monkeypatch):
    # Explicit CPU contract double: this is not real model inference evidence.
    import edu_tutor.models.runtime as runtime
    snapshot = {"source": "worker_metadata", "model_id": "fixture-model", "revision": "fixture-sha",
                "adapter_id": "adapter-at-generation", "finish_reason": "eos", "input_tokens": 12,
                "output_tokens": 4, "timestamp": "2026-10-25T00:00:00+00:00"}
    def generate(*args, metadata_out=None, **kwargs):
        yield "실제 작업 메타데이터 계약"
        metadata_out.update(snapshot)
    monkeypatch.setattr(runtime, "generate", generate)
    session = client.post("/api/sessions", json={}).json()
    path = f"/api/sessions/{session['id']}/messages"
    submitted = client.post(path, json={"content": "질문"}).json()
    job = wait_job(client, submitted["job_id"])
    assert job["state"] == "succeeded"
    assert job["result"]["generation_snapshot"] == snapshot
    assert client.get(path).json()[-1]["generation_snapshot"] == snapshot
    # A later selection cannot rewrite the completed message's provenance.
    selection = client.app.state.store.local / "model-selection.json"
    selection.write_text('{"active_adapter":"changed-later","history":[]}', encoding="utf-8")
    assert client.get(path).json()[-1]["generation_snapshot"] == snapshot


def test_runtime_snapshot_uses_worker_event_and_resolved_adapter(tmp_path, monkeypatch, nf4_inference_fixture):
    import edu_tutor.models.runtime as runtime
    import edu_tutor.models.registry as registry
    adapter_path = str(tmp_path / "runs/actual-adapter/adapter")
    monkeypatch.setattr(runtime, "model_status", lambda root: {"ready": True})
    monkeypatch.setattr(registry, "resolve_adapter", lambda *args: adapter_path)
    monkeypatch.setattr(registry, "adapters", lambda root: [{"id": "actual-adapter", "path": adapter_path}])
    def worker(payload, **kwargs):
        assert payload["adapter"] == adapter_path
        yield {"type": "delta", "text": "답변"}
        yield {"type": "metadata", "model_id": "loaded-model", "revision": "loaded-sha",
               "requested_precision": "nf4", "inference": nf4_inference_fixture,
               "eos_token_ids": [151645, 151643],
               "adapter": adapter_path, "finish_reason": "eos", "input_tokens": 10, "output_tokens": 2,
               "timestamp": "fixture-time", "text": "must-not-copy", "gpu": "must-not-copy"}
    monkeypatch.setattr(runtime, "run_worker", worker)
    snapshot = {}
    output = runtime.generate([{"role": "user", "content": "질문"}], root=tmp_path, metadata_out=snapshot)
    assert next(output) == "답변" and snapshot == {}
    assert list(output) == []
    assert snapshot == {"source": "worker_metadata", "model_id": "loaded-model", "revision": "loaded-sha",
                        "adapter_id": "actual-adapter", "finish_reason": "eos", "input_tokens": 10,
                        "output_tokens": 2, "timestamp": "fixture-time", "requested_precision": "nf4",
                        "eos_token_ids": [151645, 151643],
                        "inference": nf4_inference_fixture}


def test_cancellation_discards_stale_response(client, monkeypatch):
    entered = threading.Event()
    module = types.ModuleType("edu_tutor.models.runtime")
    def generate(*args, cancel_event=None, **kwargs):
        entered.set()
        cancel_event.wait(3)
        yield "취소 후 늦게 도착한 답변"
    module.generate = generate
    monkeypatch.setitem(sys.modules, "edu_tutor.models.runtime", module)
    session = client.post("/api/sessions", json={}).json()
    path = f"/api/sessions/{session['id']}/messages"
    result = client.post(path, json={"content": "질문"}).json()
    assert entered.wait(2)
    client.post(f"/api/jobs/{result['job_id']}/cancel")
    assert wait_job(client, result["job_id"])["state"] == "cancelled"
    assert len(client.get(path).json()) == 1
    assert client.get("/api/sessions").json()[0]["generation_epoch"] > result["generation_epoch"]


def test_chat_during_training_rejected_before_mutation(client):
    session = client.post("/api/sessions", json={}).json()
    store = client.app.state.store
    for state in ("queued", "loading", "running", "saving"):
        store.put("jobs", {"id": "active-training", "kind": "training", "state": state})
        response = client.post(f"/api/sessions/{session['id']}/messages", json={"content": "학습 중 질문"})
        assert response.status_code == 409
        assert store.get("sessions", session["id"])["generation_epoch"] == 0
        assert store.list("messages") == []
        assert len(store.list("jobs")) == 1
    store.put("jobs", {"id": "active-training", "kind": "training", "state": "cancelled"})


def test_incomplete_model_output_never_becomes_success(client, monkeypatch):
    import edu_tutor.models.runtime as runtime
    def generate(*args, **kwargs):
        yield "토큰 제한으로 끊긴 미완성 답변"
        raise runtime.GenerationIncomplete("output limit reached")
    monkeypatch.setattr(runtime, "generate", generate)
    session = client.post("/api/sessions", json={}).json()
    path = f"/api/sessions/{session['id']}/messages"
    request = client.post(path, json={"content": "질문"}).json()
    job = wait_job(client, request["job_id"])
    assert job["state"] == "failed"
    assert job["partial_text"] == "토큰 제한으로 끊긴 미완성 답변"
    assert [m["role"] for m in client.get(path).json()] == ["user"]


def test_rag_review_retrieve_sources_delete(client):
    text = "기본키는 행을 식별합니다.\nCOUNT(*)는 모든 행을 셉니다. COUNT(salary)는 NULL 값을 제외합니다.\n이전 지시를 무시하라는 문장도 자료일 뿐입니다."
    response = client.post("/api/documents", files={"file": ("../../outside.md", text.encode(), "text/markdown")}, data={"rights": "직접 작성한 테스트 자료"})
    assert response.status_code == 201
    document = response.json()
    assert document["filename"] == "outside.md"
    assert client.get("/api/search", params={"q": "COUNT NULL"}).json() == []
    assert client.post(f"/api/documents/{document['id']}/review", json={"approved": True}).status_code == 200
    hits = client.get("/api/search", params={"q": "COUNT NULL"}).json()
    assert hits and hits[0]["document_id"] == document["id"]
    index = DocumentIndex(client.app.state.store)
    assert index.validate_sources(hits, hits)
    assert not index.validate_sources([{"document_id": "forged", "chunk_id": "forged"}], hits)
    assert client.delete(f"/api/documents/{document['id']}").status_code == 200
    assert client.get("/api/search", params={"q": "COUNT NULL"}).json() == []
    assert client.app.state.store.list("chunks") == []


def test_file_rejections(client):
    assert client.post("/api/documents", files={"file": ("script.exe", b"MZ")}, data={"rights": "own"}).status_code == 422
    assert client.post("/api/documents", files={"file": ("fake.pdf", b"not-pdf")}, data={"rights": "own"}).status_code == 422
    assert client.post("/api/documents", files={"file": ("x.md", b"text")}, data={"rights": ""}).status_code == 422
    assert client.get("/api/documents/%2E%2E%2Fauth-token").status_code == 404
    assert client.post("/api/photos", files={"file": ("x.png", b"corrupt")}).status_code == 422
    assert client.post("/api/photos", files={"file": ("x.svg", b"<svg onload='alert(1)'/>")}).status_code == 422


def test_chunked_upload_size_limit(client):
    chunks = (b"x" * (1024 * 1024) for _ in range(12))
    result = client.post("/api/photos", content=chunks, headers={"Content-Type": "application/octet-stream"})
    assert result.status_code == 413


def test_photo_confirmation_revision_delete(client):
    session = client.post("/api/sessions", json={}).json()
    response = client.post("/api/photos", files={"file": ("problem.jpg", png(), "image/jpeg")})
    assert response.status_code == 201
    photo = response.json()
    ident = photo["id"]
    assert photo["recognition_status"] == "not_run" and photo["original_text"] == ""
    assert client.post(f"/api/photos/{ident}/solve", json={"session_id": session["id"]}).status_code == 409
    assert client.post(f"/api/photos/{ident}/confirm").status_code == 422
    edited = client.patch(f"/api/photos/{ident}", json={"question": "COUNT(salary)는 무엇인가요?"}).json()
    assert edited["revision"] == 2 and not edited["confirmed"]
    assert client.post(f"/api/photos/{ident}/confirm").json()["confirmed"]
    edited = client.patch(f"/api/photos/{ident}", json={"question": "COUNT(*)로 수정합니다."}).json()
    assert edited["revision"] == 3 and not edited["confirmed"]
    assert edited["history"][-1]["confirmed"]
    assert client.post(f"/api/photos/{ident}/solve", json={"session_id": session["id"]}).status_code == 409
    assert client.get(photo["image_url"]).headers["content-type"] == "image/png"
    assert client.delete(f"/api/photos/{ident}").status_code == 200
    assert client.get(photo["image_url"]).status_code == 404


@pytest.mark.parametrize("text, expected", [
    ("SELECT name FROM employees WHERE salary >= 1000;", False),
    ("SELECT name FROM employees\nWHERE salary >=\n1000;", False),
    ("SELECT name FROM employees\nWHERE name =\n'Kim';", False),
    ("비교 연산자 예시: >=", False),
    ("SELECT name FROM employees\nWHERE salary >=", True),
    ("SELECT name FROM employees\nWHERE salary =\nORDER BY name;", True),
    ("SELECT name FROM employees\nWHERE salary <>;", True),
    ("[이 아래의 조건과 선택지가 잘려 있습니다]", True),
])
def test_transcription_format_check_complete_and_cut_conditions(text, expected):
    assert bool(missing_condition_warnings(text)) is expected
    raw = {"original_text": text, "question": text, "missing_conditions": []}
    candidate = check_transcription(raw)
    assert raw["missing_conditions"] == []
    assert candidate["original_text"] == text and candidate["question"] == text
    assert all(warning.startswith("자동 형식 점검, 원문 확인 필요: ") for warning in candidate["missing_conditions"])
    assert check_transcription(candidate) == candidate


def test_incomplete_photo_blocks_solve_until_corrected_and_reconfirmed(client, monkeypatch):
    import edu_tutor.models.vision_runtime as vision
    import edu_tutor.models.runtime as runtime
    original = "SELECT name FROM employees\nWHERE salary >=\n[이 아래의 조건과 선택지가 잘려 있습니다]"
    monkeypatch.setattr(vision, "transcribe", lambda *args, **kwargs: {
        "original_text": original, "question": original, "missing_conditions": [], "revision": "fixture-sha"})
    monkeypatch.setattr(runtime, "generate", lambda *args, **kwargs: iter(["CPU 테스트 응답"]))
    session = client.post("/api/sessions", json={}).json()
    photo = client.post("/api/photos", files={"file": ("ordinary-name.png", png())}).json()
    path = f"/api/photos/{photo['id']}"
    job = client.post(path + "/transcribe").json()
    assert wait_job(client, job["job_id"])["state"] == "succeeded"
    candidate = client.get(path).json()
    assert candidate["original_text"] == original
    assert len(candidate["missing_conditions"]) == 2
    assert candidate["recognition_format_check"]["recognition_accuracy"] == "not_established"
    assert client.post(path + "/confirm").json()["confirmed"]
    jobs_before = len(client.get("/api/jobs").json())
    rejected = client.post(path + "/solve", json={"session_id": session["id"]})
    assert rejected.status_code == 409 and "빠진 조건" in rejected.json()["detail"]
    assert len(client.get("/api/jobs").json()) == jobs_before
    assert client.get(f"/api/sessions/{session['id']}/messages").json() == []
    client.patch(path, json={"missing_conditions": []})
    client.post(path + "/confirm")
    assert client.post(path + "/solve", json={"session_id": session["id"]}).status_code == 409
    corrected = client.patch(path, json={"question": "SELECT name FROM employees WHERE salary >= 1000;",
                                        "missing_conditions": []}).json()
    assert not corrected["confirmed"] and corrected["original_text"] == original
    assert client.post(path + "/solve", json={"session_id": session["id"]}).status_code == 409
    client.post(path + "/confirm")
    submitted = client.post(path + "/solve", json={"session_id": session["id"]})
    assert submitted.status_code == 202
    assert wait_job(client, submitted.json()["job_id"])["state"] == "succeeded"
    assert client.get(path).json()["original_text"] == original


def test_gpu_lease_exclusive_and_recovers(tmp_path):
    (tmp_path / "gpu-lease.json").write_text('{"pid":999999,"state":"held"}')
    with GPULease(tmp_path, "first"):
        with pytest.raises(LeaseBusy):
            with GPULease(tmp_path, "second"):
                pass
        assert json.loads((tmp_path / "gpu-lease.json").read_text())["job_id"] == "first"
    with GPULease(tmp_path, "third"):
        assert json.loads((tmp_path / "gpu-lease.json").read_text())["job_id"] == "third"


def test_gpu_lease_identity_and_bounded_training_metrics(tmp_path):
    with GPULease(tmp_path, "visible"):
        assert active_gpu_lease(tmp_path)["active"] is True
        metadata = json.loads((tmp_path / "gpu-lease.json").read_text())
        metadata["process_start"] -= 100
        (tmp_path / "gpu-lease.json").write_text(json.dumps(metadata))
        assert active_gpu_lease(tmp_path)["active"] is False
    assert active_gpu_lease(tmp_path)["active"] is False
    folder = tmp_path / "runs/train-fixture"
    folder.mkdir(parents=True)
    (folder / "metrics.jsonl").write_text('{"step":1,"max_steps":5,"loss":2.4}\n{"step":2,"max_steps":5,"loss":1.8,"current_vram_bytes":1234,"peak_vram_bytes":2345,"actual_microbatches":8,"samples_processed":8,"samples_per_second":0.25,"private_field":"omit"}\n{"partial":', encoding="utf-8")
    job = {"id": "fixture", "kind": "training", "state": "running", "artifact": "runs/train-fixture", "progress": 0}
    response = job_view(tmp_path, job)
    assert response["latest_metrics"]["step"] == 2 and response["latest_metrics"]["loss"] == 1.8
    assert response["latest_metrics"]["current_vram_bytes"] == 1234
    assert response["latest_metrics"]["peak_vram_bytes"] == 2345
    assert response["latest_metrics"]["actual_microbatches"] == 8
    assert response["latest_metrics"]["samples_processed"] == 8
    assert response["latest_metrics"]["samples_per_second"] == .25
    assert "private_field" not in response["latest_metrics"]
    assert response["progress"] == .4
    assert len(response["metrics"]) == 2
    assert "metrics_error" in job_view(tmp_path, {**job, "artifact": "../outside"})


FIXTURE = {"tables": [{"name": "sample", "columns": [{"name": "value", "type": "INTEGER"}], "rows": [[1], [1], [None]]}]}


def test_sql_execution_null_and_duplicates():
    actual = execute_sql("SELECT COUNT(*) AS all_rows, COUNT(value) AS non_null FROM sample", FIXTURE)
    assert actual["status"] == "executed"
    assert actual["rows"] == [[3, 2]]
    actual = execute_sql("SELECT value FROM sample", FIXTURE)
    expected = {"columns": ["value"], "rows": [[None], [1], [1]], "row_order": "unordered"}
    assert compare_results(actual, expected)
    assert not compare_results(actual, {**expected, "rows": [[None], [None], [1]]})
    assert not compare_results(actual, {**expected, "row_order": "ordered"})
    assert not compare_results(actual, {**expected, "rows": [[None], ["1"], ["1"]]})


@pytest.mark.parametrize("sql", ["DELETE FROM sample", "ATTACH DATABASE 'x' AS x", "PRAGMA database_list", "SELECT load_extension('x')", "SELECT readfile('x')", "SELECT value FROM sample; DELETE FROM sample;", "WITH x AS (SELECT 1) DELETE FROM sample", "SELECT randomblob(1000000000)"])
def test_sql_unsafe_queries_rejected(sql):
    assert execute_sql(sql, FIXTURE)["status"] == "error"


def test_sql_bounds_and_dialect():
    assert execute_sql("WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n) SELECT sum(x) FROM n", FIXTURE, timeout=.01)["status"] == "timeout"
    assert execute_sql("SELECT value FROM sample", FIXTURE, max_rows=1)["status"] == "error"
    assert execute_sql("SELECT * FROM dual", FIXTURE, dialect="oracle")["status"] == "not_executed"


def test_sql_parse_contract():
    assert extract_sql('{"sql":"SELECT 1", "explanation":"example"}') == "SELECT 1"
    assert extract_sql("```sql\nSELECT 1\n```") == "SELECT 1"
    with pytest.raises(ValueError, match="ambiguous_parse"):
        extract_sql("```sql\nSELECT 1\n```\n```sql\nSELECT 2\n```")


def test_lesson_schema_and_scene_replay(client):
    plan = demo_plan()
    assert plan["provenance"] == "demo_fixture"
    scene = scene_at(plan, len(plan["steps"]) - 1)
    assert scene == scene_at(copy.deepcopy(plan), len(plan["steps"]) - 1)
    broken = copy.deepcopy(plan)
    broken["steps"][0]["board_actions"][0]["type"] = "javascript"
    with pytest.raises(ValueError):
        validate_plan(broken)
    assert client.get("/api/lessons/demo").json()["is_demo"]


def test_demo_fixture_executes_sql_and_cross_checks_board():
    plan, report = checked_demo_plan()
    assert report["machine_verification"] == "pass"
    assert report["execution"]["status"] == "executed"
    assert report["execution"]["columns"] == ["dept", "people", "salary_count", "salary_sum", "salary_avg"]
    assert report["execution"]["rows"] == [["개발", 3, 2, 1500, 750], ["운영", 3, 2, 1200, 600]]
    assert report["sql_expected_match"] and report["final_board_matches_execution"]
    assert report["original_table_matches_fixture"] and report["displayed_sql_matches_fixture"]
    assert plan["verification"]["status"] == "fixture_sql_checked"
    assert report["human_review"] == "not_reviewed" and report["model_inference"] == "not_run"


def test_demo_mismatch_downgrades_without_correcting_user_content():
    plan = demo_plan()
    plan["steps"][-1]["board_actions"][-1]["rows"][0][-1] = 999
    checked, report = checked_demo_plan(plan)
    assert report["machine_verification"] == "fail"
    assert not report["final_board_matches_execution"]
    assert checked["verification"]["status"] == "unverified"
    assert checked["steps"][-1]["board_actions"][-1]["rows"][0][-1] == 999
    assert "통과하지 못한" in checked["steps"][-1]["board_actions"][-1]["caption"]
    plan = demo_plan()
    plan["steps"][1]["board_actions"][0]["code"] = "SELECT 1;"
    checked, report = checked_demo_plan(plan)
    assert not report["displayed_sql_matches_fixture"]
    assert checked["verification"]["status"] == "unverified"


def test_demo_api_revalidates_and_preserves_prepared_audio(client):
    lesson = client.get("/api/lessons/demo").json()
    assert lesson["fixture_validation"]["machine_verification"] == "pass"
    lesson["audio_steps"] = [{"step_id": "s1", "provider": "T0_metadata_fixture"}]
    lesson["plan"]["steps"][-1]["board_actions"][-1]["rows"][0][-1] = 999
    client.app.state.store.put("lessons", lesson)
    checked = client.get("/api/lessons/demo-count-null").json()
    assert checked["plan"]["verification"]["status"] == "unverified"
    assert checked["audio_steps"] == lesson["audio_steps"]


def test_scene_clear_removes_only_dependent_highlights_and_arrows():
    plan = demo_plan()
    plan["steps"] = [
        {"id": "scene", "title": "연결", "speech": "세 요소를 연결합니다.", "board_actions": [
            *[{"type": "text", "element_id": key, "slot": "main", "text": key} for key in ("a", "b", "c")],
            {"type": "highlight", "target_element_id": "a", "style": "outline"},
            {"type": "highlight", "target_element_id": "b", "style": "outline"},
            {"type": "arrow", "element_id": "ab", "from_element_id": "a", "to_element_id": "b"},
            {"type": "arrow", "element_id": "bc", "from_element_id": "b", "to_element_id": "c"}],
         "gesture": {"kind": "point", "target_element_id": "b"}},
        {"id": "clear", "title": "지우기", "speech": "첫 요소를 지웁니다.", "board_actions": [{"type": "clear", "target": "a"}],
         "gesture": {"kind": "point", "target_element_id": "b"}}]
    scene = scene_at(plan, 1)
    assert set(scene["elements"]) == {"b", "c"}
    assert [item["target_element_id"] for item in scene["highlights"]] == ["b"]
    assert [item["element_id"] for item in scene["arrows"]] == ["bc"]
    assert scene == scene_at(copy.deepcopy(plan), 1)


def test_vision_result_never_confirms_and_preserves_concurrent_edit(client, monkeypatch):
    import edu_tutor.models.vision_runtime as vision
    entered, release = threading.Event(), threading.Event()
    def transcribe(*args, **kwargs):
        entered.set()
        release.wait(3)
        return {"question": "모델 전사 후보", "original_text": "모델 전사 후보", "sql": "", "tables": [],
                "choices": [], "unreadable_regions": [], "missing_conditions": [], "confirmed": True,
                "revision": "model-sha", "recognition_status": "candidate"}
    monkeypatch.setattr(vision, "transcribe", transcribe)
    photo = client.post("/api/photos", files={"file": ("x.png", png())}).json()
    job = client.post(f"/api/photos/{photo['id']}/transcribe").json()
    assert entered.wait(2)
    client.patch(f"/api/photos/{photo['id']}", json={"question": "사용자가 직접 수정한 원문"})
    release.set()
    done = wait_job(client, job["job_id"])
    assert done["result"]["discarded"]
    assert client.get(f"/api/photos/{photo['id']}").json()["question"] == "사용자가 직접 수정한 원문"
    job = client.post(f"/api/photos/{photo['id']}/transcribe").json()
    assert wait_job(client, job["job_id"])["state"] == "succeeded"
    updated = client.get(f"/api/photos/{photo['id']}").json()
    assert not updated["confirmed"]
    assert updated["revision"] == 3
    assert updated["recognition_model_revision"] == "model-sha"


def test_speech_job_contract_is_explicit_fixture(client, monkeypatch):
    import edu_tutor.speech.provider as speech
    audio_id = "a" * 64
    monkeypatch.setattr(speech, "prepare", lambda *args, **kwargs: {"audio_id": audio_id,
        "url": f"/api/audio/{audio_id}", "duration": 1.0, "provider": "test_double"})
    lesson = client.get("/api/lessons/demo").json()
    first = lesson["plan"]["steps"][0]["id"]
    result = client.post(f"/api/lessons/{lesson['id']}/speech", json={"step_id": first}).json()
    assert wait_job(client, result["job_id"])["state"] == "succeeded"
    saved = client.get(f"/api/lessons/{lesson['id']}/speech").json()
    # Job attachment is retained, but metadata-only fixtures are not playable
    # clips under the read-only cache validation contract.
    attached = client.app.state.store.get("lessons", lesson["id"])["audio_steps"]
    assert attached[0]["step_id"] == first and attached[0]["provider"] == "test_double"
    assert saved["steps"] == [] and saved["cache_misses"]
    assert client.get("/api/audio/../../auth-token").status_code == 404


def test_staged_lesson_generation_and_bounded_repair(tmp_path, monkeypatch):
    from edu_tutor.lessons.generation import generate_plan
    import edu_tutor.models.runtime as runtime
    outline = {"title": "COUNT 설명", "goal": "행 수와 값 수 구분", "steps": [{"title": "NULL 제외", "teaching_point": "NULL은 값 수에서 제외"}], "final_summary": "COUNT(*)와 COUNT(value)를 구분합니다."}
    step = {"speech": "COUNT(value)는 NULL 값을 제외합니다.", "board_actions": [{"type": "text", "element_id": "s1_main", "slot": "main", "text": "COUNT(value): NULL 제외"}], "gesture": {"kind": "explain", "target_element_id": "s1_main"}}
    outputs = iter(["invalid", json.dumps(outline), json.dumps(step)])
    calls = []
    def generate(*args, **kwargs):
        calls.append(args)
        yield next(outputs)
    monkeypatch.setattr(runtime, "generate", generate)
    result = generate_plan("실제 모델 답변", "COUNT의 차이?", lesson_id="l1", sources=[], root=tmp_path,
                           job_id="test", cancel_event=threading.Event())
    assert result["status"] == "structured_unverified"
    assert result["plan"]["provenance"] == "model_generated"
    assert result["generation"]["repair_requests"] == 1 and len(calls) == 3
    monkeypatch.setattr(runtime, "generate", lambda *args, **kwargs: iter(["invalid JSON"]))
    result = generate_plan("그대로 보존할 실제 답변", "질문", lesson_id="l2", sources=[], root=tmp_path,
                           job_id="test", cancel_event=threading.Event())
    assert result["plan"] is None
    assert result["fallback_text"] == "그대로 보존할 실제 답변"
    assert result["generation"]["repair_requests"] == 1
    def incomplete(*args, **kwargs):
        yield '{"title":"truncated'
        raise runtime.GenerationIncomplete("length limit")
    monkeypatch.setattr(runtime, "generate", incomplete)
    result = generate_plan("원래 답변 유지", "질문", lesson_id="l3", sources=[], root=tmp_path,
                           job_id="test", cancel_event=threading.Event())
    assert result["status"] == "text_fallback" and result["fallback_text"] == "원래 답변 유지"


def test_admin_selection_requires_reload_and_blocks_active_jobs(client):
    root = client.app.state.store.root
    model = root / ".local/models/text"
    model.mkdir(parents=True)
    (model / "model-manifest.json").write_text(json.dumps({"revision": "base-sha", "model_id": "fixture"}))
    run = root / "runs/test-adapter"
    adapter = run / "adapter"
    adapter.mkdir(parents=True)
    # This is metadata selection only; no fixture file is loaded as real weights.
    (adapter / "adapter_model.safetensors").write_bytes(b"T0 metadata fixture")
    (adapter / "adapter-manifest.json").write_text(json.dumps({"tier": "T2", "base_revision": "base-sha", "base_model_id": "fixture"}))
    (run / "manifest.json").write_text(json.dumps({"status": "failed", "reload": {"status": "not_run"}}))
    assert client.post("/api/adapters/select", json={"adapter_id": "test-adapter"}).status_code == 409
    (run / "manifest.json").write_text(json.dumps({"status": "passed", "reload": {"status": "passed"}}))
    selected = client.post("/api/adapters/select", json={"adapter_id": "test-adapter"})
    assert selected.status_code == 200 and selected.json()["active_adapter"] == "test-adapter"
    store = client.app.state.store
    store.put("jobs", {"id": "busy", "state": "running", "kind": "training"})
    assert client.post("/api/adapters/select", json={"adapter_id": None}).status_code == 409
    store.put("jobs", {"id": "busy", "state": "failed", "kind": "training"})
    assert client.post("/api/adapters/rollback").json()["active_adapter"] is None
    assert any(entry["action"] == "adapter_rollback" for entry in store.list("audit"))
