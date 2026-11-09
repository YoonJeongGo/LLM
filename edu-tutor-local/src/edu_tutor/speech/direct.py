"""SAPI's owned native child, dispatched in the existing API job thread.

Only fully identified SAPI payloads enter here; no neural modules or GPU lease.
The caller still holds the global dispatch slot and an ordinary audio reservation.
"""
from __future__ import annotations
from pathlib import Path
import threading
import time
import uuid


def enabled(payload):
    if payload.get("kind") == "speech":
        return payload.get("spec", {}).get("provider") == "windows_sapi_local"
    return (payload.get("kind") == "speech_batch" and payload.get("speech_provider") == "windows_sapi_local"
        and isinstance(payload.get("items"), list) and 1 <= len(payload["items"]) <= 4
        and all(item.get("spec", {}).get("provider") == "windows_sapi_local" for item in payload["items"]))


def run(payload, *, root, cancel_event=None, timeout=300):
    if not enabled(payload):
        raise ValueError("Direct CPU speech requires exact SAPI payloads")
    if timeout <= 6:
        raise TimeoutError("Insufficient speech reservation for owned-child cleanup")
    from edu_tutor.speech.windows_sapi import speech_job
    folder = Path(root) / "runs" / ("runtime-" + uuid.uuid4().hex)
    folder.mkdir(parents=True)
    cancel = folder / "cancel.requested"
    started = time.perf_counter()
    stopped = threading.Event()
    expired = threading.Event()
    def watch():
        while not stopped.wait(.02):
            if time.perf_counter()-started >= timeout-6:
                expired.set()
                cancel.touch(exist_ok=True)
                return
            if cancel_event is not None and cancel_event.is_set():
                cancel.touch(exist_ok=True)
                return
    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    items = payload["items"] if payload["kind"] == "speech_batch" else [payload]
    try:
        for index, item in enumerate(items):
            if cancel_event is not None and cancel_event.is_set():
                cancel.touch(exist_ok=True)
            events = []
            speech_job({**payload, **item, "root": str(root), "run_dir": str(folder), "cancel_path": str(cancel)},
                lambda event_type, **value: events.append({"type": event_type, **value}), batch_index=index)
            if cancel.exists() or cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("CPU speech cancelled before publication")
            for event in events:
                event["parent_timing"] = {"clock": "perf_counter", "request_elapsed_seconds": time.perf_counter()-started,
                    "path": "API job thread to owned SAPI child", "gpu_lease_acquired": False}
                yield event
        yield {"type": "done"}
    except BaseException as exc:
        if expired.is_set():
            raise TimeoutError("CPU speech reached reserved deadline") from exc
        raise
    finally:
        stopped.set()
        watcher.join(timeout=.1)
