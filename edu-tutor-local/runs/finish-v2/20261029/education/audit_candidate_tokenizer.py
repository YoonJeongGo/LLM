"""Local tokenizer/config audit only. No weights, torch, network or final records."""
from pathlib import Path
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'src'))
os.environ.update(USE_TORCH='0', USE_TF='0', USE_FLAX='0', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
from edu_tutor.models.text_candidate import resolve_candidate, CANDIDATE, MODEL_ID, REVISION
from edu_tutor.training.finish_score import public_item


def main():
    target = Path(__file__).with_name('candidate-tokenizer-audit-v1.json')
    if target.exists():
        raise ValueError('Preserve existing audit; use a new explicit version for changed inputs')
    folder, manifest = resolve_candidate(ROOT, CANDIDATE, 'base', 'nf4')
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(folder, local_files_only=True, trust_remote_code=False)
    generation = json.loads((folder / 'generation_config.json').read_text(encoding='utf-8'))
    assert set(generation['eos_token_id']) == {151645, 151643}
    assert tokenizer.eos_token_id == 151645 and tokenizer.pad_token_id == 151643
    dataset = ROOT / 'runs/finish-v2/20261028/education/development/validation.jsonl'
    records = [json.loads(line) for line in dataset.read_text(encoding='utf-8').splitlines() if line.strip()]
    assert len(records) == 40 and all(r['split'] == 'validation' for r in records)
    checks = []
    for record in records:
        item = public_item(record)
        assert all(m['role'] in {'system', 'user'} for m in item['messages'])
        rendered = tokenizer.apply_chat_template(item['messages'], add_generation_prompt=True, enable_thinking=False, tokenize=False)
        tokens = tokenizer.apply_chat_template(item['messages'], add_generation_prompt=True, enable_thinking=False, tokenize=True)
        assert tokens and len(tokens) + 256 <= 2048
        assert rendered.endswith('<|im_start|>assistant\n')
        assert '<think>' not in rendered and '</think>' not in rendered
        checks.append({'id': item['id'], 'input_tokens': len(tokens), 'output_budget': 256,
                       'rendered_sha256': hashlib.sha256(rendered.encode('utf-8')).hexdigest(),
                       'token_ids_sha256': hashlib.sha256(json.dumps(tokens).encode('ascii')).hexdigest(),
                       'first_token_ids': tokens[:8], 'last_token_ids': tokens[-8:]})
    assert 'torch' not in sys.modules
    output = {'audited_at': datetime.now(timezone.utc).isoformat(), 'mode': 'CPU_tokenizer_only',
              'model_ref': CANDIDATE, 'model_id': MODEL_ID, 'revision': REVISION,
              'model_manifest_sha256': hashlib.sha256((folder / 'model-manifest.json').read_bytes()).hexdigest(),
              'tokenizer_class': type(tokenizer).__name__, 'tokenizer_eos': tokenizer.eos_token_id,
              'tokenizer_pad': tokenizer.pad_token_id, 'generation_eos': generation['eos_token_id'],
              'eos_token_strings': {str(i): tokenizer.convert_ids_to_tokens(i) for i in generation['eos_token_id']},
              'chat_template_sha256': hashlib.sha256(tokenizer.chat_template.encode('utf-8')).hexdigest(),
              'small_file_hashes': {name: hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in
                                  ['tokenizer_config.json', 'tokenizer.json', 'generation_config.json', 'config.json']},
              'validation_dataset_sha256': hashlib.sha256(dataset.read_bytes()).hexdigest(),
              'public_validation_inputs': checks, 'max_input_tokens': max(x['input_tokens'] for x in checks),
              'model_weights_loaded': False, 'torch_imported': False, 'new_generation_calls': 0,
              'final_holdout_read': False, 'network_enabled': False,
              'notice': 'Tokenizer/template/EOS compatibility only, not GPU loading or educational quality. No assistant answer labels are sent to a model.'}
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: output[k] for k in ['mode', 'tokenizer_class', 'generation_eos', 'max_input_tokens', 'model_weights_loaded', 'new_generation_calls']}))


if __name__ == '__main__':
    main()
