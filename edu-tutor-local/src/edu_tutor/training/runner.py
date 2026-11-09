"""Bounded local-only QLoRA worker. Public entrypoint never downloads weights.

Saved adapters are new-training starting points, not resumable Trainer checkpoints.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .data import load_records, validate_dataset
from .masking import ResponseOnlyCollator, encode_response_only


def _write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def _phase(output, phase, reason):
    path = Path(output) / "phase.json"
    temporary = path.with_suffix(".tmp")
    _write(temporary, {"phase":phase, "reason":reason, "timestamp":datetime.now(timezone.utc).isoformat(),
                       "pid":os.getpid(),"parent_pid":os.getppid()})
    temporary.replace(path)


def _training_resource_metrics(cuda, actual_microbatches, batch_size, elapsed_seconds):
    """Single-GPU cumulative samples/s; allocator bytes, not device-wide VRAM.

    Peak allocation is since this worker reset its CUDA peak before model load.
    Missing historical samples are intentionally never reconstructed.
    """
    samples = actual_microbatches * batch_size
    result = {"current_vram_bytes": int(cuda.memory_allocated()),
              "peak_vram_bytes": int(cuda.max_memory_allocated()),
              "samples_processed": samples}
    if elapsed_seconds > 0 and math.isfinite(elapsed_seconds):
        result["samples_per_second"] = samples / elapsed_seconds
    return result


def _assert_finite_adapter_weights(trainable):
    """Abort before another step or save if the small trainable adapter is invalid."""
    import torch
    if not trainable or not torch.stack([parameter.detach().isfinite().all()
                                        for parameter in trainable.values()]).all().item():
        raise RuntimeError("Missing or nonfinite adapter weights after optimizer step")


def _provenance(model_path, configured):
    path = Path(model_path).resolve()
    manifest = json.loads((path / "model-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("model_id") != "Qwen/Qwen3-1.7B" or not re.fullmatch(r"[a-f0-9]{40}", manifest.get("revision", "")):
        raise ValueError("A pinned official Qwen3-1.7B model manifest is required")
    if manifest["revision"] != configured["revision"] or manifest["model_id"] != configured["id"]:
        raise ValueError("Configured model/revision does not match local provenance")
    if not list(path.glob("*.safetensors")):
        raise ValueError("Local safetensors model weights are required")
    for file in manifest["files"]:
        item = (path / file["path"]).resolve()
        if not item.is_relative_to(path) or not item.is_file() or item.stat().st_size != file["size"]:
            raise ValueError("Local model manifest file missing or wrong size")
        wanted_hash = file.get("sha256")
        if not isinstance(wanted_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", wanted_hash):
            raise ValueError("Local model files require SHA256 provenance")
        digest = hashlib.sha256()
        with item.open("rb") as stream:
            while block := stream.read(8 * 1024**2):
                digest.update(block)
        if digest.hexdigest() != wanted_hash:
            raise ValueError(f"Local model file checksum mismatch: {item.name}")
    return manifest


def _smoke_evidence(project, model_revision, dataset_hash):
    for path in (project / "runs").glob("*/manifest.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (value.get("mode") == "smoke" and value.get("status") == "passed"
                and value.get("optimizer_steps") == 5 and value.get("revision") == model_revision
                and value.get("dataset_sha256") == dataset_hash and value.get("reload", {}).get("status") == "passed"):
            return str(path)
    raise ValueError("Demo requires a completed 5-step smoke and separate-process reload for this revision/dataset")


def _matching_owned_processes(identities):
    """Never operate on a recycled PID or an unrelated Python process."""
    import psutil
    found=[]
    for pid, created in identities.items():
        try:
            item=psutil.Process(pid)
            if item.create_time()==created and item.is_running():found.append(item)
        except psutil.NoSuchProcess:
            pass
    return found


def _terminate_owned_training_tree(process, identities):
    import psutil
    # Children were observed while descended from this exact Popen. Their birth
    # times retain ownership even if a Windows venv redirector already exited.
    owned=_matching_owned_processes(identities)
    for item in sorted(owned,key=lambda p:p.pid==process.pid):
        try:item.terminate()
        except psutil.NoSuchProcess:pass
    _, alive=psutil.wait_procs(owned,timeout=3)
    for item in alive:
        try:
            if item.create_time()==identities[item.pid]:item.kill()
        except psutil.NoSuchProcess:pass
    _, alive=psutil.wait_procs(alive,timeout=2)
    if alive:raise RuntimeError('Owned training worker termination unconfirmed; do not start another model')
    process.wait(timeout=1)


def _bounded_subprocess(command, log, env, timeout, cancel_event, output):
    import psutil
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                               env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    launcher=psutil.Process(process.pid)
    identities={process.pid:launcher.create_time()}
    started = time.monotonic()
    cancelled_at = None
    last_progress = started
    previous_progress = None
    try:
        while process.poll() is None:
            try:
                if launcher.create_time()!=identities[process.pid]:raise RuntimeError('Training launcher PID identity changed')
                for child in launcher.children(recursive=True):identities[child.pid]=child.create_time()
            except psutil.NoSuchProcess:
                pass
            evidence = tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns)
                             for p in (output / "phase.json", output / "metrics.jsonl") if p.exists())
            if evidence != previous_progress:
                previous_progress, last_progress = evidence, time.monotonic()
            if time.monotonic()-last_progress > min(300, timeout):
                _terminate_owned_training_tree(process,identities)
                raise TimeoutError("Training worker made no observable progress for 300 seconds")
            if cancel_event is not None and cancel_event.is_set():
                (output / "CANCEL").touch()
                cancelled_at = cancelled_at or time.monotonic()
                if time.monotonic()-cancelled_at > 20:
                    _terminate_owned_training_tree(process,identities)
                    raise InterruptedError("Cancelled; worker did not finish saving within 20 seconds")
            if time.monotonic()-started > timeout:
                _terminate_owned_training_tree(process,identities)
                raise TimeoutError("Hard worker wall-clock budget reached")
            time.sleep(0.2)
        if _matching_owned_processes({p:t for p,t in identities.items() if p!=process.pid}):
            raise RuntimeError('Training launcher exited while its owned worker remained alive')
        return process.returncode
    finally:
        if process.poll() is None or _matching_owned_processes({p:t for p,t in identities.items() if p!=process.pid}):
            _terminate_owned_training_tree(process,identities)
        _write(output/('process-'+str(process.pid)+'.json'),{'popen_pid':process.pid,
            'observed_owned_processes':[{'pid':pid,'created':created} for pid,created in identities.items()],
            'exit_code':process.returncode,'elapsed_seconds':time.monotonic()-started,
            'remaining_owned_processes':[p.pid for p in _matching_owned_processes(identities)]})


def education_bounds(config, sample_count):
    """Compute the stricter epoch/step bound before allocating a model."""
    training, budgets = config['training'], config['budgets']
    epochs = int(training.get('max_epochs', 3))
    if not 1 <= epochs <= 3 or sample_count < 1:
        raise ValueError('Education training requires 1..3 epochs and training samples')
    accumulation = int(training['gradient_accumulation_steps'])
    maximum = int(budgets.get('education_optimizer_steps', 600))
    wall = int(budgets.get('education_wall_seconds', 7200))
    if not 1 <= maximum <= 600 or not 1 <= wall <= 7200:
        raise ValueError('Education experiment exceeds 600 steps or 7200 seconds')
    return min(maximum, math.ceil(sample_count/accumulation)*epochs), wall, epochs


def _remaining_work_seconds(started, wall_seconds, *, now=None):
    """Keep the existing six-second owned-process cleanup margin inside cap."""
    remaining=float(wall_seconds)-(time.monotonic() if now is None else now)+started-6.0
    if remaining<=0:
        raise TimeoutError('No bounded worker time remains after cleanup margin')
    return remaining


def run_gpu_training(config_path, model_path, output_dir, mode="smoke", dataset_paths=None, local_dir=None,
                     cancel_event=None, job_id=None, scope_id=None):
    if mode not in {"smoke", "demo", "education"}:
        raise ValueError("mode must be smoke, demo or education")
    config_path = Path(config_path).resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    fixed_policy = {"load_in_4bit": True, "bnb_4bit_quant_type": "nf4", "bnb_4bit_use_double_quant": True,
                    "lora_r": 8, "lora_alpha": 16, "lora_dropout": 0.05, "target_modules": ["q_proj", "v_proj"],
                    "batch_size": 1, "gradient_accumulation_steps": 8, "learning_rate": 0.0001,
                    "max_sequence_length": 512, "gradient_checkpointing": True, "use_cache": False,
                    "packing": False, "train_last_assistant_only": True, "auto_promote_adapter": False}
    if any(config["training"].get(k) != v for k, v in fixed_policy.items()):
        raise ValueError("Training configuration differs from the currently validated bounded policy")
    project = config_path.parent.parent
    from edu_tutor.models import budget as model_budget
    if mode == 'education':
        allowed = getattr(model_budget, 'training_allowed', lambda *_: False)
        active = getattr(model_budget, 'active_scope_id', lambda *_: None)
        if not scope_id or scope_id != active(project) or not allowed(project):
            raise ValueError('Education training requires an explicitly active training allowance; old policy remains blocked')
    elif model_budget.policy(project).get("enabled"):
        raise ValueError("v0.2 검증 회차에서는 추가 GPU 학습을 실행하지 않습니다.")
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "manifest.json").exists():
        raise ValueError("Run output already contains a manifest; choose a new run ID")
    local = Path(local_dir).resolve() if local_dir else project / ".local"
    paths = [str(Path(p).resolve()) for p in dataset_paths] if dataset_paths else [str(project / p) for p in config["training"]["dataset_paths"]]
    data_report = validate_dataset(paths, profile=config["training"]["profile"], enforce_minimums=dataset_paths is None and mode != 'education')
    records = load_records(paths)
    if mode == 'education' and any(r['split'] not in {'train','validation'} for r in records):
        raise ValueError('Final holdout or fixture records are forbidden in education training input')
    provenance = _provenance(model_path, config["models"]["text"])
    if not any(r["split"] == "train" for r in load_records(paths)):
        raise ValueError("Dataset has no training records")
    disk_floor = max(20, config["budgets"]["disk_free_floor_gib"]) * 1024**3
    if shutil.disk_usage(output).free < disk_floor:
        raise ValueError("Disk free space below configured floor")
    max_epochs = None
    if mode == 'education':
        maximum_steps, wall_seconds, max_epochs = education_bounds(config, sum(r['split']=='train' for r in records))
    else:
        maximum_steps = 5 if mode == "smoke" else min(50, int(config["budgets"]["demo_optimizer_steps"]))
        wall_seconds = min(600 if mode == "smoke" else 900, int(config["budgets"][f"{mode}_wall_seconds"]))
    if maximum_steps < 1 or wall_seconds < 1:
        raise ValueError("Invalid training budgets")
    prior_smoke = _smoke_evidence(project, provenance["revision"], data_report["sha256"]) if mode == "demo" else None
    if mode == "demo":
        for path in (project / "runs").glob("*/manifest.json"):
            previous = json.loads(path.read_text(encoding="utf-8"))
            if previous.get("mode") == "demo" and previous.get("dataset_sha256") == data_report["sha256"]:
                raise ValueError("The single bounded demo attempt for this dataset has already been used")
    request = {"config": config, "model_path": str(Path(model_path).resolve()), "output": str(output),
               "local_dir": str(local), "dataset_paths": paths, "data_report": data_report, "provenance": provenance,
               "mode": mode, "max_steps": maximum_steps, "wall_seconds": wall_seconds,
               "prior_smoke": prior_smoke, "job_id": job_id or output.name,
               "execution_allowance_id":scope_id, "max_epochs":max_epochs}
    _write(output / "request.json", request)
    reservation = None
    if mode == 'education':
        reservation, wall_seconds = model_budget.reserve(project, {'kind':'training',
            'execution_allowance_id':scope_id,'job_id':request['job_id'],
            'max_optimizer_steps':maximum_steps,'max_epochs':max_epochs}, wall_seconds)
        request['wall_seconds']=wall_seconds
        _write(output / 'request.json',request)
    started = time.monotonic()
    request['deadline_monotonic']=started+wall_seconds-6.0
    _write(output / 'request.json',request)
    successful = False
    env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
           "PYTHONUTF8": "0", "PYTHONIOENCODING": "utf-8", "TOKENIZERS_PARALLELISM": "false", "WANDB_DISABLED": "true"}
    status = {"tier": "T2", "mode": mode, "status": "running", "revision": provenance["revision"],
              "dataset_sha256": data_report["sha256"], "optimizer_steps": 0, "resume_training": "not_supported"}
    _write(output / "manifest.json", status)
    try:
        with (output / "worker.log").open("w", encoding="utf-8") as log:
            returncode = _bounded_subprocess([sys.executable, "-m", "edu_tutor.training.runner", "--internal-worker", str(output / "request.json")],
                                  log, env, _remaining_work_seconds(started,wall_seconds), cancel_event, output)
        if returncode:
            raise RuntimeError(f"Training worker exited {returncode}; see worker.log")
        status = json.loads((output / "training-result.json").read_text(encoding="utf-8"))
        if cancel_event is not None and cancel_event.is_set():
            status["status"] = "cancelled"
            status["reload"] = {"status": "not_run", "reason": "cancelled"}
            return status
        remaining = _remaining_work_seconds(started,wall_seconds)
        if remaining <= 0:
            raise TimeoutError("No budget remains for separate-process reload")
        reload_reservation = None
        reload_success = False
        try:
            if reservation is not None:
                reload_reservation, reload_limit = model_budget.reserve_included_text(reservation, job_id=request['job_id']+'-reload')
                remaining=min(remaining,float(reload_limit)-6.0)
                if remaining<=0:raise TimeoutError('No nested reload time remains after cleanup margin')
            with (output / "reload.log").open("w", encoding="utf-8") as log:
                returncode = _bounded_subprocess([sys.executable, "-m", "edu_tutor.training.runner", "--internal-reload", str(output / "request.json")],
                                      log, env, remaining, cancel_event, output)
            reload_success=returncode==0
        finally:
            if reload_reservation is not None:model_budget.finish(reload_reservation, reload_success)
        if returncode:
            raise RuntimeError(f"Reload worker exited {returncode}; see reload.log")
        status["reload"] = json.loads((output / "reload-result.json").read_text(encoding="utf-8"))
        status["status"] = "passed" if status["optimizer_steps"] == maximum_steps else "bounded_partial"
        successful=status['status']=='passed'
    except (Exception, KeyboardInterrupt) as exc:
        if (output / "training-result.json").exists():
            status.update(json.loads((output / "training-result.json").read_text(encoding="utf-8")))
        status.update(status="interrupted" if isinstance(exc, (KeyboardInterrupt, InterruptedError)) else "failed", error=str(exc)[:500])
        raise
    finally:
        status["elapsed_seconds"] = time.monotonic()-started
        _write(output / "manifest.json", status)
        if reservation is not None:model_budget.finish(reservation,successful)
    return status


def _load_quantized(request):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    if not torch.cuda.is_available():
        raise RuntimeError("Actual CUDA GPU is required for T2 QLoRA")
    torch.cuda.set_device(0)
    torch.cuda.reset_peak_memory_stats()
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    tokenizer = AutoTokenizer.from_pretrained(request["model_path"], local_files_only=True, trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    quantization = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                     bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype)
    model = AutoModelForCausalLM.from_pretrained(request["model_path"], local_files_only=True,
                trust_remote_code=False, use_safetensors=True, quantization_config=quantization,
                torch_dtype=dtype, device_map={"": 0}, attn_implementation="sdpa")
    if any(str(d) not in {"0", "cuda:0"} for d in model.hf_device_map.values()):
        raise RuntimeError("CPU/offload/distributed model placement is forbidden")
    model.config.use_cache = False
    return model, tokenizer, dtype


def _worker(request):
    from edu_tutor.jobs.lease import GPULease
    with GPULease(Path(request["local_dir"]), request["job_id"]):
        _train_under_lease(request)


def _train_under_lease(request):
    import torch
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import Trainer, TrainerCallback, TrainingArguments, set_seed
    output = Path(request["output"])
    config = request["config"]["training"]
    _phase(output, "loading", "기반 모델과 실제 학습 데이터를 준비하고 있습니다.")
    set_seed(42)
    model, tokenizer, dtype = _load_quantized(request)
    records = load_records(request["dataset_paths"])
    encoded, audits, exclusions = [], [], []
    for record in records:
        try:
            feature = encode_response_only(tokenizer, record["messages"], max_length=512)
        except ValueError as exc:
            if "truncated" not in str(exc):
                raise
            exclusions.append({"id": record["id"], "reason": str(exc)})
            continue
        audits.append({"id": record["id"], "split": record["split"], **feature})
        if record["split"] == "train":
            encoded.append({k: v for k, v in feature.items() if k != "audit"})
    _write(output / "target-token-audit.json", audits)
    _write(output / "excluded-samples.json", exclusions)
    if request['mode']=='education' and exclusions:
        raise ValueError('Education dataset has truncated samples; fix data before training instead of silently excluding them')
    if not encoded:
        raise ValueError("No nontruncated training samples")
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model = get_peft_model(model, LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05,
                                          target_modules=["q_proj", "v_proj"], task_type="CAUSAL_LM"))
    trainable_parameter_count, total_parameter_count = model.get_nb_trainable_parameters()
    trainable = {n: p for n, p in model.named_parameters() if p.requires_grad}
    if not trainable or not all("lora_" in n for n in trainable):
        raise RuntimeError("Unexpected trainable base weights")
    before = {n: p.detach().cpu().clone() for n, p in trainable.items()}
    selected_base = {n: p.detach().reshape(-1)[:1024].cpu().clone() for n, p in model.named_parameters()
                     if not p.requires_grad and ("q_proj.base_layer.weight" in n or "embed_tokens.weight" in n)}
    optimizer = torch.optim.AdamW(list(trainable.values()), lr=1e-4)
    optimizer_ids = {id(p) for group in optimizer.param_groups for p in group["params"]}
    if any(id(p) in optimizer_ids for p in model.parameters() if not p.requires_grad):
        raise RuntimeError("Optimizer includes frozen base")
    training_start = time.monotonic()
    gradient_checks = []
    microbatch_counts = []

    class Bounds(TrainerCallback):
        def __init__(self):
            self.pending_microbatches = 0

        def on_substep_end(self, args, state, control, **kwargs):
            self.pending_microbatches += 1

        def on_pre_optimizer_step(self, args, state, control, **kwargs):
            gradients = [p.grad for p in trainable.values() if p.grad is not None]
            if not gradients or not all(torch.isfinite(g).all() for g in gradients):
                raise RuntimeError("Missing or nonfinite adapter gradients")
            gradient_checks.append(any(torch.count_nonzero(g).item() for g in gradients))

        def on_step_end(self, args, state, control, **kwargs):
            self.pending_microbatches += 1
            microbatch_counts.append(self.pending_microbatches)
            self.pending_microbatches = 0
            _assert_finite_adapter_weights(trainable)
            if request['mode']=='education' and state.global_step % 30 == 0:
                checkpoint=output / ('checkpoint-adapter-'+str(state.global_step))
                model.save_pretrained(checkpoint,safe_serialization=True)
                _write(checkpoint/'checkpoint-scope.json',{'step':state.global_step,
                    'kind':'adapter_weights_only','optimizer_resume_supported':False})
            save_deadline=request.get('deadline_monotonic',training_start+request['wall_seconds'])-120
            if (output / "CANCEL").exists() or time.monotonic()>save_deadline:
                control.should_training_stop = True
            if shutil.disk_usage(output).free < 20 * 1024**3:
                raise RuntimeError("Disk floor reached during training")
            return control

        def on_log(self, args, state, control, logs=None, **kwargs):
            if not logs:
                return
            metrics = {}
            for key in ("loss", "learning_rate", "grad_norm", "epoch"):
                if key in logs:
                    value = float(logs[key])
                    if not math.isfinite(value):
                        raise RuntimeError(f"Nonfinite training metric: {key}")
                    metrics[key] = value
            if not metrics:
                return
            elapsed_seconds = time.monotonic() - training_start
            actual_microbatches = sum(microbatch_counts)
            metrics.update(timestamp=datetime.now(timezone.utc).isoformat(), step=state.global_step,
                           max_steps=request["max_steps"], elapsed_seconds=elapsed_seconds,
                           actual_microbatches=actual_microbatches)
            metrics.update(_training_resource_metrics(torch.cuda, actual_microbatches,
                                                      args.per_device_train_batch_size, elapsed_seconds))
            with (output / "metrics.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(metrics, allow_nan=False) + "\n")
                stream.flush()

    arguments = TrainingArguments(output_dir=str(output / "trainer"), max_steps=request["max_steps"],
        per_device_train_batch_size=1, gradient_accumulation_steps=8, learning_rate=1e-4,
        gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False},
        bf16=dtype == torch.bfloat16, fp16=dtype == torch.float16,
        logging_steps=1, logging_nan_inf_filter=False, save_strategy="no", eval_strategy="no",
        report_to=["tensorboard"], logging_dir=str(output / "tensorboard"), seed=42,
        data_seed=42, dataloader_num_workers=0, remove_unused_columns=False, disable_tqdm=True,
        optim="adamw_torch", max_grad_norm=1.0, use_cpu=False)
    trainer = Trainer(model=model, args=arguments, train_dataset=encoded,
                      data_collator=ResponseOnlyCollator(tokenizer.pad_token_id),
                      optimizers=(optimizer, None), callbacks=[Bounds()])
    _phase(output, "training", "실제 optimizer step을 실행합니다. 취소는 안전한 step 경계에서 처리합니다.")
    train_result = trainer.train()
    if not math.isfinite(train_result.training_loss):
        raise RuntimeError("Nonfinite final training loss")
    changed = [n for n, value in before.items() if not torch.equal(value, trainable[n].detach().cpu())]
    if not changed or not any(gradient_checks):
        raise RuntimeError("No actual adapter update")
    parameters = dict(model.named_parameters())
    if not all(torch.equal(value, parameters[n].detach().reshape(-1)[:1024].cpu()) for n, value in selected_base.items()):
        raise RuntimeError("Selected frozen base values changed")
    _assert_finite_adapter_weights(trainable)
    adapter = output / "adapter"
    _phase(output, "saving", "어댑터와 실행 기록을 저장 중입니다. 취소 요청 시 저장 완료까지 기다립니다.")
    model.save_pretrained(adapter, safe_serialization=True)
    tokenizer.save_pretrained(adapter)
    adapter_info = {"model_id": request["provenance"]["model_id"], "revision": request["provenance"]["revision"],
                    "base_model_id": request["provenance"]["model_id"], "base_revision": request["provenance"]["revision"],
                    "dataset_sha256": request["data_report"]["sha256"], "tier": "T2", "auto_promoted": False,
                    "profile": config["profile"], "human_review": request["data_report"]["human_review"]}
    _write(adapter / "adapter-manifest.json", adapter_info)
    manifest = {**adapter_info, "status": "trained_pending_reload", "mode": request["mode"],
        "optimizer_steps": trainer.state.global_step, "requested_optimizer_steps": request["max_steps"],
        "configured_gradient_accumulation_steps": 8, "actual_microbatches": sum(microbatch_counts),
        "microbatches_per_optimizer_step": microbatch_counts, "training_loss": train_result.training_loss,
        "log_history": trainer.state.log_history, "finite_gradients": True, "changed_adapter_parameter_count": len(changed),
        "frozen_base_requires_grad_false": True, "optimizer_excludes_base": True,
        "selected_frozen_base_values_unchanged": True, "selected_base_modules": list(selected_base),
        "total_parameters": total_parameter_count, "trainable_parameters": trainable_parameter_count,
        "optimizer": {"class": "torch.optim.AdamW", "learning_rate": 1e-4, "weight_decay": 0.01,
                      "betas": [0.9, 0.999], "epsilon": 1e-8, "scheduler": "linear", "warmup_steps": 0},
        "target_modules": [n for n, m in model.named_modules() if hasattr(m, "lora_A")],
        "dtype": str(dtype), "device": "cuda:0", "device_map": model.hf_device_map,
        "max_input_tokens": max(len(f["input_ids"]) for f in encoded), "training_samples": len(encoded),
        "excluded_samples": exclusions, "adapter_dir": str(adapter), "peak_vram_bytes": torch.cuda.max_memory_allocated(),
        "packages": {p: importlib.metadata.version(p) for p in ("torch", "transformers", "peft", "bitsandbytes", "accelerate")},
        "template_sha256": hashlib.sha256(tokenizer.chat_template.encode()).hexdigest(),
        "resume_training": "not_supported; adapter weights only", "seed": 42,
        "education_quality": "not_reviewed; no quality improvement inferred from training loss or step count",
        "max_epochs":request.get('max_epochs'),"execution_allowance_id":request.get('execution_allowance_id')}
    _write(output / "training-result.json", manifest)
    _phase(output, "saved", "어댑터 가중치를 저장했습니다. optimizer 상태에서 이어하기용 체크포인트는 아닙니다.")


def _reload(request):
    import torch
    from peft import PeftModel
    from edu_tutor.jobs.lease import GPULease
    output = Path(request["output"])
    _phase(output, "reloading", "별도 프로세스에서 기반 모델과 저장한 어댑터를 다시 불러옵니다.")
    with GPULease(Path(request["local_dir"]), output.name + "-reload"):
        model, tokenizer, dtype = _load_quantized(request)
        adapter_manifest = json.loads((output / "adapter/adapter-manifest.json").read_text(encoding="utf-8"))
        if adapter_manifest["revision"] != request["provenance"]["revision"]:
            raise ValueError("Adapter base revision mismatch")
        model = PeftModel.from_pretrained(model, output / "adapter", local_files_only=True,
                                          is_trainable=False).eval()
        question = "SQLite에서 COUNT(*)와 COUNT(값)의 NULL 처리 차이를 짧게 설명해 주세요."
        inputs = tokenizer.apply_chat_template([{"role":"user","content":question}], tokenize=True,
                        add_generation_prompt=True, enable_thinking=False, return_tensors="pt").to("cuda:0")
        with torch.no_grad():
            generated = model.generate(inputs, attention_mask=torch.ones_like(inputs), do_sample=False,
                                       max_new_tokens=160, use_cache=True, pad_token_id=tokenizer.pad_token_id)
        answer_tokens = generated[0, inputs.shape[-1]:]
        text = tokenizer.decode(answer_tokens, skip_special_tokens=True)
        if not text.strip():
            raise RuntimeError("Reload produced empty text")
        _write(output / "reload-result.json", {"tier":"T2", "status":"passed", "separate_process":True,
            "pid":os.getpid(), "revision":request["provenance"]["revision"], "question":question,
            "answer":text, "generated_tokens":len(answer_tokens),
            "status_scope":"adapter loading and generation wiring only; not an answer quality grade",
            "generation_complete":tokenizer.eos_token_id in answer_tokens.tolist(),
            "finish_reason":"eos" if tokenizer.eos_token_id in answer_tokens.tolist() else "length",
            "education_quality":"not_reviewed", "peak_vram_bytes":torch.cuda.max_memory_allocated()})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--internal-worker")
    parser.add_argument("--internal-reload")
    parser.add_argument("--config", default="configs/local_8gb.yaml")
    parser.add_argument("--model", default=".local/models/text")
    parser.add_argument("--output")
    parser.add_argument("--mode", choices=["smoke", "demo", "education"], default="smoke")
    parser.add_argument("--scope-id")
    parser.add_argument("--dataset", action="append")
    parser.add_argument("--local-dir")
    args = parser.parse_args()
    internal = args.internal_worker or args.internal_reload
    if internal:
        request = json.loads(Path(internal).read_text(encoding="utf-8"))
        (_worker if args.internal_worker else _reload)(request)
    else:
        if not args.output:
            parser.error("--output is required")
        print(json.dumps(run_gpu_training(args.config, args.model, args.output, args.mode, args.dataset, args.local_dir, scope_id=args.scope_id), ensure_ascii=False))


if __name__ == "__main__":
    main()
