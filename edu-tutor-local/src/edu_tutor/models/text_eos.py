"""Use the actual reviewed Qwen generation termination contract."""
from __future__ import annotations


def generation_eos_ids(model, tokenizer, *, cpu_fixture=False):
    """Production generation needs both configured EOS IDs; never infer one.

    An explicitly injected, marked CPU fixture may have no generation_config.
    That seam does not authorize a production fallback or alter stored runs.
    """
    values = getattr(getattr(model, "generation_config", None), "eos_token_id", None)
    if values is None and cpu_fixture:
        token = getattr(tokenizer, "eos_token_id", None)
        if type(token) is not int or token < 0:
            raise ValueError("Explicit CPU fixture EOS is invalid")
        return [token]
    if (not isinstance(values, list) or len(values) != 2 or set(values) != {151645, 151643}
            or any(type(value) is not int for value in values) or tokenizer.eos_token_id not in values):
        raise ValueError("Production generation EOS differs from the reviewed two-token configuration")
    return list(values)
