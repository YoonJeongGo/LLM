"""One bounded, no-model regression set covering the changed execution paths."""
import argparse, hashlib, json, subprocess, sys, time
from pathlib import Path
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
p = argparse.ArgumentParser()
p.add_argument('name')
a = p.parse_args()
dest = OUT / a.name
assert dest.is_relative_to(OUT) and not dest.exists(), 'Preserve previous test results'
dest.mkdir()
old = ET.parse(ROOT/'runs/v021-support/20261029/cpu-final-r3-v1.xml')
files = {n.attrib['classname'].replace('.', '/')+'.py' for n in old.iter('testcase')}
files.update('tests/'+name+'.py' for name in [
    'test_partial_persistence','test_partial_persistence_failures',
    'test_v021r3_explanation_repair','test_v021r3_explanation_api',
    'test_runtime_cancellation_ownership','test_text_residency','test_text_dispatch',
    'test_storage_scan','test_student_budget_api','test_student_budget_cpu',
    'test_runtime_contract','test_speech_cache_replay','test_scoped_lesson_execution',
])
assert all((ROOT/f).is_file() for f in files)
def sources():
    return {str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest()
        for x in (ROOT/'src/edu_tutor').rglob('*') if x.suffix in {'.py','.ps1'}}
before = sources()
command = [sys.executable,'-X','utf8','-m','pytest','-q','-m','not gpu and not tiny',
           *sorted(files),'--basetemp='+str(dest/'tmp'),'--junitxml='+str(dest/'junit.xml')]
(dest/'command.json').write_text(json.dumps(command,indent=2),encoding='utf-8')
started=time.perf_counter()
with (dest/'pytest.log').open('w',encoding='utf-8') as log:
    result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
tests=ET.parse(dest/'junit.xml').getroot() if (dest/'junit.xml').exists() else None
log=(dest/'pytest.log').read_text(encoding='utf-8')
receipt={'at':datetime.now(timezone.utc).isoformat(),'exit_code':result.returncode,
    'elapsed_seconds':time.perf_counter()-started,'file_count':len(files),'files':sorted(files),
    'tests':len(list(tests.iter('testcase'))) if tests is not None else None,
    'failures':len(list(tests.iter('failure'))) if tests is not None else None,
    'errors':len(list(tests.iter('error'))) if tests is not None else None,
    'native_diagnostics':sum(log.lower().count(s) for s in ['fatal python error','windows fatal exception']),
    'production_sources_unchanged':before==sources(),'production_hashes':before,
    'new_model_audio_vision_training_download':0}
(dest/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k not in {'files','production_hashes'}}))
sys.exit(result.returncode if before==sources() else 2)
