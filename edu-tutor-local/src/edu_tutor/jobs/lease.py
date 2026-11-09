from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from edu_tutor.storage.db import utcnow


class LeaseBusy(RuntimeError):
    pass


class GPULease:
    """OS lock is authoritative; stale JSON never authorizes killing a process.

    OS releases the lock on process exit. Lock file remains in place to avoid
    unlink/recreate races. Metadata records identity and a periodic heartbeat.
    """

    def __init__(self, local_dir: Path, job_id: str, device: str = "cuda:0", *, lock_name: str = "gpu"):
        if lock_name not in {"gpu", "api"}:
            raise ValueError("Unknown application lock")
        self.local = Path(local_dir)
        self.local.mkdir(parents=True, exist_ok=True)
        self.job_id, self.device = job_id, device
        self.lock_name = lock_name
        self.handle = None
        self.stop = threading.Event()
        self.thread = None

    def _metadata(self, state="held"):
        try:
            import psutil
            started = psutil.Process(os.getpid()).create_time()
        except (ImportError, OSError):
            started = None
        value = {"job_id": self.job_id, "pid": os.getpid(), "process_start": started,
                 "device": self.device, "heartbeat": utcnow(), "state": state}
        target = self.local / f"{self.lock_name}-lease.json"
        temp = self.local / f"{self.lock_name}-lease.{os.getpid()}.tmp"
        temp.write_text(json.dumps(value), encoding="utf-8")
        temp.replace(target)

    def _heartbeat(self):
        while not self.stop.wait(2):
            try:
                self._metadata()
            except OSError:
                pass

    def __enter__(self):
        self.handle = (self.local / f"{self.lock_name}.lock").open("a+b")
        self.handle.seek(0, 2)
        if self.handle.tell() == 0:
            self.handle.write(b"\0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            message = "같은 자료 폴더를 사용하는 API 서버가 이미 실행 중입니다." if self.lock_name == "api" else "다른 작업이 GPU를 사용 중입니다."
            raise LeaseBusy(message) from exc
        try:
            self._metadata()
            self.thread = threading.Thread(target=self._heartbeat, daemon=True)
            self.thread.start()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=3)
        if self.handle:
            try:
                self._metadata("released")
            finally:
                self.handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.handle, fcntl.LOCK_UN)
                self.handle.close()
                self.handle = None
