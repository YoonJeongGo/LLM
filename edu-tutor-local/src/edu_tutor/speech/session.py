"""Opt-in TTS child lifetime and serialized dispatch; the API holds no tensors.

The child owns the existing OS GPU lease even while idle. Only the exact Popen
created here may be stopped. A failed request is never transparently retried.
"""
from __future__ import annotations

import atexit
import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class SessionUnavailable(RuntimeError):
    pass


_REGISTRY_LOCK = threading.RLock()
_COORDINATORS = {}


def _now():
    return datetime.now(timezone.utc).isoformat()


def policy(root):
    path = Path(root) / ".local/tts-session-policy.json"
    value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    mode = value.get("mode", "per_request")
    idle = float(value.get("idle_seconds", 30))
    maximum = float(value.get("max_session_seconds", 600))
    if mode not in {"per_request", "session"} or not 1 <= idle <= 120 or not 1 <= maximum <= 600:
        raise ValueError("잘못된 TTS 세션 설정입니다. mode와 유휴/전체 수명 한도를 확인하세요.")
    return {"mode": mode, "idle_seconds": idle, "max_session_seconds": maximum}


def enabled(root, payload):
    return (payload.get("kind") in {"speech", "speech_batch"}
            and isinstance(payload.get("tts_session_key"), str)
            and 0 < len(payload["tts_session_key"]) <= 500
            and (payload.get("tts_benchmark") is True or policy(root)["mode"] == "session"))


class _Coordinator:
    def __init__(self):
        self.dispatch = threading.RLock()
        self.state = threading.RLock()
        self.current = None
        self.last = None


def _coordinator(root):
    key = str(Path(root).resolve()).casefold() if os.name == "nt" else str(Path(root).resolve())
    with _REGISTRY_LOCK:
        return _COORDINATORS.setdefault(key, _Coordinator())


@contextmanager
def execution_slot(root, cancel_event=None, timeout=300):
    """Serialize all model dispatch; queued waiting precedes budget reservation."""
    state = _coordinator(root)
    started = time.monotonic()
    while True:
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Model request cancelled before dispatch")
        remaining = float(timeout) - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("Model dispatch queue timeout; no worker started")
        if state.dispatch.acquire(timeout=min(.1, remaining)):
            break
    try:
        waited = time.monotonic() - started
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Model request cancelled before dispatch")
        yield {"queue_wait_seconds": waited, "remaining_seconds": max(0, float(timeout)-waited)}
    finally:
        state.dispatch.release()


# Public alias for non-runtime jobs (training/diagnostics) using the same queue.
dispatch = execution_slot


def _python_command(root, *, module=None, script=None, args=()):
    """Launch the actual interpreter, avoiding Windows venv redirector children.

The parent already resolved the project virtualenv's paths. Restore that same
path/prefix environment in the direct child, without installing or changing
packages. This makes the Popen handle refer to the process holding the GPU.
"""
    executable = getattr(sys, "_base_executable", None) if os.name == "nt" else sys.executable
    if not executable or not Path(executable).is_file():
        raise SessionUnavailable("Cannot identify the actual Python interpreter for owned worker cleanup")
    bootstrap = (
        "import json,os,runpy,sys; "
        "spec=json.loads(sys.argv[1]); "
        "sys.path[:]=json.loads(os.environ['EDU_TTS_PARENT_SYS_PATH']); "
        "sys.prefix=os.environ['EDU_TTS_PARENT_PREFIX']; "
        "sys.exec_prefix=os.environ['EDU_TTS_PARENT_EXEC_PREFIX']; "
        "sys.argv=[spec['target'],*spec['args']]; "
        "runpy.run_module(spec['target'],run_name='__main__') if spec['module'] "
        "else runpy.run_path(spec['target'],run_name='__main__')"
    )
    spec = {"module": bool(module), "target": module or str(script), "args": list(args)}
    return [str(executable), "-u", "-c", bootstrap, json.dumps(spec, ensure_ascii=False)]


def _worker_command(root):
    """Small transport seam used by CPU tests with a non-model child."""
    return _python_command(root, module="edu_tutor.speech.session_worker")


def _save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


class _Session:
    def __init__(self, root, key, settings):
        self.root = Path(root).resolve()
        self.key = key
        self.settings = settings
        self.instance_id = uuid.uuid4().hex
        self.started_at = _now()
        self.started = time.monotonic()
        self.folder = self.root / "runs" / ("tts-session-"+self.instance_id)
        self.folder.mkdir(parents=True)
        self.events = queue.Queue()
        self.reader_error = None
        self.closed = threading.Event()
        self.active = False
        self.latest_job_id = None
        self.cancel_path = None
        self.idle_timer = None
        self.lifetime_timer = None
        self.requests = 0
        self.error_stream = (self.folder / "stderr.log").open("w", encoding="utf-8")
        env = os.environ.copy()
        env.update(PYTHONUTF8="0", PYTHONIOENCODING="utf-8", HF_HUB_OFFLINE="1",
                   TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1",
                   TOKENIZERS_PARALLELISM="false")
        env["PYTHONPATH"] = str(self.root / "src") + os.pathsep + env.get("PYTHONPATH", "")
        paths = [str(self.root / "src"), *[str(Path(p).resolve()) if p else str(self.root) for p in sys.path]]
        env["EDU_TTS_PARENT_SYS_PATH"] = json.dumps(list(dict.fromkeys(paths)), ensure_ascii=False)
        env["EDU_TTS_PARENT_PREFIX"] = sys.prefix
        env["EDU_TTS_PARENT_EXEC_PREFIX"] = sys.exec_prefix
        try:
            self.process = subprocess.Popen(_worker_command(self.root), cwd=self.root,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.error_stream,
                text=True, encoding="utf-8", env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except BaseException:
            self.error_stream.close()
            raise
        self.record = {"instance_id": self.instance_id, "launcher_pid": self.process.pid, "worker_pid": None,
            "parent_pid": os.getpid(), "started_at": self.started_at, "session_key": key,
            "status": "started_without_model_request", "settings": settings,
            "launch_mode": "direct_actual_interpreter_with_parent_virtualenv_paths",
            "parent_python_executable": sys.executable, "worker_python_executable": _worker_command(self.root)[0],
            "gpu_memory_ownership": "Child keeps OS GPU lease while loaded and idle"}
        self._record()
        self.reader = threading.Thread(target=self._read, daemon=True, name="tts-session-reader")
        self.reader.start()

    def _record(self, **fields):
        self.record.update(fields)
        _save(self.folder / "session.json", self.record)

    def _read(self):
        try:
            for line in self.process.stdout:
                self.events.put(line)
        except (UnicodeError, OSError) as exc:
            # Keep strict UTF-8: corrupt protocol bytes must fail the request,
            # not be silently replaced or mistaken for a normal worker EOF.
            self.reader_error = {"at": _now(), "operation": "read_utf8_protocol_stdout",
                "instance_id": self.instance_id, "worker_pid": self.process.pid,
                "error_type": type(exc).__name__, "message": str(exc)}
            try:
                _save(self.folder / "reader-error.json", self.reader_error)
            except OSError as write_error:
                self.reader_error["evidence_write_error"] = f"{type(write_error).__name__}: {write_error}"
            print(f"TTS protocol reader failed: {type(exc).__name__}: {exc}; "
                  f"evidence: {self.folder / 'reader-error.json'}", file=sys.stderr, flush=True)
        finally:
            self.events.put(None)

    def send(self, value):
        if self.closed.is_set() or self.process.poll() is not None:
            raise SessionUnavailable("TTS session worker is not alive; no automatic restart")
        self.process.stdin.write(json.dumps(value, ensure_ascii=False)+"\n")
        self.process.stdin.flush()

    def stop(self, reason):
        if (self.closed.is_set() and self.process.poll() is not None
                and self.record.get("process_exit_confirmed") is True):
            return
        # Mark closed before sending anything: no late output can be published.
        self.closed.set()
        for timer in (self.idle_timer, self.lifetime_timer):
            if timer:
                timer.cancel()
        if self.cancel_path:
            self.cancel_path.touch(exist_ok=True)
        exit_confirmed = False
        cleanup_errors = []
        try:
            if self.process.poll() is None:
                try:
                    self.process.stdin.write(json.dumps({"command": "shutdown", "instance_id": self.instance_id,
                                                         "request_id": None, "reason": reason})+"\n")
                    self.process.stdin.flush()
                    self.process.stdin.close()
                except (BrokenPipeError, OSError, ValueError):
                    pass
                try:
                    self.process.wait(timeout=.5 if self.active else 1)
                except subprocess.TimeoutExpired:
                    # Uses the owned process handle; never kills a looked-up PID.
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=2)
            exit_confirmed = self.process.poll() is not None
        finally:
            # An exited child can leave a Windows pipe that raises EINVAL on
            # close. That local stream error must not erase confirmed process
            # termination or leave the dispatch registry permanently blocked.
            exit_confirmed = self.process.poll() is not None
            release_report = None
            if exit_confirmed:
                self.reader.join(timeout=1)
                for name, stream in (("stdout", self.process.stdout), ("stdin", self.process.stdin)):
                    try:
                        if not stream.closed:
                            stream.close()
                    except (OSError, ValueError) as exc:
                        cleanup_errors.append({"stream": name, "error": f"{type(exc).__name__}: {exc}"})
                # Cleanup reports are evidence only. Closing forbids publishing
                # any late audio even if it was written before cancellation.
                while True:
                    try:
                        line = self.events.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        value = json.loads(line) if line is not None else None
                    except (TypeError, json.JSONDecodeError):
                        continue
                    if isinstance(value, dict) and value.get("type") == "closed" and value.get("instance_id") == self.instance_id:
                        release_report = value
            try:
                self.error_stream.close()
            except (OSError, ValueError) as exc:
                cleanup_errors.append({"stream": "stderr", "error": f"{type(exc).__name__}: {exc}"})
            self._record(status="closed" if exit_confirmed else "termination_unconfirmed", reason=reason,
                         finished_at=_now(), process_exit_code=self.process.poll(),
                         process_exit_confirmed=exit_confirmed,
                         gpu_memory_retained=False if exit_confirmed else "unknown",
                         child_release_report=release_report, stream_cleanup_errors=cleanup_errors,
                         reader_error=self.reader_error)


def close(root, session_key=None, reason="explicit_close", *, job_id=None):
    state = _coordinator(root)
    with state.state:
        current = state.current
        if current is None or (session_key is not None and current.key != session_key):
            return {"closed": False, "reason": "no_matching_owned_session"}
        if job_id is not None and current.latest_job_id != job_id:
            return {"closed": False, "reason": "no_matching_owned_job"}
        # Holding this short ownership lock prevents a replacement child from
        # being published until the previous owned handle has actually exited.
        current.stop(reason)
        if current.process.poll() is None or current.record.get("process_exit_confirmed") is not True:
            raise SessionUnavailable("Owned TTS worker termination is unconfirmed; new model dispatch is blocked")
        state.current = None
        state.last = dict(current.record)
        return {"closed": True, **current.record}


def status(root):
    state = _coordinator(root)
    with state.state:
        current = state.current
        if current is None:
            return {"resident": False, "last_session": state.last, "policy": policy(root)}
        return {"resident": current.process.poll() is None and not current.closed.is_set(),
                "active_request": current.active, "requests": current.requests,
                "latest_job_id": current.latest_job_id,
                "launcher_pid": current.process.pid, "worker_pid": current.record.get("worker_pid"), "instance_id": current.instance_id,
                "session_key": current.key, "started_at": current.started_at,
                "gpu_memory_retained": current.process.poll() is None,
                "session_record": str(current.folder / "session.json"), "policy": policy(root)}


def _expire(root, instance_id, reason):
    state = _coordinator(root)
    with state.state:
        current = state.current
        if current is None or current.instance_id != instance_id:
            return
        if reason == "idle_expired" and current.active:
            return
        close(root, current.key, reason)


def run(payload, *, root, cancel_event=None, timeout=300):
    """Process one already-reserved request; a second call reuses the child."""
    if not enabled(root, payload):
        raise ValueError("TTS session reuse is not enabled for this request")
    root = Path(root).resolve()
    key = payload["tts_session_key"]
    settings = policy(root)
    with execution_slot(root, cancel_event, timeout) as dispatch:
        started = time.monotonic()
        # Leave bounded cleanup time inside the reserved request duration.
        limit = dispatch["remaining_seconds"]
        if limit <= 6:
            raise TimeoutError("TTS request has insufficient time for safe worker cleanup; no model was started")
        deadline = started + limit - 6.0
        state = _coordinator(root)
        request_id = uuid.uuid4().hex
        with state.state:
            current = state.current
            expected = payload.get("expected_instance_id")
            if expected is not None and (current is None or current.key != key
                    or current.instance_id != expected or current.process.poll() is not None
                    or current.closed.is_set()):
                raise SessionUnavailable("Required warm TTS instance is unavailable; reloading is forbidden")
            if current and current.key != key:
                close(root, reason="session_owner_changed")
                current = None
            if current and current.process.poll() is not None:
                close(root, key, "worker_died_before_request")
                raise SessionUnavailable("TTS session worker died; request was not retried")
            if current is None:
                current = _Session(root, key, settings)
                state.current = current
                timer = threading.Timer(settings["max_session_seconds"], _expire,
                                        (root, current.instance_id, "maximum_session_lifetime"))
                timer.daemon = True
                current.lifetime_timer = timer
                timer.start()
            if current.idle_timer:
                current.idle_timer.cancel()
            current.active = True
            current.requests += 1
            current.latest_job_id = payload.get("job_id") or request_id
            current._record(latest_job_id=current.latest_job_id)
        folder = current.folder / ("request-"+request_id)
        folder.mkdir()
        cancel_path = folder / "cancel.requested"
        current.cancel_path = cancel_path
        request_payload = {**payload, "root": str(root), "run_dir": str(folder), "cancel_path": str(cancel_path)}
        request_payload.setdefault("job_id", request_id)
        envelope = {"command": "synthesize", "instance_id": current.instance_id, "request_id": request_id,
                    "payload": request_payload, "idle_seconds": settings["idle_seconds"],
                    "max_session_seconds": settings["max_session_seconds"]}
        report = {"request_id": request_id, "job_id": request_payload["job_id"], "instance_id": current.instance_id,
            "launcher_pid": current.process.pid, "worker_pid": current.record.get("worker_pid"), "started_at": _now(), "ordinal": current.requests,
            "parent_clock": "monotonic", "queue_wait_seconds": payload.get("parent_queue_wait_seconds", 0),
            "timeout_seconds": limit, "worker_deadline_seconds": deadline-started, "status": "running"}
        _save(folder / "request.json", {**report, "payload": request_payload})
        success = False
        try:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError("TTS request deadline elapsed before worker dispatch")
            envelope["request_timeout_seconds"] = min(300.0, remaining)
            envelope["request_deadline_monotonic"] = deadline
            current.send(envelope)
            while True:
                if current.closed.is_set() or (cancel_event is not None and cancel_event.is_set()):
                    cancel_path.touch(exist_ok=True)
                    raise RuntimeError("TTS session request cancelled; late outputs discarded")
                if time.monotonic() >= deadline:
                    cancel_path.touch(exist_ok=True)
                    raise TimeoutError("TTS session request reached its bounded timeout")
                try:
                    line = current.events.get(timeout=min(.1, max(.001, deadline-time.monotonic())))
                except queue.Empty:
                    if current.process.poll() is not None:
                        raise SessionUnavailable("TTS session worker exited without request completion")
                    continue
                if line is None:
                    if current.reader_error is not None:
                        error = current.reader_error
                        raise SessionUnavailable(f"TTS protocol stdout reader failed: {error['error_type']}: "
                            f"{error['message']}; log: {current.folder.name}/reader-error.json")
                    raise SessionUnavailable("TTS session worker closed its output without completion")
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue  # Library startup diagnostics are not protocol events.
                if not isinstance(event, dict) or "type" not in event:
                    continue
                if event.get("instance_id") != current.instance_id or event.get("request_id") != request_id:
                    raise SessionUnavailable("TTS session output identity mismatch; stale output rejected")
                worker_pid = event.get("worker_pid") or (event.get("session_info") or {}).get("worker_pid")
                if worker_pid is not None:
                    if worker_pid != current.process.pid:
                        raise SessionUnavailable("Actual TTS worker PID differs from its owned process handle")
                    report["worker_pid"] = worker_pid
                    current._record(worker_pid=worker_pid,
                                    process_start_time=event.get("process_start_time") or (event.get("session_info") or {}).get("process_start_time"))
                if current.closed.is_set() or (cancel_event is not None and cancel_event.is_set()):
                    raise RuntimeError("TTS session request cancelled before output publication")
                if event["type"] == "error":
                    raise SessionUnavailable(event.get("message", "TTS session synthesis failed"))
                event["parent_timing"] = {"clock": "monotonic", "request_elapsed_seconds": time.monotonic()-started,
                    "queue_wait_seconds": report["queue_wait_seconds"], "queue_in_budget_charge": False,
                    "scope": "reserved request dispatch to event; not GPU kernel time"}
                if event["type"] == "done":
                    success = True
                    report.update(status="completed", elapsed_seconds=time.monotonic()-started)
                    yield event
                    break
                yield event
        except BaseException as exc:
            report.update(status="failed_or_cancelled", error=f"{type(exc).__name__}: {exc}",
                          elapsed_seconds=time.monotonic()-started)
            raise
        finally:
            _save(folder / "request-result.json", report)
            if not success:
                close(root, key, "request_failed_or_cancelled")
            else:
                with state.state:
                    if state.current is current and not current.closed.is_set():
                        current.active = False
                        current.cancel_path = None
                        current._record(status="idle_model_retained", completed_requests=current.requests,
                                        gpu_memory_retained=True, last_request_id=request_id)
                        timer = threading.Timer(settings["idle_seconds"], _expire,
                                                (root, current.instance_id, "idle_expired"))
                        timer.daemon = True
                        current.idle_timer = timer
                        timer.start()


def close_all(reason="parent_exit"):
    with _REGISTRY_LOCK:
        states = list(_COORDINATORS.values())
    for state in states:
        with state.state:
            if state.current:
                close(state.current.root, reason=reason)


atexit.register(close_all)
