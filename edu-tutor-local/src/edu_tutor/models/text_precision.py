"""Explicit student inference choice; absent policy preserves historical NF4."""
from __future__ import annotations

import json
from pathlib import Path


def validate_precision(value):
    if not isinstance(value, str) or value not in {"nf4", "bf16"}:
        raise ValueError("Text precision must be exactly nf4 or bf16")
    return value


def policy(root):
    from edu_tutor.paths import project_root
    path = project_root(root) / ".local/text-inference-policy.json"
    if not path.exists():
        return {"precision": "nf4"}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {"precision"}:
        raise ValueError("Text inference policy accepts only an explicit precision field")
    return {"precision": validate_precision(value["precision"])}


def validate_inference(inference, requested, adapter=None):
    """Check reported loaded state before any generated output may be emitted.

    The loader records actual dtype/device/storage independently of the request.
    PEFT can retain FP32 adapter tensors; this is kept visible in metadata and
    must not be represented as a wholly BF16 adapter model.
    """
    requested = validate_precision(requested)
    if not isinstance(inference, dict):
        raise RuntimeError("Loaded text precision metadata is missing")
    if (inference.get("requested_precision") != requested
            or inference.get("actual_is_loaded_in_4bit") is not (requested == "nf4")
            or inference.get("quantization") != ("nf4_double" if requested == "nf4" else "none")
            or inference.get("actual_parameter_devices") != ["cuda:0"]):
        raise RuntimeError("Loaded text precision/device differs from the requested configuration")
    dtypes = inference.get("actual_parameter_dtypes_elements")
    if not isinstance(dtypes, dict) or not dtypes or any(not isinstance(count, int) or count <= 0 for count in dtypes.values()):
        raise RuntimeError("Loaded text parameter dtype evidence is invalid")
    if requested == "bf16":
        allowed = {"torch.bfloat16", "torch.float32"} if adapter else {"torch.bfloat16"}
        if (inference.get("load_dtype") != "torch.bfloat16" or "torch.bfloat16" not in dtypes
                or not set(dtypes) <= allowed):
            raise RuntimeError("BF16 text load has contradictory parameter dtypes")
    elif (inference.get("load_dtype") not in {"torch.bfloat16", "torch.float16"}
          or "torch.uint8" not in dtypes
          or not set(dtypes) <= {"torch.uint8", "torch.bfloat16", "torch.float16", "torch.float32"}):
        raise RuntimeError("NF4 text load has contradictory parameter dtypes")
    return dict(inference)
