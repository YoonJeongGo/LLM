"""T0: real random CPU Qwen3 forward; no downloaded weights, CUDA, or training."""
import json
import threading
import time

import pytest
import torch
from transformers import Qwen3Config, Qwen3ForCausalLM, StoppingCriteria, StoppingCriteriaList

from edu_tutor.models.observation import (BoundedEmitter, ModelObserver, describe_model,
                                          observed_streamer, persisted_report)


class Tokenizer:
    all_special_ids = [0, 1, 2]
    pad_token_id = 0
    eos_token_id = 2

    def decode(self, ids, skip_special_tokens=True, **kwargs):
        return "".join(f"단어{v} " for v in ids if not skip_special_tokens or v not in self.all_special_ids)


class Sink:
    dropped = 0

    def __init__(self):
        self.events = []

    def put(self, event, critical=False):
        # Roundtrip rejects tensors / computation graphs in every queued payload.
        self.events.append(json.loads(json.dumps(event)))


@pytest.fixture
def model():
    torch.manual_seed(41)
    config = Qwen3Config(vocab_size=40, hidden_size=16, intermediate_size=32,
                        num_hidden_layers=3, num_attention_heads=2, num_key_value_heads=1,
                        head_dim=8, max_position_embeddings=64, pad_token_id=0,
                        bos_token_id=1, eos_token_id=2, attention_dropout=0.)
    return Qwen3ForCausalLM(config).eval()


def make_observer(model, **config):
    sink = Sink()
    observer = ModelObserver(model, Tokenizer(), {"mode": "light", "run_id": "cpu-run",
                            "request_id": "cpu-request", "generation_epoch": 7, **config},
                             sink, {"model_id": "random-cpu-qwen3", "revision": "T0"}).start()
    assert not observer.failed
    return observer, sink


def hook_count(model):
    return sum(len(m._forward_hooks) + len(m._forward_pre_hooks) for m in model.modules())


def test_loaded_graph_counts_real_layers_and_shared_weights(model):
    model.lm_head.weight = model.model.embed_tokens.weight
    result = describe_model(model)
    assert result["layer_count"] == model.config.num_hidden_layers == 3
    assert [n["path"] for n in result["nodes"] if n["role"] == "block"] == [f"model.layers.{i}" for i in range(3)]
    assert result["parameter_count"] == sum(p.numel() for p in model.parameters())
    assert ["model.embed_tokens.weight", "lm_head.weight"] in result["shared_parameter_aliases"]
    assert result["graph_kind"] == "verified_block_summary"
    assert "hidden_states = residual + hidden_states" in result["forward_evidence"]["source"]
    assert len(result["forward_evidence"]["sha256"]) == 64
    assert result["currently_training"] is False


def test_peft_wrapper_uses_actual_base_and_adapter_dedup(model):
    from peft import LoraConfig, get_peft_model
    wrapped = get_peft_model(model, LoraConfig(r=2, lora_alpha=4, target_modules=["q_proj"], task_type="CAUSAL_LM"))
    result = describe_model(wrapped)
    assert result["wrapper_type"] == "PeftModelForCausalLM"
    assert result["base_path"] == "base_model.model"
    assert result["parameter_counts"]["adapter"] > 0
    assert result["parameter_count"] == sum(p.numel() for p in wrapped.parameters())
    assert all(n["path"].startswith("base_model.model.") for n in result["nodes"])


@pytest.mark.parametrize("mask,expected_index", [([1, 1, 0, 0], 1), ([0, 0, 1, 1], 3), ([1, 1, 1, 1], 3)])
def test_small_samples_equal_actual_last_valid_cpu_output(model, mask, expected_index):
    observer, sink = make_observer(model, mode="detail", selected_layers=["model.layers.0", "model.layers.2"], components=99, sample_every=1)
    references = {}
    handles = [model.model.layers[i].register_forward_hook(lambda m, a, o, index=i: references.update({index: o.detach().clone()})) for i in (0, 2)]
    try:
        with torch.inference_mode():
            model(input_ids=torch.tensor([[4, 5, 6, 7]]), attention_mask=torch.tensor([mask]), use_cache=True)
    finally:
        observer.close()
        for handle in handles:
            handle.remove()
    samples = [v for v in sink.events if v["event_type"] == "activation_sample"]
    assert len(samples) == 2
    for event, index in zip(samples, (0, 2)):
        assert event["payload"]["values"] == references[index][0, expected_index, :32].tolist()
        assert event["sampling_info"]["token_index"] == expected_index
        assert event["sampling_info"]["every_steps"] == 8
        assert len(event["payload"]["values"]) <= 32
        assert event["payload"]["gpu_elapsed_ms"] is None
        assert event["payload"]["sample_cpu_transfer_and_stats_ms"] >= 0
    assert observer._mask is None and hook_count(model) == 0


def test_all_padding_never_claims_last_valid_sample(model):
    observer, sink = make_observer(model, mode="detail", selected_layers=["model.layers.0"])
    try:
        with torch.inference_mode():
            model(torch.tensor([[0, 0]]), attention_mask=torch.tensor([[0, 0]]))
    finally:
        observer.close()
    assert not [v for v in sink.events if v["event_type"] == "activation_sample"]


@pytest.mark.parametrize("use_cache", [True, False])
def test_generate_equivalent_inputs_weights_unchanged_and_cache_phases(model, use_cache):
    ids = torch.tensor([[5]])  # single-token prompt is still prefill
    original_ids = ids.clone()
    weights = {name: p.detach().clone() for name, p in model.named_parameters()}
    settings = {"input_ids": ids, "attention_mask": torch.ones_like(ids), "max_new_tokens": 10,
                "do_sample": False, "use_cache": use_cache, "eos_token_id": None, "pad_token_id": 0}
    with torch.inference_mode():
        baseline = model.generate(**settings)
    observer, sink = make_observer(model, mode="detail", selected_layers=["model.layers.0", "model.layers.1", "model.layers.2"], sample_every=8)
    streamer = observed_streamer(Tokenizer(), observer, skip_prompt=True, skip_special_tokens=True)
    try:
        with torch.inference_mode():
            actual = model.generate(**settings, streamer=streamer)
    finally:
        observer.close()
    assert torch.equal(baseline, actual)
    assert torch.equal(ids, original_ids)
    assert all(torch.equal(weights[name], p) for name, p in model.named_parameters())
    forwards = [e for e in sink.events if e["event_type"] == "forward"]
    assert len(forwards) == 10
    assert forwards[0]["phase"] == "prefill"
    assert forwards[0]["payload"]["cache_length_before"] == 0
    assert all(e["phase"] == "decode" for e in forwards[1:])
    assert all(e["payload"]["cache_reused"] is use_cache for e in forwards[1:])
    assert all(e["payload"]["recomputes_context"] is (not use_cache) for e in forwards[1:])
    tokens = [e for e in sink.events if e["event_type"] == "token"]
    assert [v for e in tokens for v in e["payload"]["token_ids"]] == actual[0, 1:].tolist()
    assert tokens[-1]["payload"]["cumulative_text"] == Tokenizer().decode(actual[0, 1:].tolist())
    assert "".join(streamer) == Tokenizer().decode(actual[0, 1:].tolist())
    samples = [e for e in sink.events if e["event_type"] == "activation_sample"]
    assert {e["payload"]["step"] for e in samples} == {0, 8}
    assert len(samples) == 4  # <= 2 selected layers, never the third
    assert hook_count(model) == 0


def test_light_mode_no_activation_copy_and_all_calls_have_real_shapes(model):
    observer, sink = make_observer(model)
    try:
        with torch.inference_mode():
            model(torch.tensor([[5, 6]]))
    finally:
        observer.close()
    calls = [e for e in sink.events if e["event_type"] == "block_call"]
    assert len(calls) == 6
    assert [e["payload"]["call_order"] for e in calls] == list(range(1, 7))
    assert all(e["payload"]["output"]["device"] == "cpu" for e in calls)
    assert all(e["payload"]["gpu_elapsed_ms"] is None for e in calls)
    assert not [e for e in sink.events if e["event_type"] == "activation_sample"]


def test_module_metadata_every_four_steps_keeps_exact_calls_and_skips_shape_work(model, monkeypatch):
    from edu_tutor.models import observation
    observer, sink = make_observer(model)
    original = observation.tensor_info
    metadata_reads = []
    def count_read(value):
        metadata_reads.append(1)
        return original(value)
    monkeypatch.setattr(observation, "tensor_info", count_read)
    try:
        with torch.inference_mode():
            model.generate(torch.tensor([[5]]), max_new_tokens=9, do_sample=False, eos_token_id=None, pad_token_id=0,
                           streamer=observed_streamer(Tokenizer(), observer, skip_prompt=True))
    finally:
        observer.close()
    calls = [e for e in sink.events if e["event_type"] == "block_call"]
    assert {e["payload"]["step"] for e in calls} == {0, 4, 8}
    assert len(calls) == 18 and len(metadata_reads) == 36  # input/output only on sampled calls
    assert all(count == 9 for count in observer.calls.values())
    assert {e["payload"]["call_count"] for e in calls if e["payload"]["step"] == 8} == {9}
    assert observer.summary()["aggregated_events"] == 36
    assert observer.summary()["module_event_every_steps"] == 4
    assert all(e["sampling_info"]["every_steps"] == 4 for e in calls)
    assert len([e for e in sink.events if e["event_type"] == "forward"]) == 9
    assert len([e for e in sink.events if e["event_type"] == "token"]) == 9


def test_detail_sampling_independent_of_module_metadata_interval(model):
    observer, sink = make_observer(model, mode="detail", selected_layers=["model.layers.0"], sample_every=9)
    try:
        with torch.inference_mode():
            model.generate(torch.tensor([[5]]), max_new_tokens=10, do_sample=False, eos_token_id=None, pad_token_id=0,
                           streamer=observed_streamer(Tokenizer(), observer, skip_prompt=True))
    finally:
        observer.close()
    assert [e["payload"]["step"] for e in sink.events if e["event_type"] == "activation_sample"] == [0, 9]
    assert 9 not in {e["payload"]["step"] for e in sink.events if e["event_type"] == "block_call"}
    assert observer.summary()["activation_sample_count"] == 2


def test_dynamic_disable_reenable_stale_epoch_and_no_duplicate_hooks(model, tmp_path):
    control = tmp_path / "control.json"
    observer, sink = make_observer(model, control_path=str(control))
    initial = hook_count(model)
    observer.attach()
    assert hook_count(model) == initial
    duplicate = ModelObserver(model, Tokenizer(), {"mode": "light"}, Sink()).start()
    assert duplicate.failed
    assert hook_count(model) == initial  # failed duplicate does not detach the owner
    for _ in range(3):
        control.write_text(json.dumps({"generation_epoch": 7, "enabled": False, "mode": "light"}))
        observer.poll_control(force=True)
        assert hook_count(model) == 0
        control.write_text(json.dumps({"generation_epoch": 7, "enabled": True, "mode": "light"}))
        observer.poll_control(force=True)
        assert hook_count(model) == initial
    control.write_text(json.dumps({"generation_epoch": 6, "enabled": False}))
    observer.poll_control(force=True)
    assert hook_count(model) == initial
    observer.close()
    observer.close()
    assert hook_count(model) == 0


def test_late_enable_without_cache_is_decode_not_prefill(model):
    observer, sink = make_observer(model)
    observer.detach()
    class EnableAfterFirstToken(StoppingCriteria):
        def __call__(self, *args, **kwargs):
            observer.attach()
            return False
    try:
        with torch.inference_mode():
            model.generate(torch.tensor([[5]]), max_new_tokens=3, do_sample=False, use_cache=False,
                           eos_token_id=None, pad_token_id=0,
                           stopping_criteria=StoppingCriteriaList([EnableAfterFirstToken()]),
                           streamer=observed_streamer(Tokenizer(), observer, skip_prompt=True))
    finally:
        observer.close()
    forwards = [e for e in sink.events if e["event_type"] == "forward"]
    assert len(forwards) == 2
    assert all(e["phase"] == "decode" and e["payload"]["recomputes_context"] for e in forwards)
    assert [e["payload"]["step"] for e in forwards] == [1, 2]


def test_observation_exception_fails_open_and_cleans_hooks(model, monkeypatch):
    ids = torch.tensor([[5, 6]])
    with torch.inference_mode():
        baseline = model(ids).logits
    observer, sink = make_observer(model)
    def broken(*args):
        raise RuntimeError("synthetic observer failure")
    monkeypatch.setattr(observer, "_module_post", broken)
    try:
        with torch.inference_mode():
            actual = model(ids).logits
    finally:
        observer.close("error")
    assert torch.equal(baseline, actual)
    assert observer.failed and hook_count(model) == 0
    assert any(e["event_type"] == "observer_error" for e in sink.events)


def test_model_error_finally_cleanup(model):
    observer, _ = make_observer(model)
    try:
        with pytest.raises((IndexError, RuntimeError)):
            model(torch.tensor([[9999]]))
    finally:
        observer.close("error")
    assert hook_count(model) == 0 and observer._mask is None


def test_cancel_criteria_cleanup_without_changing_generation(model):
    observer, _ = make_observer(model)
    class Cancel(StoppingCriteria):
        def __call__(self, *args, **kwargs):
            return True
    try:
        with torch.inference_mode():
            output = model.generate(torch.tensor([[5]]), max_new_tokens=8, do_sample=False,
                        stopping_criteria=StoppingCriteriaList([Cancel()]),
                        streamer=observed_streamer(Tokenizer(), observer, skip_prompt=True))
    finally:
        observer.close("cancelled")
    assert output.shape[-1] == 2 and hook_count(model) == 0


def test_cumulative_korean_decoding_and_special_token_flags(model):
    class Korean(Tokenizer):
        def decode(self, ids, **kwargs):
            return "가" if 5 in ids and 6 in ids else "�" if 5 in ids else ""
    sink = Sink()
    observer = ModelObserver(model, Korean(), {"mode": "light"}, sink).start()
    streamer = observed_streamer(Korean(), observer, skip_prompt=True, skip_special_tokens=True)
    try:
        streamer.put(torch.tensor([[1, 9]]))
        for token in (5, 6, 2):
            streamer.put(torch.tensor([token]))
        streamer.end()
    finally:
        observer.close()
    events = [v for v in sink.events if v["event_type"] == "token"]
    assert events[0]["payload"]["cumulative_text"] == "�"
    assert events[1]["payload"]["cumulative_text"] == "가"
    assert events[-1]["payload"]["special_tokens"] == [True]
    assert "".join(streamer) == "가"


def test_bounded_emitter_drops_samples_without_blocking_and_retains_state():
    release, entered = threading.Event(), threading.Event()
    batches = []
    def slow(event_type, **payload):
        entered.set()
        release.wait(3)
        batches.append(payload)
    emitter = BoundedEmitter(slow, flush_ms=100, capacity=4)
    event = lambda i: {"sequence_no": i, "event_type": "block_call"}
    emitter.put(event(0))
    assert entered.wait(1)
    start = time.perf_counter()
    for i in range(1, 1001):
        emitter.put(event(i))
    emitter.put({"sequence_no": 1001, "event_type": "summary"}, critical=True)
    elapsed = time.perf_counter() - start
    assert elapsed < .5 and emitter.samples.qsize() <= 4 and emitter.dropped >= 996
    release.set()
    emitter.close()
    assert any(e["event_type"] == "summary" for b in batches for e in b["events"])


def test_emitter_global_order_across_critical_and_sample_batch_boundaries():
    batches = []
    emitter = BoundedEmitter(lambda event_type, **payload: batches.append(payload), flush_ms=100, capacity=2048)
    for i in range(1000):
        emitter.put({"sequence_no": i, "event_type": "token" if i % 8 == 0 else "block_call"}, critical=i % 8 == 0)
        if i % 35 == 0:
            time.sleep(.008)
    emitter.close()
    received = [event["sequence_no"] for batch in batches for event in batch["events"]]
    assert received == list(range(1000))
    assert emitter.dropped == 0


def test_observer_persistence_is_opt_in_and_normal_chat_unchanged():
    report = {"text": "학생 원문", "input_token_ids": [1], "output_token_ids": [2],
              "activation_sample_count": 1, "output_tokens": 1}
    assert persisted_report(report, None) is report
    assert persisted_report(report, {"save_sensitive": True}) is report
    assert persisted_report(report, {}) == {"activation_sample_count": 1, "output_tokens": 1}


@pytest.mark.parametrize("mode", [None, "off", "light", "detail"])
def test_worker_cpu_integration_preserves_chat_and_redacts_observer_disk(model, monkeypatch, tmp_path, mode, nf4_inference_fixture):
    from transformers import BatchEncoding
    from edu_tutor.models import worker
    class ChatTokenizer(Tokenizer):
        def apply_chat_template(self, *args, **kwargs):
            return BatchEncoding({"input_ids": torch.tensor([[1, 5, 6]]), "attention_mask": torch.ones((1, 3), dtype=torch.long)})
    events = []
    # This random 40-token CPU model uses the explicit fixture seam; it cannot
    # claim the production model's two 151xxx EOS IDs.
    model.generation_config.eos_token_id = None
    def cpu_loader(*args, **kwargs):
        return model, ChatTokenizer(), {"model_id": "cpu-tiny", "revision": "test", "inference": nf4_inference_fixture}
    monkeypatch.setattr(worker, "emit", lambda event_type, **values: events.append({"type": event_type, **values}))
    monkeypatch.setattr(torch.cuda, "max_memory_allocated", lambda: 0)
    monkeypatch.setattr(torch.cuda, "max_memory_reserved", lambda: 0)
    monkeypatch.setattr(torch.cuda, "get_device_name", lambda *_: "CPU test; no CUDA inference")
    payload = {"root": str(tmp_path), "messages": [{"role": "user", "content": "private"}],
               "max_new_tokens": 10, "cancel_path": str(tmp_path / "cancel"), "run_dir": str(tmp_path)}
    if mode is not None:
        payload["observation"] = {"mode": mode, "run_id": "cpu-integration", "request_id": "cpu-request",
                                  "generation_epoch": 1, "selected_layers": ["model.layers.0"]}
    worker.text_job(payload, model_loader=cpu_loader)
    saved = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    metadata = next(e for e in events if e["type"] == "metadata")
    assert metadata["eos_token_ids"] == [Tokenizer.eos_token_id]
    assert hook_count(model) == 0
    assert "text" in metadata
    if mode is None:
        assert saved["text"] == metadata["text"]
        assert "output_token_ids" not in metadata
    else:
        assert "text" not in saved and "output_token_ids" not in saved and "input_token_ids" not in saved
        assert len(metadata["output_token_ids"]) == metadata["output_tokens"]
        assert metadata["generation_seconds"] > 0 and metadata["preparation_seconds"] >= 0
        assert 0 < metadata["first_token_latency_seconds"] <= metadata["generation_seconds"]
        assert metadata["first_token_latency_status"] == "measured_host_stopping_callback"
        assert metadata["first_token_latency_kind"] == "generation_start_to_first_existing_stopping_callback_after_streamer"
        assert metadata["first_token_latency_seconds"] + metadata["generation_remaining_seconds"] == pytest.approx(metadata["generation_seconds"])
        assert metadata["remaining_output_tokens"] == max(metadata["output_tokens"] - 1, 0)
        assert metadata["warmup_seconds"] is None
        assert metadata["peak_vram_reserved_bytes"] == 0
        assert metadata["observation"]["remaining_hooks"] == 0
    batches = [e for b in events if b["type"] == "observation_batch" for e in b["events"]]
    if mode in {"light", "detail"}:
        assert any(e["event_type"] == "structure" for e in batches)
        assert any(e["event_type"] == "summary" for e in batches)
        assert [v for e in batches if e["event_type"] == "token" for v in e["payload"]["token_ids"]] == metadata["output_token_ids"]
    else:
        assert not batches


def test_worker_observer_setup_failure_keeps_generation(model, monkeypatch, tmp_path, nf4_inference_fixture):
    from transformers import BatchEncoding
    from edu_tutor.models import worker, observation
    class ChatTokenizer(Tokenizer):
        def apply_chat_template(self, *args, **kwargs):
            return BatchEncoding({"input_ids": torch.tensor([[5]]), "attention_mask": torch.ones((1, 1), dtype=torch.long)})
    def broken(*args, **kwargs):
        raise RuntimeError("synthetic publisher setup failure")
    events = []
    monkeypatch.setattr(observation, "BoundedEmitter", broken)
    model.generation_config.eos_token_id = None
    def cpu_loader(*args, **kwargs):
        return model, ChatTokenizer(), {"model_id": "cpu", "revision": "T0", "inference": nf4_inference_fixture}
    monkeypatch.setattr(worker, "emit", lambda event_type, **values: events.append({"type": event_type, **values}))
    monkeypatch.setattr(torch.cuda, "max_memory_allocated", lambda: 0)
    monkeypatch.setattr(torch.cuda, "max_memory_reserved", lambda: 0)
    monkeypatch.setattr(torch.cuda, "get_device_name", lambda *_: "CPU fixture")
    worker.text_job({"root": str(tmp_path), "messages": [], "max_new_tokens": 3,
                     "cancel_path": str(tmp_path / "cancel"), "run_dir": str(tmp_path), "observation": {"mode": "light"}},
                    model_loader=cpu_loader)
    metadata = next(e for e in events if e["type"] == "metadata")
    assert metadata["eos_token_ids"] == [Tokenizer.eos_token_id]
    assert metadata["output_tokens"] > 0
    assert metadata["observation"]["observer_failed"] is True
    assert hook_count(model) == 0


@pytest.mark.parametrize("observed", [True, False])
def test_worker_error_does_not_leak_observer_prompt(monkeypatch, tmp_path, capsys, observed):
    import contextlib
    import io
    from edu_tutor.models import worker
    payload = {"kind": "text", "root": str(tmp_path), "job_id": "cpu-error"}
    if observed:
        payload["observation"] = {"mode": "light"}
    monkeypatch.setattr(worker.sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(worker, "GPULease", lambda *args: contextlib.nullcontext())
    def fail(*args):
        raise ValueError("private student text")
    monkeypatch.setattr(worker, "text_job", fail)
    with pytest.raises(SystemExit):
        worker.main()
    result = json.loads(capsys.readouterr().out)
    assert ("private student text" in result["message"]) is (not observed)
