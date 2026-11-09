import json
import threading
from pathlib import Path

import pytest

from edu_tutor.training.runner import (_assert_finite_adapter_weights, _provenance, _smoke_evidence,
                                      _training_resource_metrics, run_gpu_training)


def test_rejects_unpinned_local_provenance_before_model_import(tmp_path):
    (tmp_path / "model-manifest.json").write_text(json.dumps({"model_id":"Qwen/Qwen3-1.7B", "revision":"main"}))
    with pytest.raises(ValueError, match="pinned"):
        _provenance(tmp_path, {"id":"Qwen/Qwen3-1.7B", "revision":"main"})


def test_revision_mismatch_blocks_adapter_base(tmp_path):
    (tmp_path / "model-manifest.json").write_text(json.dumps({"model_id":"Qwen/Qwen3-1.7B", "revision":"a"*40}))
    with pytest.raises(ValueError, match="does not match"):
        _provenance(tmp_path, {"id":"Qwen/Qwen3-1.7B", "revision":"b"*40})


def test_manifest_cannot_escape_model_directory(tmp_path):
    (tmp_path / "model.safetensors").write_bytes(b"fixture")
    (tmp_path / "model-manifest.json").write_text(json.dumps({
        "model_id":"Qwen/Qwen3-1.7B", "revision":"a"*40,
        "files":[{"path":"../outside", "size":1}]}))
    with pytest.raises(ValueError, match="missing or wrong size"):
        _provenance(tmp_path, {"id":"Qwen/Qwen3-1.7B", "revision":"a"*40})


def test_demo_requires_actual_five_steps_and_reload(tmp_path):
    folder = tmp_path / "runs/smoke"
    folder.mkdir(parents=True)
    report = {"mode":"smoke", "status":"passed", "optimizer_steps":4,
              "revision":"a"*40, "dataset_sha256":"data", "reload":{"status":"passed"}}
    (folder / "manifest.json").write_text(json.dumps(report))
    with pytest.raises(ValueError, match="5-step"):
        _smoke_evidence(tmp_path, "a"*40, "data")
    report["optimizer_steps"] = 5
    report["reload"]["status"] = "not_run"
    (folder / "manifest.json").write_text(json.dumps(report))
    with pytest.raises(ValueError, match="5-step"):
        _smoke_evidence(tmp_path, "a"*40, "data")


def test_unknown_mode_rejected_without_loading_model(tmp_path):
    with pytest.raises(ValueError, match="mode"):
        run_gpu_training("missing", "missing", tmp_path, mode="unbounded")


def test_resource_throughput_counts_actual_short_accumulation_groups():
    class CudaFixture:
        def memory_allocated(self):
            return 1024

        def max_memory_allocated(self):
            return 4096

    # Four optimizer steps can contain 8+8+8+1 microbatches, not 4*8.
    metrics = _training_resource_metrics(CudaFixture(), 25, 1, 10)
    assert metrics == {"current_vram_bytes": 1024, "peak_vram_bytes": 4096,
                       "samples_processed": 25, "samples_per_second": 2.5}
    assert "tokens_per_second" not in metrics
    assert "samples_per_second" not in _training_resource_metrics(CudaFixture(), 0, 1, 0)


def test_weight_guard_catches_optimizer_corruption_even_when_gradients_are_finite():
    torch = pytest.importorskip("torch")
    weight = torch.nn.Parameter(torch.tensor([1.0, 2.0], device="cpu"))
    optimizer = torch.optim.AdamW([weight], lr=1e-4)
    weight.grad = torch.ones_like(weight)
    optimizer.step()
    _assert_finite_adapter_weights({"lora_A.weight": weight})
    # Fault injection: a corrupted second moment creates NaN weights despite
    # entirely finite input weights and gradients. A gradient-only gate misses it.
    optimizer.state[weight]["exp_avg_sq"].fill_(-1)
    assert torch.isfinite(weight.grad).all()
    optimizer.step()
    with pytest.raises(RuntimeError, match="nonfinite adapter weights"):
        _assert_finite_adapter_weights({"lora_A.weight": weight})


def test_weight_guard_rejects_infinity_and_missing_adapter():
    torch = pytest.importorskip("torch")
    for trainable in ({}, {"lora_B.weight": torch.tensor([float("inf")], device="cpu")}):
        with pytest.raises(RuntimeError, match="adapter weights"):
            _assert_finite_adapter_weights(trainable)
