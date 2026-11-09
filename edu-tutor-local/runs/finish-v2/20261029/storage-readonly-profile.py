"""One profiled call of current mutable_bytes; no model, mutation or caching."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from edu_tutor.models import budget

original = os.scandir
calls = {}
groups = {}
started = time.perf_counter()
ledger = ROOT / 'runs/phase2/current/resource-budget.json'
ledger_before = hashlib.sha256(ledger.read_bytes()).hexdigest()

def measured(name, callback):
    before = time.perf_counter()
    try:
        return callback()
    finally:
        row = calls.setdefault(name, {'count': 0, 'seconds': 0})
        row['count'] += 1
        row['seconds'] += time.perf_counter() - before

class Entry:
    def __init__(self, entry):
        self.entry = entry
        self.path = entry.path
    def is_dir(self): return measured('is_dir', self.entry.is_dir)
    def is_symlink(self): return measured('is_symlink', self.entry.is_symlink)
    def is_junction(self): return measured('is_junction', self.entry.is_junction)
    def stat(self): return measured('stat', self.entry.stat)

class Entries:
    def __init__(self, directory):
        self.directory = Path(directory)
        relative = self.directory.relative_to(ROOT).parts
        self.group = '/'.join(relative[:2])
        self.iterator = measured('scandir_open', lambda: original(directory))
    def __enter__(self):
        def entries():
            row = groups.setdefault(self.group, {'directories': 0, 'entries': 0, 'enumeration_seconds': 0})
            row['directories'] += 1
            while True:
                if time.perf_counter() - started > 45:
                    raise TimeoutError('Read-only scan profile exceeded 45 seconds')
                before = time.perf_counter()
                try:
                    item = next(self.iterator)
                except StopIteration:
                    return
                finally:
                    row['enumeration_seconds'] += time.perf_counter() - before
                row['entries'] += 1
                yield Entry(item)
        return entries()
    def __exit__(self, *_): self.iterator.close()

before = time.perf_counter()
free = shutil.disk_usage('C:/').free
disk_usage_seconds = time.perf_counter() - before
os.scandir = Entries
try:
    before = time.perf_counter()
    size = budget.mutable_bytes(ROOT)
    scan_seconds = time.perf_counter() - before
finally:
    os.scandir = original
report = {
    'kind': 'single_current_function_read_only_profile',
    'source_sha256': hashlib.sha256((ROOT/'src/edu_tutor/models/budget.py').read_bytes()).hexdigest(),
    'bytes': size, 'scan_seconds_with_instrumentation': scan_seconds,
    'disk_usage_seconds': disk_usage_seconds, 'C_free_bytes': free,
    'method_calls': calls, 'groups': groups,
    'ledger_unchanged': ledger_before == hashlib.sha256(ledger.read_bytes()).hexdigest(),
    'scope': ['runs', '.local'], 'excluded_subtrees': [], 'persistent_size_cache': False,
    'interpretation': 'Instrumentation overhead included. One current scan only, not an optimization comparison or student latency.'}
out = ROOT/'runs/finish-v2/20261029/storage-current-profile-after-J02.json'
with out.open('x', encoding='utf-8') as handle: json.dump(report, handle, ensure_ascii=False, indent=2)
print(json.dumps({key: report[key] for key in ('bytes','scan_seconds_with_instrumentation','disk_usage_seconds','method_calls','ledger_unchanged')}))
print(json.dumps(sorted(groups.items(), key=lambda pair: pair[1]['enumeration_seconds'], reverse=True)[:8]))
