"""CPU-only disclosed replay of the preserved J04 question; no API or generation."""
import copy
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from edu_tutor.lessons.verified import generate_verified_plan, validated_logical_stage
from edu_tutor.lessons.plans import scene_at

root = Path(__file__).resolve().parents[4]
source = root / "runs/v021-support/20261029/student/final-v021-r3-student-v3/J04/actual.json"
raw = source.read_bytes()
saved = json.loads(raw)
assistants = [m for m in saved["actual_messages"] if m["role"] == "assistant"]
original, child = copy.deepcopy(assistants)
question = saved["spec"]["followup"]["question"]
old_context = child["lesson_context"]
old_context["_verified_logical_stage"] = validated_logical_stage(saved["actual_lesson"], original, old_context)
assert old_context["_verified_logical_stage"], "Saved current-board/source binding must still validate"
start = time.perf_counter()
result = generate_verified_plan(child, question, "cpu-saved-j04-reprocessed")
elapsed = time.perf_counter() - start
assert result["speech_allowed"], result
assert source.read_bytes() == raw
report = {"tier": "CPU_saved_development_replay", "new_independent_evaluation": False,
    "source_path": str(source), "source_sha256": hashlib.sha256(raw).hexdigest(),
    "original_preserved": True, "created_at": datetime.now(timezone.utc).isoformat(),
    "question": question, "original_problem": child["problem"], "saved_raw_model_response": child["raw_model_response"],
    "reused_saved_evidence": child["evidence"], "saved_context": child["lesson_context"],
    "result": result, "scenes": [scene_at(result["plan"], i) for i in range(len(result["plan"]["steps"]))],
    "reprocess_seconds": elapsed, "new_text_calls": 0, "new_tts_calls": 0, "human_review": "H_PENDING",
    "source_hashes": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root / "src/edu_tutor/lessons/verified.py", root / "src/edu_tutor/lessons/requested_explanations.py",
                  root / "src/edu_tutor/problems/explanation_requests.py", root / "src/edu_tutor/problems/models.py",
                  root / "src/edu_tutor/problems/intent_language.py", root / "src/edu_tutor/problems/pipeline.py")}}
destination = Path(__file__).with_name("saved-j04-reprocessed.json")
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"artifact": str(destination), "steps": len(result["plan"]["steps"]),
                  "speech_characters": [len(s["speech"]) for s in result["plan"]["steps"]],
                  "fulfillment": result["explanation_fulfillment"]["status"], "seconds": elapsed}, ensure_ascii=False))
