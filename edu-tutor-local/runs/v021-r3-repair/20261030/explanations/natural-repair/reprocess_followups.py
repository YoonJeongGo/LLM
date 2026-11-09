"""CPU fixture only. Original actual followups were NOT_REACHED, no generation."""
import copy
import hashlib
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from edu_tutor.problems.app_correction import verify_with_app_correction
from edu_tutor.problems.evidence import display_answer, verify_answer
from edu_tutor.lessons.verified import generate_verified_plan, validated_logical_stage
from edu_tutor.lessons.plans import scene_at

root=Path(__file__).resolve().parents[5]


def run(case):
    path=root/f"runs/v021-r3-repair/20261030/student/repair-new-final02/{case}/actual.json"
    original=path.read_bytes(); saved=json.loads(original)
    source=next(m for m in saved["actual_messages"] if m["role"]=="assistant")
    p=copy.deepcopy(source["problem"]); question=saved["spec"]["followup"]["question"]
    evidence=verify_with_app_correction(p,source["raw_model_response"],p["raw_text"])
    m={"id":"cpu-original-"+case,"problem":p,"evidence":evidence,"content":display_answer(evidence)}
    base={"id":"cpu-base-"+case,"source_message_id":m["id"],**generate_verified_plan(m,p["raw_text"],"cpu-base-plan-"+case)}
    spec=saved["spec"]["followup"]; table=evidence["working_tables"][0]
    ri=spec["row_index"];ci=table["columns"].index(spec["column"])
    assert table["rows"][ri]==spec["source_row"]
    assert table["rows"][ri][ci]==spec["value"]
    context={"lesson_id":base["id"],"step":1,"problem_revision":p["revision"],
        "selected_cell":{"cell_id":table["cell_ids"][ri][ci],"row_id":table["row_ids"][ri],
                         "column_id":table["column_ids"][ci],"table_element_id":table["id"]}}
    context["_verified_logical_stage"]=validated_logical_stage(base,m,context)
    assert context["_verified_logical_stage"]
    model_double=json.dumps({"sql":evidence["sql"],"explanation":"CPU double only; not an actual model followup."},ensure_ascii=False)
    double_evidence=verify_answer(p,model_double,p["raw_text"])
    child={"id":"cpu-followup-"+case,"problem":copy.deepcopy(p),"evidence":double_evidence,
           "content":display_answer(double_evidence),"lesson_context":context,"raw_model_response":model_double}
    result=generate_verified_plan(child,question,"cpu-followup-plan-"+case)
    assert path.read_bytes()==original
    return {"case":case,"source_path":str(path),"source_sha256":hashlib.sha256(original).hexdigest(),
        "actual_followup_status":"NOT_REACHED","question_original_unchanged":question,"spec":spec,
        "model_double":model_double,"model_double_origin":"original independently verified SQL; no actual followup response exists",
        "base_message":m,"base_lesson":base,"cpu_selected_cell_context":context,"child_message":child,
        "result":result,"final_scene":scene_at(result["plan"],len(result["plan"]["steps"])-1) if result.get("plan") else None,
        "speech_lengths":[len(s["speech"]) for s in (result.get("plan") or {}).get("steps",[])]}


if __name__=="__main__":
    records=[run(case) for case in ("N01","N02")]
    output={"tier":"disclosed_development_CPU_followup_double_NOT_ACTUAL_MODEL","at":datetime.now(timezone.utc).isoformat(),
        "new_text_calls":0,"new_audio_calls":0,"new_vision_calls":0,"human_review":"H_PENDING","records":records}
    destination=Path(__file__).with_name(sys.argv[1] if len(sys.argv)>1 else "followup-reprocessed.json")
    destination.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    for record in records:
        print(json.dumps({"case":record["case"],"status":record["result"]["status"],"reason":record["result"].get("reason"),
            "speech_lengths":record["speech_lengths"],"fulfillment":record["result"].get("explanation_fulfillment")},ensure_ascii=False))
