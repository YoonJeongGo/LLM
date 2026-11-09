"""Synthetic DOM/native event records, not actual media or character review."""
import importlib.util
import json
from pathlib import Path
import pytest


@pytest.fixture
def record(tmp_path):
    spec = importlib.util.spec_from_file_location('prepared_gesture', Path(__file__).with_name('audit_gestures.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    media = {'paused': False, 'muted': False, 'volume': 1, 'playbackRate': 1, 'currentTime': 1,
             'duration': 3, 'lesson_id': 'lesson', 'step_id': 's1', 'media_id': 1, 'epoch': 3}
    value = {'id': 'J03', 'version': 'fixture', 'status': 'COMPLETED_CPU_FIXTURE', 'completed_at': 'fixture',
        'responses': [{'value': {'id': 'lesson', 'source_message_id': 'message', 'plan': {'steps': [
            {'id': 's1', 'speech': 'CPU dummy sentence', 'gesture': {'kind': 'write'}}]}}}],
        'scene_samples': [{'type': 'progress', 'at_ms': 1000, 'dom_lesson_record_id': 'lesson', 'dom_step_id': 's1',
                           'caption': 'CPU dummy sentence', 'gesture': 'write', 'media': media}],
        'native_media': [{'type': 'playing', 'at_ms': 900, **media}]}
    return module, tmp_path/'record.json', value


def test_one_actual_matching_kind_is_not_all_three(record):
    module, path, value = record
    path.write_text(json.dumps(value))
    result = module.audit(path)
    assert result['observed_with_native_audio'] == ['write']
    assert result['status'] == 'PARTIAL_GESTURE_EVIDENCE'
    assert result['steps'][0]['status'] == 'PASS_OBSERVED_STEP'


@pytest.mark.parametrize('mutate', [lambda r: r['native_media'][0].update(epoch=2),
    lambda r: r['scene_samples'][0].update(gesture='point'),
    lambda r: r['scene_samples'][0]['media'].update(muted=True)])
def test_wrong_epoch_gesture_or_muted_audio_is_not_observed_match(record, mutate):
    module, path, value = record
    mutate(value)
    path.write_text(json.dumps(value))
    result = module.audit(path)
    assert result['observed_with_native_audio'] == []
    assert result['steps'][0]['status'] == 'NOT_OBSERVED_OR_MISMATCH'
