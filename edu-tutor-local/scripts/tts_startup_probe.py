"""Bounded, model-free child used for the explicitly authorized environment comparison."""
import contextlib
import faulthandler
import importlib
import json
import os
from pathlib import Path
import sys
import time


def main():
    from edu_tutor.speech.session_worker import environment_snapshot, interpreter_checks
    protocol = sys.stdout
    started = time.monotonic()
    command = json.loads(sys.stdin.readline())
    root = Path(command["root"]).resolve()
    assert os.environ.get("CUDA_VISIBLE_DEVICES") == ""
    faulthandler.enable(file=sys.stderr, all_threads=True)
    # This timer diagnoses a hang; it never extends the external 45s bound.
    faulthandler.dump_traceback_later(35, file=sys.stderr)
    blocked = []
    def forbidden(*args, **kwargs):
        blocked.append("forbidden_model_or_cuda_call")
        raise AssertionError("Model weights, CUDA and synthesis are forbidden in this CPU probe")
    def unique_forbidden(name):
        # torch._dynamo indexes APIs by callable identity. Reusing one guard
        # across distinct APIs introduces duplicate-rule errors during import.
        def guard(*args, **kwargs):
            blocked.append(name)
            raise AssertionError("Forbidden CPU-probe operation: " + name)
        return guard
    def audit(event, args):
        if event == "socket.connect":
            raise AssertionError("Network use forbidden in startup probe")
        if event == "open" and isinstance(args[0], (str, bytes)):
            filename = os.fsdecode(args[0]).lower()
            if filename.endswith((".safetensors", ".bin", ".pt", ".pth")):
                raise AssertionError("Weight-like file read forbidden in startup probe: " + filename)
    sys.addaudithook(audit)
    def emit(stage, **value):
        print(json.dumps({"type": "startup_probe", "stage": stage, "pid": os.getpid(),
            "parent_pid": os.getppid(), "request_id": command["request_id"],
            "monotonic": time.monotonic(), "elapsed_seconds": time.monotonic()-started,
            **value}, ensure_ascii=False), file=protocol, flush=True)
    initial = environment_snapshot(root)
    emit("process_started", environment=initial, checks=interpreter_checks(initial, root))
    with contextlib.redirect_stdout(sys.stderr):
        for name in ("numpy", "torch", "transformers", "qwen_tts"):
            emit("import_started", module=name)
            module = importlib.import_module(name)
            if name == "torch":
                module.load = unique_forbidden("torch.load")
                module.cuda.is_available = lambda: False
                module.cuda.device_count = lambda: 0
                for attribute in ("_lazy_init", "init", "synchronize", "set_device", "mem_get_info"):
                    setattr(module.cuda, attribute, unique_forbidden("torch.cuda."+attribute))
            elif name == "transformers":
                module.PreTrainedModel.from_pretrained = classmethod(forbidden)
                module.AutoModel.from_pretrained = classmethod(forbidden)
            elif name == "qwen_tts":
                module.Qwen3TTSModel.from_pretrained = classmethod(forbidden)
                module.Qwen3TTSModel.generate_custom_voice = forbidden
            emit("import_ready", module=name, loaded_path=module.__file__)
    imported = environment_snapshot(root)
    checks = interpreter_checks(imported, root, require_imports=True)
    emit("imports_ready", environment=imported, checks=checks, forbidden_calls=blocked,
         weights_loaded=False, cuda_used=False, generated=False)
    # Keep stdin alive, as in the resident protocol. The parent explicitly closes.
    next_command = json.loads(sys.stdin.readline())
    assert next_command == {"command": "shutdown", "request_id": command["request_id"]}
    emit("closed", weights_loaded=False, cuda_used=False)
    faulthandler.cancel_dump_traceback_later()


if __name__ == "__main__":
    main()
