"""CPU API recovery keeps failed records and cannot invoke text/TTS workers."""
import copy
import json

import pytest

from test_phase2_backend import client, problem


def seed(client):
    store = client.app.state.store
    p = problem("write_sql")
    p["raw_text"] = "전체 행 수와 score가 NULL이 아닌 행 수를 차례대로 구해 줘."
    raw = json.dumps({"sql": "SELECT COUNT(*), SUM(score IS NOT NULL) FROM exam_result",
                      "explanation": "COUNT(*)는 NULL이 아닌 행만 셉니다."}, ensure_ascii=False)
    session = {"id": "saved-session", "generation_epoch": 1}
    question = {"id": "saved-user", "role": "user", "session_id": session["id"],
                "request_id": "original-request", "content": p["raw_text"]}
    answer = {"id": "saved-answer", "role": "assistant", "session_id": session["id"],
        "request_id": "original-request", "generation_epoch": 1, "verification_mode": "tools",
        "raw_model_response": raw, "model_attempts": [{"attempt": 0, "text": raw, "incomplete": None}],
        "generation_snapshot": {"finish_reason": "eos", "model_load_seconds": 42},
        "content": "확인 필요: 집계 설명 미지원", "problem": p, "original_problem": p,
        "evidence": {"status": "stopped"}, "sources": [], "latency": {"request_to_verified_core_seconds": 99}}
    lesson = {"id": "saved-failed", "source_message_id": answer["id"], "is_demo": False,
        "problem": p, "original_problem": p, "plan": None, "status": "verification_stopped",
        "fallback_text": answer["content"], "evidence": answer["evidence"], "valid": True,
        "speech_allowed": False, "generation_epoch": 0}
    for table, value in (("sessions", session), ("messages", question), ("messages", answer), ("lessons", lesson)):
        store.put(table, value)
    return store, answer, lesson


def test_reprocess_is_append_only_idempotent_and_never_calls_workers(client, monkeypatch):
    from edu_tutor.models import runtime
    from edu_tutor.speech import provider
    def forbidden(*args, **kwargs):
        raise AssertionError("Saved recovery must not call a worker")
    monkeypatch.setattr(runtime, "generate", forbidden)
    monkeypatch.setattr(provider, "prepare_batch", forbidden)
    store, old_answer, old_lesson = seed(client)
    before = copy.deepcopy({name: store.list(name) for name in ("sessions", "messages", "lessons", "jobs")})
    response = client.post("/api/lessons/saved-failed/reprocess", json={"request_id": "recovery-one"})
    assert response.status_code == 201, response.text
    new = response.json()
    assert new["id"] != old_lesson["id"] and new["source_message_id"] != old_answer["id"]
    assert new["status"] == "verified_tool_plan" and new["valid"] and new["speech_allowed"]
    assert len(new["plan"]["steps"]) == 2 and new["evidence"]["result"]["rows"] == [[3, 2]]
    assert new["source_session_id"] == "saved-session" and new["speech_binding_fingerprint"]
    derived = store.get("messages", new["source_message_id"])
    assert derived["raw_model_response"] == old_answer["raw_model_response"]
    assert derived["problem"] == old_answer["problem"] and derived["model_attempts"] == old_answer["model_attempts"]
    assert derived["generation_snapshot"] == old_answer["generation_snapshot"] and "latency" not in derived
    assert derived["reprocessing"]["new_model_calls"] == 0
    assert derived["reprocessing"]["generation_snapshot_is_historical"]
    assert "NULL이 아닌 행만 셉니다" not in " ".join(s["speech"] for s in new["plan"]["steps"])
    for table, rows in before.items():
        for row in rows:
            assert store.get(table, row["id"]) == row
    assert store.list("jobs") == []
    sizes = {name: len(store.list(name)) for name in ("messages", "lessons", "audit")}
    repeat = client.post("/api/lessons/saved-failed/reprocess", json={"request_id": "recovery-one"})
    assert repeat.status_code == 201 and repeat.json()["id"] == new["id"]
    assert {name: len(store.list(name)) for name in sizes} == sizes
    assert not (store.root / "runs/phase2/current/resource-budget.json").exists()


@pytest.mark.parametrize("failure", ["unconfirmed", "incomplete", "mismatched_problem", "model_only", "missing_question"])
def test_reprocess_preserves_safety_boundaries(client, failure):
    store, answer, lesson = seed(client)
    if failure == "unconfirmed":
        answer["problem"]["confirmed"] = False
        lesson["problem"]["confirmed"] = False
    elif failure == "incomplete":
        answer["model_attempts"][0]["incomplete"] = "token limit"
    elif failure == "mismatched_problem":
        lesson["problem"] = copy.deepcopy(lesson["problem"])
        lesson["problem"]["revision"] += 1
    elif failure == "model_only":
        answer["verification_mode"] = "model_only"
    else:
        store.delete("messages", "saved-user")
    store.put("messages", answer)
    store.put("lessons", lesson)
    before = copy.deepcopy(lesson)
    r = client.post("/api/lessons/saved-failed/reprocess", json={"request_id": failure})
    if failure == "unconfirmed":
        assert r.status_code == 201 and r.json()["plan"] is None and not r.json()["speech_allowed"]
        assert client.post("/api/lessons/"+r.json()["id"]+"/speech", json={}).status_code == 409
    else:
        assert r.status_code == 422, r.text
        assert len(store.list("lessons")) == 1
    assert store.get("lessons", "saved-failed") == before


def test_reprocess_rejects_client_raw_sql_and_requires_auth(client):
    seed(client)
    path = "/api/lessons/saved-failed/reprocess"
    assert client.post(path, json={"request_id": "x", "sql": "SELECT 99"}).status_code == 422
    assert client.post(path, json={"request_id": "x"}, headers={"Authorization": "Bearer wrong"}).status_code == 401
