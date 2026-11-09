"""Private JSON pipe protocol. Not an arbitrary-command worker."""
from __future__ import annotations
import json
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from edu_tutor.jobs.lease import GPULease

_emit_lock = threading.Lock()


def emit(event_type, **values):
    # The optional telemetry publisher and existing text streamer share this pipe.
    with _emit_lock:
        print(json.dumps({"type": event_type, **values}, ensure_ascii=False), flush=True)


def inference_snapshot(model, precision, dtype, torch):
    """Parameter storage only; excludes KV cache, quantization buffers and CUDA context."""
    storages = {}
    dtypes = {}
    devices = set()
    for parameter in model.parameters():
        storage = parameter.untyped_storage()
        key = (str(parameter.device), storage.data_ptr())
        storages.setdefault(key, storage.nbytes())
        dtypes[str(parameter.dtype)] = dtypes.get(str(parameter.dtype), 0) + parameter.numel()
        devices.add(str(parameter.device))
    if devices != {"cuda:0"}:
        raise RuntimeError("Text inference requires all parameters on cuda:0; no CPU offload")
    quantized = bool(getattr(model, "is_loaded_in_4bit", False))
    if precision == "nf4" and not quantized:
        raise RuntimeError("Requested NF4 model did not confirm 4bit loading")
    if precision == "bf16" and quantized:
        raise RuntimeError("Requested BF16 model is still quantized")
    incoming = model.get_input_embeddings().weight
    outgoing = model.get_output_embeddings().weight
    return {"requested_precision": precision, "quantization": "nf4_double" if precision == "nf4" else "none",
        "load_dtype": str(dtype), "actual_parameter_dtypes_elements": dtypes,
        "actual_parameter_devices": sorted(devices), "actual_is_loaded_in_4bit": quantized,
        "unique_parameter_storage_bytes": sum(storages.values()), "unique_parameter_storage_count": len(storages),
        "parameter_storage_scope": "Unique parameter storages only; excludes KV/quantization buffers/CUDA context/allocator reserve",
        "word_embeddings_tied": incoming.untyped_storage().data_ptr() == outgoing.untyped_storage().data_ptr(),
        "allocated_after_load_bytes": torch.cuda.memory_allocated(), "reserved_after_load_bytes": torch.cuda.memory_reserved(),
        "peak_allocated_during_load_bytes": torch.cuda.max_memory_allocated(),
        "peak_reserved_during_load_bytes": torch.cuda.max_memory_reserved()}


def load_text(root, adapter=None, *, precision="nf4", model_ref="installed"):
    if model_ref != "installed":
        from .text_candidate import resolve_candidate
        candidate_folder, candidate_meta = resolve_candidate(root, model_ref, adapter, precision)
    if precision not in {"nf4", "bf16"}:
        raise ValueError("Only explicit nf4 or bf16 text inference is supported")
    import_started = time.perf_counter()
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    loader_import_seconds = time.perf_counter() - import_started
    folder = root / ".local/models/text" if model_ref == "installed" else candidate_folder
    meta = (json.loads((folder / "model-manifest.json").read_text(encoding="utf-8"))
            if model_ref == "installed" else candidate_meta)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable; full text-model CPU fallback is disabled")
    bf16_supported = torch.cuda.is_bf16_supported()
    if precision == "bf16" and not bf16_supported:
        raise RuntimeError("BF16 is unsupported on this device; FP16 fallback is forbidden")
    dtype = torch.bfloat16 if bf16_supported else torch.float16
    tokenizer = AutoTokenizer.from_pretrained(folder, local_files_only=True, trust_remote_code=False)
    options = dict(local_files_only=True, trust_remote_code=False, use_safetensors=True,
                   device_map={"": 0}, torch_dtype=dtype, attn_implementation="sdpa")
    if precision == "nf4":
        options["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype)
    model = AutoModelForCausalLM.from_pretrained(folder, **options)
    if adapter:
        from peft import PeftModel
        path = Path(adapter).resolve()
        if not any(path.is_relative_to(base.resolve()) for base in (root / ".local/adapters", root / "runs")):
            raise ValueError("Adapter must be a registered project artifact")
        manifest_path = path / "adapter-manifest.json"
        if not manifest_path.exists():
            manifest_path = path.parent / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        revision = manifest.get("base_revision") or manifest.get("model_revision") or manifest.get("revision")
        if revision != meta["revision"]:
            raise ValueError("Adapter base revision mismatch")
        if not (path / "adapter_model.safetensors").is_file() or any(path.glob("*.bin")) or any(path.glob("*.pkl")) or any(path.glob("*.pt")):
            raise ValueError("Only safetensors adapters are allowed")
        model = PeftModel.from_pretrained(model, path, local_files_only=True, is_trainable=False,
                                         use_safetensors=True, trust_remote_code=False)
    model.eval()
    meta = {**meta, "inference": {**inference_snapshot(model, precision, dtype, torch),
                                 "loader_import_seconds": loader_import_seconds}}
    structure = {"validation": "loaded_on_gpu", "device": str(model.device), "dtype": str(dtype),
        "last_loaded_at": datetime.now(timezone.utc).isoformat(), "last_loaded_adapter": str(adapter) if adapter else None,
        "resident": False, "structure_notice": "최근 로딩 기록입니다. 작업이 끝나면 모델 프로세스는 종료됩니다.",
        "parameter_count": sum(p.numel() for p in model.parameters()),
        "parameter_count_kind": "stored_tensor_elements_quantized",
        "parameter_count_notice": "양자화된 저장 텐서의 요소 수입니다. 원래 모델의 논리적 파라미터 수와 다를 수 있습니다.",
        "config": model.config.to_dict(),
        "modules": [{"name": name, "type": type(module).__name__, "parameters": sum(p.numel() for p in module.parameters(recurse=False)),
                     "lora": "lora_" in name or hasattr(module, "lora_A"),
                     "tensors": [{"name": key, "shape": list(parameter.shape), "dtype": str(parameter.dtype),
                                  "device": str(parameter.device), "trainable": parameter.requires_grad}
                                 for key, parameter in module.named_parameters(recurse=False)]}
                    for name, module in model.named_modules() if name]}
    structure["inference"] = meta["inference"]
    structure["module_count_total"] = len(structure["modules"])
    structure["modules_truncated"] = False
    (folder / "runtime-structure.json").write_text(json.dumps(structure, ensure_ascii=False, indent=2), encoding="utf-8")
    return model, tokenizer, meta


def text_job(payload, model_loader=None, emit_fn=None, residency=None):
    emit = emit_fn or globals()["emit"]
    from .text_precision import validate_precision, validate_inference
    precision = validate_precision(payload.get("precision", "nf4"))
    import torch
    from transformers import TextIteratorStreamer, StoppingCriteria, StoppingCriteriaList
    root = Path(payload["root"])
    if payload.get("observation") is not None and not 1 <= int(payload["max_new_tokens"]) <= 128:
        raise ValueError("Observed text requests are limited to 1..128 new tokens")
    started = time.monotonic()
    performance_clock = {"started": time.perf_counter()}
    model, tokenizer, meta = (model_loader or load_text)(root, payload.get("adapter"), precision=precision)
    actual_inference = validate_inference(meta.get("inference"), precision, payload.get("adapter"))
    from .text_eos import generation_eos_ids
    cpu_fixture = (model_loader is not None and meta.get("inference", {}).get("fixture_only") is True
                   and meta.get("download_complete") is not True)
    eos_ids = generation_eos_ids(model, tokenizer, cpu_fixture=cpu_fixture)
    loaded_at = time.monotonic()
    performance_clock["loaded"] = time.perf_counter()
    inputs = tokenizer.apply_chat_template(payload["messages"], add_generation_prompt=True,
        enable_thinking=False, tokenize=True, return_dict=True, return_tensors="pt").to(model.device)
    count = inputs["input_ids"].shape[-1]
    budget = payload["max_new_tokens"]
    if count + budget > 2048:
        raise ValueError(f"Token budget exceeded ({count}+{budget}>2048). 질문/대화를 줄여 주세요.")
    cancel = Path(payload["cancel_path"])
    observation = payload.get("observation")
    observer = None
    publisher = None
    observation_setup_error = None
    observation_setup_started = time.perf_counter()
    if observation and observation.get("mode", "light") != "off":
        try:
            from edu_tutor.models.observation import BoundedEmitter, ModelObserver
            publisher = BoundedEmitter(emit, flush_ms=observation.get("flush_ms", 250))
            observer = ModelObserver(model, tokenizer, observation, publisher, meta, payload.get("adapter")).start()
        except Exception as exc:
            observation_setup_error = type(exc).__name__
            if observer is not None:
                observer.close("setup_error")
            if publisher is not None:
                publisher.close()
            observer = publisher = None
    observation_setup_seconds = time.perf_counter() - observation_setup_started
    first_token_observed = []
    class Stop(StoppingCriteria):
        def __call__(self, *_args, **_kwargs):
            if observation is not None and not first_token_observed:
                first_token_observed.append(time.perf_counter())
            if observer is not None:
                observer.poll_control()
            return cancel.exists() or time.monotonic() - started > 285
    if observer is None:
        streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True, timeout=1)
    else:
        from edu_tutor.models.observation import observed_streamer
        streamer = observed_streamer(tokenizer, observer, skip_prompt=True, skip_special_tokens=True, timeout=1)
    errors = []
    outputs = []
    generation_started = []
    generation_finished = []
    def work():
        try:
            generation_started.append(time.monotonic())
            performance_clock["generation_started"] = time.perf_counter()
            with torch.inference_mode():
                outputs.append(model.generate(**inputs, max_new_tokens=budget, do_sample=False,
                    streamer=streamer, stopping_criteria=StoppingCriteriaList([Stop()]),
                    pad_token_id=tokenizer.pad_token_id, eos_token_id=eos_ids))
        except BaseException as exc:
            errors.append(exc)
            streamer.end()
        finally:
            generation_finished.append(time.monotonic())
            performance_clock["generation_finished"] = time.perf_counter()
            if observer is not None:
                observer.close("error" if errors else "cancelled" if cancel.exists() else "completed")
            if publisher is not None:
                publisher.close()
    thread = threading.Thread(target=work)
    thread.start()
    import queue
    while True:
        try:
            delta = next(streamer)
        except queue.Empty:
            if not thread.is_alive():
                break
            continue
        except StopIteration:
            break
        if delta:
            emit("delta", text=delta)
    thread.join()
    if errors:
        raise errors[0]
    output = outputs[0][0][count:].tolist() if outputs else []
    reason = "cancelled" if cancel.exists() else "eos" if output and output[-1] in eos_ids else "length_or_timeout"
    report = {"tier": "T2", "kind": "text", "timestamp": datetime.now(timezone.utc).isoformat(),
              "model_id": meta["model_id"], "revision": meta["revision"], "adapter": payload.get("adapter"),
              "requested_precision": precision, "inference": actual_inference,
              "input_tokens": count, "output_tokens": len(output), "finish_reason": reason, "eos_token_ids": eos_ids,
              "elapsed_seconds": time.monotonic() - started,
              "model_load_seconds": loaded_at - started, "generation_seconds": (generation_finished[0] if generation_finished else time.monotonic()) - loaded_at,
              "model_load_count": 1, "peak_vram_bytes": torch.cuda.max_memory_allocated(),
              "gpu": torch.cuda.get_device_name(0), "text": tokenizer.decode(output, skip_special_tokens=True)}
    if residency is not None:
        report.update(residency)
        report["model_load_count"] = residency["request_model_load_count"]
        report["model_resident"] = True
        report["peak_vram_scope"] = "process cumulative peak; resident requests are not independently reset"
    if observation is not None:
        import hashlib
        from edu_tutor.models.observation import persisted_report
        report["observation"] = observer.summary(reason) if observer else {"mode": "off", "remaining_hooks": 0, "gpu_elapsed_ms": None}
        if observation_setup_error:
            report["observation"].update({"observer_failed": True, "setup_error_type": observation_setup_error})
        report["observation_setup_seconds"] = observation_setup_seconds
        report["elapsed_seconds"] = time.perf_counter() - performance_clock["started"]
        report["model_load_seconds"] = performance_clock["loaded"] - performance_clock["started"]
        report["generation_seconds"] = performance_clock["generation_finished"] - performance_clock["generation_started"]
        report["preparation_seconds"] = performance_clock["generation_started"] - performance_clock["loaded"]
        report["first_token_latency_seconds"] = first_token_observed[0] - performance_clock["generation_started"] if first_token_observed else None
        report["first_token_latency_status"] = "measured_host_stopping_callback" if first_token_observed else "not_measured"
        report["first_token_latency_kind"] = "generation_start_to_first_existing_stopping_callback_after_streamer"
        report["generation_remaining_seconds"] = performance_clock["generation_finished"] - first_token_observed[0] if first_token_observed else None
        report["remaining_output_tokens"] = max(len(output) - 1, 0)
        report["warmup_seconds"] = None
        report["host_clock"] = time.get_clock_info("perf_counter").implementation
        report["host_clock_resolution_seconds"] = time.get_clock_info("perf_counter").resolution
        report["generation_timing_notice"] = "Cold worker. First callback interval includes prefill, initial CUDA preparation and streamer handling. Load/preparation and remaining generation are separate; standalone warmup is unmeasured. Host wall time, not GPU kernel time."
        report["peak_vram_reserved_bytes"] = torch.cuda.max_memory_reserved()
        report["input_token_ids"] = inputs["input_ids"][0].tolist()
        report["output_token_ids"] = output
        report["input_token_ids_sha256"] = hashlib.sha256(json.dumps(report["input_token_ids"]).encode()).hexdigest()
        report["output_token_ids_sha256"] = hashlib.sha256(json.dumps(output).encode()).hexdigest()
        saved_report = persisted_report(report, observation)
    else:
        saved_report = report
    (Path(payload["run_dir"]) / "result.json").write_text(json.dumps(saved_report, ensure_ascii=False, indent=2), encoding="utf-8")
    emit("metadata", **report)


def main():
    payload = None
    try:
        payload = json.loads(sys.stdin.readline())
        if payload.get("kind") not in {"text", "text_batch", "speech", "speech_batch", "vision", "evaluation"}:
            raise ValueError("Unsupported worker type")
        with GPULease(Path(payload["root"]) / ".local", payload["job_id"]):
            if payload["kind"] == "text":
                text_job(payload)
            elif payload["kind"] in {"evaluation", "text_batch"}:
                from edu_tutor.models.evaluate import evaluation_job
                evaluation_job(payload, emit)
            elif payload["kind"] == "speech":
                from edu_tutor.speech.provider import speech_job
                speech_job(payload, emit)
            elif payload["kind"] == "speech_batch":
                from edu_tutor.speech.provider import speech_batch_job
                speech_batch_job(payload, emit)
            else:
                from edu_tutor.models.vision_runtime import vision_job
                vision_job(payload, emit)
        emit("done")
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        if isinstance(payload, dict) and payload.get("observation") is not None:
            # New observer requests do not persist an arbitrary exception that
            # might quote student input. Ordinary chat behavior is unchanged.
            message = f"{type(exc).__name__}: Observed text worker failed"
        emit("error", message=message)
        sys.exit(1)


if __name__ == "__main__":
    main()
