"""Temporary dummy bytes and mocked GET only; no app/model imports or live files."""
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest


def module(name):
    spec = importlib.util.spec_from_file_location('prepared_' + name, Path(__file__).with_name(name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    probe = module('cache_missing_probe')
    monkeypatch.setattr(probe, 'ROOT', tmp_path)
    folder = tmp_path / '.local/audio'
    folder.mkdir(parents=True)
    key = 'a' * 64
    source = folder / (key + '.wav')
    source.write_bytes(b'CPU fixture only; not a WAV or speech')
    original = source.read_bytes()
    clip = {'provider': 'windows_sapi_local', 'voice': 'fixture_HEAMI', 'audio_id': key, 'cache_source': 'attached',
            'checksum': hashlib.sha256(original).hexdigest(), 'step_id': 's1', 'audio_url': '/api/lessons/fake/speech/s1/audio?binding=fixture'}
    monkeypatch.setattr(probe, 'quiescent', lambda: None)
    monkeypatch.setattr(probe, 'snapshot', lambda: {'preservation': {p.name: probe.sha(p) for p in folder.iterdir() if p.is_file()}})
    def manifest(_):
        return {'steps': [clip], 'cache_misses': []} if source.exists() else {'steps': [], 'cache_misses': [{'step_id': 's1', 'code': 'cache_missing'}]}
    monkeypatch.setattr(probe, 'require_get', manifest)
    monkeypatch.setattr(probe, 'get', lambda _, binary: (200, source.read_bytes()) if source.exists() else (409, b'missing'))
    out = tmp_path / 'runs/result'
    out.mkdir(parents=True)
    return probe, source, original, out, clip


def test_single_owned_file_restored_and_digest_preserved(prepared):
    probe, source, original, out, _ = prepared
    result = probe.cache_probe('b' * 32, 's1', out)
    assert result['status'] == 'PASS_API_CACHE_MISSING_GUARD'
    assert source.read_bytes() == original
    assert not list(source.parent.glob('*.backup'))
    assert result['preservation_unchanged']


def test_api_error_after_move_restores_before_failure(prepared, monkeypatch):
    probe, source, original, out, _ = prepared
    base = probe.require_get
    def failing(path):
        if not source.exists():
            raise TimeoutError('CPU simulated disconnected API')
        return base(path)
    monkeypatch.setattr(probe, 'require_get', failing)
    with pytest.raises(TimeoutError):
        probe.cache_probe('b' * 32, 's1', out)
    assert source.read_bytes() == original
    journal = json.loads((out / 'result.json').read_text())
    assert journal['status'] == 'FAILED_GUARD_RESTORED' and journal['restored_hash_matches']


def test_unsafe_success_during_missing_is_failure_but_restores(prepared, monkeypatch):
    probe, source, original, out, _ = prepared
    monkeypatch.setattr(probe, 'get', lambda _, binary: (200, original))
    with pytest.raises(RuntimeError, match='safely rejected'):
        probe.cache_probe('b' * 32, 's1', out)
    assert source.read_bytes() == original


def test_reappeared_source_not_overwritten_backup_preserved(prepared, monkeypatch):
    probe, source, original, out, _ = prepared
    base = probe.require_get
    def conflict(path):
        if not source.exists():
            source.write_bytes(b'foreign concurrent file')
        return base(path)
    monkeypatch.setattr(probe, 'require_get', conflict)
    with pytest.raises(RuntimeError, match='Do not overwrite'):
        probe.cache_probe('b' * 32, 's1', out)
    assert source.read_bytes() == b'foreign concurrent file'
    backups = list(source.parent.glob('*.backup'))
    assert len(backups) == 1 and backups[0].read_bytes() == original
    assert json.loads((out / 'result.json').read_text())['status'] == 'RESTORE_BLOCKED_PRESERVE_BACKUP'


def test_scope_escape_rejected(tmp_path):
    probe = module('cache_missing_probe')
    with pytest.raises(ValueError, match='escaped'):
        probe.safe_child(tmp_path / 'audio/../foreign.wav', tmp_path / 'audio')


def test_nonheami_clip_never_moved(prepared):
    probe, source, original, out, clip = prepared
    clip['voice'] = 'Other Windows Voice'
    with pytest.raises(RuntimeError, match='Heami'):
        probe.cache_probe('b' * 32, 's1', out)
    assert source.read_bytes() == original and not list(source.parent.glob('*.backup'))


@pytest.fixture
def identity():
    return {'source': 'worker_metadata', 'model_id': 'Qwen/Qwen3-1.7B', 'revision': 'revision', 'adapter_id': 'base',
            'requested_precision': 'bf16', 'eos_token_ids': [151645, 151643],
            'inference': {'requested_precision': 'bf16', 'actual_is_loaded_in_4bit': False, 'quantization': 'none',
                          'actual_parameter_devices': ['cuda:0'], 'load_dtype': 'torch.bfloat16',
                          'actual_parameter_dtypes_elements': {'torch.bfloat16': 100}}}


def test_exact_bf16_identity(identity):
    audit = module('audit_identity')
    assert all(audit.checks(identity, {'model_id': 'Qwen/Qwen3-1.7B', 'revision': 'revision'}).values())


@pytest.mark.parametrize('mutate', [lambda s: s.update(requested_precision='nf4'),
    lambda s: s['inference'].update(actual_is_loaded_in_4bit=True),
    lambda s: s['inference']['actual_parameter_dtypes_elements'].update({'torch.float32': 1}),
    lambda s: s.update(adapter_id='training1'), lambda s: s.update(eos_token_ids=[151645]),
    lambda s: s.update(eos_token_ids=[151645, 151645]), lambda s: s.update(revision='different')])
def test_actual_identity_mismatch_rejected(identity, mutate):
    audit = module('audit_identity')
    mutate(identity)
    assert not all(audit.checks(identity, {'model_id': 'Qwen/Qwen3-1.7B', 'revision': 'revision'}).values())
