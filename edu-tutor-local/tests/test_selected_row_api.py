"""Server provenance checks using a CPU runtime double, no real model calls."""
import copy

import pytest

from test_phase2_backend import client, answer, make_lesson, wait
from test_selected_row_lessons import development_problem


@pytest.mark.parametrize("replacement_problem,step",[(False,0),(True,0),(False,4),(False,5),(False,True)])
def test_client_stage_claim_is_removed_and_only_stored_original_plan_can_reestablish_it(client,monkeypatch,replacement_problem,step):
    import edu_tutor.models.runtime as runtime
    monkeypatch.setattr(runtime,"generate",lambda *args,**kwargs:iter(["CPU double: model number 999 is not authoritative"]))
    p=development_problem()
    session,message=answer(client,p["raw_text"],p)
    original=make_lesson(client,session,message)
    preserved=copy.deepcopy(original["plan"])
    table=message["evidence"]["working_tables"][0]
    context={"lesson_id":original["id"],"step":step,"problem_revision":1,
        "selected_cell":{"table_element_id":table["id"],"row_id":table["row_ids"][0],
            "column_id":table["column_ids"][0],"cell_id":table["cell_ids"][0][0]},
        "_verified_logical_stage":{"kind":"server_verified_logical_plan_v1","index":3,"stage":"having","step_id":"s4"}}
    payload={"content":"왜 이 행이 포함돼?","lesson_context":context}
    if replacement_problem:payload["problem"]=p
    response=client.post(f"/api/sessions/{session['id']}/messages",json=payload)
    assert response.status_code==202,response.text
    job=wait(client,response.json()["job_id"])
    assert job["state"]=="succeeded",job
    followup=next(m for m in client.get(f"/api/sessions/{session['id']}/messages").json() if m["id"]==job["result"]["message_id"])
    lesson=make_lesson(client,session,followup)
    if replacement_problem or type(step) is not int or step not in range(len(original["plan"]["steps"])):
        assert "_verified_logical_stage" not in followup["lesson_context"]
        assert not lesson["speech_allowed"] and lesson["plan"] is None
    else:
        scope=followup["lesson_context"]["_verified_logical_stage"]
        assert scope["index"]==step and scope["stage"]==("where" if step==0 else "order") and scope["source_lesson_id"]==original["id"]
        speech=lesson["plan"]["steps"][0]["speech"]
        if step==0:
            assert len(speech)<100 and "4열이 1인 조건" in speech and "HAVING" not in speech
        else:
            assert "정렬" in speech and "999" not in speech
    assert followup["raw_model_response"]=="CPU double: model number 999 is not authoritative"
    assert client.get("/api/lessons/"+original["id"]).json()["plan"]==preserved
