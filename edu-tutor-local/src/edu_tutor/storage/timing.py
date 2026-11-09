"""Bounded per-job host timing. No contents, SQL values, or credentials are captured."""
from contextlib import contextmanager
from contextvars import ContextVar
import time
import threading

_CURRENT = ContextVar("tutor_storage_timing", default=None)


class StorageTiming:
    def __init__(self):
        self.started = time.perf_counter()
        self.phases = {}
        self.lock = threading.Lock()

    def add(self, phase, elapsed):
        with self.lock:
            value = self.phases.setdefault(phase, {"count": 0, "seconds": 0.0, "max_seconds": 0.0})
            value["count"] += 1
            value["seconds"] += elapsed
            value["max_seconds"] = max(value["max_seconds"], elapsed)

    def snapshot(self):
        with self.lock:
            return {"clock": "host_perf_counter", "elapsed_seconds": time.perf_counter()-self.started,
                    "phases": {key: dict(value) for key, value in self.phases.items()},
                    "scope": "current job and its owned partial-flush callbacks; SQLite busy/lock wait is within execute/commit",
                    "snapshot_boundary": "before final job-state write; final write/commit and HTTP/SSE delivery are excluded",
                    "intervals_not_all_additive": True}


@contextmanager
def capture_storage_timing():
    timing = StorageTiming()
    token = _CURRENT.set(timing)
    try:
        yield timing
    finally:
        _CURRENT.reset(token)


def record_timing(phase, started):
    timing = _CURRENT.get()
    if timing is not None:
        timing.add(phase, time.perf_counter()-started)


def storage_timing_snapshot():
    timing = _CURRENT.get()
    return timing.snapshot() if timing is not None else None
