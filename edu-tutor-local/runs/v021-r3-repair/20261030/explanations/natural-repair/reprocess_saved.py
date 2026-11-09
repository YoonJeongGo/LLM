"""Disclosed N01/N02 saved response replay; CPU SQLite only, never generation."""
import copy
import hashlib
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

from edu_tutor.problems.models import normalize_problem, infer_basic_intent
from edu_tutor.problems.app_correction import verify_with_app_correction
from edu_tutor.problems.evidence import display_answer
from edu_tutor.lessons.verified import generate_verified_plan

root=Path(__file__).resolve().parents[5]
records=[]
for case in ("N01","N02"):
    path=root/f"runs/v021-r3-repair/20261030/student/repair-new-final02/{case}/actual.json"
    saved_bytes=path.read_bytes();saved=json.loads(saved_bytes)
    source=next(m for m in saved["actual_messages"] if m["role"]=="assistant")
    problem=copy.deepcopy(source["problem"]);raw=source["raw_model_response"]
    for counterexample in ((False,True) if case=="N02" else (False,)):
        p=copy.deepcopy(problem)
        if counterexample:
            p["tables"][0]["rows"].append(["DEV_COUNTEREXAMPLE",6,9,"ready"])
            p.pop("id",None);p=normalize_problem(p)
        intent,reason=infer_basic_intent(p,p["raw_text"])
        evidence=verify_with_app_correction(p,raw,p["raw_text"])
        message={"id":"saved-replay-"+case+str(counterexample),"problem":p,"evidence":evidence,
                 "content":display_answer(evidence),"raw_model_response":raw}
        lesson=generate_verified_plan(message,p["raw_text"],message["id"]+"-plan")
        records.append({"case":case,"counterexample":counterexample,"source_path":str(path),
            "source_sha256":hashlib.sha256(saved_bytes).hexdigest(),"question":p["raw_text"],
            "original_problem":problem,"working_problem":p,"raw_model_response":raw,
            "original_evidence":source["evidence"],"parsed_intent":intent,"intent_reason":reason,
            "evidence":evidence,"lesson":lesson})
    assert path.read_bytes()==saved_bytes
result={"tier":"disclosed_development_replay_after_actual_failure","at":datetime.now(timezone.utc).isoformat(),
        "original_independent_actual_files_preserved":True,"new_independent_evaluation":False,
        "new_text_calls":0,"new_audio_calls":0,"new_vision_calls":0,"human_review":"H_PENDING", "records":records,
        "product_sha256":{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in (
            'src/edu_tutor/problems/intent_language.py','src/edu_tutor/problems/explanation_requests.py',
            'src/edu_tutor/lessons/requested_explanations.py')}}
destination=Path(__file__).with_name(sys.argv[1] if len(sys.argv)>1 else "reprocessed-saved.json")
destination.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
for r in records:
    e=r["evidence"];c=e.get("app_correction",{})
    print(json.dumps({"case":r["case"],"counterexample":r["counterexample"],"intent":r["parsed_intent"],
        "intent_reason":r["intent_reason"],"evidence_status":e["status"],"candidate_status":c.get("original_candidate",e)["intent"]["status"],
        "app_correction":bool(c),"model_answer_status":c.get("model_answer_status"),"lesson_status":r["lesson"]["status"],
        "lesson_reason":r["lesson"].get("reason")},ensure_ascii=False))
