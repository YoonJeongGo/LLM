"""One real chat, externally coordinated server restart, then read-only recovery.

The start phase never repeats inference. The check phase never starts inference
or stops a process. A root coordinator owns the server stop/restart operation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {"succeeded", "failed", "interrupted", "cancelled", "blocked"}

def now():
    return datetime.now(timezone.utc).isoformat()

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def request(client, method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return response.json()

def alive_identity(pid, started):
    try:
        return psutil.Process(pid).is_running() and abs(psutil.Process(pid).create_time() - started) < .01
    except psutil.NoSuchProcess:
        return False

def os_lease_is_free():
    """Probe the existing OS lock without rewriting stale lease metadata."""
    with (ROOT / ".local/gpu.lock").open("r+b") as handle:
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(handle, fcntl.LOCK_UN)
            return True
        except OSError:
            return False

def start(client):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = ROOT / "runs/integration-live" / (stamp + "-inflight-recovery-" + uuid4().hex[:6])
    folder.mkdir()
    prior = read(ROOT / "runs/integration-live/latest-text.json")
    old_export = request(client, "GET", f"/api/sessions/{prior['session_id']}/export")
    old_export.pop("exported_at", None)
    old_training = [item for item in request(client, "GET", "/api/jobs") if item["kind"] == "training"]
    if any(job["state"] not in TERMINAL for job in old_training):
        raise RuntimeError("An existing training job is still active; no chat started")
    api_lease = read(ROOT / ".local/api-lease.json")
    session = request(client, "POST", "/api/sessions", json={"title": "실제 생성 중 재시작 복구 검사"})
    request_id = "inflight-recovery-" + uuid4().hex
    submitted = request(client, "POST", f"/api/sessions/{session['id']}/messages", json={
        "content": "데이터베이스의 관계, 기본키, 외래키, NULL, COUNT, GROUP BY, JOIN을 초보자가 학습할 수 있도록 순서대로 아주 자세히 설명해주세요. 각 개념마다 정의, 표 예시, SQL 예시, 흔한 실수, 확인 문제를 포함하고 충분히 긴 한국어 설명을 작성해주세요.",
        "request_id": request_id, "use_rag": False, "adapter": "base"})
    data = {"tier": "T2", "status": "waiting_for_actual_load", "started_at": now(), "folder": str(folder),
            "scope": "Actual in-flight chat recovery; one inference request only",
            "inference_requests": 1, "job_id": submitted["job_id"], "session_id": session["id"],
            "old_server_identity": api_lease, "old_chat": old_export, "old_training": old_training,
            "human_review": "not_reviewed"}
    write(ROOT / "runs/integration-live/latest-recovery.json", {"folder": str(folder)})
    write(folder / "checkpoint.json", data)
    print(json.dumps({"event": "submitted_once", "job_id": submitted["job_id"], "artifact": str(folder)}), flush=True)
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        job = request(client, "GET", f"/api/jobs/{submitted['job_id']}")
        if job["state"] in TERMINAL:
            data.update(status="failed_before_external_restart", job_at_failure=job)
            write(folder / "checkpoint.json", data)
            raise RuntimeError("The one chat ended before the restart checkpoint; no retry")
        try:
            lease = read(ROOT / ".local/gpu-lease.json")
            structure_path = ROOT / ".local/models/text/runtime-structure.json"
            raw_structure = structure_path.read_bytes()
            structure = json.loads(raw_structure)
            loaded_after_submit = datetime.fromisoformat(structure["last_loaded_at"]) > datetime.fromisoformat(job["created_at"])
            if (lease.get("state") == "held" and lease.get("job_id") == submitted["job_id"]
                and alive_identity(lease["pid"], lease["process_start"]) and loaded_after_submit):
                (folder / "actual-loaded-structure.json").write_bytes(raw_structure)
                data.update(status="ready_for_external_restart", ready_at=now(), job_at_ready=job,
                            gpu_child_identity=lease, actual_loaded_at=structure["last_loaded_at"],
                            full_structure_sha256=hashlib.sha256(raw_structure).hexdigest(),
                            module_count=len(structure["modules"]), module_count_total=structure.get("module_count_total"),
                            modules_truncated=structure.get("modules_truncated"))
                write(folder / "checkpoint.json", data)
                print(json.dumps({"event": "READY_STOP_OWNED_SERVER", "job_id": job["id"],
                    "server_pid": api_lease["pid"], "child_pid": lease["pid"], "child_start": lease["process_start"],
                    "loaded_at": structure["last_loaded_at"], "module_count": len(structure["modules"]),
                    "modules_truncated": structure.get("modules_truncated"), "artifact": str(folder)}, ensure_ascii=False), flush=True)
                return
        except (OSError, ValueError, KeyError):
            pass  # Metadata may be in the middle of its bounded write.
        time.sleep(.1)
    request(client, "POST", f"/api/jobs/{submitted['job_id']}/cancel")
    data.update(status="load_checkpoint_timeout", finished_at=now())
    write(folder / "checkpoint.json", data)
    raise TimeoutError("The single chat did not reach its load checkpoint in 150 seconds; cancellation requested")

def check(client):
    folder = Path(read(ROOT / "runs/integration-live/latest-recovery.json")["folder"])
    data = read(folder / "checkpoint.json")
    if data["status"] != "ready_for_external_restart":
        raise RuntimeError("There is no real in-flight ready checkpoint")
    child = data["gpu_child_identity"]
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            lease = read(ROOT / ".local/api-lease.json")
            job = request(client, "GET", f"/api/jobs/{data['job_id']}")
            gpu = read(ROOT / ".local/gpu-lease.json")
            child_alive = alive_identity(child["pid"], child["process_start"])
            changed = lease.get("pid") != data["old_server_identity"]["pid"] or lease.get("process_start") != data["old_server_identity"].get("process_start")
            released = not child_alive and os_lease_is_free()
            if changed and job["state"] in TERMINAL and released:
                old_chat = request(client, "GET", f"/api/sessions/{data['old_chat']['session']['id']}/export")
                old_chat.pop("exported_at", None)
                preserved_training = all(request(client, "GET", f"/api/jobs/{item['id']}") == item for item in data["old_training"])
                current_messages = request(client, "GET", f"/api/sessions/{data['session_id']}/messages")
                passed = job["state"] == "interrupted" and old_chat == data["old_chat"] and preserved_training and not any(m["role"] == "assistant" for m in current_messages)
                report = {"tier": "T2", "status": "passed" if passed else "failed", "timestamp": now(),
                          "scope": data["scope"], "inference_requests": 1, "checkpoint": "checkpoint.json",
                          "old_server": data["old_server_identity"], "new_server": lease,
                          "old_child_identity": child, "old_child_exited": not child_alive, "gpu_lease_after": gpu,
                          "gpu_os_lock_free": released, "lease_release_verification": "OS lock probe plus exited process identity; stale JSON is not authoritative",
                          "job_after_restart": job, "old_chat_exactly_preserved": old_chat == data["old_chat"],
                          "training_records_exactly_preserved": preserved_training, "training_record_count": len(data["old_training"]),
                          "interrupted_session_messages": current_messages, "human_review": "not_reviewed"}
                write(folder / "report.json", report)
                print(json.dumps({"status": report["status"], "job_state": job["state"], "old_child_exited": not child_alive,
                                  "artifact": str(folder / "report.json")}), flush=True)
                return 0 if passed else 2
        except (httpx.HTTPError, OSError, ValueError):
            pass
        time.sleep(.5)
    write(folder / "report.json", {"tier": "T2", "status": "failed", "reason": "Restart/release observation exceeded 180 seconds", "timestamp": now()})
    raise TimeoutError("Restart/release observation exceeded 180 seconds; no new inference started")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["start", "check"], required=True)
    args = parser.parse_args()
    token = (ROOT / ".local/auth-token").read_text(encoding="utf-8").strip()
    with httpx.Client(base_url="http://127.0.0.1:8000", headers={"Authorization": "Bearer " + token},
                      timeout=10, trust_env=False, follow_redirects=False) as client:
        result = start(client) if args.phase == "start" else check(client)
    raise SystemExit(result or 0)
