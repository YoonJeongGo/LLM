"""Text-only resident child. Standard venv startup; no TTS bootstrap/imports."""
from __future__ import annotations
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid


class ResidentModel:
    def __init__(self, root, emit):
        self.root, self.emit = root, emit
        self.bundle = None
        self.identity = None
        self.loads = 0
        self.info = {}
        self.load_key = None

    def load(self, root, adapter, *, precision="nf4"):
        from edu_tutor.models.text_precision import validate_precision, validate_inference
        precision = validate_precision(precision)
        if Path(root).resolve() != Path(self.root).resolve():
            raise ValueError("Resident text root differs from its initialized owner")
        key = (str(Path(root).resolve()), str(Path(adapter).resolve()) if adapter else None, precision)
        if self.bundle is not None and self.load_key != key:
            raise RuntimeError("Resident text model/adapter/precision identity mismatch; no implicit reload")
        from edu_tutor.models.worker import load_text
        if self.bundle is None:
            self.emit("progress", stage="imports_ready")
            self.emit("progress", stage="model_load_started")
            bundle = load_text(root, adapter, precision=precision)
            inference = validate_inference(bundle[2].get("inference"), precision, adapter)
            self.bundle, self.load_key = bundle, key
            self.loads += 1
            self.identity = uuid.uuid4().hex
            model, tokenizer, _ = self.bundle
            import torch
            self.info.update(model_instance_id=self.identity, model_python_id=id(model), tokenizer_python_id=id(tokenizer),
                requested_precision=precision, inference=inference,
                cumulative_model_load_count=self.loads, request_model_load_count=1,
                device=str(model.device), dtype=str(next(model.parameters()).dtype),
                allocated_bytes=torch.cuda.memory_allocated(), reserved_bytes=torch.cuda.memory_reserved())
            self.emit("model_ready", **self.info)
        else:
            validate_inference(self.bundle[2].get("inference"), precision, adapter)
            self.info.update(request_model_load_count=0)
            self.emit("model_ready", **self.info)
        return self.bundle

    def process(self, payload):
        self.emit("progress", stage="text_runtime_import_started")
        from edu_tutor.models.worker import text_job
        text_job(payload, model_loader=self.load, emit_fn=self.emit, residency=self.info)

    def close(self):
        if self.bundle is not None:
            self.bundle = None
            import gc
            import torch
            gc.collect()
            torch.cuda.empty_cache()
        return {"model_resident": False, "model_load_count": self.loads}


def main(engine_factory=ResidentModel):
    protocol = sys.stdout
    lock = threading.RLock()
    state_lock = threading.Lock()  # Never held across stdout/file/model I/O.
    instance = request_id = None
    started = time.perf_counter()
    deadline = None
    last_finished = started
    active = False
    expired = False
    activity_token = activity_job_id = None
    stopped = threading.Event()
    engine = lease = None
    import psutil
    birth = psutil.Process(os.getpid()).create_time()
    def emit(event_type, **values):
        with lock:
            print(json.dumps({"type": event_type, "instance_id": instance, "request_id": request_id,
                "worker_pid": os.getpid(), "process_start_time": birth,
                "worker_elapsed_seconds": time.perf_counter()-started, **values}, ensure_ascii=False), file=protocol, flush=True)
    try:
        init = json.loads(sys.stdin.readline())
        if init.get("command") != "initialize":
            raise ValueError("Expected explicit text session initialization")
        instance = init["instance_id"]
        root = Path(init["root"]).resolve()
        idle, maximum = float(init["idle_seconds"]), float(init["max_session_seconds"])
        if not 1 <= idle <= 60 or not 1 <= maximum <= 600:
            raise ValueError("Text session lifetime policy invalid")
        emit("hello", nonce=init["nonce"], parent_pid=os.getppid(), executable=sys.executable,
            base_executable=getattr(sys, "_base_executable", None), prefix=sys.prefix,
            base_prefix=sys.base_prefix, cwd=str(Path.cwd()), python_version=sys.version)
        allowed = json.loads(sys.stdin.readline())
        if allowed != {"command": "owned", "instance_id": instance, "nonce": init["nonce"]}:
            raise ValueError("Parent did not confirm process ownership")
        emit("owned")
        def watchdog():
            nonlocal expired
            while not stopped.wait(.1):
                now = time.perf_counter()
                reason = None
                with state_lock:
                    if now-started >= maximum or (active and deadline is not None and now >= deadline):
                        expired, reason = True, (124, b"Text session reached its bounded lifetime/request deadline\n")
                    elif not active and now-last_finished >= idle+1:
                        expired, reason = True, (0, b"Text session idle watchdog exit\n")
                if reason:
                    os.write(2, reason[1])
                    os._exit(reason[0])
        thread = threading.Thread(target=watchdog, daemon=True)
        thread.start()
        engine = engine_factory(root, emit)
        for line in sys.stdin:
            envelope = json.loads(line)
            if envelope.get("command") == "preflight_activity":
                token, job = envelope.get("activity_token"), envelope.get("job_id")
                with state_lock:
                    now = time.perf_counter()
                    accepted = (not expired and not active and request_id is not None
                        and envelope.get("instance_id") == instance and envelope.get("nonce") == init["nonce"]
                        and envelope.get("previous_request_id") == request_id
                        and isinstance(token, str) and len(token) == 32 and all(c in "0123456789abcdef" for c in token)
                        and isinstance(job, str) and 1 <= len(job) <= 100
                        and token != activity_token and job != activity_job_id
                        and now-last_finished < idle and now-started < maximum
                        and isinstance(envelope.get("activity_deadline"), (int, float))
                        and not isinstance(envelope["activity_deadline"], bool)
                        and now < envelope["activity_deadline"] <= now+2)
                    if accepted:
                        last_finished, activity_token, activity_job_id = now, token, job
                # Separate ACK identity; the generation request_id is unchanged.
                emit("activity_ack", nonce=init["nonce"], previous_request_id=request_id,
                     activity_token=token, job_id=job, accepted=accepted)
                continue
            if envelope.get("instance_id") != instance:
                raise ValueError("Text session identity mismatch")
            if envelope.get("command") == "shutdown":
                break
            if envelope.get("command") != "generate":
                raise ValueError("Unsupported resident text command")
            request_id = envelope["request_id"]
            payload = envelope["payload"]
            if payload.get("kind") != "text" or Path(payload["root"]).resolve() != root or payload.get("observation") is not None:
                raise ValueError("Text session payload root/kind/observation mismatch")
            with state_lock:
                if expired or time.perf_counter()-started >= maximum:
                    raise RuntimeError("Text session lifetime expired before model work")
                active = True
                deadline = time.perf_counter() + min(294, float(envelope["request_seconds"]))
            if Path(payload["cancel_path"]).exists():
                raise RuntimeError("Text request cancelled before model work")
            emit("request_started")
            with redirect_stdout(sys.stderr):
                if lease is None:
                    from edu_tutor.jobs.lease import GPULease
                    lease = GPULease(root / ".local", "text-session:" + instance).__enter__()
                engine.process(payload)
            emit("done")
            with state_lock:
                active = False
                deadline = None
                last_finished = time.perf_counter()
    except BaseException as exc:
        emit("error", message=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        stopped.set()
        with redirect_stdout(sys.stderr):
            released = engine.close() if engine is not None else {"model_resident": False}
            if lease is not None:
                lease.__exit__(None, None, None)
        emit("closed", **released)


if __name__ == "__main__":
    main()
