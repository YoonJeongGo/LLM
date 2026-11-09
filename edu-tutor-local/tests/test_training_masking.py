from pathlib import Path
import pytest

from edu_tutor.training.masking import ResponseOnlyCollator, encode_response_only


class SyntheticTokenizer:
    """Explicit fixture; does not prove the real Qwen chat template."""
    eos_token_id = 1
    pad_token_id = 1

    def apply_chat_template(self, messages, tokenize, add_generation_prompt, enable_thinking):
        assert enable_thinking is False
        prefix = [2] + [ord(c) % 100 + 3 for c in messages[0]["content"]] + [104]
        if add_generation_prompt:
            return prefix
        return prefix + [ord(c) % 100 + 3 for c in messages[-1]["content"]] + [1]

    def decode(self, ids, skip_special_tokens=False):
        return ",".join(str(i) for i in ids)


def test_target_boundary_uses_position_and_preserves_eos_when_pad_matches():
    torch = pytest.importorskip("torch")
    tokenizer = SyntheticTokenizer()
    first = encode_response_only(tokenizer, [{"role":"user","content":"duplicate answer"},{"role":"assistant","content":"answer"}])
    second = encode_response_only(tokenizer, [{"role":"user","content":"x"},{"role":"assistant","content":"y"}])
    batch = ResponseOnlyCollator(tokenizer.pad_token_id)([first, second])
    for i, feature in enumerate((first, second)):
        start, end = feature["audit"]["prefix_length"], len(feature["input_ids"])
        assert torch.all(batch["labels"][i,:start] == -100)
        assert batch["labels"][i,end-1].item() == tokenizer.eos_token_id
        assert torch.all(batch["labels"][i,end:] == -100)
        assert torch.all(batch["attention_mask"][i,end:] == 0)
        assert torch.equal(batch["labels"][i,start:end], batch["input_ids"][i,start:end])


def test_empty_and_overlong_answer_are_not_silently_truncated():
    tokenizer = SyntheticTokenizer()
    with pytest.raises(ValueError, match="Empty"):
        encode_response_only(tokenizer, [{"role":"user","content":"x"},{"role":"assistant","content":" "}])
    with pytest.raises(ValueError, match="truncated"):
        encode_response_only(tokenizer, [{"role":"user","content":"x"},{"role":"assistant","content":"y"*20}], max_length=10)


def test_unstable_template_prefix_is_rejected():
    class Unstable(SyntheticTokenizer):
        def apply_chat_template(self, *args, **kwargs):
            result = super().apply_chat_template(*args, **kwargs)
            if kwargs["add_generation_prompt"]:
                result[-1] = 105
            return result
    with pytest.raises(ValueError, match="prefix"):
        encode_response_only(Unstable(), [{"role":"user","content":"x"},{"role":"assistant","content":"y"}])


def test_all_masked_batch_is_rejected():
    pytest.importorskip("torch")
    with pytest.raises(ValueError, match="No response"):
        ResponseOnlyCollator(1)([{"input_ids":[2,1],"attention_mask":[1,1],"labels":[-100,-100]}])


def test_actual_pinned_qwen_template_all_data(tmp_path):
    transformers = pytest.importorskip("transformers")
    from edu_tutor.training.data import load_records
    root = Path(__file__).resolve().parents[1]
    model_path = root / ".local/models/text"
    if not (model_path / "tokenizer.json").is_file():
        pytest.skip("Actual Qwen tokenizer not cached; synthetic fixtures only")
    tokenizer = transformers.AutoTokenizer.from_pretrained(model_path, local_files_only=True, trust_remote_code=False)
    for record in load_records(sorted((root / "data/demo").glob("*.jsonl"))):
        value = encode_response_only(tokenizer, record["messages"])
        assert value["audit"]["target_tokens"] > 1
        assert "<|im_end|>" in value["audit"]["target_decode"]
        assert "<think>" not in value["audit"]["target_decode"]


@pytest.mark.tiny
def test_real_cpu_tiny_lora_updates_freezes_and_reloads(tmp_path):
    pytest.importorskip("torch")
    pytest.importorskip("peft")
    from edu_tutor.training.tiny import tiny_lora_smoke
    result = tiny_lora_smoke(tmp_path / "tiny")
    assert result["status"] == "passed"
    assert result["optimizer_steps"] == 3
    assert result["frozen_base_unchanged"]
    assert result["reload_logits_max_abs_diff"] <= 1e-6
