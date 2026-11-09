from __future__ import annotations

import os
import threading
import time
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor

from edu_tutor.storage.db import Store, new_id, utcnow
from edu_tutor.jobs.lease import GPULease
from edu_tutor.storage.timing import capture_storage_timing, record_timing, storage_timing_snapshot

TERMINAL = {"succeeded", "failed", "cancelled", "interrupted", "blocked"}


class JobManager:
    def __init__(self, store: Store):
        self.store = store
        self.lock = threading.RLock()
        self.cancels = {}
        # At most one bounded prefix per active chat; no unbounded delta queue.
        self.partials = {}
        self.closed = False
        self.instance = new_id()
        # Acquire before recovery: a second server must not interrupt live jobs.
        self.instance_lease = GPULease(store.local, self.instance, device="api", lock_name="api").__enter__()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tutor-job")
        try:
            self.recover()
        except BaseException:
            self.instance_lease.__exit__(None, None, None)
            raise

    def recover(self):
        # Called only when the application starts. No processes are killed.
        for job in self.store.list("jobs"):
            if job["state"] not in TERMINAL:
                job.update(state="interrupted", error="서버 재시작으로 작업이 중단되었습니다.", updated_at=utcnow())
                self.store.put("jobs", job)

    def update(self, ident, **fields):
        started = time.perf_counter()
        with self.lock:
            record_timing("job_lock_wait", started)
            job = self.store.get("jobs", ident)
            if self.closed or job["state"] in TERMINAL:
                return job
            pending = self.partials.get(ident)
            if pending:
                if (pending.get("error") and not (fields.get("cancel_requested") and "state" not in fields)
                        and fields.get("state") not in {"failed", "cancelled", "interrupted", "blocked"}):
                    raise RuntimeError("Partial output persistence failed: " + pending["error"])
                job.update(pending["fields"])
                if pending.get("error"):
                    job["partial_persistence_error"] = pending["error"]
                    if not fields.get("error"):
                        fields["error"] = "Partial output persistence failed: " + pending["error"]
            job.update(fields, updated_at=utcnow())
            self.store.put("jobs", job)
            if pending:
                self._reset_partial(ident, pending, terminal=job["state"] in TERMINAL)
            return job

    def _reset_partial(self, ident, pending, *, terminal=False):
        timer = pending.get("timer")
        if timer is not None:
            timer.cancel()
        pending.update(timer=None, dirty=False, saved_at=time.monotonic(), saved_chars=len(pending["fields"]["raw_partial_text"]))
        if terminal:
            self.partials.pop(ident, None)

    def view(self, ident):
        """Live UI prefix overlays durable state; terminal states are always durable."""
        with self.lock:
            job = self.store.get("jobs", ident)
            pending = self.partials.get(ident)
            if job and pending and not self.closed and job["state"] not in TERMINAL and job["generation_epoch"] == pending["epoch"]:
                job.update(pending["fields"], partial_snapshot_pending=pending["dirty"])
            return job

    def _flush_partial(self, ident, pending):
        # The callback's identity protects against a stale timer or replacement.
        with self.lock:
            if self.closed or self.partials.get(ident) is not pending or not pending["dirty"]:
                return
            job = self.store.get("jobs", ident)
            if not job or job["state"] in TERMINAL or job["generation_epoch"] != pending["epoch"]:
                self._reset_partial(ident, pending, terminal=True)
                return
            job.update(pending["fields"], updated_at=utcnow())
            job["partial_persistence"] = {**pending["fields"]["partial_persistence"],
                                          "snapshot_writes": pending["writes"] + 1}
            self.store.put("jobs", job)
            pending["writes"] += 1
            pending["fields"]["partial_persistence"] = dict(job["partial_persistence"])
            self._reset_partial(ident, pending)

    def _partial_timer(self, ident, pending):
        try:
            self._flush_partial(ident, pending)
        except Exception as exc:
            # A failed durable write stops generation; it never reports success.
            with self.lock:
                if self.partials.get(ident) is pending:
                    pending["error"] = f"{type(exc).__name__}: {exc}"[:400]
                    pending["timer"] = None
                    cancel = self.cancels.get(ident)
                    if cancel is not None:
                        cancel.set()

    def update_partial(self, ident, generation_epoch, *, partial_text, raw_partial_text):
        """Expose every prefix; persist after 250ms or 4096 new chars, and at every state transition."""
        if not isinstance(raw_partial_text, str) or not isinstance(partial_text, str) or max(len(raw_partial_text), len(partial_text)) > 60000:
            raise ValueError("모델 출력 크기 제한을 초과했습니다.")
        started = time.perf_counter()
        with self.lock:
            record_timing("job_lock_wait", started)
            if self.closed:
                return
            pending = self.partials.get(ident)
            cancel = self.cancels.get(ident)
            if cancel is None or cancel.is_set():
                return
            if pending is None:
                job = self.store.get("jobs", ident)
                if (not job or job["state"] in TERMINAL or job.get("kind") != "chat"
                        or job.get("owner_instance") != self.instance or job["generation_epoch"] != generation_epoch):
                    return
                pending = {"epoch": generation_epoch, "fields": {"partial_text": "", "raw_partial_text": ""},
                           "saved_at": 0.0, "saved_chars": 0, "dirty": False, "timer": None, "chunks": 0, "writes": 0}
                self.partials[ident] = pending
            if pending.get("error"):
                raise RuntimeError("Partial output persistence failed: " + pending["error"])
            if pending["epoch"] != generation_epoch:
                return
            if not raw_partial_text.startswith(pending["fields"]["raw_partial_text"]):
                raise ValueError("Partial output prefix changed within one request")
            pending["fields"] = {"partial_text": partial_text, "raw_partial_text": raw_partial_text}
            pending["chunks"] += 1
            pending["dirty"] = True
            pending["fields"]["partial_persistence"] = {"chunks": pending["chunks"], "snapshot_writes": pending["writes"],
                "interval_seconds": .25, "growth_chars": 4096, "max_prefix_chars": 60000,
                "final_state_flush_required": True}
            if time.monotonic()-pending["saved_at"] >= .25 or len(raw_partial_text)-pending["saved_chars"] >= 4096:
                self._flush_partial(ident, pending)
            elif pending["timer"] is None:
                context = copy_context()
                timer = threading.Timer(max(.001, .25-(time.monotonic()-pending["saved_at"])),
                                        lambda: context.run(self._partial_timer, ident, pending))
                timer.daemon = True
                pending["timer"] = timer
                timer.start()

    def submit(self, kind, target, *, request_id=None, session_id=None, generation_epoch=0):
        with self.lock:
            if self.closed:
                raise RuntimeError("API job manager is shutting down")
            if request_id:
                for job in self.store.list("jobs"):
                    if job.get("request_id") == request_id and job.get("session_id") == session_id and job.get("kind") == kind:
                        return job
            ident = new_id()
            job = {"id": ident, "kind": kind, "state": "queued", "cancel_requested": False,
                   "progress": 0, "result": None, "error": None, "request_id": request_id,
                   "session_id": session_id, "generation_epoch": generation_epoch,
                   "created_at": utcnow(), "updated_at": utcnow(), "owner_pid": os.getpid(),
                   "owner_instance": self.instance}
            self.store.put("jobs", job)
            cancel = threading.Event()
            self.cancels[ident] = cancel

            def run_inner():
                try:
                    if cancel.is_set():
                        self.update(ident, state="cancelled")
                        return
                    self.update(ident, state="loading")
                    if kind in {"chat", "vision", "evaluation", "training", "diagnostic"}:
                        from edu_tutor.speech.session import dispatch, close
                        # Training/diagnostics may bypass run_worker; release
                        # resident TTS memory before their authoritative GPU lease.
                        with dispatch(self.store.root, cancel_event=cancel):
                            close(self.store.root, reason="other_model_job")
                            if kind != "chat":
                                from edu_tutor.models.text_session import close as close_text
                                close_text(self.store.root, reason="other_gpu_job")
                            result = target(ident, cancel)
                    else:
                        result = target(ident, cancel)
                    self.update(ident, state="cancelled" if cancel.is_set() else "succeeded", result=result,
                                progress=1 if not cancel.is_set() else 0, storage_timing=storage_timing_snapshot())
                except Exception as exc:
                    blocked = isinstance(exc, (FileNotFoundError, ImportError)) or type(exc).__name__ in {"ModelUnavailable", "LeaseBusy", "ResourceBudgetExceeded"} or "unavailable" in str(exc).lower()
                    self.update(ident, state="cancelled" if cancel.is_set() else ("blocked" if blocked else "failed"),
                                error=str(exc)[:700], storage_timing=storage_timing_snapshot())
                finally:
                    with self.lock:
                        self.cancels.pop(ident, None)
                        pending = self.partials.pop(ident, None)
                        if pending and pending.get("timer") is not None:
                            pending["timer"].cancel()

            def run():
                with capture_storage_timing():
                    run_inner()

            context = copy_context()
            self.pool.submit(context.run, run)
            return job

    def cancel(self, ident):
        with self.lock:
            job = self.store.get("jobs", ident)
            if not job:
                raise KeyError(ident)
            if job["state"] not in TERMINAL:
                if ident in self.cancels:
                    self.cancels[ident].set()
                job = self.update(ident, cancel_requested=True)
            return job

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            for ident, cancel in list(self.cancels.items()):
                cancel.set()
                job = self.store.get("jobs", ident)
                if job and job["state"] not in TERMINAL:
                    pending = self.partials.get(ident)
                    if pending:
                        job.update(pending["fields"])
                        if pending.get("error"):
                            job["partial_persistence_error"] = pending["error"]
                    job.update(state="interrupted", cancel_requested=True, updated_at=utcnow(),
                               error="서버 종료로 작업이 중단되었습니다.")
                    self.store.put("jobs", job)
                    if pending:
                        self._reset_partial(ident, pending, terminal=True)
        self.pool.shutdown(wait=False, cancel_futures=True)
        from edu_tutor.speech.session import close
        close(self.store.root, reason="api_shutdown")
        from edu_tutor.models.text_session import close as close_text
        close_text(self.store.root, reason="api_shutdown")
        self.instance_lease.__exit__(None, None, None)
