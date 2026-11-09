"""Final07 preregistered N01 subset audit; saved files only, no product/API/model/DB/WAV."""
from pathlib import Path
from datetime import datetime, timezone
import importlib.util
import json

BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("frozen_postrun",BASE/"postrun_review.py")
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

root=BASE.parent
version_dir=root/"student/repair-development-final07"
collected_dir=version_dir/"report-20261030T144127911336Z"
target=BASE/"development-final07-n01-assessment.json"
if target.exists(): raise ValueError("Preserve earlier assessment")
subset_path=BASE/"final07-n01-regression.json"
subset=audit.read(subset_path)
version=audit.read(version_dir/"execution-version.json")
actual_path=version_dir/"N01/actual.json"
actual=audit.read(actual_path)
if actual.get("status")=="RUNNING" or not actual.get("completed_at"):
    raise ValueError("Actual is not terminal")
if [c["id"] for c in subset["journeys"]]!=["N01"]:
    raise ValueError("This audit is only the preregistered N01 two-question subset")
if actual.get("repeat_followup") or version.get("repeat_followup_case_id"):
    raise ValueError("No repeat belongs in final07 subset")
if version.get("input_sha256")!=audit.sha(subset_path):
    raise ValueError("Preregistered subset hash differs")
frozen,original,oracle=audit.checked_inputs(BASE)
case=subset["journeys"][0]
original_case=next(c for c in original["journeys"] if c["id"]=="N01")
if case!=original_case or actual.get("spec")!=case:
    raise ValueError("Original N01 question/table was changed")
collected=audit.read(collected_dir/"N01.json")
messages,lessons=audit.records(actual,collected)
integrity=actual.get("source_unchanged_at_end") is True and actual.get("source_hashes")==version.get("source_hashes")
if not integrity: raise ValueError("Final07 source integrity unproved")
questions=[]
for phase in ["initial","followup"]:
    grade=audit.grade_question(case,oracle["cases"]["N01"],phase,actual,messages,lessons,collected)
    grade["source_integrity"]=integrity
    questions.append(grade)
def correct_raw(q):
    raw=q["raw_model"]
    return raw["status"]=="ONE" and len(raw["checks"])==1 and raw["checks"][0]["status"]=="CORRECT_SQL_AND_RESULT"
result={
    "at":datetime.now(timezone.utc).isoformat(),
    "cohort":"preregistered-development-subset",
    "version":version["version"],
    "source":str(version_dir),
    "subset_notice":"Same disclosed N01 original input, initial+one followup. Final06 N02/repeat and independent N03 are excluded.",
    "questions":questions,
    "repeat_stability":[],
    "cases":[{"id":"N01","actual_json":str(actual_path),"actual_sha256":audit.sha(actual_path),
              "source_integrity":integrity,"harness_status":actual["status"],"harness_failure":actual.get("failure"),
              "timings":collected.get("timings"),"playback_checks":collected.get("evidence_requirements"),
              "lessons":lessons}],
    "metrics":{"planned_denominator":2,"submitted":sum(q["submitted"] for q in questions),
               "raw_sql_and_result_proved":sum(correct_raw(q) for q in questions),
               "app_sql_and_result_proved":sum(q["app"]["result_matches_oracle"] is True and
                   q["app"]["independent_sql_check"]["status"]=="CORRECT_SQL_AND_RESULT" for q in questions),
               "substantive_lesson_reached":sum(q["app"]["actual_speech_support_not_human_audition"] is True for q in questions),
               "repeat_stability_excluded":0,"semantic_pass_count":None},
    "lineage":{"subset_sha256":audit.sha(subset_path),"original_freeze_sha256":audit.sha(BASE/"freeze.json"),
               "execution_version_sha256":audit.sha(version_dir/"execution-version.json"),
               "collector_sha256":audit.sha(collected_dir/"N01.json"),"tool_sha256":audit.sha(BASE/"postrun_review.py"),
               "subset_wrapper_sha256":audit.sha(Path(__file__))},
    "human_review":"H_PENDING","readiness":"NOT_READY"}
target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"output":str(target),"metrics":result["metrics"]},ensure_ascii=False))

