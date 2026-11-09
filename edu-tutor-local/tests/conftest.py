"""Shared CPU seam fixtures; these metadata values are not device evidence."""
import pytest


@pytest.fixture
def nf4_inference_fixture():
    return {"fixture_only": True, "requested_precision": "nf4", "quantization": "nf4_double",
            "load_dtype": "torch.bfloat16", "actual_is_loaded_in_4bit": True,
            "actual_parameter_devices": ["cuda:0"],
            "actual_parameter_dtypes_elements": {"torch.bfloat16": 10, "torch.uint8": 10}}
