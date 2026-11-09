"""Ephemeral observation broker; no model imports and no browser backpressure.

Only identifiers and scalar performance metrics enter the ordinary jobs table.
Raw text, token IDs and tiny activation samples stay in a bounded memory window
unless an authenticated user explicitly saves a sensitive trace.
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import threading
import time
from collections import OrderedDict, deque
from pathlib import Path

from edu_tutor.jobs.inspection import active_gpu_lease, job_view
from edu_tutor.jobs.manager import TERMINAL
from edu_tutor.storage.db import new_id, utcnow

MAX_EVENTS = 2048
MAX_BUFFER_BYTES = 2_000_000
MAX_STRUCTURE_BYTES = 1_000_000
MAX_RUNS = 8
MAX_TRACE_BYTES = 20_000_000
MAX_TOTAL_TRACE_BYTES = 200_000_000
CRITICAL_TYPES = {"run_state", "observer_state", "observer_error", "summary", "error", "end", "cancel"}
SENSITIVE_TYPES = {"input_tokens", "token", "activation_sample"}
METRIC_KEYS = {
    "model_id", "revision", "finish_reason", "input_tokens", "output_tokens", "timestamp",
    "elapsed_seconds", "model_load_seconds", "generation_seconds", "model_load_count",
    "peak_vram_bytes", "gpu_name", "observer_host_ms", "sample_cpu_transfer_and_stats_ms",
    "observer_mode", "observer_failed", "remaining_hooks", "output_token_sha256",
    "input_token_sha256", "tokens_per_second", "observer_summary", "observation",
    "output_token_ids_sha256", "input_token_ids_sha256", "peak_vram_reserved_bytes",
    "preparation_seconds", "observation_setup_seconds", "gpu",
    "first_token_latency_seconds", "first_token_latency_status", "first_token_latency_kind",
    "generation_remaining_seconds", "remaining_output_tokens", "warmup_seconds",
}


class NeuralConflict(ValueError):
    pass


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_bytes(_json_bytes(value))
    temp.replace(path)


def _metrics(metadata):
    # Scalar whitelist prevents accidental persistence of an evolving worker
    # report's raw text, token arrays, tensors or arbitrary exception strings.
    return {key: value for key, value in metadata.items()
            if key in METRIC_KEYS and (value is None or isinstance(value, (str, int, float, bool)))}


class NeuralRun:
    def __init__(self, body, model, instance):
        self.run_id = new_id()
        self.job_id = None
        self.request_id = body["request_id"]
        self.generation_epoch = body["generation_epoch"]
        self.model_id, self.revision = model.get("model_id"), model.get("revision")
        self.adapter_id = body["adapter_id"]
        self.observation_mode = body["observation_mode"]
        self.initial_observation_mode = self.observation_mode
        self.intended_enabled = self.observation_mode != "off"
        self.observer_enabled = self.intended_enabled
        self.selected_layers = body["selected_layers"]
        self.sample_every_steps = body["sample_every_steps"]
        self.update_interval_ms = body["update_interval_ms"]
        self.state = "queued"
        self.mode = "STATIC" if self.observation_mode == "off" else "STALE"
        self.resident = False
        self.output_text = ""
        self.metadata = {}
        self.structure = None
        self.created_at = self.updated_at = utcnow()
        self.started_clock = time.monotonic()
        self.sequence_no = self.worker_sequence_no = 0
        self.events = deque()
        self.tokens = []
        self.token_bytes = 0
        self.critical_bytes = 0
        self.critical = []
        self.buffer_bytes = 0
        self.dropped_events = 0
        self.worker_dropped_events = 0
        self.aggregated_events = 0
        self.rejected_stale_events = 0
        self.subscribers = set()
        self.ever_subscribed = False
        self.instance = instance
        self.control_error = None
        self.observation_error = None
        self.save_status = "not_saved"
        self.control_transitions = 0

    def view(self, *, include_structure=True):
        result = {key: copy.deepcopy(getattr(self, key)) for key in (
            "run_id", "job_id", "request_id", "generation_epoch", "model_id", "revision",
            "adapter_id", "observation_mode", "observer_enabled", "selected_layers",
            "sample_every_steps", "update_interval_ms", "state", "mode", "resident", "output_text",
            "metadata", "created_at", "updated_at", "sequence_no", "dropped_events",
            "worker_dropped_events", "aggregated_events", "rejected_stale_events", "control_error", "observation_error", "save_status")}
        result.update(connected_subscribers=len(self.subscribers), server_instance=self.instance,
                      buffer_bytes=self.buffer_bytes, buffer_event_count=len(self.events) + len(self.critical) + len(self.tokens))
        if include_structure:
            result["structure"] = copy.deepcopy(self.structure)
        return result

    def append(self, event_type, payload, *, event=None):
        self.sequence_no += 1
        envelope = {"run_id": self.run_id, "request_id": self.request_id,
                    "generation_epoch": self.generation_epoch, "model_id": self.model_id,
                    "module_path": None, "phase": self.state, "event_type": event_type,
                    "observed_at": utcnow(), "source": "backend_derived", "sampling_info": None,
                    "timing_kind": "host_call", "payload": payload}
        if event:
            envelope.update(event)
            envelope["worker_sequence_no"] = event.get("sequence_no")
        envelope.update(sequence_no=self.sequence_no, backend_received_at=utcnow())
        size = len(_json_bytes(envelope))
        if size > MAX_STRUCTURE_BYTES:
            self.dropped_events += 1
            return
        if event_type in {"input_tokens", "token"}:
            # A prompt and at most 128 generation calls. Retain real token IDs
            # independently of high-volume module events and control states.
            if len(self.tokens) >= 129 or self.token_bytes + size > 256_000:
                self.dropped_events += 1
                return
            self.tokens.append((envelope, size))
            self.token_bytes += size
            self.buffer_bytes += size
        elif event_type in CRITICAL_TYPES:
            # The finite job lifecycle contains < 256 critical events. Refuse
            # pathological observers rather than silently evict lifecycle data.
            if (len(self.critical) >= 256 or self.critical_bytes + size > 512_000) and event_type != "run_state":
                raise ValueError("Too many observer state transitions")
            self.critical.append((envelope, size))
            self.critical_bytes += size
            self.buffer_bytes += size
        else:
            self.events.append((envelope, size))
            self.buffer_bytes += size
        while self.events and (len(self.events) > MAX_EVENTS or self.buffer_bytes > MAX_BUFFER_BYTES):
            _, removed = self.events.popleft()
            self.buffer_bytes -= removed
            self.dropped_events += 1
        self.updated_at = utcnow()

    def after(self, sequence_no):
        return [copy.deepcopy(item) for item, _ in sorted(
            [entry for entry in (*self.critical, *self.tokens, *self.events) if entry[0]["sequence_no"] > sequence_no],
            key=lambda entry: entry[0]["sequence_no"])]


class NeuralService:
    def __init__(self, root, store, jobs, *, worker=None):
        self.root, self.store, self.jobs = Path(root).resolve(), store, jobs
        self.worker = worker
        self.lock = threading.RLock()
        self.save_lock = threading.Lock()
        self.runs = OrderedDict()
        self.closed = threading.Event()
        self.control_dir = self.root / ".local/neural-control"
        self.records_dir = self.root / ".local/neural-records"
        self.cache_path = self.root / ".local/models/text/neural-structure.json"
        self.maintenance = threading.Thread(target=self._maintain, daemon=True, name="neural-observation-control")
        self.maintenance.start()

    def _get(self, ident):
        if ident not in self.runs:
            raise KeyError(ident)
        return self.runs[ident]

    def _control(self, run):
        try:
            _atomic_json(self.control_dir / f"{run.run_id}.json", {
                "enabled": run.observer_enabled and run.state not in TERMINAL,
                "mode": run.observation_mode if run.observation_mode != "off" else "light",
                "selected_layers": run.selected_layers, "sample_every": run.sample_every_steps,
                "generation_epoch": run.generation_epoch,
            })
            run.control_error = None
        except OSError:
            run.control_error = "계측 제어 파일을 갱신하지 못했습니다. 작업 종료 시 worker가 훅을 해제합니다."

    def _state(self, run, state, *, error_type=None):
        run.state = state
        if state in TERMINAL:
            run.resident = False
            run.observer_enabled = False
            run.mode = "STATIC" if run.structure else "UNAVAILABLE"
            if run.structure:
                run.structure = {**run.structure, "resident": False, "source": "cached", "cached_at": utcnow()}
        payload = {"state": state, "resident": run.resident, "error_type": error_type}
        run.append("run_state", payload)

    def _maintain(self):
        while not self.closed.wait(.5):
            try:
                with self.lock:
                    for run in self.runs.values():
                        if run.state in TERMINAL:
                            continue
                        # Handle cancellation before JobManager invoked the target.
                        if run.job_id:
                            job = self.store.get("jobs", run.job_id)
                            if job and job["state"] in TERMINAL:
                                self._state(run, job["state"])
                                self._control(run)
                                continue
                        if run.observer_enabled and not run.subscribers and (
                            run.ever_subscribed or time.monotonic() - run.started_clock > 10
                        ):
                            run.observer_enabled = False
                            run.mode = "STALE"
                            run.append("observer_state", {"state": "disabled", "reason": "no_connected_viewer"})
                            self._control(run)
            except Exception:
                # Observation maintenance cannot take down the API or a lesson.
                continue

    def start(self, body):
        from edu_tutor.models.runtime import model_status
        from edu_tutor.models.registry import resolve_adapter
        model = model_status(self.root)
        if not model.get("ready"):
            raise NeuralConflict("로컬 텍스트 모델이 준비되지 않았습니다.")
        adapter = resolve_adapter(body["adapter_id"], self.root, use_selection=False)
        with self.jobs.lock:
            with self.lock:
                for run in self.runs.values():
                    if run.request_id == body["request_id"]:
                        if run.generation_epoch != body["generation_epoch"]:
                            raise NeuralConflict("동일 요청 ID의 generation_epoch가 다릅니다.")
                        return run.view()
                if any(j.get("kind") == "neural_observation" and j.get("request_id") == body["request_id"]
                       for j in self.store.list("jobs")):
                    raise NeuralConflict("이전 서버 또는 만료된 메모리 창의 요청 ID입니다. 새 요청 ID로 실행하세요.")
                if any(j["state"] not in TERMINAL for j in self.store.list("jobs")):
                    raise NeuralConflict("진행 중인 작업을 완료하거나 중단한 후 실행하세요.")
                # Only evict completed memory windows; never mutate saved traces
                # or unrelated jobs. IDs from another server cannot be reused.
                while len(self.runs) >= MAX_RUNS:
                    old_id = next((key for key, item in self.runs.items()
                                   if item.state in TERMINAL and not item.subscribers), None)
                    if old_id is None:
                        raise NeuralConflict("관측 메모리 창이 가득 찼습니다. 이전 관측 연결을 닫아 주세요.")
                    del self.runs[old_id]
                run = NeuralRun(body, model, self.jobs.instance)
                self.runs[run.run_id] = run
                run.append("run_state", {"state": "queued", "resident": False})
                self._control(run)

            def target(job_id, cancel):
                from edu_tutor.models.runtime import run_worker
                with self.lock:
                    run.job_id = job_id
                    self._state(run, "loading")
                payload = {"kind": "text", "messages": [{"role": "user", "content": body["text"]}],
                           "adapter": adapter, "max_new_tokens": body["max_new_tokens"], "job_id": job_id,
                           "observation": {"mode": body["observation_mode"], "run_id": run.run_id,
                               "request_id": run.request_id, "generation_epoch": run.generation_epoch,
                               "selected_layers": run.selected_layers, "sample_every": run.sample_every_steps,
                               "components": 32, "flush_ms": run.update_interval_ms,
                               "control_path": str(self.control_dir / f"{run.run_id}.json"),
                               "save_sensitive": False}}
                try:
                    for event in (self.worker or run_worker)(payload, root=self.root, cancel_event=cancel):
                        if event.get("type") == "observation_batch":
                            self._ingest_safe(run, event)
                        elif event.get("type") == "delta":
                            first_output = False
                            with self.lock:
                                if run.state == "loading":
                                    run.resident = True
                                    self._state(run, "running")
                                    first_output = True
                                text = str(event.get("text", ""))
                                # Worker has a 128-token limit; this independent
                                # character bound also protects injected runtimes.
                                if len(run.output_text) < 64000:
                                    run.output_text += text[:64000 - len(run.output_text)]
                                run.append("output", {"text": run.output_text})
                            if first_output:
                                self.jobs.update(run.job_id, state="running")
                        elif event.get("type") == "metadata":
                            with self.lock:
                                # Live only. Persisted job result below is scalar-whitelisted.
                                raw = {key: value for key, value in event.items() if key != "type"}
                                if len(_json_bytes(raw)) <= 128000:
                                    run.metadata = raw
                                run.append("metrics", _metrics(raw))
                    with self.lock:
                        self._state(run, "cancelled" if cancel.is_set() else "succeeded")
                    return {"neural_run_id": run.run_id, "source": "text_worker", **_metrics(run.metadata)}
                except Exception as exc:
                    with self.lock:
                        state = "cancelled" if cancel.is_set() else "failed"
                        self._state(run, state, error_type=type(exc).__name__)
                    # Do not let arbitrary model exception strings leak prompt
                    # fragments into the ordinary persistent jobs table.
                    raise RuntimeError("신경망 관측 작업이 완료되지 않았습니다: " + type(exc).__name__) from exc
                finally:
                    with self.lock:
                        run.resident = False
                        run.observer_enabled = False
                        self._control(run)
                    # Remove only this service-created, non-sensitive control.
                    try:
                        (self.control_dir / f"{run.run_id}.json").unlink(missing_ok=True)
                    except OSError:
                        pass

            job = self.jobs.submit("neural_observation", target, request_id=run.request_id,
                                   generation_epoch=run.generation_epoch)
            with self.lock:
                run.job_id = job["id"]
                return run.view()

    def _ingest_safe(self, run, batch):
        became_running = False
        try:
            with self.lock:
                run.worker_dropped_events = max(run.worker_dropped_events, int(batch.get("dropped_events", 0)))
                run.aggregated_events = max(run.aggregated_events, int(batch.get("aggregated_events", 0)))
                for event in batch.get("events", [])[:4096]:
                    if not isinstance(event, dict) or any(event.get(key) != getattr(run, key) for key in (
                        "run_id", "request_id", "generation_epoch"
                    )):
                        run.rejected_stale_events += 1
                        continue
                    sequence = event.get("sequence_no", 0)
                    if not isinstance(sequence, int) or sequence <= run.worker_sequence_no:
                        run.rejected_stale_events += 1
                        continue
                    run.worker_sequence_no = sequence
                    kind, value = event.get("event_type"), event.get("payload", {})
                    if kind == "structure":
                        if not isinstance(value, dict) or len(_json_bytes(value)) > MAX_STRUCTURE_BYTES:
                            raise ValueError("Invalid structure")
                        run.structure = value
                        run.resident = True
                        self._state(run, "running")
                        became_running = True
                        # Metadata-only structure. No token or activation payload.
                        _atomic_json(self.cache_path, {"structure": value, "cached_at": utcnow(),
                                                     "source_run_id": run.run_id, "resident": False})
                    elif kind == "observer_state":
                        run.observer_enabled = value.get("state") == "observing" and run.intended_enabled
                    elif kind == "observer_error":
                        run.observer_enabled = False
                        run.observation_error = str(value.get("message", "관측 중단"))[:300]
                    elif kind == "summary":
                        run.observer_enabled = False
                    if run.resident and run.observer_enabled and run.subscribers and run.state not in TERMINAL:
                        run.mode = "LIVE"
                    elif run.state not in TERMINAL:
                        run.mode = "STALE"
                    run.append(kind, value, event=event)
        except Exception as exc:
            with self.lock:
                run.observer_enabled = run.intended_enabled = False
                run.mode = "STALE"
                run.observation_error = "관측 오류로 계측을 중지했습니다. 모델 작업은 계속됩니다."
                try:
                    run.append("observer_error", {"error_type": type(exc).__name__, "message": run.observation_error,
                                                  "inference_continues": True})
                except ValueError:
                    pass
                self._control(run)
        if became_running:
            # Keep lock order consistent with start(): never acquire jobs.lock
            # while holding the observation lock.
            try:
                self.jobs.update(run.job_id, state="running")
            except Exception:
                pass

    def get(self, ident):
        with self.lock:
            return self._get(ident).view()

    def subscribe(self, ident):
        with self.lock:
            run = self._get(ident)
            subscription = new_id()
            run.subscribers.add(subscription)
            run.ever_subscribed = True
            if run.state not in TERMINAL and run.intended_enabled:
                run.observer_enabled = True
                self._control(run)
            return subscription

    def unsubscribe(self, ident, subscription):
        with self.lock:
            if ident not in self.runs:
                return
            run = self.runs[ident]
            run.subscribers.discard(subscription)
            if not run.subscribers and run.state not in TERMINAL:
                run.observer_enabled = False
                run.mode = "STALE"
                run.append("observer_state", {"state": "disabled", "reason": "last_viewer_disconnected"})
                self._control(run)

    def snapshot(self, ident):
        with self.lock:
            run = self._get(ident)
            events = run.after(0)
            return {"run_id": run.run_id, "request_id": run.request_id, "generation_epoch": run.generation_epoch,
                    "event_type": "snapshot", "sequence_no": run.sequence_no, "observed_at": utcnow(),
                    "source": "backend_derived", "timing_kind": "host_call", "payload": {
                        "run": run.view(), "structure": copy.deepcopy(run.structure),
                        "earliest_sequence_no": events[0]["sequence_no"] if events else run.sequence_no + 1,
                        "dropped_events": run.dropped_events, "server_instance": self.jobs.instance}}

    def events_after(self, ident, after):
        with self.lock:
            run = self._get(ident)
            return run.after(after), run.state in TERMINAL, run.update_interval_ms

    def observation(self, ident, body):
        with self.lock:
            run = self._get(ident)
            if body["generation_epoch"] != run.generation_epoch:
                raise NeuralConflict("이전 generation_epoch의 관측 제어를 거부했습니다.")
            if run.state in TERMINAL:
                raise NeuralConflict("이미 종료된 작업의 관측을 다시 켤 수 없습니다.")
            if body["enabled"] and run.initial_observation_mode == "off":
                raise NeuralConflict("OFF 기준 실행에는 관측기가 없습니다. 완료 후 경량 계측으로 새 요청을 실행하세요.")
            if run.control_transitions >= 100:
                raise NeuralConflict("이 작업의 관측 제어 100회 한도에 도달했습니다. 종료 상태 기록 공간은 보존됩니다.")
            run.control_transitions += 1
            run.intended_enabled = body["enabled"]
            run.observer_enabled = body["enabled"]
            if body.get("mode"):
                run.observation_mode = body["mode"]
            for key in ("selected_layers", "sample_every_steps", "update_interval_ms"):
                if body.get(key) is not None:
                    setattr(run, key, body[key])
            if not run.observer_enabled:
                run.mode = "STALE"
            self._control(run)
            run.append("observer_state", {"state": "enable_requested" if run.observer_enabled else "disabled",
                                          "reason": "authenticated_viewer_control"})
            return run.view()

    def cancel(self, ident, generation_epoch):
        with self.lock:
            run = self._get(ident)
            if generation_epoch != run.generation_epoch:
                raise NeuralConflict("이전 generation_epoch의 취소를 거부했습니다.")
            if run.state in TERMINAL:
                return run.view()
            job_id = run.job_id
            run.observer_enabled = run.intended_enabled = False
            run.mode = "STALE"
            self._control(run)
            run.append("cancel", {"state": "cancel_requested"})
        self.jobs.cancel(job_id)
        return self.get(ident)

    def state(self):
        from edu_tutor.models.runtime import model_status
        from edu_tutor.models.budget import status as budget_status
        all_jobs = self.store.list("jobs")
        active_jobs = [{key: j.get(key) for key in ("id", "kind", "state", "request_id", "generation_epoch")}
                       for j in all_jobs if j["state"] not in TERMINAL]
        training = [job_view(self.root, j) for j in all_jobs if j.get("kind") == "training"]
        model = model_status(self.root)
        with self.lock:
            active = next((run for run in reversed(self.runs.values()) if run.state not in TERMINAL), None)
            structure = copy.deepcopy(active.structure) if active and active.structure else None
            source = "live_worker" if structure else None
            if not structure and self.cache_path.is_file() and self.cache_path.stat().st_size <= MAX_STRUCTURE_BYTES + 4096:
                try:
                    cached = json.loads(self.cache_path.read_text(encoding="utf-8"))
                    structure = cached["structure"]
                    structure = {**structure, "resident": False, "source": "cached", "cached_at": cached.get("cached_at"),
                                 "source_run_id": cached.get("source_run_id")}
                    source = "cached"
                except (OSError, ValueError, KeyError, TypeError):
                    pass
            mode = active.mode if active else ("STATIC" if structure else "UNAVAILABLE")
            result = {"mode": mode, "server_instance": self.jobs.instance, "structure": structure,
                      "structure_source": source, "active_run": active.view() if active else None,
                      "active_jobs": active_jobs, "gpu_lease": active_gpu_lease(self.store.local),
                      "model": {key: model.get(key) for key in ("model_id", "revision", "ready", "active_adapter")},
                      "training": {"current": [j for j in training if j["state"] not in TERMINAL],
                                   "history": [j for j in training if j["state"] in TERMINAL],
                                   "source": "existing_training_callbacks",
                                   "gradient_note": "기존 Trainer on_log의 전체 gradient norm입니다. 현재 단일 GPU Trainer 경로는 필요시 AMP unscale 후 clipping 전 norm 반환값을 기록합니다. clipping 후 norm·층별 gradient·가중치 변화는 미측정입니다.",
                                   "gradient_source": "설치된 transformers 4.57.3 trainer.py의 accelerator.clip_grad_norm_ 반환값; accelerate 1.12.0 unscale_gradients → torch clip_grad_norm_. 기존 training runner Bounds.on_log 기록을 재사용하며 다른 경로는 미검증.",
                                   "step_note": "step은 Trainer global_step(optimizer update), actual_microbatches는 기존 callback 누적값입니다. checkpoint 재계산 횟수가 아닙니다."},
                      "limits": {"max_new_tokens": 128, "max_selected_layers": 2, "max_components": 32,
                                 "min_sample_every_steps": 8, "memory_events_per_run": MAX_EVENTS,
                                 "memory_bytes_per_run": MAX_BUFFER_BYTES, "max_memory_runs": MAX_RUNS,
                                 "trace_bytes_per_run": MAX_TRACE_BYTES, "trace_bytes_total": MAX_TOTAL_TRACE_BYTES,
                                 "disk_trace_default": False}, "budget": budget_status(self.root)}
        result["records"] = self.records()
        return result

    @staticmethod
    def _record_summary(record, size):
        return {key: record.get(key) for key in ("id", "run_id", "created_at", "include_sensitive", "event_count",
                                                 "model_id", "revision", "original_source")} | {"bytes": size}

    def records(self):
        result = []
        for file in self.records_dir.glob("*.json"):
            if not re.fullmatch(r"[a-f0-9]{32}", file.stem) or file.is_symlink() or file.stat().st_size > MAX_TRACE_BYTES:
                continue
            try:
                value = json.loads(file.read_text(encoding="utf-8"))
                result.append(self._record_summary(value, file.stat().st_size))
            except (OSError, ValueError, TypeError):
                continue
        return sorted(result, key=lambda item: item.get("created_at") or "", reverse=True)

    def record(self, ident):
        if not re.fullmatch(r"[a-f0-9]{32}", ident):
            raise KeyError(ident)
        path = self.records_dir / f"{ident}.json"
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_TRACE_BYTES:
            raise KeyError(ident)
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, ident, include_sensitive=False):
        # Snapshot only under the broker lock. Quota scanning and disk writes
        # use a separate lock so a slow disk never holds up worker ingestion.
        with self.lock:
            run = self._get(ident)
            events = run.after(0)
            current = run.view(include_structure=False)
            if not include_sensitive:
                current.pop("output_text", None)
                current["metadata"] = _metrics(current["metadata"])
                for event in events:
                    if event["event_type"] not in CRITICAL_TYPES | {"structure", "block_call", "metrics"}:
                        event["payload"] = {"redacted": True, "reason": "sensitive_values_not_opted_in"}
            replay_structure = copy.deepcopy(run.structure)
            if replay_structure:
                replay_structure.update(resident=False, source="saved_observed_structure")
            current.update(resident=False, mode="REPLAY", connected_subscribers=0)
            record = {"id": new_id(), "run_id": ident, "created_at": utcnow(), "mode": "REPLAY",
                      "include_sensitive": bool(include_sensitive), "original_source": "saved_observed_events",
                      "model_id": run.model_id, "revision": run.revision, "event_count": len(events),
                      "structure": replay_structure, "run": current, "events": events,
                      "dropped_events": run.dropped_events, "worker_dropped_events": run.worker_dropped_events,
                      "aggregated_events": run.aggregated_events}
        data = _json_bytes(record)

        def status(value):
            with self.lock:
                run.save_status = value

        with self.save_lock:
            self.records_dir.mkdir(parents=True, exist_ok=True)
            total = sum(file.stat().st_size for file in self.records_dir.iterdir() if file.is_file())
            # Repeated snapshots of the SAME run share its 20 MB allowance.
            per_run = sum(item["bytes"] for item in self.records() if item.get("run_id") == ident)
            if per_run + len(data) > MAX_TRACE_BYTES or total + len(data) > MAX_TOTAL_TRACE_BYTES:
                status("limit_reached")
                raise NeuralConflict("관측 기록 20MB/회 또는 총 200MB 한도에 도달해 저장을 중지했습니다. 기존 파일은 보존합니다.")
            from edu_tutor.models.budget import policy, mutable_bytes
            limits = policy(self.root)
            if limits.get("enabled"):
                if shutil.disk_usage(limits.get("system_volume", "C:/")).free - len(data) < limits["min_C_free_bytes"]:
                    status("storage_policy_blocked")
                    raise NeuralConflict("C 드라이브 여유 공간 정책으로 관측 기록 저장을 중지했습니다.")
                if "fixed_storage_upper_bound_bytes" in limits and (
                    limits["fixed_storage_upper_bound_bytes"] + mutable_bytes(self.root) + len(data) > limits["max_project_bytes"]
                ):
                    status("storage_policy_blocked")
                    raise NeuralConflict("프로젝트 전체 저장 공간 정책으로 관측 기록 저장을 중지했습니다.")
            path = self.records_dir / f"{record['id']}.json"
            with path.open("xb") as handle:
                handle.write(data)
            status("saved_with_sensitive_values" if include_sensitive else "saved_metadata_only")
            return self._record_summary(record, len(data))

    def close(self):
        self.closed.set()
        with self.lock:
            for run in self.runs.values():
                if run.state not in TERMINAL:
                    run.observer_enabled = run.intended_enabled = False
                    self._state(run, "interrupted")
                    self._control(run)
        self.maintenance.join(timeout=1)
