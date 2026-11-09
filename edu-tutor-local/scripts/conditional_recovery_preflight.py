"""Read-only source/budget check and CPU replay, with no model worker imports."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from edu_tutor.lessons.reprocessing import reprocess_saved_lesson
from edu_tutor.models.budget import status

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/student-latency/20261027/condition-recovery"
OLD = ROOT / "runs/student-latency/20261027/new-lesson/result.json"


def main():
    old = json.loads(OLD.read_text(encoding="utf-8"))
    actual = old["actual"]
    with sqlite3.connect((ROOT / ".local/tutor.sqlite3").as_uri()+"?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        message = json.loads(db.execute("SELECT payload FROM messages WHERE id=?", (actual["message"]["id"],)).fetchone()[0])
        lesson = json.loads(db.execute("SELECT payload FROM lessons WHERE id=?", ("c03a2b61607b471580296e98ec1a15eb",)).fetchone()[0])
    started = perf_counter()
    derived, plan_record = reprocess_saved_lesson(lesson, message, actual["question"], "cpu-preview-not-persisted")
    elapsed = perf_counter() - started
    checks = {
        "saved_raw_equals_failed_run": message["raw_model_response"] == actual["message"]["raw_model_response"],
        "saved_problem_equals_failed_run": message["problem"] == actual["message"]["problem"],
        "derived_raw_unchanged": derived["raw_model_response"] == message["raw_model_response"],
        "verified_independent": derived["evidence"]["calculation"]["status"] == "independent_aggregate_match",
        "original_sql_unchanged": derived["evidence"]["sql"] == json.loads(message["raw_model_response"])["sql"],
        "result_matches_failed_sql_execution": derived["evidence"]["result"]["rows"] == message["evidence"]["execution"]["rows"],
        "two_steps": bool(plan_record["plan"]) and len(plan_record["plan"]["steps"]) == 2,
        "speech_allowed": plan_record["speech_allowed"],
        "old_failure_unchanged": lesson["plan"] is None and not lesson["speech_allowed"],
    }
    budget = status(ROOT)
    grant = budget["active_execution_allowance"]
    report = {"at": datetime.now(timezone.utc).isoformat(), "status": "PASS" if all(checks.values()) else "FAIL",
        "mode": "CPU preview only; not stored as an app lesson and not a new-question latency",
        "elapsed_seconds": elapsed, "checks": checks, "budget_before": budget,
        "source_question": actual["question"], "source_message": message, "source_lesson": lesson,
        "derived_preview": derived, "lesson_preview": plan_record}
    target = OUT / "cpu-saved-E-preview.json"
    if target.exists():
        raise SystemExit("Preserve existing preview; use a distinct path after a justified change")
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    authorization = {"at": report["at"], "type": "existing_allowance_scope_clarification_not_new_grant",
        "allowance_id": grant["id"], "same_source_lesson_id": lesson["id"],
        "authorized_remaining": {"new_text": 0, "new_audio_max": min(2, grant["audio_remaining"]),
                                 "seconds": grant["seconds_remaining"], "vision": 0},
        "user_instruction": "검증을 통과한 저장 실패 수업 E의 두 설명 단계에만 남은 음성 사용. 정확히 일치하는 캐시 우선. 실패도 횟수에 포함하며 자동 재시도 없음. 새 승인·시간 예산 추가 없음.",
        "prohibited": ["new_text_inference", "OCR", "training", "download", "paid_calls", "external_upload"],
        "policy_and_ledger_not_modified": True}
    (OUT / "authorization-scope.json").write_text(json.dumps(authorization, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": checks, "cpu_seconds": elapsed,
                      "grant": grant}, ensure_ascii=False))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
