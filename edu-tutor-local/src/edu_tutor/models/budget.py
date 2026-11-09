"""Persistent, conservative limits for the explicitly enabled phase-two run.

Reserve the full request duration before starting a process. An interrupted API
leaves that reservation charged; a restart cannot silently reset its budget.
"""
from __future__ import annotations

import json
import hashlib
import os
import shutil
import time
import uuid
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock
from edu_tutor.storage.timing import record_timing


class ResourceBudgetExceeded(RuntimeError):
    pass


STUDENT_FIELDS = ("seconds", "text_requests", "new_audio_clips", "vision_requests")


def _student_used(rows):
    return {"seconds": sum(row["charged_seconds"] for row in rows),
            "text_requests": sum(row.get("text_requests", int(row["kind"] == "text")) for row in rows),
            "new_audio_clips": sum(row["new_audio_clips"] for row in rows),
            "vision_requests": sum(row["vision_requests"] for row in rows)}


def _student_parent_remaining(grant):
    if not grant or grant.get("accounting") != "scope_only_preserve_lifetime":
        return {key: 0 for key in STUDENT_FIELDS}
    return {"seconds": grant["seconds_remaining"], "text_requests": grant["text_remaining"],
            "new_audio_clips": grant["audio_remaining"], "vision_requests": grant["vision_remaining"]}


def _student_view(state, grant, session_id):
    entry = state.get("student_session_budgets", {}).get(session_id)
    parent = _student_parent_remaining(grant)
    if not entry:
        return {"exists": False, "session_id": session_id, "parent_remaining": parent}
    used = _student_used([row for row in state["requests"]
                          if row.get("student_session_id") == session_id])
    remaining = {key: max(0, entry["limits"][key] - used[key]) for key in STUDENT_FIELDS}
    available = entry["state"] == "active" and grant and entry["parent_scope_id"] == grant["id"]
    return {**entry, "exists": True, "used": used, "remaining": remaining,
            "parent_remaining": parent,
            "effective_remaining": {key: min(remaining[key], parent[key]) if available else 0 for key in STUDENT_FIELDS},
            "allocation_note": "Session ceilings are not extra credit or a guaranteed reservation of the shared approved remainder."}


def student_budget(root, session_id, *, limits=None, request_id=None, close=False):
    """Explicit immutable session cap; shares the existing locked lifetime ledger."""
    root = Path(root)
    if not isinstance(session_id, str) or not re.fullmatch(r"[a-f0-9]{32}", session_id):
        raise ResourceBudgetExceeded("올바른 대화 세션이 필요합니다.")
    path = root / "runs/phase2/current/resource-budget.json"
    with FileLock(str(root / ".local/phase2-budget.lock")):
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"requests": []}
        policy_value = policy(root)
        grant = _execution_allowance(policy_value, state["requests"])
        entry = state.get("student_session_budgets", {}).get(session_id)
        if limits is not None:
            if (not policy_value.get("enabled") or not grant
                    or grant.get("accounting") != "scope_only_preserve_lifetime"):
                raise ResourceBudgetExceeded("기존 승인 범위 안에서만 학생 수업 예산을 시작할 수 있습니다.")
            if (not isinstance(request_id, str) or not 1 <= len(request_id) <= 100
                    or set(limits) != set(STUDENT_FIELDS)
                    or not isinstance(limits["seconds"], (int, float)) or isinstance(limits["seconds"], bool)
                    or not math.isfinite(limits["seconds"]) or limits["seconds"] < 1
                    or any(type(limits[key]) is not int or limits[key] < 0 for key in STUDENT_FIELDS[1:])
                    or not any(limits[key] for key in STUDENT_FIELDS[1:])):
                raise ResourceBudgetExceeded("시간과 텍스트·음성·사진의 유한한 세션 한도를 직접 지정하세요.")
            if entry:
                if entry["request_id"] != request_id or entry["limits"] != limits:
                    raise ResourceBudgetExceeded("이 세션의 예산은 이미 정해졌습니다. 자동 재충전하거나 변경하지 않습니다.")
                return _student_view(state, grant, session_id)
            if any(value.get("request_id") == request_id for value in state.get("student_session_budgets", {}).values()):
                raise ResourceBudgetExceeded("다른 세션에 사용된 예산 시작 요청입니다.")
            if any(limits[key] > _student_parent_remaining(grant)[key] for key in STUDENT_FIELDS):
                raise ResourceBudgetExceeded("학생 세션 한도는 현재 전체 승인 잔여보다 클 수 없습니다.")
            state.setdefault("student_session_budgets", {})[session_id] = {
                "session_id": session_id, "parent_scope_id": grant["id"], "request_id": request_id,
                "limits": limits, "state": "active", "created_at": datetime.now(timezone.utc).isoformat()}
            path.parent.mkdir(parents=True, exist_ok=True)
            _save(path, state)
        elif close:
            if not entry:
                raise ResourceBudgetExceeded("시작된 학생 세션 예산이 없습니다.")
            if entry["state"] != "closed":
                entry.update(state="closed", closed_at=datetime.now(timezone.utc).isoformat())
                _save(path, state)
        return _student_view(state, grant, session_id)


def student_scope(root, session_id, *, kind=None):
    """Lookup only: never creates, reopens, or expands a session budget."""
    view = student_budget(root, session_id)
    if not view["exists"]:
        return None
    if view["state"] != "active" or view["effective_remaining"]["seconds"] < 1:
        raise ResourceBudgetExceeded("학생 수업 예산이 종료되었거나 실행 시간이 남지 않았습니다. 저장된 수업은 볼 수 있습니다.")
    key = {"text": "text_requests", "speech": "new_audio_clips", "vision": "vision_requests"}.get(kind)
    if key and view["effective_remaining"][key] < 1:
        raise ResourceBudgetExceeded("이 학생 세션의 해당 실행 한도를 소진했습니다. 입력과 기존 기록을 보존합니다.")
    return view["parent_scope_id"]


def _execution_allowance(limits, rows):
    """Validate the historical baseline; replacement scopes retain lifetime rows."""
    grant = limits.get("active_execution_allowance")
    if grant is None:
        return None
    baseline = grant["baseline_request_count"]
    prefix = json.dumps(rows[:baseline], ensure_ascii=False, sort_keys=True,
                        separators=(",", ":")).encode("utf-8")
    if baseline > len(rows) or hashlib.sha256(prefix).hexdigest() != grant["baseline_requests_sha256"]:
        raise ResourceBudgetExceeded("추가 승인 기준 장부가 달라졌습니다. 자동으로 한도를 초기화하지 않습니다.")
    scoped = grant.get("accounting") == "scope_only_preserve_lifetime"
    new = ([r for r in rows[baseline:] if r.get("execution_allowance_id") == grant["id"]]
           if scoped else rows[baseline:])
    caps = grant["limits"]
    texts = sum(r.get("text_requests", int(r["kind"] == "text")) for r in new)
    result = {"id": grant["id"],
        "text_remaining": max(0, caps["text_requests"] - texts),
        "audio_remaining": max(0, caps["new_audio_clips"] - sum(r["new_audio_clips"] for r in new)),
        "vision_remaining": max(0, caps["vision_requests"] - sum(r["vision_requests"] for r in new)),
        "seconds_remaining": max(0, caps["gpu_seconds"] - sum(r["charged_seconds"] for r in new))}
    if scoped:
        result.update(runtime_scope=grant["runtime_scope"], accounting=grant["accounting"],
            limits=caps, requests=len(new), text_used=texts,
            training_remaining=max(0, caps["training_experiments"] - sum(r.get("training_experiments", 0) for r in new)),
            download_bytes_remaining=max(0, caps["download_bytes"] - sum(r.get("download_bytes", 0) for r in new)),
            new_text_candidates_remaining=max(0, caps["new_text_candidates"] - sum(r.get("new_text_candidates", 0) for r in new)),
            new_tts_candidates_remaining=max(0, caps["new_tts_candidates"] - sum(r.get("new_tts_candidates", 0) for r in new)))
    return result


def active_scope_id(root):
    """Return configured scope metadata, without granting a request implicitly."""
    grant = policy(root).get("active_execution_allowance") or {}
    return grant.get("id") if grant.get("accounting") == "scope_only_preserve_lifetime" else None


def training_allowed(root):
    limits = policy(root)
    if not limits.get("enabled"):
        return not limits.get("no_new_training", False)
    if limits.get("no_new_training", True) or not active_scope_id(root):
        return False
    grant = status(root)["active_execution_allowance"]
    return grant["training_remaining"] > 0 and grant["seconds_remaining"] >= 1


def policy(root):
    path = Path(root) / ".local/phase2-policy.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def status(root):
    root = Path(root)
    limits = policy(root)
    if not limits.get("enabled"):
        return {"enabled": False}
    path = root / "runs/phase2/current/resource-budget.json"
    with FileLock(str(root / ".local/phase2-budget.lock")):
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"requests": []}
    rows = state["requests"]
    used = sum(r["charged_seconds"] for r in rows)
    clips = sum(r["new_audio_clips"] for r in rows)
    photos = sum(r["vision_requests"] for r in rows)
    grant = _execution_allowance(limits, rows)
    result = {"enabled": True, "gpu_seconds_used": used, "gpu_seconds_remaining": max(0,limits["gpu_seconds"]-used),
            "new_audio_attempts":clips,"new_audio_remaining":max(0,limits["new_audio_clips"]-clips),
            "vision_attempts":photos,"vision_remaining":max(0,limits["vision_requests"]-photos),
            "requests":len(rows),"new_training_allowed":False,"new_model_download_allowed":False,
            "active_execution_allowance": grant,
            "storage_estimate_bytes":state.get("storage_estimate_bytes",limits.get("conservative_total_bytes_at_start")),
            "storage_warning":state.get("storage_warning",False),"per_request_seconds":300,
            "accounting":"Model subprocess wall time including load, failed attempts included; unfinished reservations remain charged."}


    if grant and grant.get("accounting") == "scope_only_preserve_lifetime":
        caps = grant["limits"]
        result.update(accounting_scope=grant["id"],
            gpu_seconds_used=caps["gpu_seconds"]-grant["seconds_remaining"], gpu_seconds_remaining=grant["seconds_remaining"],
            new_audio_attempts=caps["new_audio_clips"]-grant["audio_remaining"], new_audio_remaining=grant["audio_remaining"],
            vision_attempts=caps["vision_requests"]-grant["vision_remaining"], vision_remaining=grant["vision_remaining"],
            new_training_allowed=not limits.get("no_new_training", True) and grant["training_remaining"] > 0 and grant["seconds_remaining"] >= 1,
            new_model_download_allowed=not limits.get("no_new_model_download", True) and grant["download_bytes_remaining"] > 0,
            training_experiments_remaining=grant["training_remaining"], download_bytes_remaining=grant["download_bytes_remaining"],
            lifetime={"requests": len(rows), "model_seconds": used, "audio_attempts": clips, "vision_attempts": photos},
            historical_limits={"gpu_seconds": limits["gpu_seconds"], "new_audio_clips": limits["new_audio_clips"], "vision_requests": limits["vision_requests"]},
            accounting="Explicit active scope enforced independently of historical caps; lifetime ledger retained. Training includes reload wall time once. Failed attempts and unfinished reservations count.")
        scoped_rows = [row for row in rows if row.get("execution_allowance_id") == grant["id"]]
        result["usage_by_purpose"] = {
            "student_sessions": _student_used([row for row in scoped_rows if row.get("student_session_id")]),
            "development": _student_used([row for row in scoped_rows if not row.get("student_session_id")]),
            "total_approved_scope": _student_used(scoped_rows),
            "meaning": "Student and development counters are separate; both consume the same unchanged approved total."}
    return result


def _save(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def mutable_bytes(root):
    total = 0
    pending = [Path(root) / part for part in ("runs", ".local")]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir():
                            if not entry.is_symlink() and not entry.is_junction():
                                pending.append(entry.path)
                        else:
                            # File symlinks retain the previous target-size rule.
                            # On Windows, this uses current enumeration metadata
                            # for regular files. Entries never outlive this scan.
                            total += entry.stat().st_size
                    except FileNotFoundError:
                        # A concurrently removed file cannot consume storage.
                        continue
        except FileNotFoundError:
            # Missing roots or directories removed during this scan.
            continue
    return total


def reserve(root, payload, timeout, *, timing=None, on_admitted=None):
    root = Path(root)
    limits = policy(root)
    if payload.get("student_session_id") and (not limits.get("enabled") or
            (limits.get("active_execution_allowance") or {}).get("accounting") != "scope_only_preserve_lifetime"):
        raise ResourceBudgetExceeded("학생 수업은 명시적인 기존 승인 상한과 장부가 필요합니다.")
    if not limits.get("enabled"):
        if payload.get("tts_benchmark"):
            raise ResourceBudgetExceeded("TTS 비교는 명시적인 활성 승인과 누적 장부가 필요합니다.")
        return None, timeout
    path = root / "runs/phase2/current/resource-budget.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(root / ".local/phase2-budget.lock")):
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"requests": []}
        settings = limits.get("active_execution_allowance") or {}
        if settings.get("accounting") == "scope_only_preserve_lifetime":
            return _reserve_integrated(root, path, state, limits, payload, timeout, timing=timing, on_admitted=on_admitted)
        charged = sum(r.get("charged_seconds", 0) for r in state["requests"])
        duration = min(float(timeout), 300.0, float(limits.get("per_request_seconds", 300)), limits["gpu_seconds"] - charged)
        if duration < 1:
            raise ResourceBudgetExceeded("이번 회차의 90분 모델 작업 예산을 모두 사용했습니다.")
        clips = len(payload.get("items", [])) if payload["kind"] == "speech_batch" else int(payload["kind"] == "speech")
        photos = int(payload["kind"] == "vision")
        grant = _execution_allowance(limits, state["requests"])
        if payload.get("tts_benchmark") and (not grant or grant["id"] != "20261027-tts-worker-reuse-2calls"):
            raise ResourceBudgetExceeded("이번 TTS worker 비교의 명시적 승인이 없습니다.")
        if (limits.get("active_execution_allowance") or {}).get("runtime_scope") == "tts_session_benchmark":
            if not payload.get("tts_benchmark") or payload["kind"] != "speech_batch" or clips != 1:
                raise ResourceBudgetExceeded("이번 승인은 같은 TTS의 독립 비교 합성 두 번만 허용합니다.")
        if grant is not None:
            # Evaluation/planner warmups and retries are not a separate allowance.
            if payload["kind"] not in {"text", "speech", "speech_batch"}:
                raise ResourceBudgetExceeded("이번 추가 승인은 텍스트 1회와 음성 2개만 허용합니다.")
            if ((payload["kind"] == "text" and grant["text_remaining"] < 1)
                    or clips > grant["audio_remaining"] or photos > grant["vision_remaining"]):
                raise ResourceBudgetExceeded("이번 추가 승인 호출 한도를 소진했습니다. 실패·재시도도 포함합니다.")
            duration = min(duration, grant["seconds_remaining"])
            if duration < 1:
                raise ResourceBudgetExceeded("이번 추가 승인 모델 작업 시간 한도를 소진했습니다.")
        if sum(r["new_audio_clips"] for r in state["requests"]) + clips > limits["new_audio_clips"]:
            raise ResourceBudgetExceeded(f"누적 새 음성 {limits['new_audio_clips']}개 제한에 도달했습니다.")
        if sum(r["vision_requests"] for r in state["requests"]) + photos > limits["vision_requests"]:
            raise ResourceBudgetExceeded(f"누적 사진 추론 {limits['vision_requests']}회 제한에 도달했습니다.")
        # On Windows C is the protected system volume. Tests use an injected
        # path so they do not depend on the host's available disk space.
        if shutil.disk_usage(limits.get("system_volume", "C:/")).free < limits["min_C_free_bytes"]:
            raise ResourceBudgetExceeded("C 드라이브 50GB 여유 공간 조건을 충족하지 못합니다.")
        if "fixed_storage_upper_bound_bytes" in limits:
            scan_started = time.perf_counter()
            usage = limits["fixed_storage_upper_bound_bytes"] + mutable_bytes(root)
            if timing is not None:
                timing["storage_check_seconds"] = time.perf_counter()-scan_started
            # Keep room for at most four small PCM clips and runtime reports.
            if usage + 100_000_000 > limits["max_project_bytes"]:
                raise ResourceBudgetExceeded("프로젝트 귀속 50GB 저장공간 한도에 도달했습니다.")
            state["storage_estimate_bytes"] = usage
            state["storage_warning"] = usage >= limits["warning_project_bytes"]
        ident = uuid.uuid4().hex
        entry = {"id": ident, "kind": payload["kind"], "job_id": payload.get("job_id"),
                 "started_at": datetime.now(timezone.utc).isoformat(), "status": "reserved",
                 "charged_seconds": duration, "request_limit_seconds": duration,
                 "new_audio_clips": clips, "vision_requests": photos}
        if grant is not None:
            entry["execution_allowance_id"] = grant["id"]
        state["requests"].append(entry)
        state["limits"] = limits
        state["accounting"] = "Parent subprocess wall time including model load; conservative GPU-work upper bound. Unfinished reservations remain fully charged. New clip attempts charged even if failed."
        _save(path, state)
    return (root, path, ident, time.monotonic()), duration


def finish(reservation, success):
    if reservation is None:
        return
    root, path, ident, started = reservation
    with FileLock(str(root / ".local/phase2-budget.lock")):
        state = json.loads(path.read_text(encoding="utf-8"))
        row = next(r for r in state["requests"] if r["id"] == ident)
        elapsed = time.monotonic() - started
        row.update(charged_seconds=0 if row.get("time_accounted_by") or row["kind"] == "download" else elapsed,
                   observed_wall_seconds=elapsed,
                   finished_at=datetime.now(timezone.utc).isoformat(),
                   status="completed" if success else "failed_or_cancelled")
        _save(path, state)


def _storage_check(root, limits, state, extra_bytes=100_000_000):
    started = time.perf_counter()
    free = shutil.disk_usage(limits.get("system_volume", "C:/")).free
    record_timing("system_volume_free_check", started)
    if free < limits["min_C_free_bytes"]:
        raise ResourceBudgetExceeded("C 드라이브 50GB 여유 공간 조건을 충족하지 못합니다.")
    if "fixed_storage_upper_bound_bytes" in limits:
        started = time.perf_counter()
        usage = limits["fixed_storage_upper_bound_bytes"] + mutable_bytes(root)
        record_timing("project_mutable_storage_scan", started)
        if usage + extra_bytes > limits["max_project_bytes"]:
            raise ResourceBudgetExceeded("프로젝트 귀속 50GB 저장공간 한도에 도달했습니다.")
        state.update(storage_estimate_bytes=usage, storage_warning=usage >= limits["warning_project_bytes"])


def _reserve_integrated(root, path, state, limits, payload, timeout, *, timing=None, on_admitted=None):
    """Runs under the existing budget lock; no implicit or unlimited scope."""
    grant = _execution_allowance(limits, state["requests"])
    if payload.get("execution_allowance_id") != grant["id"]:
        raise ResourceBudgetExceeded("실행 요청에 현재 승인 scope ID를 명시해야 합니다.")
    kind = payload["kind"]
    if kind not in {"text", "text_batch", "speech", "speech_batch", "vision", "training", "download"} or payload.get("tts_benchmark"):
        raise ResourceBudgetExceeded("이 통합 승인 범위에 없는 실행 종류입니다.")
    items = payload.get("items", [])
    if kind in {"text_batch", "speech_batch"} and (not isinstance(items, list) or not 1 <= len(items) <= 4):
        raise ResourceBudgetExceeded("한 요청의 묶음은 1~4개여야 합니다.")
    texts = len(items) if kind == "text_batch" else int(kind == "text")
    clips = len(items) if kind == "speech_batch" else int(kind == "speech")
    photos, training = int(kind == "vision"), int(kind == "training")
    student_id = payload.get("student_session_id")
    student = None
    if student_id:
        student = _student_view(state, grant, student_id)
        if (not student["exists"] or student["state"] != "active" or student["parent_scope_id"] != grant["id"]
                or kind not in {"text", "speech", "speech_batch", "vision"} or payload.get("time_accounted_by")):
            raise ResourceBudgetExceeded("명시적으로 시작한 같은 학생 세션에서만 수업 작업을 실행할 수 있습니다.")
        remaining = student["effective_remaining"]
        if texts > remaining["text_requests"] or clips > remaining["new_audio_clips"] or photos > remaining["vision_requests"]:
            raise ResourceBudgetExceeded("학생 세션의 실행 한도를 소진했습니다. 실패와 재시도도 포함합니다.")
    if texts > grant["text_remaining"] or clips > grant["audio_remaining"] or photos > grant["vision_remaining"]:
        raise ResourceBudgetExceeded("현재 scope의 호출 한도를 소진했습니다. 실패·재시도도 포함합니다.")
    cap = min(300.0, float(limits.get("per_request_seconds", 300)))
    if training:
        cfg = grant["limits"]["training_per_experiment"]
        steps, epochs = payload.get("max_optimizer_steps"), payload.get("max_epochs")
        if (limits.get("no_new_training", True) or grant["training_remaining"] < 1
                or type(steps) is not int or not 1 <= steps <= cfg["max_optimizer_steps"]
                or not isinstance(epochs, (int, float)) or isinstance(epochs, bool)
                or not math.isfinite(epochs) or not 0 < epochs <= cfg["max_epochs"]):
            raise ResourceBudgetExceeded("학습 실험 수·optimizer step·epoch 승인 한도를 확인하세요.")
        cap = min(7200.0, float(cfg["max_seconds"]))
    if not isinstance(timeout, (float, int)) or not math.isfinite(timeout):
        raise ResourceBudgetExceeded("유한한 요청 시간 한도가 필요합니다.")
    duration = min(float(timeout), cap, grant["seconds_remaining"])
    if student:
        duration = min(duration, student["effective_remaining"]["seconds"])
    accounted_by = payload.get("time_accounted_by")
    if accounted_by:
        parent = next((r for r in state["requests"] if r["id"] == accounted_by), None)
        if (kind != "text" or not parent or parent["kind"] != "training" or parent["status"] != "reserved"
                or parent.get("execution_allowance_id") != grant["id"]):
            raise ResourceBudgetExceeded("재로딩 추론은 진행 중인 같은 scope 학습 예약에만 연결할 수 있습니다.")
        elapsed = (datetime.now(timezone.utc)-datetime.fromisoformat(parent["started_at"])).total_seconds()
        duration = min(float(timeout), 300.0, parent["request_limit_seconds"]-elapsed)
    download_bytes = 0
    candidate_fields = {}
    if kind == "download":
        download_bytes = payload.get("download_bytes")
        if (limits.get("no_new_model_download", True) or type(download_bytes) is not int
                or not 0 < download_bytes <= grant["download_bytes_remaining"]):
            raise ResourceBudgetExceeded("다운로드 바이트 승인 한도를 확인하세요.")
        from urllib.parse import urlparse
        url = urlparse(payload.get("official_source_url", ""))
        if url.scheme != "https" or not url.hostname or not payload.get("official_source_verified"):
            raise ResourceBudgetExceeded("다운로드 전에 공식 HTTPS 출처와 이용 조건을 확인해야 합니다.")
        candidate = payload.get("candidate_kind")
        if candidate is not None:
            if candidate not in {"text", "tts"} or not isinstance(payload.get("candidate_id"), str) or not payload["candidate_id"]:
                raise ResourceBudgetExceeded("새 모델 후보 종류와 식별자가 필요합니다.")
            seen = any(r.get("candidate_kind") == candidate and r.get("candidate_id") == payload["candidate_id"]
                       and r.get("execution_allowance_id") == grant["id"] for r in state["requests"])
            field = "new_"+candidate+"_candidates"
            if not seen and grant[field+"_remaining"] < 1:
                raise ResourceBudgetExceeded("새 모델 후보 한도를 소진했습니다.")
            candidate_fields.update({field: int(not seen), "candidate_kind": candidate, "candidate_id": payload["candidate_id"]})
        duration = 0.0
    elif duration < 1:
        raise ResourceBudgetExceeded("현재 scope의 모델 작업 시간 한도를 소진했습니다.")
    # Caps/scope are valid, but no reservation has been written yet. One normal
    # student text activity may refresh its existing owner's bounded idle timer.
    if on_admitted is not None and kind == "text" and student:
        on_admitted()
    storage_started = time.perf_counter()
    _storage_check(root, limits, state, download_bytes + 100_000_000)
    if timing is not None:
        timing["storage_check_seconds"] = time.perf_counter()-storage_started
    ident = uuid.uuid4().hex
    row = {"id": ident, "kind": kind, "job_id": payload.get("job_id"), "execution_allowance_id": grant["id"],
        "started_at": datetime.now(timezone.utc).isoformat(), "status": "reserved",
        "charged_seconds": 0 if accounted_by else duration, "request_limit_seconds": duration,
        "new_audio_clips": clips, "vision_requests": photos, "text_requests": texts,
        "training_experiments": training, "download_bytes": download_bytes, **candidate_fields}
    if student:
        row.update(student_session_id=student_id, usage_purpose="student_session")
    if accounted_by:
        row["time_accounted_by"] = accounted_by
    if training:
        row.update(max_optimizer_steps=steps, max_epochs=epochs)
    if kind == "download":
        row["official_source_url"] = payload["official_source_url"]
    state["requests"].append(row)
    state["limits"] = limits
    state["accounting"] = "Append-only reservations across approvals. Scope caps exclude historical usage; lifetime totals retained. Failures count. Nested training reload time is charged once by its parent."
    _save(path, state)
    return (root, path, ident, time.monotonic()), duration


def reserve_included_text(training_reservation, job_id=None):
    """Count a separate reload generation within the training wall reservation."""
    if training_reservation is None:
        return None, 300.0
    root, path, ident, _ = training_reservation
    with FileLock(str(root / ".local/phase2-budget.lock")):
        state = json.loads(path.read_text(encoding="utf-8"))
        parent = next(r for r in state["requests"] if r["id"] == ident)
        scope = parent.get("execution_allowance_id")
    return reserve(root, {"kind": "text", "job_id": job_id,
        "execution_allowance_id": scope, "time_accounted_by": ident}, 300)


def finish_download(reservation, downloaded_bytes, success):
    """Unknown interrupted transfer bytes stay reserved; known actuals are recorded."""
    root, path, ident, started = reservation
    with FileLock(str(root / ".local/phase2-budget.lock")):
        state = json.loads(path.read_text(encoding="utf-8"))
        row = next(r for r in state["requests"] if r["id"] == ident)
        if row["kind"] != "download" or type(downloaded_bytes) is not int or not 0 <= downloaded_bytes <= row["download_bytes"]:
            raise ResourceBudgetExceeded("다운로드 실측이 예약 범위를 벗어났습니다.")
        row.update(download_bytes=downloaded_bytes, charged_seconds=0,
            observed_wall_seconds=time.monotonic()-started,
            finished_at=datetime.now(timezone.utc).isoformat(), status="completed" if success else "failed_or_cancelled")
        _save(path, state)
