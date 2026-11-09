"""Read-only, post-run analysis. Does not change the frozen replay harness/results."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
SOURCES = [
    ROOT / "runs/v021-r3-repair/20261030/student/saved-final05/report.json",
    ROOT / "runs/v021-r3-repair/20261030/student/saved-final04-supplements-on-final05/report.json",
]


def analyze_action(case, bound):
    lesson, step = case["lesson_id"], bound["step"]
    matching = [e for e in case["native_media"] if e.get("lesson_id") == lesson and e.get("step_id") == step]
    starts = [e for e in matching if e["type"] == "playing"]
    result = {"case": case["id"], "step": step, "element_id": bound["element_id"],
              "type": bound["type"], "threshold_ms": 75, "original_bound": bound}
    result["original_observation_status"] = (
        "INVALID_TIMING_OBSERVATION" if bound.get("delay_upper_ms") is None or bound["delay_upper_ms"] < 0
        else "VALID_ORIGINAL_BOUND")
    if len(starts) != 1:
        return {**result, "status": "UNRESOLVED_PLAYING_INTERVAL", "playing_count": len(starts)}
    start = starts[0]
    ends = [e for e in matching if e["type"] == "ended" and e.get("epoch") == start["epoch"] and e["at_ms"] >= start["at_ms"]]
    if len(ends) != 1:
        return {**result, "status": "UNRESOLVED_END_INTERVAL"}
    frames = [f for f in case["frames"] if f["lesson"] == lesson and f["step"] == step and f["epoch"] == start["epoch"]]
    key = "arrows" if bound["type"] == "arrow" else "elements"
    transitions = []
    previous = None
    for frame in frames:
        present = bound["element_id"] in frame[key]
        if present != previous:
            transitions.append({"at_ms": frame["at_ms"], "media_time": frame["time"], "present": present,
                                "before_native_playing": frame["at_ms"] < start["at_ms"]})
            previous = present
    active = [f for f in frames if start["at_ms"] <= f["at_ms"] <= ends[0]["at_ms"]]
    due = bound["due"]
    visible = [f for f in active if bound["element_id"] in f[key]]
    early = [f for f in visible if f["time"] < due]
    first = next((f for f in visible if f["time"] >= due), None)
    absent = [f for f in active if bound["element_id"] not in f[key] and first and f["at_ms"] < first["at_ms"]]
    last = absent[-1] if absent else None
    result.update({"native_playing_at_ms": start["at_ms"], "native_ended_at_ms": ends[0]["at_ms"],
                   "epoch": start["epoch"], "visibility_transitions": transitions,
                   "early_frames_during_native_playing": len(early), "active_frame_count": len(active),
                   "due_media_seconds": due,
                   "last_absent_media_seconds": last["time"] if last else None,
                   "first_present_media_seconds": first["time"] if first else None})
    if early:
        result["status"] = "EARLY_DURING_NATIVE_PLAYING"
    elif not first or not last:
        result["status"] = "INCOMPLETE_VISIBILITY_BRACKET"
    else:
        lower, upper = max(0, (last["time"] - due) * 1000), (first["time"] - due) * 1000
        result.update(delay_lower_ms=lower, delay_upper_ms=upper,
                      status="PASS_OBSERVED_INTERVAL" if 0 <= lower <= upper <= 75 else "FAIL_OBSERVED_INTERVAL")
    return result


def main():
    target = OUT / "saved-final05-visibility-interval-analysis.json"
    if target.exists():
        raise FileExistsError("Preserve earlier derived analysis")
    report = {"scope": "Post-run visibility intervals for saved real-WAV replay only; no new model/OCR/voice calls.",
              "method": "Same lesson/step/playback epoch, frames between native playing and ended, all visibility transitions retained. Before-playing preview frames are excluded from active speech timing, never silently deleted from original data.",
              "threshold_ms": 75, "threshold_changed": False, "source_results_modified": False,
              "human_review": "H_PENDING", "sources": [], "actions": []}
    for path in SOURCES:
        raw = path.read_bytes()
        data = json.loads(raw)
        assert data["status"] != "RUNNING", "Do not analyze an active result"
        report["sources"].append({"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(raw).hexdigest(), "status": data["status"]})
        for case in data["cases"]:
            report["actions"].extend(analyze_action(case, b) for b in case.get("timing_bounds", []))
    actions = report["actions"]
    report["summary"] = {"actions": len(actions), "observed_interval_pass": sum(a["status"] == "PASS_OBSERVED_INTERVAL" for a in actions),
                         "invalid_original_observations": sum(a["original_observation_status"] == "INVALID_TIMING_OBSERVATION" for a in actions),
                         "early_during_native_playing": sum(a["status"] == "EARLY_DURING_NATIVE_PLAYING" for a in actions),
                         "max_observed_upper_ms": max((a.get("delay_upper_ms", 0) for a in actions), default=None)}
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["summary"]))


if __name__ == "__main__":
    main()
