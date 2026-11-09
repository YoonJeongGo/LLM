"""Opt-in text residency through the existing serialized/budgeted dispatch."""
from __future__ import annotations
import atexit
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid

from edu_tutor.jobs.owned_process import OwnedWindowsJob

_LOCK = threading.RLock()
_CURRENT = {}
_LAST = {}


def policy(root):
    file = Path(root) / ".local/text-session-policy.json"
    value = json.loads(file.read_text(encoding="utf-8")) if file.exists() else {}
    result = {"mode": value.get("mode", "per_request"), "idle_seconds": float(value.get("idle_seconds", 60)),
        "max_session_seconds": float(value.get("max_session_seconds", 600))}
    if result["mode"] not in {"per_request", "session"} or not 1 <= result["idle_seconds"] <= 60 or not 1 <= result["max_session_seconds"] <= 600:
        raise ValueError("Invalid text session policy")
    return result


def enabled(root, payload):
    return payload.get("kind") == "text" and payload.get("observation") is None and policy(root)["mode"] == "session"


def _save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def _key(root, payload):
    from .text_precision import validate_precision
    precision = validate_precision(payload.get("precision", "nf4"))
    path = Path(root) / ".local/models/text/model-manifest.json"
    revision = json.loads(path.read_text(encoding="utf-8")).get("revision") if path.exists() else None
    return json.dumps([payload.get("adapter"), revision, payload.get("execution_allowance_id"), precision])


def _command(root):
    executable = Path(root) / ".venv/Scripts/python.exe"
    if not executable.is_file():
        # CPU fixture roots have no venv; production roots use the explicit path.
        executable = Path(sys.executable)
    return [str(executable), "-u", "-m", "edu_tutor.models.text_session_worker"]


class _Child:
    def __init__(self, root, key, settings, deadline, cancel_event):
        self.root, self.key, self.settings = root, key, settings
        self.instance_id, self.nonce = uuid.uuid4().hex, uuid.uuid4().hex
        self.folder = root / "runs" / ("text-session-" + self.instance_id)
        self.folder.mkdir(parents=True)
        # Bounded IPC buffering; cancelled consumers must not leave a reader
        # permanently blocked on a full queue during owned-child shutdown.
        self.events = queue.Queue(maxsize=128)
        self.reader_stopped = threading.Event()
        self.last_receive_timing = None
        self.closed = False
        self.active = False
        self.job_id = self.request_id = self.cancel_path = self.idle_timer = self.lifetime_timer = None
        self.idle_generation = 0
        self.idle_deadline = None
        self.lifetime_deadline = time.perf_counter() + settings["max_session_seconds"]
        self.activity_token = self.activity_job_id = None
        self.activity_acks = queue.Queue(maxsize=1)
        self.requests = 0
        self.reader_error = None
        self.record = {"instance_id": self.instance_id, "launch_mode": "explicit_project_venv_module",
            "status": "starting_no_weights", "settings": settings, "key_sha256": hashlib.sha256(key.encode()).hexdigest()}
        env = os.environ.copy()
        env.update(PYTHONUTF8="0", PYTHONIOENCODING="utf-8", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
            HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1", TOKENIZERS_PARALLELISM="false")
        env["PYTHONPATH"] = str(root / "src") + os.pathsep + env.get("PYTHONPATH", "")
        self.errors = (self.folder / "stderr.log").open("w", encoding="utf-8")
        try:
            self.process = subprocess.Popen(_command(root), cwd=root, env=env, text=True, encoding="utf-8",
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errors,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except BaseException:
            self.errors.close()
            raise
        self.owned = None
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            if os.name != "nt":
                raise RuntimeError("This residency implementation requires verified Windows process ownership")
            self.owned = OwnedWindowsJob(self.process)
            self.send({"command": "initialize", "root": str(root), "instance_id": self.instance_id,
                "nonce": self.nonce, **settings})
            hello = self.receive(deadline, cancel_event)
            if hello.get("type") != "hello" or hello.get("nonce") != self.nonce or hello.get("instance_id") != self.instance_id:
                raise RuntimeError("Invalid text worker handshake")
            owned = self.owned.attach_handshaken_child(self.process, hello["worker_pid"], hello["process_start_time"])
            if (root / ".venv/pyvenv.cfg").exists() and Path(hello["prefix"]).resolve() != root / ".venv":
                raise RuntimeError("Actual text child prefix is not the project virtualenv")
            self.record.update(launcher_pid=self.process.pid, worker_pid=owned["pid"], process_start_time=owned["create_time"],
                ownership=owned, interpreter=hello, status="owned_before_weights")
            self.send({"command": "owned", "instance_id": self.instance_id, "nonce": self.nonce})
            if self.receive(deadline, cancel_event).get("type") != "owned":
                raise RuntimeError("Text child did not acknowledge ownership")
            self._record()
        except BaseException:
            self.stop("initialization_failed")
            raise

    def _record(self, **value):
        self.record.update(value)
        _save(self.folder / "session.json", self.record)

    def _read(self):
        try:
            with (self.folder / "events.jsonl").open("w", encoding="utf-8") as log:
                for line in self.process.stdout:
                    received = time.perf_counter()
                    log.write(line)
                    log.flush()
                    logged = time.perf_counter()
                    # Activity ACKs have their own bounded channel. A late ACK
                    # must never become the next generation's foreign event.
                    if line.startswith('{"type": "activity_ack",'):
                        ack = json.loads(line)
                        if ack.get("activity_token") == self.activity_token:
                            try:
                                self.activity_acks.put_nowait(ack)
                            except queue.Full:
                                pass
                        continue
                    if not self._enqueue(line, received, logged):
                        break
        except (OSError, UnicodeError, ValueError) as exc:
            self.reader_error = f"{type(exc).__name__}: {exc}"
        finally:
            self._enqueue(None, time.perf_counter(), time.perf_counter())

    def _enqueue(self, line, received, logged):
        while not self.reader_stopped.is_set():
            try:
                self.events.put_nowait((line, received, logged, time.perf_counter()))
                return True
            except queue.Full:
                self.reader_stopped.wait(.01)
        return False

    def send(self, value):
        self.process.stdin.write(json.dumps(value, ensure_ascii=False)+"\n")
        self.process.stdin.flush()

    def receive(self, deadline, cancel_event):
        while True:
            if self.closed or cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("Text request cancelled; late events rejected")
            if time.perf_counter() >= deadline:
                raise TimeoutError("Text session request reached its reserved deadline")
            try:
                line, received, logged, enqueued = self.events.get(timeout=.05)
                consumed = time.perf_counter()
                self.last_receive_timing = {
                    "reader_received_at": received, "consumer_received_at": consumed,
                    "reader_log_seconds": logged-received,
                    "reader_backpressure_seconds": max(0, enqueued-logged),
                    "queue_wait_seconds": max(0, consumed-enqueued),
                }
            except queue.Empty:
                if self.process.poll() is not None:
                    raise RuntimeError("Text worker exited without completion; no automatic retry")
                continue
            if self.closed or cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("Text request cancelled; late events rejected")
            if time.perf_counter() >= deadline:
                raise TimeoutError("Text session request reached its reserved deadline")
            if line is None:
                raise RuntimeError("Text protocol closed: " + (self.reader_error or "EOF without completion"))
            try:
                event = json.loads(line)
            except ValueError as exc:
                raise RuntimeError("Non-JSON output contaminated the text protocol") from exc
            return event

    def stop(self, reason):
        if self.closed and self.record.get("process_exit_confirmed") and self.record.get("actual_worker_exit_confirmed"):
            return
        self.closed = True
        for timer in (self.idle_timer, self.lifetime_timer):
            if timer:
                timer.cancel()
        if self.cancel_path:
            self.cancel_path.touch(exist_ok=True)
        actual = None
        if self.record.get("worker_pid"):
            import psutil
            try:
                candidate = psutil.Process(self.record["worker_pid"])
                if abs(candidate.create_time()-self.record["process_start_time"]) < .01:
                    actual = candidate
            except psutil.NoSuchProcess:
                pass
        try:
            if self.process.poll() is None:
                try:
                    self.send({"command": "shutdown", "instance_id": self.instance_id})
                    self.process.wait(timeout=.25 if self.active else 1)
                except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                    pass
        finally:
            if self.owned is not None:
                self.owned.close()
            elif self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=2.5)
                if actual is not None:
                    import psutil
                    try:
                        actual.wait(timeout=2)
                    except psutil.NoSuchProcess:
                        pass
            except BaseException as exc:
                self._record(status="cleanup_unconfirmed", reason=reason, cleanup_error=f"{type(exc).__name__}: {exc}",
                    process_exit_code=self.process.poll(), process_exit_confirmed=self.process.poll() is not None,
                    actual_worker_exit_confirmed=False)
                # Keep this closed owner registered. No replacement can start
                # until cleanup is confirmed; a later close may recheck exit.
                raise
            finally:
                self.reader_stopped.set()
                self.reader.join(timeout=.5)
                for stream in (self.process.stdin, self.process.stdout, self.errors):
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        pass
            self._record(status="closed", reason=reason, process_exit_code=self.process.returncode,
                process_exit_confirmed=True, actual_worker_exit_confirmed=True,
                model_resident=False, active_request=False, reader_error=self.reader_error)


def close(root, reason="explicit_close", *, job_id=None, instance_id=None, request_id=None):
    root = Path(root).resolve()
    with _LOCK:
        child = _CURRENT.get(str(root))
        if (child is None or job_id is not None and child.job_id != job_id
                or instance_id is not None and child.instance_id != instance_id
                or request_id is not None and child.request_id != request_id):
            return {"closed": False, "reason": "no_matching_owned_text_session"}
        child.stop(reason)
        _LAST[str(root)] = dict(child.record)
        _CURRENT.pop(str(root), None)
        return {"closed": True, **child.record}


def status(root):
    root = Path(root).resolve()
    with _LOCK:
        child = _CURRENT.get(str(root))
        return {"policy": policy(root), "resident": bool(child and not child.closed and child.process.poll() is None and child.record.get("model_instance_id")),
            "active_request": bool(child and child.active), "session": dict(child.record) if child else None,
            "last_session": _LAST.get(str(root))}


def _expire(root, instance_id, reason, *, idle_generation=None):
    with _LOCK:
        current = _CURRENT.get(str(Path(root).resolve()))
        if current is None or current.instance_id != instance_id or reason == "idle_expired" and current.active:
            return
        if reason == "idle_expired" and idle_generation is not None and current.idle_generation != idle_generation:
            return
        close(root, reason, instance_id=instance_id)


def _arm_idle(root, child, *, now=None):
    """Caller holds _LOCK. Maximum-lifetime timers are never changed here."""
    if child.idle_timer:
        child.idle_timer.cancel()
    child.idle_generation += 1
    child.idle_deadline = (time.perf_counter() if now is None else now) + child.settings["idle_seconds"]
    child.idle_timer = threading.Timer(max(0, child.idle_deadline-time.perf_counter()), _expire,
        args=(root, child.instance_id, "idle_expired"), kwargs={"idle_generation": child.idle_generation})
    child.idle_timer.daemon = True
    child.idle_timer.start()


def refresh_preflight_idle(payload, *, root, instance_id, previous_request_id, cancel_event, deadline):
    """One admitted student request; no model load/reservation/heartbeat.

    Parent refresh occurs once at activity entry. Admission followed by storage
    denial, cancellation or missing ACK may leave this one bounded idle period.
    Pipe I/O and ACK waits never hold _LOCK, so lifetime expiry can still close.
    """
    root = Path(root).resolve()
    job_id = payload.get("job_id")
    expected = payload.get("expected_text_instance_id")
    if (not enabled(root, payload) or not payload.get("student_session_id")
            or not isinstance(job_id, str) or not 1 <= len(job_id) <= 100
            or expected is not None and expected != instance_id):
        return False
    key = _key(root, payload)
    def pending():
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Text activity cancelled during preflight")
        if time.perf_counter() >= deadline:
            raise TimeoutError("Text activity request deadline reached")
    with _LOCK:
        pending()
        child = _CURRENT.get(str(root))
        now = time.perf_counter()
        if (child is None or child.instance_id != instance_id or child.request_id != previous_request_id
                or previous_request_id is None or child.key != key or child.closed or child.active
                or child.process.poll() is not None or not child.record.get("model_instance_id")
                or child.idle_deadline is None or now >= child.idle_deadline or now >= child.lifetime_deadline
                or child.activity_job_id == payload["job_id"]):
            return False
        token = uuid.uuid4().hex
        while not child.activity_acks.empty():
            child.activity_acks.get_nowait()
        child.activity_token, child.activity_job_id = token, payload["job_id"]
        ack_deadline = min(deadline, now+2)
        _arm_idle(root, child, now=now)
        generation = child.idle_generation
        child.record.update(preflight_activity_job_id=payload["job_id"], preflight_activity_token=token,
                            preflight_activity_status="sent_not_acknowledged")
    pending()
    child.send({"command": "preflight_activity", "instance_id": instance_id, "nonce": child.nonce,
        "previous_request_id": previous_request_id, "activity_token": token, "job_id": payload["job_id"],
        "activity_deadline": ack_deadline})  # Same-host Windows perf_counter clock.
    while True:
        pending()
        remaining = ack_deadline-time.perf_counter()
        if remaining <= 0:
            raise TimeoutError("Text activity acknowledgment deadline reached; no model work started")
        try:
            ack = child.activity_acks.get(timeout=min(.05, remaining))
            break
        except queue.Empty:
            continue
    with _LOCK:
        pending()
        if (_CURRENT.get(str(root)) is not child or child.closed or child.active or child.request_id != previous_request_id
                or child.key != key or child.idle_generation != generation or child.activity_token != token
                or time.perf_counter() >= child.lifetime_deadline):
            raise RuntimeError("Text activity owner expired or changed before acknowledgment")
        if (ack.get("instance_id") != instance_id or ack.get("worker_pid") != child.record["worker_pid"]
                or ack.get("nonce") != child.nonce or ack.get("activity_token") != token
                or ack.get("previous_request_id") != previous_request_id or ack.get("job_id") != payload["job_id"]
                or ack.get("accepted") is not True):
            raise RuntimeError("Text activity acknowledgment rejected; no model work started")
        child.record.update(preflight_activity_status="acknowledged", preflight_activity_ack=ack)
        return True


def run(payload, *, root, cancel_event=None, timeout=300):
    """One request already reserved by runtime.run_worker; no hidden generation."""
    root = Path(root).resolve()
    if not enabled(root, payload):
        raise ValueError("Text residency is not enabled")
    from edu_tutor.speech.session import execution_slot
    with execution_slot(root, cancel_event, timeout):
        started = time.perf_counter()
        if timeout <= 6:
            raise TimeoutError("Insufficient text time for owned-child cleanup")
        deadline = started + timeout - 6
        key, settings = _key(root, payload), policy(root)
        with _LOCK:
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("Text request cancelled before ownership transition")
            if time.perf_counter() >= deadline:
                raise TimeoutError("Text request deadline reached before ownership transition")
            child = _CURRENT.get(str(root))
            # Timer callbacks can be delayed by another short ownership lock.
            # Never turn an already expired owner back into an active request.
            now = time.perf_counter()
            if child and not child.closed and (now >= child.lifetime_deadline
                    or not child.active and child.idle_deadline is not None and now >= child.idle_deadline):
                reason = "maximum_lifetime" if now >= child.lifetime_deadline else "idle_expired"
                close(root, reason, instance_id=child.instance_id)
                child = None
            expected = payload.get("expected_text_instance_id")
            if expected is not None and (child is None or child.instance_id != expected or child.key != key or child.closed or child.process.poll() is not None):
                raise RuntimeError("Expected warm text instance unavailable; cold reload is forbidden")
            if child and child.key != key:
                close(root, "model_or_scope_changed")
                child = None
            if child and child.closed:
                close(root, "retry_unconfirmed_cleanup")
                raise RuntimeError("Previous text cleanup was unconfirmed; request not automatically restarted")
            if child and child.process.poll() is not None:
                close(root, "unexpected_worker_exit")
                raise RuntimeError("Text worker died; request not transparently retried")
            if child is None:
                child = _Child(root, key, settings, deadline, cancel_event)
                _CURRENT[str(root)] = child
                child.lifetime_timer = threading.Timer(settings["max_session_seconds"], _expire,
                    args=(root, child.instance_id, "maximum_lifetime"))
                child.lifetime_timer.daemon = True
                child.lifetime_timer.start()
            if child.idle_timer:
                child.idle_timer.cancel()
            child.idle_generation += 1
            child.active = True
            child.requests += 1
            request_id = uuid.uuid4().hex
            child.request_id = request_id
            child.job_id = payload.get("job_id") or request_id
            folder = child.folder / ("request-" + request_id)
            folder.mkdir()
            child.cancel_path = folder / "cancel.requested"
            request = {**payload, "root": str(root), "run_dir": str(folder), "cancel_path": str(child.cancel_path), "job_id": child.job_id}
            child._record(latest_job_id=child.job_id, latest_request_id=request_id,
                          request_count=child.requests, active_request=True)
        request_job_id = child.job_id
        transport = {"clock": "parent_perf_counter", "scope": "resident text reader and consumer, same API process",
            "queue_capacity_events": 128, "received_event_count": 0, "delta_event_count": 0,
            "reader_log_seconds_total": 0.0, "reader_backpressure_seconds_total": 0.0,
            "queue_wait_seconds_total": 0.0, "queue_wait_seconds_max": 0.0,
            "consumer_yield_seconds_total": 0.0, "consumer_yield_seconds_max": 0.0,
            "consumer_yield_count": 0,
            "notice": "Queue wait overlaps consumer work; do not sum with DB or model intervals. Reader timing starts after a complete protocol line arrives; pipe transit before that is unmeasured."}
        report = {"request_id": request_id, "job_id": child.job_id, "instance_id": child.instance_id,
            "status": "running", "clock": "parent_perf_counter", "timeout_seconds": timeout, "payload": request}
        _save(folder / "request.json", report)
        success = False
        try:
            child.send({"command": "generate", "instance_id": child.instance_id, "request_id": request_id,
                "request_seconds": max(.1, deadline-time.perf_counter()), "payload": request})
            while True:
                event = child.receive(deadline, cancel_event)
                if event.get("instance_id") != child.instance_id or event.get("request_id") != request_id or event.get("worker_pid") != child.record["worker_pid"]:
                    raise RuntimeError("Stale or foreign text event rejected")
                timing = child.last_receive_timing
                transport["received_event_count"] += 1
                transport["reader_log_seconds_total"] += timing["reader_log_seconds"]
                transport["reader_backpressure_seconds_total"] += timing["reader_backpressure_seconds"]
                transport["queue_wait_seconds_total"] += timing["queue_wait_seconds"]
                transport["queue_wait_seconds_max"] = max(transport["queue_wait_seconds_max"], timing["queue_wait_seconds"])
                if event["type"] == "delta":
                    transport["delta_event_count"] += 1
                    transport.setdefault("first_delta_reader_elapsed_seconds", timing["reader_received_at"]-started)
                    transport.setdefault("first_delta_consumer_elapsed_seconds", timing["consumer_received_at"]-started)
                if event["type"] == "metadata":
                    transport.update(metadata_reader_elapsed_seconds=timing["reader_received_at"]-started,
                        metadata_consumer_elapsed_seconds=timing["consumer_received_at"]-started,
                        observed_through="metadata receipt before caller processing")
                    event["transport_timing"] = dict(transport)
                if event["type"] == "error":
                    raise RuntimeError(event.get("message", "Resident text failed"))
                event["parent_timing"] = {"request_elapsed_seconds": time.perf_counter()-started, "clock": "perf_counter"}
                if event["type"] == "model_ready":
                    child._record(**{k: event[k] for k in ("model_instance_id", "model_python_id", "cumulative_model_load_count", "request_model_load_count",
                                                         "requested_precision", "inference") if k in event})
                if event["type"] == "done":
                    success = True
                yielded_at = time.perf_counter()
                yield event
                consumer_seconds = time.perf_counter()-yielded_at
                transport["consumer_yield_seconds_total"] += consumer_seconds
                transport["consumer_yield_seconds_max"] = max(transport["consumer_yield_seconds_max"], consumer_seconds)
                transport["consumer_yield_count"] += 1
                if success:
                    break
        except BaseException as exc:
            report["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            report.update(status="completed" if success else "failed_or_cancelled", elapsed_seconds=time.perf_counter()-started,
                transport_timing={**transport, "observed_through": "request finalization"})
            _save(folder / "request-result.json", report)
            if not success:
                close(root, "request_failed_or_cancelled", instance_id=child.instance_id,
                      job_id=request_job_id, request_id=request_id)
            else:
                with _LOCK:
                    if not child.closed and _CURRENT.get(str(root)) is child:
                        child.active = False
                        child.cancel_path = None
                        child._record(active_request=False, status="idle_model_retained")
                        _arm_idle(root, child)


def close_all():
    for root in list(_CURRENT):
        close(root, "parent_exit")


atexit.register(close_all)
