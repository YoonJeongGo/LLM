"""Post-run geometry comparison; no API, generation, or result mutation."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
STUDENT = OUT.parent / "student"
sys.path.insert(0, str(STUDENT))
from collect_journeys import scene_binding_checks


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def geometry_summary(check):
    stable = [s for s in check["samples"] if s["status"] != "SKIPPED_ACTION_BOUNDARY"]
    failures = [s for s in stable if s["pointer"]["status"] == "FAIL"]
    return {"pass": check["pass"], "stable": check["stable_sample_count"],
            "late": check["complete_late_sample_count"], "pointer_failed_samples": len(failures),
            "pointer_pass_samples": sum(s["pointer"]["status"] == "PASS" for s in stable),
            "board_failed_samples": sum(not s["board"]["pass"] for s in stable),
            "arrow_failed_samples": sum(not s["arrows"]["pass"] for s in stable),
            "representative": (failures or stable or [{}])[0]}


def main():
    target = OUT / "saved-final05-pointer-regression.json"
    if target.exists():
        raise FileExistsError("Preserve prior analysis")
    source = STUDENT / "saved-final04-supplements-on-final05/report.json"
    replay = read(source)
    assert replay["status"] != "RUNNING"
    previous_dir = STUDENT / "repair-development-final04/report-20261030T124511994292Z"
    sources = [source, previous_dir / "N01.json", previous_dir / "N02.json", STUDENT / "collect_journeys.py"]
    report = {"scope": "Same saved supplementary plans and existing WAVs, final04 failure versus final05 GET-only replay. This is geometry/reentry evidence, not a new answer, live interruption, or human quality review.",
              "action_boundary_seconds": .075, "pointer_tolerance_css_px": 4, "thresholds_changed": False,
              "sources": [{"path": str(p.relative_to(ROOT)), "sha256": digest(p)} for p in sources],
              "human_review": "H_PENDING", "comparisons": [], "new_scene_checks": []}
    for case in replay["cases"]:
        previous = read(previous_dir / (case["id"].split("-")[0] + ".json"))
        lesson = case["lesson"]
        old_lesson = next(l for l in previous["lessons"] if l["id"] == lesson["id"])
        assert old_lesson["plan"] == lesson["plan"], "Plan changed; cannot compare identical source"
        assert old_lesson["audio_steps"] == lesson["audio_steps"], "Audio records changed"
        played = []
        # The existing helper's input selects scene samples by native media identity.
        # This explicit record/DOM/native linkage is only a scene selector here; it
        # does not substitute for a fresh independent PCM/fingerprint assessment.
        for event in case["events"]:
            if event.get("type") != "audio_playing":
                continue
            native = [n for n in case["native_media"] if n["type"] == "playing"
                      and n["lesson_id"] == event["lesson_record_id"] and n["step_id"] == event["step_id"]
                      and n["epoch"] == event["epoch"] and n["media_id"] == event["media"]["media_id"]
                      and n["current_src"] == event["media"]["current_src"]]
            assert len(native) == 1 and not native[0]["muted"] and native[0]["playbackRate"] == 1
            assert event["dom_lesson_record_id"] == lesson["id"] and event["dom_step_id"] == event["step_id"]
            played.append({"lesson_id": lesson["id"], "step_id": event["step_id"], "event": event,
                           "valid_explanation_by_record_linkage": True})
        checks = scene_binding_checks(case, {lesson["id"]: lesson}, played)
        assert len(checks) == len(lesson["plan"]["steps"]), "Missing native played steps"
        report["new_scene_checks"].append({"id": case["id"], "same_plan": True, "same_audio_records": True,
                                           "no_completed_autoplay": case["no_completed_autoplay"], "checks": checks})
        for check in checks:
            old = next(s for s in previous["scene_binding_checks"]
                       if s["lesson_id"] == lesson["id"] and s["step_id"] == check["step_id"])
            report["comparisons"].append({"case": case["id"], "lesson_id": lesson["id"], "step_id": check["step_id"],
                                          "before": geometry_summary(old), "after": geometry_summary(check)})
    prior_failed = [c for c in report["comparisons"] if not c["before"]["pass"]]
    report["summary"] = {"same_saved_lessons": len(replay["cases"]), "compared_steps": len(report["comparisons"]),
                         "prior_failed_steps": len(prior_failed),
                         "prior_failed_steps_now_pass": sum(c["after"]["pass"] for c in prior_failed),
                         "all_current_steps_pass": sum(c["after"]["pass"] for c in report["comparisons"]),
                         "prior_pointer_failed_samples": sum(c["before"]["pointer_failed_samples"] for c in report["comparisons"]),
                         "current_pointer_failed_samples": sum(c["after"]["pointer_failed_samples"] for c in report["comparisons"]),
                         "current_stable_samples": sum(c["after"]["stable"] for c in report["comparisons"]),
                         "current_late_samples": sum(c["after"]["late"] for c in report["comparisons"])}
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"]))


if __name__ == "__main__":
    main()
