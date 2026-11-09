"""Bounded TTS-only child: a GPU lease covers the entire resident lifetime.

The authenticated parent reserves each request before sending it. No model is
loaded on module import or while merely starting an unused process.
"""
from __future__ import annotations

import gc
import importlib.metadata
import importlib.util
import json
import math
import os
import site
import struct
import sys
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from contextlib import redirect_stdout

from edu_tutor.jobs.lease import GPULease


def environment_snapshot(root):
    """Read interpreter/package provenance without importing numerical modules.

    Only explicitly selected environment variables are recorded. The same helper
    is used by the bounded CPU control and by the actual child before weights.
    """
    root = Path(root).resolve()
    cfg_path = root / ".venv/pyvenv.cfg"
    cfg = {}
    if cfg_path.is_file():
        for line in cfg_path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator:
                cfg[key.strip().lower()] = value.strip()
    modules = {}
    for name, distribution in (("numpy", "numpy"), ("torch", "torch"),
                               ("transformers", "transformers"), ("qwen_tts", "qwen-tts")):
        module = sys.modules.get(name)
        try:
            spec = importlib.util.find_spec(name)
            origin = spec.origin if spec else None
        except (ImportError, ValueError):
            origin = None
        try:
            package = importlib.metadata.distribution(distribution)
            version, location = package.version, str(package.locate_file(""))
        except importlib.metadata.PackageNotFoundError:
            version = location = None
        modules[name] = {"loaded": module is not None,
            "module_file": getattr(module, "__file__", None),
            "module_version": getattr(module, "__version__", None),
            "resolved_spec_origin": origin, "distribution_version": version,
            "distribution_location": location}
    relevant = ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "PATH", "PYTHONUTF8",
        "PYTHONIOENCODING", "PYTHONNOUSERSITE", "CUDA_VISIBLE_DEVICES", "CUDA_PATH",
        "CUDA_PATH_V12_8", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY",
        "TOKENIZERS_PARALLELISM", "EDU_TTS_PARENT_SYS_PATH", "EDU_TTS_PARENT_PREFIX", "EDU_TTS_PARENT_EXEC_PREFIX")
    return {"python_version": sys.version, "python_bits": struct.calcsize("P") * 8,
        "executable": sys.executable, "base_executable": getattr(sys, "_base_executable", None),
        "prefix": sys.prefix, "base_prefix": sys.base_prefix, "exec_prefix": sys.exec_prefix,
        "base_exec_prefix": sys.base_exec_prefix, "python_home_state": getattr(sys, "_home", None),
        "cwd": str(Path.cwd()), "sys_path": list(sys.path), "pid": os.getpid(), "parent_pid": os.getppid(),
        "flags": {key: getattr(sys.flags, key, None) for key in ("utf8_mode", "isolated", "ignore_environment",
            "no_site", "no_user_site", "safe_path", "hash_randomization", "dev_mode")},
        "site": {"prefixes": list(site.PREFIXES), "enable_user_site": site.ENABLE_USER_SITE,
            "getsitepackages": site.getsitepackages()},
        "pyvenv_cfg": {"path": str(cfg_path), "exists": cfg_path.is_file(), "values": cfg},
        "selected_environment": {key: os.environ.get(key) for key in relevant}, "modules": modules,
        "scope": "Interpreter and imported-module metadata; no model weights, tensors or full environment dump"}


def interpreter_checks(snapshot, root, *, require_imports=False):
    """Validate the configured project venv, without assuming executable equality."""
    root = Path(root).resolve()
    cfg = snapshot["pyvenv_cfg"]
    if not cfg["exists"]:
        return {"applicable": False, "verified": False, "reason": "Project pyvenv.cfg is absent"}
    expected = root / ".venv"
    checks = {"project_prefix": Path(snapshot["prefix"]).resolve() == expected,
              "project_exec_prefix": Path(snapshot["exec_prefix"]).resolve() == expected}
    home = cfg["values"].get("home")
    checks["base_prefix_matches_cfg_home"] = bool(home) and Path(snapshot["base_prefix"]).resolve() == Path(home).resolve()
    checks["base_exec_prefix_matches_cfg_home"] = bool(home) and Path(snapshot["base_exec_prefix"]).resolve() == Path(home).resolve()
    if require_imports:
        site_packages = expected / "Lib/site-packages"
        for name, module in snapshot["modules"].items():
            file = module["module_file"]
            checks[name+"_loaded_from_project_venv"] = bool(module["loaded"] and file
                and Path(file).resolve().is_relative_to(site_packages))
    return {"applicable": True, "verified": all(checks.values()), "checks": checks}


def memory_snapshot(torch):
    free, total = torch.cuda.mem_get_info()
    return {"device": str(torch.cuda.current_device()), "device_name": torch.cuda.get_device_name(),
        "allocated_bytes": torch.cuda.memory_allocated(), "reserved_bytes": torch.cuda.memory_reserved(),
        "peak_allocated_bytes": torch.cuda.max_memory_allocated(), "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
        "device_free_bytes": free, "device_total_bytes": total, "device_used_bytes": total-free,
        "scope": "allocated/reserved are this process PyTorch allocator; device_used includes other processes and driver allocations"}


def placement(model):
    """Inspect placement metadata only; never copy tensor contents or weights."""
    def describe(obj):
        if obj is None:
            return None
        counts = Counter((str(p.device), str(p.dtype)) for p in obj.parameters()) if hasattr(obj, "parameters") else Counter()
        return {"python_id": id(obj), "type": type(obj).__name__,
            "parameter_tensor_counts": [{"device": device, "dtype": dtype, "tensors": n}
                                        for (device, dtype), n in sorted(counts.items())],
            "declared_device": str(getattr(obj, "device", "not_applicable"))}
    generator = model.model
    codec = generator.speech_tokenizer
    return {"wrapper": describe(model), "text_processor": describe(model.processor),
        "text_tokenizer": describe(getattr(model.processor, "tokenizer", None)),
        "generator": describe(generator), "talker": describe(generator.talker),
        "subtalker": describe(getattr(generator.talker, "code_predictor", None)),
        "speech_tokenizer_wrapper": describe(codec), "codec_model": describe(codec.model),
        "codec_decoder": describe(getattr(codec.model, "decoder", None)),
        "text_preparation_notice": "Processor tokenization is CPU Python; package transfers token IDs to the wrapper model device. Actual parameter devices are listed separately."}


def load_model(root, progress=None):
    progress = progress or (lambda *_args, **_kwargs: None)
    imports_started = time.monotonic()
    progress("imports_started")
    progress("torch_import_started")
    import torch
    progress("torch_import_finished")
    progress("tts_import_started")
    from qwen_tts import Qwen3TTSModel
    progress("tts_import_finished")
    imports_finished = time.monotonic()
    environment = environment_snapshot(root)
    checks = interpreter_checks(environment, root, require_imports=True)
    progress("imports_ready", environment=environment, interpreter_checks=checks)
    if checks["applicable"] and not checks["verified"]:
        raise RuntimeError("Imported TTS modules do not match the configured project virtualenv")
    progress("cuda_initialization_started")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable; no CPU fallback")
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    torch.cuda.synchronize()
    progress("cuda_initialization_finished")
    started = time.monotonic()
    progress("model_load_started")
    model = Qwen3TTSModel.from_pretrained(str(root / ".local/models/tts"), device_map="cuda:0",
        dtype=dtype, attn_implementation="sdpa", local_files_only=True)
    torch.cuda.synchronize()
    finished = time.monotonic()
    progress("model_load_finished")
    return torch, model, {"worker_heavy_import_seconds": imports_finished-imports_started,
        "model_load_seconds": finished-started, "requested_dtype": str(dtype), "attention_backend": "sdpa",
        "device_map": "cuda:0", "local_files_only": True, "model_path": str(root / ".local/models/tts")}


class SessionEngine:
    def __init__(self, root, instance_id, *, model_loader=load_model):
        self.root = Path(root).resolve()
        self.instance_id = instance_id
        self.model_loader = model_loader
        self.model = self.torch = None
        self.model_instance_id = None
        self.load_count = 0
        self.request_count = 0
        self.model_placement = None
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.load_report = None
        try:
            import psutil
            self.process_start_time = psutil.Process(os.getpid()).create_time()
        except (ImportError, OSError):
            self.process_start_time = None

    def process(self, payload, request_id, emit, progress=None):
        started = time.monotonic()
        progress = progress or (lambda *_args, **_kwargs: None)
        root = Path(payload["root"]).resolve()
        if root != self.root or payload.get("kind") not in {"speech", "speech_batch"}:
            raise ValueError("TTS session root/kind mismatch")
        items = payload.get("items") if payload["kind"] == "speech_batch" else [{"audio_id": payload["audio_id"], "spec": payload["spec"]}]
        if not isinstance(items, list) or not 1 <= len(items) <= 4:
            raise ValueError("TTS session request must contain 1..4 clips")
        if payload.get("tts_benchmark") and len(items) != 1:
            raise ValueError("Benchmark requests must each synthesize exactly one clip")
        if Path(payload["cancel_path"]).exists():
            raise RuntimeError("Speech cancelled before model load")
        if payload.get("output_dir"):
            output = Path(payload["output_dir"]).resolve()
            if not payload.get("tts_benchmark") or not output.is_relative_to((root / "runs").resolve()):
                raise ValueError("Invalid benchmark output directory")
        if self.model is None:
            self.torch, self.model, self.load_report = (self.model_loader(root, progress=progress)
                if self.model_loader is load_model else self.model_loader(root))
            self.load_count += 1
            self.model_instance_id = uuid.uuid4().hex
            self.model_placement = placement(self.model)
            load_seconds = self.load_report["model_load_seconds"]
            request_load_count = 1
            imports_seconds = self.load_report["worker_heavy_import_seconds"]
        else:
            load_seconds = 0.0
            request_load_count = 0
            imports_seconds = 0.0
        self.request_count += 1
        info = {"worker_pid": os.getpid(), "process_start_time": self.process_start_time,
            "worker_instance_id": self.instance_id, "worker_created_at": self.created_at,
            "model_instance_id": self.model_instance_id, "model_python_id": id(self.model), "model_object_id": id(self.model),
            "cumulative_model_load_count": self.load_count, "request_model_load_count": request_load_count,
            "load_count_total": self.load_count, "load_count_this_request": request_load_count,
            "request_index": self.request_count, "request_id": request_id, "job_id": payload.get("job_id"),
            "model_placement": self.model_placement, "model_load_settings": self.load_report,
            "request_heavy_import_seconds": imports_seconds, "model_resident_before_request": not bool(request_load_count),
            "_request_started_monotonic": started}
        progress("model_ready", model_instance_id=self.model_instance_id,
            model_object_id=id(self.model), load_count_total=self.load_count,
            load_count_this_request=request_load_count, model_placement=self.model_placement,
            model_load_settings=self.load_report, memory=memory_snapshot(self.torch))
        from edu_tutor.speech.provider import speech_job
        results = []
        for index, item in enumerate(items):
            if Path(payload["cancel_path"]).exists():
                raise RuntimeError("Speech cancelled")
            def guarded_emit(kind, **value):
                if Path(payload["cancel_path"]).exists():
                    raise RuntimeError("Speech cancelled before publishing audio")
                emit(kind, **value)
            results.append(speech_job({**payload, **item}, guarded_emit, model=self.model,
                model_load_seconds=load_seconds if index == 0 else 0.0, batch_index=index,
                session_info=info, model_load_count=request_load_count if index == 0 else 0,
                progress=progress))
        return {"worker_pid": os.getpid(), "process_start_time": self.process_start_time,
            "model_instance_id": self.model_instance_id, "model_python_id": id(self.model), "model_object_id": id(self.model),
            "cumulative_model_load_count": self.load_count, "request_model_load_count": request_load_count,
            "load_count_total": self.load_count, "load_count_this_request": request_load_count,
            "worker_request_seconds": time.monotonic()-started, "completed_clips": len(results),
            "memory_after_request": memory_snapshot(self.torch), "model_resident": True}

    def close(self):
        if self.model is None:
            return {"model_resident": False, "model_load_count": self.load_count}
        self.model = None
        gc.collect()
        self.torch.cuda.synchronize()
        self.torch.cuda.empty_cache()
        self.torch.cuda.synchronize()
        return {"model_resident": False, "model_load_count": self.load_count,
                "memory_after_release": memory_snapshot(self.torch)}


def main():
    protocol = sys.stdout
    instance_id = request_id = None
    engine = lease = None
    started = time.monotonic()
    last_finished = started
    idle_seconds, max_session_seconds = 30.0, 600.0
    exit_reason = "eof"
    active = False
    request_deadline = None
    watchdog_stop = threading.Event()
    def emit(kind, **value):
        print(json.dumps({"type": kind, "instance_id": instance_id, "request_id": request_id,
            "worker_pid": os.getpid(),
            "process_start_time": engine.process_start_time if engine is not None else None,
            "worker_elapsed_seconds": time.monotonic()-started, **value},
            ensure_ascii=False), file=protocol, flush=True)
    def watchdog():
        # No thread may block in stdio while native numerical DLLs import.
        # The parent provides normal idle/deadline shutdown. This own-process
        # backstop also bounds an orphan whose stdin remains open elsewhere.
        while not watchdog_stop.wait(.25):
            now = time.monotonic()
            reason = ("session_deadline" if now-started >= max_session_seconds else
                      "request_deadline" if active and request_deadline is not None and now >= request_deadline else
                      "idle_timeout" if engine is not None and not active and now-last_finished >= idle_seconds else None)
            if reason:
                # Do not log to a pipe here: a dead/blocked parent could make
                # logging itself block forever. Process exit releases owned
                # GPU allocations and the OS lease; the parent records exit.
                os._exit(124)
    threading.Thread(target=watchdog, daemon=True, name="tts-lifetime-watchdog").start()
    try:
        while True:
            now = time.monotonic()
            if now-started >= max_session_seconds:
                exit_reason = "session_deadline"
                break
            if engine is not None and now-last_finished >= idle_seconds:
                exit_reason = "idle_timeout"
                break
            # Main-thread-only reading avoids the observed Windows native import
            # stall when another thread is already waiting inside stdin.read.
            line = sys.stdin.readline()
            if not line:
                break
            command = json.loads(line)
            new_instance = command.get("instance_id")
            if not isinstance(new_instance, str) or not new_instance or (instance_id is not None and new_instance != instance_id):
                raise ValueError("Session instance mismatch")
            instance_id = new_instance
            request_id = command.get("request_id")
            if command.get("command") == "shutdown":
                exit_reason = command.get("reason", "shutdown")
                break
            if command.get("command") != "synthesize" or not isinstance(request_id, str) or not request_id:
                raise ValueError("Invalid TTS command/request identity")
            payload = command["payload"]
            request_timeout = float(command.get("request_timeout_seconds", 300))
            if not math.isfinite(request_timeout) or not 0 < request_timeout <= 300:
                raise ValueError("Invalid bounded TTS request lifetime")
            request_deadline = time.monotonic()+request_timeout
            if command.get("request_deadline_monotonic") is not None:
                absolute_deadline = float(command["request_deadline_monotonic"])
                if not math.isfinite(absolute_deadline):
                    raise ValueError("Invalid TTS request absolute deadline")
                request_deadline = min(request_deadline, absolute_deadline)
            if time.monotonic() >= request_deadline:
                raise TimeoutError("TTS request deadline expired before processing")
            active = True
            request_started = time.monotonic()
            progress_request_id = request_id
            def progress(stage, **details):
                record = {"stage": stage, "worker_request_elapsed_seconds": time.monotonic()-request_started,
                          "worker_pid": os.getpid(), "instance_id": instance_id,
                          "request_id": progress_request_id, **details}
                with (Path(payload["run_dir"]) / "worker-progress.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False)+"\n")
                    handle.flush()
                emit("progress", **{key: value for key, value in record.items() if key not in {"instance_id", "request_id"}})
            if engine is None:
                idle_seconds = float(command.get("idle_seconds", 30))
                max_session_seconds = float(command.get("max_session_seconds", 600))
                if not 1 <= idle_seconds <= 120 or not 1 <= max_session_seconds <= 600:
                    raise ValueError("Invalid bounded TTS session lifetime")
                root = Path(payload["root"]).resolve()
                progress("process_started", parent_pid=os.getppid(),
                    process_age_seconds=time.monotonic()-started)
                environment = environment_snapshot(root)
                checks = interpreter_checks(environment, root)
                progress("interpreter_verified" if checks["verified"] else "interpreter_unverified",
                    environment=environment, interpreter_checks=checks)
                if checks["applicable"] and not checks["verified"]:
                    raise RuntimeError("TTS interpreter does not match the configured project virtualenv")
                lease = GPULease(root / ".local", "tts-session-"+instance_id).__enter__()
                engine = SessionEngine(root, instance_id)
            emit("request_started", worker_pid=os.getpid(), process_start_time=engine.process_start_time)
            # Installed libraries print diagnostic banners to Python stdout.
            # Preserve them on stderr while this captured stream stays JSON-only.
            with redirect_stdout(sys.stderr):
                result = engine.process(payload, request_id, emit, progress=progress)
            last_finished = time.monotonic()
            emit("done", **result)
            request_id = None
            active = False
            request_deadline = None
    except Exception as exc:
        exit_reason = "request_error"
        emit("error", message=f"{type(exc).__name__}: {exc}")
        raise SystemExit(1)
    finally:
        try:
            with redirect_stdout(sys.stderr):
                released = engine.close() if engine else {"model_resident": False}
            if engine is not None:
                progress("closed", reason=exit_reason, **released)
            emit("closed", reason=exit_reason, worker_pid=os.getpid(), **released)
        finally:
            try:
                if lease is not None:
                    lease.__exit__(None, None, None)
            finally:
                watchdog_stop.set()


if __name__ == "__main__":
    main()
