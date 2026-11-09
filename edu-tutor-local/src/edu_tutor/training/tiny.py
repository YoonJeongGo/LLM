"""T1: real FP32 CPU LoRA on a small random Qwen3; never a teaching model."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import time
from pathlib import Path


def tiny_lora_smoke(output_dir, steps=3):
    import torch
    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import Qwen3Config, Qwen3ForCausalLM
    from .masking import ResponseOnlyCollator

    if not 2 <= steps <= 5:
        raise ValueError("Tiny wiring test is limited to 2..5 optimizer steps")
    started = time.monotonic()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(42)
    torch.set_num_threads(min(4, torch.get_num_threads()))
    config = Qwen3Config(vocab_size=128, hidden_size=64, intermediate_size=128,
                         num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2,
                         head_dim=16, max_position_embeddings=128, attention_dropout=0.0,
                         bos_token_id=0, eos_token_id=1, pad_token_id=1, tie_word_embeddings=False)
    base = Qwen3ForCausalLM(config).float().cpu()
    base.config.use_cache = False
    base.save_pretrained(output / "tiny-base", safe_serialization=True)
    model = get_peft_model(base, LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05,
                                          target_modules=["q_proj", "v_proj"], task_type="CAUSAL_LM"))
    frozen = {n: p.detach().clone() for n, p in model.named_parameters() if not p.requires_grad}
    before = {n: p.detach().clone() for n, p in model.named_parameters() if p.requires_grad}
    assert before and all("lora_" in n for n in before), "Unexpected trainable base weights"
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=1e-3)
    optimizer_ids = {id(p) for group in optimizer.param_groups for p in group["params"]}
    assert all(id(p) not in optimizer_ids for p in model.parameters() if not p.requires_grad)
    fixture = [
        {"input_ids": [2,3,4,5,6,7,8,1], "attention_mask": [1]*8, "labels": [-100]*4+[6,7,8,1]},
        {"input_ids": [2,9,10,11,12,1], "attention_mask": [1]*6, "labels": [-100]*3+[11,12,1]},
    ]
    batch = ResponseOnlyCollator(1)(fixture)
    (output / "synthetic-mask-audit.json").write_text(json.dumps({
        "fixture_only": True, "actual_qwen_tokenizer": False,
        **{k: v.tolist() for k, v in batch.items()}}, indent=2), encoding="utf-8")
    losses, nonzero_gradients = [], []
    model.train()
    for _ in range(steps):
        optimizer.zero_grad(set_to_none=True)
        loss = model(**batch).loss
        assert torch.isfinite(loss), "Nonfinite loss"
        loss.backward()
        gradients = {n: p.grad for n, p in model.named_parameters() if p.requires_grad and p.grad is not None}
        assert gradients and all(torch.isfinite(g).all() for g in gradients.values()), "Nonfinite/missing gradients"
        changed_gradients = [n for n, g in gradients.items() if torch.count_nonzero(g).item()]
        assert changed_gradients, "No nonzero gradient in any adapter parameter"
        nonzero_gradients.append(len(changed_gradients))
        optimizer.step()
        losses.append(float(loss.detach()))
    named = dict(model.named_parameters())
    changed = [n for n in before if not torch.equal(before[n], named[n].detach())]
    assert changed, "Adapter weights did not update"
    assert all(torch.equal(value, named[n].detach()) for n, value in frozen.items()), "Frozen base changed"
    assert all(torch.isfinite(p).all() for p in model.parameters()), "Nonfinite weights"
    model.eval()
    with torch.no_grad():
        logits_before = model(**{k: v for k, v in batch.items() if k != "labels"}).logits
    model.save_pretrained(output / "adapter", safe_serialization=True)
    same_base = Qwen3ForCausalLM.from_pretrained(output / "tiny-base", local_files_only=True,
                                              use_safetensors=True, torch_dtype=torch.float32)
    reloaded = PeftModel.from_pretrained(same_base, output / "adapter", local_files_only=True,
                                         is_trainable=False).eval()
    with torch.no_grad():
        logits_after = reloaded(**{k: v for k, v in batch.items() if k != "labels"}).logits
    max_diff = float((logits_before - logits_after).abs().max())
    assert torch.allclose(logits_before, logits_after, atol=1e-6, rtol=1e-5), "Adapter reload logits differ"
    manifest = {
        "tier": "T1", "status": "passed", "purpose": "random tiny CPU wiring only; not an educational model",
        "device": "cpu", "dtype": "float32", "seed": 42, "optimizer_steps": steps,
        "losses": losses, "finite_gradients": True, "nonzero_gradient_parameter_counts": nonzero_gradients,
        "changed_adapter_parameters": changed, "frozen_base_unchanged": True, "optimizer_excludes_base": True,
        "trainable_parameters": sum(p.numel() for p in model.parameters() if p.requires_grad),
        "total_parameters": sum(p.numel() for p in model.parameters()),
        "target_modules": [n for n, m in model.named_modules() if hasattr(m, "lora_A")],
        "saved_adapter_safetensors": True, "reload_same_saved_base": True, "reload_logits_max_abs_diff": max_diff,
        "base_sha256": hashlib.sha256((output / "tiny-base" / "model.safetensors").read_bytes()).hexdigest(),
        "packages": {p: importlib.metadata.version(p) for p in ("torch", "transformers", "peft", "safetensors")},
        "elapsed_seconds": time.monotonic()-started, "actual_qwen_template": "not_part_of_this_synthetic_test",
        "resume_training": "not_supported; saved adapter is weights, not a resumable training checkpoint",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
