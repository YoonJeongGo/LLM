"""Synthetic frozen hashes only; do not touch current freezes or model data."""
import importlib.util
import json
from pathlib import Path
import pytest


def module():
    spec = importlib.util.spec_from_file_location('prepared_cross_version', Path(__file__).with_name('cross_version_receipt.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.fixture
def versions(tmp_path):
    value = module()
    paths = tmp_path/'first', tmp_path/'second'
    for i, path in enumerate(paths):
        write(path/'execution-version.json', {'version': path.name, 'authorization_id': 'same-scope',
            'input_sha256': 'same-input', 'source_hashes': {'src/core.py': 'core-unchanged', '.local/policy.json': 'policy',
            'web/dist/app.js': 'built-ui', value.ALLOWED_TEST_CHANGE: 'harness'+str(i)},
            'state': {'model': {'id': 'same-base', 'precision': 'bf16'}, 'speech': {'provider': 'Heami'}}})
    return value, *paths


def test_only_harness_difference_produces_explicit_case_mapping(versions):
    value, first, second = versions
    result = value.compare(first, second)
    assert result['status'] == 'SAME_FROZEN_PRODUCTION_DIFFERENT_TEST_HARNESS'
    assert set(result['different_frozen_files']) == {value.ALLOWED_TEST_CHANGE}
    assert Path(result['case_mapping']['J01']).is_relative_to(first)
    assert Path(result['case_mapping']['J02']).is_relative_to(first)
    assert all(Path(result['case_mapping'][f'J{i:02}']).is_relative_to(second) for i in range(3, 9))


@pytest.mark.parametrize('mutate', [lambda r: r['source_hashes'].update({'src/core.py': 'changed'}),
    lambda r: r['source_hashes'].update({'src/new.py': 'new'}), lambda r: r.update(input_sha256='different-question'),
    lambda r: r['state']['model'].update(precision='nf4'), lambda r: r.update(authorization_id='different-scope')])
def test_production_input_model_or_approval_drift_rejected(versions, mutate):
    value, first, second = versions
    path = second/'execution-version.json'
    data = value.read(path)
    mutate(data)
    write(path, data)
    with pytest.raises(ValueError):
        value.compare(first, second)


def reports(versions, tmp_path):
    value, first, second = versions
    receipt = value.compare(first, second)
    paths = tmp_path/'report1', tmp_path/'report2'
    for index, (version, report) in enumerate(zip((first, second), paths)):
        summary = {'version': version.name, 'frozen_execution': value.read(version/'execution-version.json'),
                   'cases': [], 'question_events': [], 'interruptions': [], 'stage_gaps': []}
        for number in (range(1, 3) if index == 0 else range(3, 9)):
            ident = f'J{number:02}'
            actual = Path(receipt['case_mapping'][ident])
            write(actual, {'version': version.name, 'completed_at': 'CPU-only', 'status': 'CPU_FIXTURE'})
            evidence = report/(ident+'.json')
            write(evidence, {'actual_json': str(actual), 'actual_sha256': value.sha(actual)})
            summary['cases'].append({'id': ident, 'evidence': str(evidence), 'status': 'CPU_FIXTURE'})
            for _ in range(2 if number in {4, 5} else 1):
                summary['question_events'].append({'case': ident, 'first_valid_explanation_ms': None if number == 2 else 1000})
        write(report/'summary.json', summary)
    return value, receipt, paths


def test_merge_preserves_failed_question_denominator_and_original_versions(versions, tmp_path):
    value, receipt, paths = reports(versions, tmp_path)
    result = value.merge(receipt, *paths)
    assert result['latency_denominator'] == len(result['question_events']) == 10
    assert result['question_to_audio']['measured_count'] == 9
    assert result['readiness'] == 'NOT_READY' and result['human_review'] == 'H_PENDING'
    assert [r['source_version'] for r in result['cases']] == ['first', 'first']+['second']*6


def test_merge_rejects_changed_actual_bytes(versions, tmp_path):
    value, receipt, paths = reports(versions, tmp_path)
    Path(receipt['case_mapping']['J04']).write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='artifact/hash differs'):
        value.merge(receipt, *paths)
