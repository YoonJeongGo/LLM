"""Read existing JSON/JSONL only; no product imports, API, DB or profiling run."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[4]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def worker_trace(snapshot):
    instance = snapshot.get("instance_id")
    if not isinstance(instance, str) or not re.fullmatch(r"[a-f0-9]{32}", instance):
        return {"status": "NOT_MEASURED_INSTANCE_ID_ABSENT"}
    path = ROOT / "runs" / ("text-session-" + instance) / "events.jsonl"
    if not path.is_file():
        return {"status": "NOT_MEASURED_EVENT_FILE_ABSENT", "path": str(path)}
    events = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            event = json.loads(line)
            events.append({"line": index, **event})
    matches = [e for e in events if e.get("type") == "metadata" and e.get("instance_id") == instance
               and e.get("worker_pid") == snapshot.get("worker_pid") and e.get("model_instance_id") == snapshot.get("model_instance_id")
               and e.get("timestamp") == snapshot.get("timestamp")]
    if len(matches) != 1:
        return {"status": "NOT_MEASURED_METADATA_BINDING_AMBIGUOUS", "path": str(path), "matches": len(matches)}
    metadata = matches[0]
    rid = metadata["request_id"]
    selected = [e for e in events if e.get("instance_id") == instance and e.get("request_id") == rid]
    def event(kind, stage=None):
        return next((e for e in selected if e.get("type") == kind and (stage is None or e.get("stage") == stage)), None)
    points = {"request_started": event("request_started"),
              "runtime_import_started": event("progress", "text_runtime_import_started"),
              "imports_ready": event("progress", "imports_ready"),
              "model_load_started": event("progress", "model_load_started"),
              "model_ready": event("model_ready"), "first_delta": event("delta"), "metadata": metadata, "done": event("done")}
    boundaries = {}
    for name, first, last in [
        ("request_to_import_start", "request_started", "runtime_import_started"),
        ("runtime_import_window", "runtime_import_started", "imports_ready"),
        ("imports_ready_to_load_start", "imports_ready", "model_load_started"),
        ("load_start_to_model_ready", "model_load_started", "model_ready"),
        ("warm_reuse_entry_to_ready", "runtime_import_started", "model_ready"),
        ("model_ready_to_first_delta", "model_ready", "first_delta"),
        ("first_delta_to_metadata", "first_delta", "metadata"),
        ("model_ready_to_metadata", "model_ready", "metadata"),
        ("request_to_metadata", "request_started", "metadata"),
        ("metadata_to_done", "metadata", "done")]:
        a, b = points[first], points[last]
        if a is None or b is None:
            boundaries[name] = {"status": "NOT_EMITTED_FOR_REQUEST", "seconds": None}
        else:
            value = b["worker_elapsed_seconds"] - a["worker_elapsed_seconds"]
            if value < 0:
                raise ValueError("Non-monotonic worker events")
            boundaries[name] = {"status": "MEASURED", "seconds": value, "start_line": a["line"], "end_line": b["line"]}
    # This encompasses the cold import+load path; label it reuse-only when load0.
    if snapshot.get("request_model_load_count") != 0:
        boundaries["warm_reuse_entry_to_ready"] = {"status": "NOT_APPLICABLE_COLD", "seconds": None}
    kept = {k: {key: val for key, val in value.items() if key in {"line", "type", "stage", "worker_elapsed_seconds", "request_id", "timestamp", "worker_pid", "instance_id", "model_instance_id", "model_python_id", "request_model_load_count", "cumulative_model_load_count", "text"}} if value else None for k, value in points.items()}
    return {"status": "BOUND_TO_EXACT_WORKER_REQUEST", "path": str(path.relative_to(ROOT)), "sha256": sha(path),
            "protocol_request_id": rid, "clock": "one worker's worker_elapsed_seconds (perf_counter origin)",
            "boundaries": boundaries, "event_points": kept,
            "notice": "runtime_import_window includes module import and pre-loader setup; no per-package profiler exists. Model-ready-to-metadata overlaps model generation. Intervals are not all additive."}


def collect_case(entry):
    actual_path, collected_path = ROOT / entry["actual"], ROOT / entry["collected"]
    actual, collected = read(actual_path), read(collected_path)
    if not actual.get("completed_at"):
        raise ValueError("Actual run has not completed: " + str(actual_path))
    if collected.get("actual_sha256") != sha(actual_path):
        raise ValueError("Collector is not bound to the same preserved actual output")
    timings = collected.get("timings") or {}
    rows = []
    for message in actual.get("actual_messages", []):
        if message.get("role") != "assistant":
            continue
        snapshot = message.get("generation_snapshot") or {}
        if not snapshot.get("instance_id"):
            continue
        user = next((m for m in actual.get("actual_messages", []) if m.get("role") == "user" and m.get("request_id") == message.get("request_id")), {})
        job = next((j for j in actual.get("owned_jobs", []) if j.get("kind") == "chat" and j.get("request_id") == message.get("request_id")), {})
        first = next((r for r in timings.get("question_to_first_valid_explanation", []) if r.get("request_id") == message.get("request_id")), {})
        lesson_ids = {v["id"] for v in collected.get("lessons", []) if v.get("source_message_id") == message["id"]}
        playback = [v for v in collected.get("playback", []) if v.get("lesson_id") in lesson_ids and v.get("valid_explanation_by_record_linkage") is True]
        native = next((v.get("native_playing_event") for v in playback if v.get("native_playing_event")), None)
        start = first.get("submission_event", {}).get("at_ms")
        native_seconds = (native["at_ms"] - start) / 1000 if native and numeric(start) else None
        audio = [a for a in timings.get("stage_breakdown", {}).get("audio", []) if a.get("lesson_id") in lesson_ids]
        row = {"label": entry["label"], "message_id": message["id"], "request_id": message.get("request_id"),
            "question": user.get("content"), "raw_model_response": message.get("raw_model_response"), "app_response": message.get("content"),
            "app_evidence_status": (message.get("evidence") or {}).get("status"),
            "identity": {k: snapshot.get(k) for k in ["model_id", "revision", "adapter_id", "requested_precision", "worker_pid", "process_start_time", "instance_id", "model_instance_id", "model_python_id", "request_model_load_count", "cumulative_model_load_count", "input_tokens", "output_tokens"]},
            "regime": "warm_same_model_record" if snapshot.get("request_model_load_count") == 0 else "cold_loading_record",
            "worker": worker_trace(snapshot),
            "worker_reported": {k: snapshot.get(k) for k in ["model_load_seconds", "generation_seconds", "elapsed_seconds"]},
            "nested_loader_import_seconds": snapshot.get("inference", {}).get("loader_import_seconds"),
            "nested_loader_import_historical_on_warm": snapshot.get("request_model_load_count") == 0,
            "parent_transport": snapshot.get("transport_timing"), "parent_resident_request": snapshot.get("parent_timing"),
            "parent_dispatch": snapshot.get("dispatch_timing"), "api_recorded_latency": message.get("latency"),
            "api_evidence_timings": (message.get("evidence") or {}).get("timings_seconds"),
            "storage": job.get("storage_timing"), "partial_persistence": job.get("partial_persistence"),
            "ui_first_valid_text": {"status": "NOT_MEASURED", "seconds": None, "reason": "No recorded criterion-linked first valid UI text event. Raw first delta is not a substitute."},
            "browser_first_valid_voice": {"collector_status": first.get("status", "NOT_MEASURED"),
                "onPlaying_seconds": first.get("first_valid_explanation_ms") / 1000 if numeric(first.get("first_valid_explanation_ms")) else None,
                "native_playing_seconds": native_seconds, "native_playing_event": native,
                "boundary": "same-case browser performance.now from actual question submission to linked native playing; audible word/listening not reviewed"},
            "first_clip_metadata": audio[:1], "browser_intervals": timings.get("stage_breakdown", {}).get("browser_intervals", []),
            "plan_jobs": timings.get("stage_breakdown", {}).get("plan_jobs", []),
            "stage_gaps": timings.get("stage_gaps", []), "stage_gap_status": timings.get("stage_gap_status"),
            "interruptions": timings.get("interruptions", []), "human_review": "H_PENDING"}
        rows.append(row)
    return {"label": entry["label"], "actual_path": entry["actual"], "actual_sha256": sha(actual_path),
            "collector_path": entry["collected"], "collector_sha256": sha(collected_path),
            "version": actual.get("version"), "measurement_mode": actual.get("measurement_mode"),
            "status": actual.get("status"), "failure": actual.get("failure"), "source_unchanged_at_end": actual.get("source_unchanged_at_end"),
            "started_at": actual.get("started_at"), "completed_at": actual.get("completed_at"), "answers": rows}


def val(value):
    return f"{value:.6f}" if numeric(value) else "미측정/해당 없음"


def report(data):
    out = ["# 기존 실행 기록의 지연 분해", "", "이 보고서는 이미 끝난 actual·collector·text-session events.jsonl만 읽었다. 모델 생성, 새 import 프로파일링, 네트워크, 운영 DB·장부 변경은 없다. 각 원문 답변과 worker 식별자, 원본 파일 SHA256은 data.json에 보존했다.", "",
           "## 학생이 기다린 시간과 모델 단계", "", "단위는 초다. 각 열은 측정 시작점이 다르므로 가로로 더하지 않는다.", "",
           "| 실행 | worker import 구간 | load→ready | 생성(모델 기록) | 부모 요청→첫 delta | API 완료 지점 | native 첫 설명 음성 |",
           "|---|---:|---:|---:|---:|---:|---:|"]
    rows = [r for c in data["cases"] for r in c["answers"]]
    for r in rows:
        b = r["worker"].get("boundaries", {})
        out.append("| " + r["label"] + " | " + " | ".join(val(v) for v in [b.get("runtime_import_window", {}).get("seconds"), b.get("load_start_to_model_ready", {}).get("seconds"),
            r["worker_reported"].get("generation_seconds"), (r.get("parent_transport") or {}).get("first_delta_reader_elapsed_seconds"),
            (r.get("api_recorded_latency") or {}).get("request_to_verified_core_seconds"), r["browser_first_valid_voice"]["native_playing_seconds"]]) + " |")
    out += ["", "API의 필드명 request_to_verified_core_seconds는 코드가 검증/보류 경로를 마친 시각이다. needs_input으로 끝난 실행에는 유효한 설명이 없으므로 이 값을 첫 설명 시간이라고 해석하지 않는다. 첫 UI 유효 텍스트는 네 실행 모두 NOT_MEASURED다. 첫 delta 도착은 모델 조각 수신 시각이며 학생에게 의미 있는 문장이 보인 시각이 아니다.", "",
            "## 이벤트 소비와 저장", "", "| 실행 | delta 수 | 부분 snapshot 쓰기 | reader queue 총/최대 | consumer yield 총 | DB commit 총 | DB close 총 | 저장소 검사 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        t = r.get("parent_transport") or {}; s = (r.get("storage") or {}).get("phases", {})
        out.append(f"| {r['label']} | {t.get('delta_event_count')} | {(r.get('partial_persistence') or {}).get('snapshot_writes')} | {val(t.get('queue_wait_seconds_total'))} / {val(t.get('queue_wait_seconds_max'))} | {val(t.get('consumer_yield_seconds_total'))} | {val(s.get('db_commit', {}).get('seconds'))} | {val(s.get('db_close', {}).get('seconds'))} | {val(s.get('project_mutable_storage_scan', {}).get('seconds'))} |")
    out += ["", "reader queue 합계는 이벤트별 대기 합계로 요청 벽시계 지연과 같지 않다. consumer yield는 API가 이전 이벤트를 소비한 구간이며 timer의 DB 작업과 중첩될 수 있다. DB commit/close와 잠금 대기·worker 생성시간을 합쳐 전체 지연의 원인 비율로 만들지 않는다. storage snapshot은 최종 job 상태 쓰기 직전이어서 그 write/commit 및 HTTP/SSE 완료 전달은 제외한다.", "",
            "## 경계와 아직 확인되지 않은 부분", "", "- 같은 worker의 progress→model_ready→metadata 차이만 worker 단계 분해에 썼다. 서로 다른 프로세스·브라우저 시계의 절대 시각을 빼지 않았다.",
            "- runtime import 구간은 imports_ready 전의 모듈 import와 설정 진입을 포함한다. 어떤 패키지·디스크·OS 캐시가 얼마를 차지했는지는 이 기록으로 증명되지 않는다.",
            "- inference.loader_import_seconds는 load_text 내부의 추가 import 구간이며 cold model load 구간에 포함된다. warm 응답에서는 같은 모델 metadata에 남은 과거 값이므로 현재 작업 시간에 더하면 안 된다.",
            "- load0의 import/load progress 생략은 새 로딩이 없었다는 모델 기록과 함께 해석한다. 생략된 개별 단계 시간을 정확히 0초 측정했다고 주장하지 않는다.",
            "- 캐시 음성의 voice_api_seconds·elapsed_seconds는 그 WAV를 처음 만들 때의 과거 값이다. 이번 첫 음성 시작의 TTS 합성 비용으로 쓰지 않는다.",
            "- controlled first-voice 시험은 전체 자연 수업·중간 질문·반복 취소 시험이 아니다. 다른 새 cold 질문이 막혔다면 빠른 모델 완료 시간으로 학생 수업 속도 성공을 주장할 수 없다.",
            "- 교육 정확도와 실제 발음·청취 품질은 이 지연 보고의 판정 범위 밖이며 H_PENDING이다.", ""]
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if (args.out / "data.json").exists() or (args.out / "REPORT_KO.md").exists():
        raise ValueError("Refusing to overwrite a previous timing report")
    manifest = read(args.manifest)
    data = {"at": datetime.now(timezone.utc).isoformat(), "source_manifest": str(args.manifest), "source_manifest_sha256": sha(args.manifest),
            "reader_sha256": sha(Path(__file__)), "method": "existing files only, no product imports or profiling",
            "cases": [collect_case(entry) for entry in manifest["cases"]], "new_model_calls": 0, "network_calls": 0,
            "database_access": False, "ledger_mutation": False, "human_review": "H_PENDING"}
    rows = [r for c in data["cases"] for r in c["answers"]]
    data["reuse_pairs"] = [{"earlier": a["label"], "later": b["label"], "same_identity": all(a["identity"].get(k) == b["identity"].get(k) for k in ["worker_pid", "process_start_time", "instance_id", "model_instance_id", "model_python_id"]),
                            "later_request_load_count": b["identity"].get("request_model_load_count"), "cumulative_load_count": b["identity"].get("cumulative_model_load_count")}
                           for i, a in enumerate(rows) for b in rows[i+1:] if a["identity"].get("instance_id") == b["identity"].get("instance_id")]
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.out / "REPORT_KO.md").write_text(report(data), encoding="utf-8")
    print(json.dumps({"saved": str(args.out), "cases": len(data["cases"]), "answers": len(rows), "reuse_pairs": data["reuse_pairs"]}))


if __name__ == "__main__":
    main()
