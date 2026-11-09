"""Summarize saved actual evidence without making any inference calls."""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/phase2/current"


def main():
    text_records, audio_records = {}, {}

    def collect(value, source):
        if isinstance(value, dict):
            snap = value.get("generation_snapshot")
            if isinstance(snap, dict) and snap.get("timestamp"):
                key = (snap["timestamp"], snap.get("adapter_id"))
                record = text_records.setdefault(key, {"message_id": value.get("id"), "snapshot": snap, "sources": []})
                if source not in record["sources"]:
                    record["sources"].append(source)
            if value.get("audio_id") and "duration" in value:
                audio_records[value["audio_id"]] = {k: value.get(k) for k in (
                    "audio_id", "duration", "elapsed_seconds", "peak_vram_bytes", "model_load_seconds",
                    "model_load_count", "batch_index", "cache_hit", "generation_settings", "completion")}
            for nested in value.values():
                collect(nested, source)
        elif isinstance(value, list):
            for nested in value:
                collect(nested, source)

    files = list((OUT / "live").glob("*.json")) + list((OUT / "diagnostics").rglob("report.json"))
    files += [ROOT / "web/test-results-phase2-live/evidence.json"]
    for path in files:
        collect(json.loads(path.read_text(encoding="utf-8")), path.relative_to(ROOT).as_posix())
    ledger = json.loads((OUT / "resource-budget.json").read_text(encoding="utf-8"))
    requests = ledger["requests"]
    profile = {"created_at": datetime.now(timezone.utc).isoformat(),
        "text_generations": sorted(text_records.values(), key=lambda item: item["snapshot"]["timestamp"]),
        "audio_clips": list(audio_records.values()), "model_requests": requests,
        "charged_model_subprocess_seconds": sum(item["charged_seconds"] for item in requests),
        "latency_interpretation": "Every text subprocess loads weights anew. OS file cache cold/warm state was not controlled. model_load_count=0 for later units in one shared TTS batch is actual reuse. Cached browser playback makes no model call. No stable p95 claim.",
        "scope": "Deduplicated saved generation timestamps and audio IDs from actual live/diagnostic records, including failures/repairs. Original three OCR ledger status errors are documented separately; wall-time charges unchanged.",
        "human_listening_and_prose_review": "not_reviewed"}
    (OUT / "runtime-metrics.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"text_generations": len(text_records), "saved_audio_clips": len(audio_records),
                      "ledger_requests": len(requests), "charged_seconds": profile["charged_model_subprocess_seconds"]}))


if __name__ == "__main__":
    main()
