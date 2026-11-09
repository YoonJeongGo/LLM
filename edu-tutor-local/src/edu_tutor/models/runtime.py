"""Bounded subprocess inference: the API never imports torch or holds weights."""
from __future__ import annotations

import importlib.util
import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from edu_tutor.paths import initialize, project_root


class ModelUnavailable(RuntimeError):
    pass


class GenerationIncomplete(RuntimeError):
    pass


def model_status(root=None):
    root = project_root(root)
    folder = root / ".local/models/text"
    manifest = folder / "model-manifest.json"
    result = {"model_id": "Qwen/Qwen3-1.7B", "installed": False, "ready": False,
              "revision": None, "reason": "모델 미설치", "validation": "not_run", "modules": []}
    if manifest.exists():
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        installed = meta.get("download_complete", False) and all((folder / f["path"]).is_file() for f in meta["files"])
        result.update(installed=installed, revision=meta["revision"], license=meta["license"])
        missing = [name for name in ("torch", "transformers", "bitsandbytes", "accelerate") if importlib.util.find_spec(name) is None]
        result.update(ready=installed and not missing, reason="로컬 GPU 실행 가능 여부는 실제 검증 결과를 확인하세요." if not missing else "런타임 미설치: " + ", ".join(missing))
    structure = folder / "runtime-structure.json"
    if structure.exists():
        result.update(json.loads(structure.read_text(encoding="utf-8")))
    from .registry import selection
    result["active_adapter"] = selection(root)["active_adapter"]
    from .text_session import status as resident_status
    result["text_session"] = resident_status(root)
    result["resident"] = result["text_session"]["resident"]
    if result["resident"]:
        result["structure_notice"] = "현재 텍스트 worker가 모델을 보유 중입니다. 유휴/전체 수명 제한과 취소 정책이 적용됩니다."
    return result


def _read_pipe(stream, events, stopped=None):
    def put(value):
        while stopped is None or not stopped.is_set():
            try:
                events.put(value, timeout=0.1)
                return True
            except queue.Full:
                continue
        return False

    try:
        for line in stream:
            if not put(line):
                break
    finally:
        put(None)


def run_worker(payload, *, root=None, cancel_event=None, timeout=300):
    request_started = time.perf_counter()
    request_deadline = request_started + float(timeout)
    from .budget import reserve, finish
    from .execution_context import bind_scope
    payload = bind_scope(payload)
    from edu_tutor.speech import session, direct
    from . import text_session
    root = initialize(root)
    def pending(deadline):
        # A queued/reserving request owns no child yet. Never cancel a different
        # request's idle model as cleanup for this request's preflight failure.
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Request cancelled during preflight; no model worker started")
        if time.perf_counter() >= deadline:
            raise TimeoutError("Request deadline consumed by queue/preflight; no model worker started")
    # Dispatch is shared with resident speech. A different model may not start
    # while an idle TTS child still owns GPU memory and its OS lease.
    with session.execution_slot(root, cancel_event, timeout) as dispatch:
        pending(request_deadline)
        reuse = session.enabled(root, payload)
        resident_text = text_session.enabled(root, payload)
        system_speech = direct.enabled(payload)
        reservation_timing = {}
        reservation_started = time.perf_counter()
        pending(request_deadline)
        def admitted_activity():
            pending(request_deadline)
            owner = text_session.status(root).get("session")
            if owner is not None:
                text_session.refresh_preflight_idle(payload, root=root,
                    instance_id=owner["instance_id"], previous_request_id=owner.get("latest_request_id"),
                    cancel_event=cancel_event, deadline=request_deadline)
            pending(request_deadline)
        reservation, limit = reserve(root, payload, min(dispatch["remaining_seconds"], request_deadline-time.perf_counter()),
                                     timing=reservation_timing,
                                     on_admitted=admitted_activity if resident_text and payload.get("student_session_id") else None)
        reserved_at = time.perf_counter()
        success = False
        try:
            worker = direct.run if system_speech else text_session.run if resident_text else session.run if reuse else _run_worker
            # Session and direct CPU routes keep six cleanup seconds internally.
            # The legacy process path can wait 5+5 seconds and join for two.
            cleanup_seconds = 0 if system_speech or resident_text or reuse else 12
            work_deadline = min(reserved_at + limit, request_deadline) - cleanup_seconds
            pending(work_deadline)
            # Only an admitted GPU transition may release the observed owners.
            # CPU Heami requires no GPU memory and must leave both owners alone.
            if not system_speech:
                if not resident_text:
                    owner = text_session.status(root).get("session")
                    pending(work_deadline)
                    if owner is not None:
                        text_session.close(root, reason="non_text_model_dispatch", instance_id=owner["instance_id"])
                if not reuse:
                    owner = session.status(root)
                    pending(work_deadline)
                    if owner.get("instance_id") is not None:
                        session.close(root, session_key=owner["session_key"],
                                      job_id=owner.get("latest_job_id"), reason="non_session_model_dispatch")
            pending(work_deadline)
            dispatch_started = time.perf_counter()
            worker_timeout = work_deadline - dispatch_started
            preflight = {"clock": "perf_counter", "queue_wait_seconds": dispatch["queue_wait_seconds"],
                "reservation_seconds": reserved_at-reservation_started,
                "storage_check_seconds": reservation_timing.get("storage_check_seconds"),
                "resource_transition_seconds": dispatch_started-reserved_at,
                "total_preflight_seconds": dispatch_started-request_started,
                "worker_timeout_seconds": worker_timeout, "outer_cleanup_reserve_seconds": cleanup_seconds,
                "request_timeout_seconds": timeout, "storage_cpu_in_model_budget_charge": False}
            request = {**payload, "parent_queue_wait_seconds": dispatch["queue_wait_seconds"], "parent_dispatch_timing": preflight}
            for event in worker(request, root=root, cancel_event=cancel_event, timeout=worker_timeout):
                success = success or event.get("type") == "done"
                if event.get("type") in {"metadata", "audio"}:
                    event["dispatch_timing"] = {**preflight, "request_start_to_event_seconds": time.perf_counter()-request_started}
                yield event
        finally:
            finish(reservation, success)


def _run_worker(payload, *, root=None, cancel_event=None, timeout=300):
    root = initialize(root)
    ident = uuid.uuid4().hex
    folder = root / "runs" / ("runtime-" + ident)
    folder.mkdir()
    cancel_path = folder / "cancel.requested"
    payload = {**payload, "root": str(root), "cancel_path": str(cancel_path), "run_dir": str(folder)}
    payload.setdefault("job_id", ident)
    env = os.environ.copy()
    env.update(PYTHONUTF8="0", PYTHONIOENCODING="utf-8", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1", TOKENIZERS_PARALLELISM="false")
    # Also works from a source checkout without an editable installation.
    env["PYTHONPATH"] = str(root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    started = time.monotonic()
    cancel_at = None
    # The observation worker already uses a bounded, nonblocking publisher.
    # Bound its second IPC buffer too. The consumer is the in-memory broker,
    # never a browser socket; slow SSE clients cannot backpressure generation.
    events = queue.Queue(maxsize=32 if payload.get("observation") is not None else 0)
    reader_stopped = threading.Event()
    with (folder / "stderr.log").open("w", encoding="utf-8") as errors:
        process = subprocess.Popen([sys.executable, "-m", "edu_tutor.models.worker"], cwd=root,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                                   text=True, encoding="utf-8", env=env,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        process.stdin.close()
        reader = threading.Thread(target=_read_pipe, args=(process.stdout, events, reader_stopped), daemon=True)
        reader.start()
        success = False
        try:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    if cancel_at is None:
                        cancel_path.touch()
                        cancel_at = time.monotonic()
                    if time.monotonic() - cancel_at > 5:
                        return
                if time.monotonic() - started > timeout:
                    cancel_path.touch()
                    if process.poll() is None:
                        process.terminate()
                    raise TimeoutError(f"모델 작업이 {timeout}초 제한에 도달했습니다. 결과는 미완료입니다.")
                try:
                    line = events.get(timeout=0.1)
                except queue.Empty:
                    continue
                if line is None:
                    break
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "error":
                    raise ModelUnavailable(event["message"])
                if event.get("type") == "done":
                    success = True
                if cancel_at is None:
                    yield event
            process.wait(timeout=5)
            if cancel_at is None and (process.returncode != 0 or not success):
                raise ModelUnavailable(f"Model worker unavailable (exit={process.returncode}); 로그: {folder.name}/stderr.log")
        finally:
            reader_stopped.set()
            # Only terminate the child created by this exact Popen; never a guessed PID.
            if process.poll() is None:
                cancel_path.touch()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=5)
            process.stdout.close()
            reader.join(timeout=2)


def generate(messages, cancel_event=None, adapter=None, root=None, job_id=None, max_new_tokens=512, metadata_out=None):
    if not messages or len(messages) > 30:
        raise ValueError("대화는 1~30개 메시지여야 합니다.")
    if any(m.get("role") not in {"system", "user", "assistant"} or not isinstance(m.get("content"), str) for m in messages):
        raise ValueError("잘못된 대화 형식입니다.")
    if sum(len(m["content"]) for m in messages) > 24000:
        raise ValueError("입력이 너무 깁니다. 대화나 자료를 줄여 주세요.")
    from .text_precision import policy as precision_policy, validate_inference
    precision = precision_policy(root)["precision"]
    state = model_status(root)
    if not state["ready"]:
        raise ModelUnavailable("Model unavailable: " + state["reason"])
    from .registry import adapters, resolve_adapter
    adapter_path = resolve_adapter(adapter, root)
    # Capture the exact resolved selection once. Later UI selection changes must
    # never relabel a historical answer or replace actual worker provenance.
    adapter_id = "base" if adapter_path is None else next(
        (item["id"] for item in adapters(root)
         if Path(item["path"]).resolve() == Path(adapter_path).resolve()), None)
    payload = {"kind": "text", "messages": messages, "adapter": adapter_path,
               "max_new_tokens": max(16, min(int(max_new_tokens), 768)), "precision": precision}
    if job_id:
        payload["job_id"] = job_id
    for event in run_worker(payload, root=root, cancel_event=cancel_event):
        if event.get("type") == "delta":
            yield event["text"]
        elif event.get("type") == "metadata":
            if event.get("requested_precision") != precision:
                raise ModelUnavailable("Text worker returned a different requested precision")
            actual_inference = validate_inference(event.get("inference"), precision, adapter_path)
            if metadata_out is not None:
                metadata_out.update({key: event.get(key) for key in
                    ("model_id", "revision", "finish_reason", "input_tokens", "output_tokens", "timestamp", "eos_token_ids")})
                metadata_out.update({key: event[key] for key in
                    ("elapsed_seconds", "model_load_seconds", "generation_seconds", "model_load_count", "peak_vram_bytes",
                     "worker_pid", "process_start_time", "instance_id", "model_instance_id", "model_python_id",
                     "cumulative_model_load_count", "request_model_load_count", "model_resident", "parent_timing", "transport_timing", "dispatch_timing") if key in event})
                metadata_out.update(source="worker_metadata",
                    adapter_id=adapter_id if event.get("adapter") == adapter_path else None,
                    requested_precision=precision, inference=actual_inference)
            if event.get("finish_reason") != "eos":
                raise GenerationIncomplete("답변이 토큰/시간 제한 또는 취소로 끝났습니다. 부분 출력은 완성된 답변이 아닙니다.")
