"""Read-only G07 evidence: actual DOM gestures while bound native audio plays."""
import argparse
import hashlib
import json
from pathlib import Path


def audit(path):
    record = json.loads(path.read_text(encoding='utf-8'))
    if record.get('status') == 'RUNNING' or not record.get('completed_at'):
        raise ValueError('Only a completed browser attempt may be audited')
    lessons = {}
    def visit(value):
        if isinstance(value, dict):
            if value.get('source_message_id') and value.get('id') and isinstance(value.get('plan'), dict):
                lessons[value['id']] = value
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(record.get('responses', []))
    steps, observed = [], set()
    for lesson_id, lesson in lessons.items():
        for step in lesson['plan']['steps']:
            expected = step.get('gesture', {}).get('kind')
            samples = []
            for sample in record.get('scene_samples', []):
                media = sample.get('media') or {}
                if not (sample.get('type') == 'progress' and media.get('paused') is False
                        and media.get('muted') is False and media.get('volume', 0) > 0 and media.get('playbackRate') == 1
                        and 0 < media.get('currentTime', 0) < media.get('duration', 0)
                        and sample.get('dom_lesson_record_id') == lesson_id == media.get('lesson_id')
                        and sample.get('dom_step_id') == step['id'] == media.get('step_id')
                        and sample.get('caption') == step['speech']):
                    continue
                start = next((event for event in record.get('native_media', []) if event.get('type') == 'playing'
                    and event.get('media_id') == media.get('media_id') and event.get('epoch') == media.get('epoch')
                    and event.get('lesson_id') == lesson_id and event.get('step_id') == step['id']
                    and event.get('at_ms', float('inf')) <= sample['at_ms']), None)
                if not start:
                    continue
                samples.append({'at_ms': sample['at_ms'], 'media_id': media['media_id'], 'epoch': media['epoch'],
                                'current_time': media['currentTime'], 'actual_dom_gesture': sample.get('gesture'),
                                'matches_plan': sample.get('gesture') == expected})
                if sample.get('gesture') == expected:
                    observed.add(expected)
            steps.append({'lesson_id': lesson_id, 'step_id': step['id'], 'planned_gesture': expected,
                          'status': 'PASS_OBSERVED_STEP' if samples and all(s['matches_plan'] for s in samples) else 'NOT_OBSERVED_OR_MISMATCH',
                          'samples': samples})
    required = {'write', 'point', 'explain'}
    return {'case': record['id'], 'version': record['version'], 'source_actual_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'steps': steps, 'observed_with_native_audio': sorted(observed), 'required_types_not_observed': sorted(required - observed),
            'status': 'PASS_ALL_THREE_OBSERVED' if steps and all(s['status'] == 'PASS_OBSERVED_STEP' for s in steps) and required <= observed
                else 'PARTIAL_GESTURE_EVIDENCE',
            'boundary': 'Gesture TYPE only: DOM + same native media/lesson/step/epoch/caption evidence. Does not establish hand-to-glyph position (G09); a broad element container can differ from actual KaTeX glyphs. Combine with collector WAV/Blob proof. No physical listening or educational review.',
            'model_calls': 0, 'human_review': 'H_PENDING'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--actual', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Preserve prior audit; choose a new output')
    result = audit(args.actual)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('case', 'status', 'observed_with_native_audio', 'required_types_not_observed')}))
