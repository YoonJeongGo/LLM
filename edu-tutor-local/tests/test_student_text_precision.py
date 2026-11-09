"""Explicit student precision wiring, using fake loaders/events only."""
from copy import deepcopy
from contextlib import nullcontext
import json
from pathlib import Path
import queue
import sys
from types import SimpleNamespace

import pytest

from edu_tutor.models import runtime, text_precision, text_session, text_session_worker, worker


def snapshot(precision="nf4"):
    return {"fixture_only": True, "requested_precision": precision,
            "quantization": "nf4_double" if precision == "nf4" else "none",
            "load_dtype": "torch.bfloat16", "actual_is_loaded_in_4bit": precision == "nf4",
            "actual_parameter_devices": ["cuda:0"],
            "actual_parameter_dtypes_elements": ({"torch.bfloat16": 10, "torch.uint8": 20}
                                                  if precision == "nf4" else {"torch.bfloat16": 10})}


def write_policy(root, value):
    (root / ".local").mkdir(exist_ok=True)
    (root / ".local/text-inference-policy.json").write_text(json.dumps(value), encoding="utf-8")


def test_policy_default_is_nf4_without_creating_file(tmp_path):
    assert text_precision.policy(tmp_path) == {"precision": "nf4"}
    assert not (tmp_path / ".local/text-inference-policy.json").exists()


@pytest.mark.parametrize("value", [{}, [], None, {"precision": "fp16"}, {"precision": None},
                                  {"precision": "BF16"}, {"precision": "bf16", "extra": True}])
def test_invalid_policy_blocks_before_any_dispatch(tmp_path, monkeypatch, value):
    write_policy(tmp_path, value)
    monkeypatch.setattr(runtime, "model_status", lambda *_: pytest.fail("invalid policy reached model status"))
    monkeypatch.setattr(runtime, "run_worker", lambda *_a, **_k: pytest.fail("invalid policy dispatched"))
    with pytest.raises(ValueError):
        list(runtime.generate([{"role": "user", "content": "fixture"}], root=tmp_path))


@pytest.mark.parametrize("precision", ["nf4", "bf16"])
def test_generate_captures_policy_once_and_preserves_actual_metadata(tmp_path, monkeypatch, precision):
    write_policy(tmp_path, {"precision": precision})
    monkeypatch.setattr(runtime, "model_status", lambda *_: {"ready": True})
    captured = []
    def events(payload, **kwargs):
        captured.append(payload)
        write_policy(tmp_path, {"precision": "nf4" if precision == "bf16" else "bf16"})
        yield {"type": "delta", "text": "CPU seam output"}
        yield {"type": "metadata", "finish_reason": "eos", "adapter": None,
               "requested_precision": precision, "inference": snapshot(precision)}
    monkeypatch.setattr(runtime, "run_worker", events)
    metadata = {}
    assert list(runtime.generate([{"role": "user", "content": "fixture"}], root=tmp_path, metadata_out=metadata)) == ["CPU seam output"]
    assert captured[0]["precision"] == precision
    assert metadata["requested_precision"] == precision
    assert metadata["inference"] == snapshot(precision)


@pytest.mark.parametrize("field,value", [("requested_precision", "nf4"), ("inference", None),
    ("inference", snapshot("nf4"))])
def test_runtime_rejects_worker_precision_mismatch(tmp_path, monkeypatch, field, value):
    write_policy(tmp_path, {"precision": "bf16"})
    monkeypatch.setattr(runtime, "model_status", lambda *_: {"ready": True})
    event = {"type": "metadata", "finish_reason": "eos", "adapter": None,
             "requested_precision": "bf16", "inference": snapshot("bf16")}
    event[field] = value
    monkeypatch.setattr(runtime, "run_worker", lambda *_a, **_k: iter([event]))
    metadata = {}
    with pytest.raises(RuntimeError):
        list(runtime.generate([{"role": "user", "content": "fixture"}], root=tmp_path, metadata_out=metadata))
    assert metadata == {}


def test_session_key_separates_precision_and_rejects_invalid(tmp_path):
    payload = {"adapter": None, "execution_allowance_id": "fixture"}
    assert text_session._key(tmp_path, payload) == text_session._key(tmp_path, {**payload, "precision": "nf4"})
    assert text_session._key(tmp_path, payload) != text_session._key(tmp_path, {**payload, "precision": "bf16"})
    with pytest.raises(ValueError):
        text_session._key(tmp_path, {**payload, "precision": "fp16"})


def test_resident_load_binds_root_adapter_precision_and_reuses_once(tmp_path, monkeypatch):
    model = SimpleNamespace(device="cuda:0", parameters=lambda: iter([SimpleNamespace(dtype="torch.bfloat16")]))
    fake_torch = SimpleNamespace(cuda=SimpleNamespace(memory_allocated=lambda: 40, memory_reserved=lambda: 80))
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    loads, events = [], []
    def loader(root, adapter, *, precision):
        loads.append((root, adapter, precision))
        return model, object(), {"inference": snapshot(precision)}
    monkeypatch.setattr(worker, "load_text", loader)
    engine = text_session_worker.ResidentModel(tmp_path, lambda kind, **values: events.append((kind, deepcopy(values))))
    first = engine.load(tmp_path, None, precision="bf16")
    second = engine.load(tmp_path, None, precision="bf16")
    assert first is second and len(loads) == 1
    ready = [values for kind, values in events if kind == "model_ready"]
    assert [values["request_model_load_count"] for values in ready] == [1, 0]
    assert ready[0]["model_instance_id"] == ready[1]["model_instance_id"]
    assert ready[1]["requested_precision"] == "bf16" and ready[1]["inference"] == snapshot("bf16")
    for root, adapter, precision in [(tmp_path, None, "nf4"), (tmp_path, str(tmp_path / "another"), "bf16"),
                                      (tmp_path / "elsewhere", None, "bf16")]:
        with pytest.raises((ValueError, RuntimeError)):
            engine.load(root, adapter, precision=precision)
    assert len(loads) == 1


def test_bf16_adapter_fp32_is_explicit_but_base_or_fp16_mismatch_rejected():
    actual = snapshot("bf16")
    actual["actual_parameter_dtypes_elements"]["torch.float32"] = 4
    assert text_precision.validate_inference(actual, "bf16", "registered-adapter") == actual
    with pytest.raises(RuntimeError, match="dtypes"):
        text_precision.validate_inference(actual, "bf16")
    actual["actual_parameter_dtypes_elements"]["torch.float16"] = 2
    with pytest.raises(RuntimeError, match="dtypes"):
        text_precision.validate_inference(actual, "bf16", "registered-adapter")


@pytest.mark.parametrize("precision", ["nf4", "bf16"])
def test_text_job_passes_precision_and_records_verified_metadata(tmp_path, monkeypatch, precision):
    class Tokens(list):
        def __getitem__(self, key):
            value = super().__getitem__(key)
            return Tokens(value) if isinstance(key, slice) else value
        def tolist(self):
            return list(self)
    class Inputs(dict):
        def to(self, device):
            return self
    class Streamer:
        def __init__(self, *args, **kwargs): self.queue = queue.Queue()
        def end(self): self.queue.put(None)
        def __next__(self):
            item = self.queue.get(timeout=2)
            if item is None: raise StopIteration
            return item
    tokenizer = SimpleNamespace(eos_token_id=9, pad_token_id=0,
        apply_chat_template=lambda *_a, **_k: Inputs(input_ids=SimpleNamespace(shape=(1, 2))),
        decode=lambda *_a, **_k: "CPU fixture output")
    def generate(**kwargs):
        kwargs["streamer"].queue.put("CPU fixture output")
        kwargs["streamer"].end()
        return [Tokens([1, 2, 3, 9])]
    model = SimpleNamespace(device="cuda:0", generate=generate)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(inference_mode=nullcontext,
        cuda=SimpleNamespace(max_memory_allocated=lambda: 0, get_device_name=lambda *_: "CPU fixture")))
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(TextIteratorStreamer=Streamer,
        StoppingCriteria=object, StoppingCriteriaList=list))
    calls, events = [], []
    def loader(root, adapter, *, precision):
        calls.append(precision)
        return model, tokenizer, {"model_id": "fixture", "revision": "fixture", "inference": snapshot(precision)}
    payload = {"root": str(tmp_path), "run_dir": str(tmp_path), "cancel_path": str(tmp_path / "cancel"),
               "precision": precision, "messages": [], "max_new_tokens": 16}
    worker.text_job(payload, model_loader=loader, emit_fn=lambda event_type, **values: events.append({"type": event_type, **values}))
    metadata = next(event for event in events if event["type"] == "metadata")
    assert calls == [precision]
    assert metadata["requested_precision"] == precision and metadata["inference"] == snapshot(precision)
    assert json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))["inference"] == snapshot(precision)
    events.clear()
    def wrong_loader(*args, **kwargs):
        return model, tokenizer, {"inference": snapshot("nf4" if precision == "bf16" else "bf16")}
    with pytest.raises(RuntimeError, match="differs"):
        worker.text_job(payload, model_loader=wrong_loader, emit_fn=lambda *a, **k: events.append((a, k)))
    assert events == []
