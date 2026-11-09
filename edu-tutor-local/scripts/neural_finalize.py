"""Read-only preservation, measured GPU comparison and storage audit."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from statistics import mean

from phase2_finalize import inventory
from phase2_snapshot import snapshot

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/neural/current'


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    start = json.loads((OUT / 'preservation-start.json').read_text(encoding='utf-8'))
    checks = {}
    with sqlite3.connect((ROOT / '.local/tutor.sqlite3').as_uri() + '?mode=ro', uri=True) as db:
        for table, expected in start['tables'].items():
            assert table.replace('_', '').isalnum()
            rows = db.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall()
            ids = set(expected['ids'])
            original = [row for row in rows if row[0] in ids]
            digest = hashlib.sha256(json.dumps(original, ensure_ascii=False).encode()).hexdigest()
            checks[table] = {'original_count': expected['count'], 'preserved_count': len(original),
                             'current_count': len(rows), 'unchanged': digest == expected['sha256'], 'sha256': digest}
        jobs = [json.loads(row[0]) for row in db.execute('SELECT payload FROM jobs')]
    checks['releases'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
                          for name, digest in start['preserved_releases'].items()}
    old_jobs = set(start['tables']['jobs']['ids'])
    checks['new_training_jobs'] = [j['id'] for j in jobs if j['id'] not in old_jobs and j.get('kind') in {'training', 'train'}]
    checks['all_original_rows_unchanged'] = all(v['unchanged'] for v in checks.values() if isinstance(v, dict) and 'unchanged' in v)
    write('preservation-final.json', checks)

    rows = []
    raw = {}
    for path in sorted((OUT / 'gpu').glob('*.json')):
        if path.name == 'attempts.json':
            continue
        record = json.loads(path.read_text(encoding='utf-8'))
        if 'request' not in record:
            continue
        meta = record.get('run', {}).get('metadata', {})
        metadata_source = 'live_worker_metadata'
        if not meta and record.get('runtime_records'):
            meta = record['runtime_records'][0].get('redacted_result') or {}
            metadata_source = 'same_run_redacted_worker_result_after_cancel'
        raw[record['name']] = record
        events = [item['event'] for item in record.get('events', [])]
        real = [item for item in events if item.get('source') == 'live_worker']
        structure = next((item['payload'] for item in real if item.get('event_type') == 'structure'), {})
        generated = [token for item in real if item.get('event_type') == 'token' for token in item['payload'].get('token_ids', [])]
        rows.append({'name': record['name'], 'run_id': record.get('run_id'), 'job_id': record.get('job_id'),
                     'question': record['request']['text'], 'mode': record['request']['observation_mode'],
                     'adapter': record['request']['adapter_id'], 'state': record.get('run', {}).get('state'),
                     'output_tokens': meta.get('output_tokens'), 'finish_reason': meta.get('finish_reason'),
                     'load_seconds': meta.get('model_load_seconds'), 'preparation_seconds': meta.get('preparation_seconds'),
                     'generation_seconds': meta.get('generation_seconds'),
                     'tokens_per_second': meta['output_tokens'] / meta['generation_seconds'] if meta.get('generation_seconds') else None,
                     'peak_vram_bytes': meta.get('peak_vram_bytes'), 'peak_reserved_bytes': meta.get('peak_vram_reserved_bytes'),
                     'observer': meta.get('observation'), 'events': dict(Counter(e.get('event_type') for e in events)),
                     'metadata_source': metadata_source,
                     'first_token_seconds': meta.get('first_token_latency_seconds'),
                     'remaining_generation_seconds': meta.get('generation_remaining_seconds'),
                     'layer_count': structure.get('layer_count'), 'hidden_size': structure.get('hidden_size'),
                     'source_sha256': structure.get('forward_evidence', {}).get('sha256'),
                     'request_linkage_matches': all(e.get('run_id') == record.get('run_id') and e.get('request_id') == record['request']['request_id'] and e.get('generation_epoch') == record['request']['generation_epoch'] for e in real),
                     'streamed_token_ids_equal_final_ids': generated == meta.get('output_token_ids') if real and meta.get('output_token_ids') else None,
                     'gpu_elapsed_ms': None, 'timing_kind': 'host_call', 'stream_errors': record.get('stream_errors'),
                     'worker_dropped_events': record.get('run', {}).get('worker_dropped_events'),
                     'buffer_evicted_events': record.get('run', {}).get('dropped_events')})
    pairs = []
    for number in (1, 2):
        off, light = raw.get(f'off-{number}'), raw.get(f'light-{number}')
        if not off or not light:
            continue
        a, b = off['run']['metadata'], light['run']['metadata']
        pairs.append({'pair': number, 'fixed_input_equal': a['input_token_ids'] == b['input_token_ids'],
                      'output_token_ids_equal': a['output_token_ids'] == b['output_token_ids'],
                      'off_generation_seconds': a['generation_seconds'], 'light_generation_seconds': b['generation_seconds'],
                      'generation_change_percent': (b['generation_seconds'] / a['generation_seconds'] - 1) * 100,
                      'implementation_stage': 'original_all_steps' if number == 1 else 'final_aggregated_metadata',
                      'off_first_token_seconds': a.get('first_token_latency_seconds'),
                      'light_first_token_seconds': b.get('first_token_latency_seconds'),
                      'off_remaining_generation_seconds': a.get('generation_remaining_seconds'),
                      'light_remaining_generation_seconds': b.get('generation_remaining_seconds'),
                      'peak_vram_change_bytes': b['peak_vram_bytes'] - a['peak_vram_bytes']})
    performance = {'runs': rows, 'pairs': pairs, 'comparison': 'One original and one final aggregated-metadata cold subprocess pair, greedy decoding, same model/prompt/max_new_tokens=128. Never average across these implementations. Load/preparation separated; no separate warmup run. Host end-to-end generate wall time, not CUDA kernel time.',
                   'warmup': 'No additional warmup inference; first prefill/runtime setup remains in generation timing. Small sample and machine activity limit generalization.',
                   'gpu_training_runs': 0, 'created_at': datetime.now(timezone.utc).isoformat()}
    if pairs:
        final_pairs = [p for p in pairs if p['implementation_stage'] == 'final_aggregated_metadata']
        if not final_pairs:
            final_pairs = pairs
        performance['mean_generation_change_percent'] = (mean(p['light_generation_seconds'] for p in final_pairs) / mean(p['off_generation_seconds'] for p in final_pairs) - 1) * 100
        performance['under_10_percent_target_in_this_sample'] = performance['mean_generation_change_percent'] <= 10
    write('gpu-summary.json', performance)

    previous = json.loads((ROOT / 'runs/phase2/current/storage-final.json').read_text(encoding='utf-8'))
    parts = [inventory(path) for path in sorted(ROOT.iterdir())]
    external = [inventory(item['path']) for item in previous['external_inventory']]
    total = sum(p['bytes'] for p in parts + external)
    storage = {'timestamp': datetime.now(timezone.utc).isoformat(), 'root': str(ROOT), 'data_root': str(ROOT / '.local'),
               'project_parts': parts, 'external_inventory': external, 'conservative_total_bytes': total,
               'shared_attribution': previous['shared_attribution'], 'disk_C': shutil.disk_usage('C:/')._asdict(),
               'disk_D': shutil.disk_usage('D:/')._asdict(), 'F_exists': Path('F:/').exists(),
               'under_50GB': total <= 50_000_000_000, 'warning_40GB': total >= 40_000_000_000,
               'C_free_at_least_50GB': shutil.disk_usage('C:/').free >= 50_000_000_000,
               'inventory_complete': not any(p['errors'] or p['skipped_links'] for p in parts + external)}
    write('storage-final.json', storage)
    write('source-final.json', snapshot(ROOT))
    print(json.dumps({'preserved': checks['all_original_rows_unchanged'], 'releases_preserved': all(checks['releases'].values()),
                      'new_training_jobs': checks['new_training_jobs'], 'gpu_attempts_recorded': len(rows),
                      'storage_GB': total / 1e9, 'C_free_GB': storage['disk_C']['free'] / 1e9,
                      'mean_generation_change_percent': performance.get('mean_generation_change_percent')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
