"""Position-based assistant-only targets, including EOS when pad == EOS."""
from __future__ import annotations


def encode_response_only(tokenizer, messages, max_length=512):
    roles = [m["role"] for m in messages]
    if roles not in (["user", "assistant"], ["system", "user", "assistant"]):
        raise ValueError("Only one user/assistant turn is supported")
    if not messages[-1]["content"].strip():
        raise ValueError("Empty assistant target")
    prefix = tokenizer.apply_chat_template(messages[:-1], tokenize=True, add_generation_prompt=True, enable_thinking=False)
    full = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False, enable_thinking=False)
    prefix, full = list(prefix), list(full)
    if not prefix or full[:len(prefix)] != prefix:
        raise ValueError("Actual template prefix token IDs are not stable; unsupported template boundary")
    if len(full) > max_length:
        raise ValueError(f"Answer would be truncated: {len(full)} > {max_length}; sample excluded")
    targets = full[len(prefix):]
    if not targets:
        raise ValueError("No response target tokens")
    eos = tokenizer.eos_token_id
    if eos is None or eos not in targets:
        raise ValueError("Actual assistant termination EOS is missing from target")
    return {
        "input_ids": full, "attention_mask": [1] * len(full),
        "labels": [-100] * len(prefix) + targets,
        "audit": {"prefix_length": len(prefix), "valid_length": len(full), "target_tokens": len(targets),
                  "target_decode": tokenizer.decode(targets, skip_special_tokens=False),
                  "enable_thinking": False},
    }


class ResponseOnlyCollator:
    def __init__(self, pad_token_id):
        if pad_token_id is None:
            raise ValueError("A pad token must be configured")
        self.pad_token_id = int(pad_token_id)

    def __call__(self, features):
        import torch
        if not features:
            raise ValueError("Empty batch")
        width = max(len(f["input_ids"]) for f in features)
        batch = {"input_ids": [], "attention_mask": [], "labels": []}
        for feature in features:
            size = len(feature["input_ids"])
            if len(feature["labels"]) != size or len(feature["attention_mask"]) != size:
                raise ValueError("Input, attention and label lengths differ")
            if not any(label != -100 for label in feature["labels"]):
                raise ValueError("No response target")
            if any(label != -100 and (not attention or label != token)
                   for token, label, attention in zip(feature["input_ids"], feature["labels"], feature["attention_mask"])):
                raise ValueError("Labels must be unshifted input tokens; padded labels must be masked")
            padding = width - size
            batch["input_ids"].append(feature["input_ids"] + [self.pad_token_id] * padding)
            batch["attention_mask"].append(feature["attention_mask"] + [0] * padding)
            batch["labels"].append(feature["labels"] + [-100] * padding)
        return {key: torch.tensor(value, dtype=torch.long) for key, value in batch.items()}
