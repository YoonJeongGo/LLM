"""Bounded, fail-open observation of the installed Qwen3 block-level forward.

Hooks observe host calls, never GPU completion. No tensor is retained in an event.
The source-verified block summary is deliberately not a complete operation graph.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import queue
import threading
import time
import weakref
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def tensor_info(value):
    """Read metadata only; never copy a tensor or keep a reference to it."""
    if hasattr(value, "shape") and hasattr(value, "dtype"):
        return {"shape": list(value.shape), "dtype": str(value.dtype), "device": str(value.device)}
    if isinstance(value, (tuple, list)):
        return next((tensor_info(v) for v in value if hasattr(v, "shape")), None)
    return None


def describe_model(model, meta=None, adapter=None):
    from transformers.models.qwen3.modeling_qwen3 import Qwen3ForCausalLM, Qwen3Model, Qwen3DecoderLayer
    import transformers
    modules = dict(model.named_modules())
    bases = [(name, item) for name, item in modules.items() if isinstance(item, Qwen3ForCausalLM)]
    if len(bases) != 1 or transformers.__version__ != "4.57.3":
        raise ValueError("Block observation supports the verified Qwen3 / transformers 4.57.3 forward only")
    base_path, base = bases[0]
    decoder = base.model
    if not isinstance(decoder, Qwen3Model) or not all(isinstance(v, Qwen3DecoderLayer) for v in decoder.layers):
        raise ValueError("Unsupported Qwen3 decoder implementation")
    paths = {id(module): name for name, module in modules.items()}
    if len(decoder.layers) != int(base.config.num_hidden_layers):
        raise ValueError("Config and loaded decoder layer count differ")
    total_seen, base_seen, adapter_seen = set(), set(), set()
    counts = {"total": 0, "base": 0, "adapter": 0, "trainable": 0}
    aliases = {}
    for name, parameter in model.named_parameters(remove_duplicate=False):
        identity = id(parameter)
        aliases.setdefault(identity, []).append(name)
        if identity not in total_seen:
            total_seen.add(identity)
            counts["total"] += parameter.numel()
            counts["trainable"] += parameter.numel() if parameter.requires_grad else 0
        is_adapter = any(part.startswith("lora_") or part == "modules_to_save" for part in name.split("."))
        bucket, seen = ("adapter", adapter_seen) if is_adapter else ("base", base_seen)
        if identity not in seen:
            seen.add(identity)
            counts[bucket] += parameter.numel()
    # A shared object belongs once to the union; the category counts expose overlap.
    counts["shared_base_adapter_objects"] = len(base_seen & adapter_seen)
    nodes = []
    points = [(decoder.embed_tokens, "embedding"), *[(v, "block") for v in decoder.layers],
              (decoder.norm, "normalization"), (base.lm_head, "output_scores")]
    for module, role in points:
        name = paths[id(module)]
        entry = {"path": name, "module_path": name, "type": type(module).__name__, "role": role,
                 "parameters": sum(p.numel() for p in module.parameters()),
                 "trainable": any(p.requires_grad for p in module.parameters())}
        if role == "block":
            entry["components"] = [{"path": paths[id(getattr(module, attr))], "type": type(getattr(module, attr)).__name__}
                                   for attr in ("input_layernorm", "self_attn", "post_attention_layernorm", "mlp")]
            entry["verified_flow"] = ["input_layernorm", "self_attn", "residual_add", "post_attention_layernorm", "mlp", "residual_add"]
        nodes.append(entry)
    source = "\n".join(inspect.getsource(cls.forward) for cls in (Qwen3ForCausalLM, Qwen3Model, Qwen3DecoderLayer))
    module_rows = []
    for name, module in modules.items():
        params = list(module.named_parameters(recurse=False))
        module_rows.append({"path": name, "type": type(module).__name__,
                            "adapter": "lora_" in name or "modules_to_save" in name,
                            "tensors": [{"name": n, **tensor_info(p), "trainable": p.requires_grad} for n, p in params]})
    return {"model_id": (meta or {}).get("model_id", getattr(base.config, "_name_or_path", "")),
            "revision": (meta or {}).get("revision"), "adapter": adapter,
            "wrapper_type": type(model).__name__, "base_path": base_path,
            "base_type": type(base).__name__, "config": base.config.to_dict(),
            "layer_count": len(decoder.layers), "hidden_size": base.config.hidden_size,
            "parameter_counts": counts, "parameter_count": counts["total"],
            "parameter_count_kind": "deduplicated_stored_tensor_elements",
            "parameter_count_notice": "전체 개수는 공유 파라미터 객체를 한 번만 집계합니다. 양자화 저장 요소 수는 원본 논리적 개수와 다를 수 있습니다. 기반/어댑터가 같은 객체를 공유하면 범주 수를 합산하지 않습니다. 노드별 수도 합산용이 아닙니다.",
            "shared_parameter_aliases": [v for v in aliases.values() if len(v) > 1],
            "nodes": nodes, "edges": [{"from": a["path"], "to": b["path"], "kind": "verified_block_path"} for a, b in zip(nodes, nodes[1:])],
            "modules": module_rows, "graph_kind": "verified_block_summary",
            "graph_notice": "설치된 Qwen3 forward를 확인한 블록 수준 구조 요약입니다. 완전한 계산 그래프나 개별 가중치 전체를 나타내지 않습니다.",
            "forward_evidence": {"transformers_version": transformers.__version__,
                                 "implementation": "transformers.models.qwen3.modeling_qwen3",
                                 "source_file": inspect.getsourcefile(Qwen3Model), "source": source,
                                 "sha256": hashlib.sha256(source.encode()).hexdigest()},
            "resident": True, "source": "live_worker", "observed_at": utc_now(),
            "device": str(base.device), "dtype": str(base.dtype), "training_mode": bool(model.training),
            "currently_training": False}


class BoundedEmitter:
    """Inference producers never wait for a slow pipe consumer.

    Metadata/samples have a bounded lossy queue. Lifecycle events have a separate
    bounded queue (256 > the <=128-token route's finite lifecycle); overflow is explicit.
    The API also derives terminal state from the existing worker exit protocol.
    """
    def __init__(self, emit, flush_ms=250, capacity=256):
        self.emit = emit
        self.interval = max(.1, min(1., int(flush_ms) / 1000))
        self.samples = queue.Queue(maxsize=capacity)
        self.critical = queue.Queue(maxsize=256)
        self._buffer_lock = threading.Lock()
        self.dropped = 0
        self.aggregated = 0
        self.failed = False
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self._publish, name="neural-telemetry", daemon=True)
        self.thread.start()

    def put(self, event, critical=False):
        if self.failed or self.closed.is_set():
            self.dropped += 1
            return
        # A short in-memory lock establishes one snapshot boundary for both
        # queues. No I/O or consumer wait occurs while holding this lock.
        with self._buffer_lock:
            try:
                (self.critical if critical else self.samples).put_nowait(event)
            except queue.Full:
                self.dropped += 1

    def _publish(self):
        while True:
            self.closed.wait(self.interval)
            batch = []
            with self._buffer_lock:
                for source in (self.critical, self.samples):
                    while True:
                        try:
                            batch.append(source.get_nowait())
                        except queue.Empty:
                            break
            if batch:
                batch.sort(key=lambda value: value["sequence_no"])
                try:
                    self.emit("observation_batch", events=batch, dropped_events=self.dropped,
                              aggregated_events=self.aggregated)
                except Exception:
                    self.failed = True
                    return
            if self.closed.is_set() and self.critical.empty() and self.samples.empty():
                return

    def close(self):
        self.closed.set()
        self.thread.join(timeout=.5)


_active = weakref.WeakKeyDictionary()
_active_lock = threading.Lock()


class ModelObserver:
    def __init__(self, model, tokenizer, config, sink, meta=None, adapter=None):
        self.model = model
        self.tokenizer = tokenizer
        self.config = dict(config)
        self.sink = sink
        self.meta = meta or {}
        self.adapter = adapter
        self.handles = []
        self.structure = None
        self.failed = False
        self.enabled = False
        self.sequence = 0
        self.forward_count = 0
        self.generated_ids = []
        self.calls = Counter()
        self.call_order = 0
        self.module_event_every_steps = max(1, min(128, int(config.get("module_event_every_steps", 4))))
        self.aggregated_events = 0
        self.record_modules = False
        self._detail_paths = ()
        self._block_paths = set()
        self.phase = "loading"
        self.step = 0
        self.context = {}
        self.starts = {}
        self.sample_cpu_ms = 0.
        self.sample_count = 0
        self.observer_host_ms = 0.
        self._guard_depth = 0
        self.last_control_mtime = None
        self._mask = None  # borrowed only during a forward, cleared by its post hook
        self._closed = False

    def event(self, kind, payload, path=None, critical=False, sampling_info=None):
        self.sequence += 1
        envelope = {"run_id": self.config.get("run_id"), "request_id": self.config.get("request_id"),
                    "generation_epoch": self.config.get("generation_epoch", 1),
                    "model_id": self.meta.get("model_id"), "module_path": path,
                    "phase": self.phase, "event_type": kind, "sequence_no": self.sequence,
                    "observed_at": utc_now(), "source": "live_worker", "sampling_info": sampling_info,
                    "timing_kind": "host_call", "payload": payload}
        self.sink.put(envelope, critical=critical)

    def _guard(self, operation, *args, **kwargs):
        if self.failed or self._closed:
            return
        begin = time.perf_counter()
        self._guard_depth += 1
        try:
            operation(*args, **kwargs)
        except Exception as exc:
            self.failed = True
            self.detach()
            try:
                self.event("observer_error", {"error_type": type(exc).__name__, "message": "관측 오류로 계측만 중지했습니다.", "inference_continues": True}, critical=True)
            except Exception:
                pass
        finally:
            self._guard_depth -= 1
            if self._guard_depth == 0:
                self.observer_host_ms += (time.perf_counter() - begin) * 1000

    def start(self):
        self._guard(self._start)
        return self

    def _start(self):
        self.structure = describe_model(self.model, self.meta, self.adapter)
        self._block_paths = {node["path"] for node in self.structure["nodes"] if node["role"] == "block"}
        self.structure["observation_sampling"] = {
            "module_event_every_steps": self.module_event_every_steps,
            "module_call_count_scope": "all_actual_calls_while_hooks_enabled",
            "notice": f"블록 메타데이터는 {self.module_event_every_steps} 생성 step마다 기록합니다. 생략한 호출도 누적 횟수에 포함하며, 의도적 집계와 큐 유실을 구분합니다. 토큰과 모델 호출 이벤트는 매 step 기록합니다.",
        }
        self.event("structure", self.structure, critical=True)
        self.poll_control(force=True)
        if self.config.get("mode", "light") != "off":
            self.attach()

    def attach(self):
        if self.enabled or self.failed or self._closed:
            return
        with _active_lock:
            previous = _active.get(self.model)
            if previous is not None and previous is not self:
                raise ValueError("An observer is already attached to this model")
            _active[self.model] = self
        modules = dict(self.model.named_modules())
        base = modules[self.structure["base_path"]]
        self.handles.append(base.register_forward_pre_hook(lambda m, a, k: self._guard(self._forward_pre, m, a, k), with_kwargs=True))
        self.handles.append(base.register_forward_hook(lambda m, a, k, o: self._guard(self._forward_post, m, a, k, o), with_kwargs=True, always_call=True))
        for node in self.structure["nodes"]:
            path = node["path"]
            module = modules[path]
            self.handles.append(module.register_forward_pre_hook(lambda m, a, k, p=path: self._guard(self._module_pre, p, a, k) if self.record_modules else None, with_kwargs=True))
            self.handles.append(module.register_forward_hook(lambda m, a, k, o, p=path: self._guard(self._module_post, p, a, k, o), with_kwargs=True, always_call=True))
        self.enabled = True
        self.event("observer_state", {"state": "observing", "mode": self.config.get("mode", "light"), "hook_count": len(self.handles),
                                      "module_event_every_steps": self.module_event_every_steps}, critical=True)

    def detach(self):
        for handle in self.handles:
            handle.remove()
        self.handles.clear()
        self.starts.clear()
        self._mask = None
        self.enabled = False
        with _active_lock:
            if _active.get(self.model) is self:
                del _active[self.model]

    def poll_control(self, force=False):
        self._guard(self._poll_control, force)

    def _poll_control(self, force):
        path = self.config.get("control_path")
        if not path:
            return
        target = Path(path)
        try:
            changed = target.stat().st_mtime_ns
        except FileNotFoundError:
            return
        if changed == self.last_control_mtime and not force:
            return
        # Atomic writes on the API side; a transient incomplete read retries next step.
        try:
            control = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self.last_control_mtime = changed
        if control.get("generation_epoch", self.config.get("generation_epoch", 1)) != self.config.get("generation_epoch", 1):
            return  # a stale browser/control write cannot alter this generation
        for key in ("mode", "selected_layers", "sample_every", "components"):
            if key in control:
                self.config[key] = control[key]
        if self.config.get("mode") == "off" or control.get("enabled") is False:
            self.config["mode"] = "off"
            self.detach()
            self.event("observer_state", {"state": "disabled", "hook_count": 0}, critical=True)
        elif self.structure is not None:
            self.attach()

    def _forward_pre(self, module, args, kwargs):
        self.step = len(self.generated_ids)
        self.record_modules = self.step % self.module_event_every_steps == 0
        self._detail_paths = tuple(self.config.get("selected_layers") or ())[:2] if (
            self.config.get("mode") == "detail" and self.step % max(8, int(self.config.get("sample_every", 16))) == 0
        ) else ()
        previous = kwargs.get("past_key_values")
        cached_length = int(previous.get_seq_length()) if previous is not None and hasattr(previous, "get_seq_length") else 0
        self.phase = "prefill" if self.step == 0 and self.forward_count == 0 and cached_length == 0 else "decode"
        source = kwargs.get("input_ids", args[0] if args else None)
        if source is None:
            source = kwargs.get("inputs_embeds")
        length = int(source.shape[1]) if source is not None else None
        self.context = {"step": self.step, "forward_index": self.forward_count, "input_sequence_length": length,
                        "cache_length_before": cached_length, "cache_reused": cached_length > 0,
                        "use_cache": bool(kwargs.get("use_cache", getattr(module.config, "use_cache", False))),
                        "recomputes_context": (self.step > 0 or self.forward_count > 0) and cached_length == 0}
        self.forward_count += 1
        self.call_order = 0
        self._mask = kwargs.get("attention_mask")
        self.event("forward", dict(self.context))

    def _forward_post(self, module, args, kwargs, output):
        self._mask = None

    def _module_pre(self, path, args, kwargs):
        value = args[0] if args else kwargs.get("hidden_states", kwargs.get("input"))
        self.call_order += 1
        self.starts[path] = (time.perf_counter(), tensor_info(value), self.call_order)

    def _module_post(self, path, args, kwargs, output):
        self.calls[path] += 1
        if self.record_modules:
            started, input_info, order = self.starts.pop(path, (time.perf_counter(), None, self.call_order))
            self.event("block_call", {**self.context, "call_order": order, "call_count": self.calls[path],
                                      "input": input_info, "output": tensor_info(output),
                                      "host_elapsed_ms": (time.perf_counter() - started) * 1000, "gpu_elapsed_ms": None}, path,
                       sampling_info={"method": "every_n_generation_steps", "every_steps": self.module_event_every_steps,
                                      "count_includes_omitted_calls": True})
        else:
            # Counters remain exact. Skip shape/dtype/device/timing assembly and
            # queue serialization on non-recorded steps, not model computation.
            self.aggregated_events += 1
            if hasattr(self.sink, "aggregated"):
                self.sink.aggregated = self.aggregated_events
        if path not in self._detail_paths:
            return
        if path not in self._block_paths or not hasattr(output, "shape") or len(output.shape) != 3:
            return
        every = max(8, int(self.config.get("sample_every", 16)))
        begin = time.perf_counter()
        length = int(output.shape[1])
        index = length - 1
        if self._mask is not None and hasattr(self._mask, "shape") and self._mask.ndim == 2:
            valid = self._mask[0, -length:].nonzero(as_tuple=False)
            if not valid.numel():
                return  # all-padding is not a valid token
            index = int(valid[-1, 0].item())
        count = max(1, min(32, int(self.config.get("components", 32)), int(output.shape[-1])))
        values = output[0, index, :count].detach().float().cpu().tolist()
        elapsed = (time.perf_counter() - begin) * 1000
        self.sample_cpu_ms += elapsed
        self.sample_count += 1
        info = {"method": "last_valid_token_first_components", "batch_index": 0, "token_index": index,
                "sequence_token_index": self.context.get("cache_length_before", 0) + index,
                "component_indices": list(range(count)), "every_steps": every,
                "scope": "selected_layer_token_components_only"}
        self.event("activation_sample", {"step": self.step, "values": values,
                     "sample_mean": sum(values) / len(values), "sample_cpu_transfer_and_stats_ms": elapsed,
                     "gpu_elapsed_ms": None}, path, sampling_info=info)

    def prompt_tokens(self, ids):
        self._guard(self._prompt_tokens, ids)

    def _prompt_tokens(self, ids):
        if not self.enabled:
            return
        specials = set(getattr(self.tokenizer, "all_special_ids", []))
        self.event("input_tokens", {"token_ids": list(ids), "special_tokens": [v in specials for v in ids], "token_count": len(ids)}, critical=True)

    def tokens(self, ids):
        self._guard(self._tokens, ids)

    def _tokens(self, ids):
        start = len(self.generated_ids)
        self.generated_ids.extend(int(v) for v in ids)
        if not self.enabled:
            return
        specials = set(getattr(self.tokenizer, "all_special_ids", []))
        self.event("token", {"step": start, "token_ids": list(ids), "special_tokens": [v in specials for v in ids],
                             "output_token_count": len(self.generated_ids),
                             "cumulative_text": self.tokenizer.decode(self.generated_ids, skip_special_tokens=True),
                             "decoding": "cumulative_tokenizer_decode_may_revise_incomplete_utf8"}, critical=True)

    def close(self, reason="completed"):
        if self._closed:
            return
        self.detach()
        try:
            self.event("summary", self.summary(reason), critical=True)
        except Exception:
            pass
        self._closed = True

    def summary(self, reason=None):
        return {"state": reason or ("failed" if self.failed else "disabled" if not self.enabled else "observing"),
                "observer_failed": self.failed, "forward_count": self.forward_count,
                "module_call_counts": dict(self.calls), "activation_sample_count": self.sample_count,
                "module_event_every_steps": self.module_event_every_steps, "aggregated_events": self.aggregated_events,
                "module_call_count_scope": "all_actual_calls_while_hooks_enabled",
                "sample_cpu_transfer_and_stats_ms": self.sample_cpu_ms, "gpu_elapsed_ms": None,
                "observer_host_ms": self.observer_host_ms,
                "timing_kind": "host_call", "remaining_hooks": len(self.handles),
                "dropped_events": getattr(self.sink, "dropped", 0)}


def observed_streamer(tokenizer, observer, **kwargs):
    from transformers import TextIteratorStreamer

    class ObservedTextIteratorStreamer(TextIteratorStreamer):
        def put(self, value):
            prompt = self.next_tokens_are_prompt
            # Keep the existing streaming decoder and visible deltas untouched.
            super().put(value)
            try:
                ids = value[0].tolist() if value.ndim > 1 else value.tolist()
                (observer.prompt_tokens if prompt else observer.tokens)(ids)
            except Exception as exc:
                observer._guard(lambda: (_ for _ in ()).throw(exc))

    return ObservedTextIteratorStreamer(tokenizer, **kwargs)


def persisted_report(report, observation):
    """The established chat report stays unchanged; observer requests default private."""
    if observation is None or observation.get("save_sensitive", False):
        return report
    return {key: value for key, value in report.items() if key not in {"text", "token_ids", "input_token_ids", "output_token_ids", "activations"}}
