"""Isolated CPU API/DB flow; runtime double, no text or audio model execution."""
import copy
import json

from test_phase2_backend import client, answer, make_lesson, wait
from edu_tutor.problems.models import normalize_problem
from edu_tutor.lessons.plans import scene_at


def test_requested_comparison_persists_through_real_api_and_source_binding(client, monkeypatch):
    import edu_tutor.models.runtime as runtime
    sql = "SELECT item, measure FROM samples WHERE measure >= 0 ORDER BY measure DESC, position ASC"
    raw = json.dumps({"sql": sql, "explanation": "검증용 틀린 원시 설명: NULL은 숫자 0이다."}, ensure_ascii=False)
    calls = []
    def fake(*args, **kwargs):
        calls.append(args)
        yield raw
    monkeypatch.setattr(runtime, "generate", fake)
    problem = normalize_problem({"task_kind": "write_sql", "confirmed": True,
        "raw_text": "출력: item, measure; 행 조건: measure >= 0; 정렬: measure DESC, position ASC",
        "tables": [{"name": "samples", "columns": [{"name": "item", "type": "TEXT"},
            {"name": "measure", "type": "INTEGER"}, {"name": "position", "type": "INTEGER"}],
            "rows": [["v", 0, 3], ["w", None, 1], ["x", 9, 2]]}]})
    session, source = answer(client, problem["raw_text"], problem)
    original = make_lesson(client, session, source)
    saved_original = copy.deepcopy(original["plan"])
    table = source["evidence"]["working_tables"][0]
    context = {"lesson_id": original["id"], "step": 1, "problem_revision": source["problem"]["revision"],
        "selected_cell": {"table_element_id": table["id"], "row_id": table["row_ids"][0],
            "column_id": table["column_ids"][1], "cell_id": table["cell_ids"][0][1]},
        "_verified_logical_stage": {"stage": "forged stage must be replaced"}}
    q = "선택한 행이 포함되는 이유와 NULL행과의 차이를 알려줘. 정렬 순서도 설명해줘."
    response = client.post(f"/api/sessions/{session['id']}/messages", json={"content": q, "lesson_context": context})
    assert response.status_code == 202, response.text
    job = wait(client, response.json()["job_id"])
    assert job["state"] == "succeeded", job
    followup = next(m for m in client.get(f"/api/sessions/{session['id']}/messages").json() if m["id"] == job["result"]["message_id"])
    assert followup["problem"] == source["problem"]
    assert followup["hypothesis"] is None
    assert followup["lesson_context"]["_verified_logical_stage"]["stage"] == "order"
    lesson = make_lesson(client, session, followup)
    assert lesson["speech_allowed"], lesson
    assert lesson["explanation_fulfillment"]["status"] == "fulfilled"
    assert {i["kind"] for i in lesson["explanation_fulfillment"]["items"]} == {"row_inclusion", "null_comparison", "ordering"}
    speech = " ".join(s["speech"] for s in lesson["plan"]["steps"])
    assert "원본 2행" in speech and "UNKNOWN" in speech and "제외" in speech
    assert "NULL은 숫자 0이다" not in speech and followup["raw_model_response"] == raw
    scene = scene_at(lesson["plan"], len(lesson["plan"]["steps"]) - 1)
    assert any(table["cell_ids"][1][1] in h.get("cell_ids", []) for h in scene["highlights"])
    persisted = client.get("/api/lessons/" + lesson["id"]).json()
    assert persisted["explanation_fulfillment"] == lesson["explanation_fulfillment"]
    assert client.get("/api/lessons/" + original["id"]).json()["plan"] == saved_original
    assert len(calls) == 2
    assert lesson["audio_steps"] == []  # CPU test does not synthesize or pretend to play.
