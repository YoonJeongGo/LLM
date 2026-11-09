"""Preserved six cases replay, now development regression after disclosure."""
import difflib
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime,timezone

out=Path(__file__).resolve().parent;root=out.parents[4]
relative='src/edu_tutor/problems/intent_language.py'
prior_path=root/'runs/v021-r3-repair/20261030/student/repair-development-final03/execution-version.json'
prior=json.loads(prior_path.read_text(encoding='utf-8-sig'))
before=out/'source-final03'/relative
assert hashlib.sha256(before.read_bytes()).hexdigest()==prior['source_hashes'][relative]
current=dict(prior['source_hashes'])
current[relative]=hashlib.sha256((root/relative).read_bytes()).hexdigest()
for name,expected in current.items():
    if name.startswith('src/edu_tutor/') and name.endswith('.py'):
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected,name
manifest={'purpose':'CPU candidate source manifest, not actual deployment or independent evaluation',
    'created_at':datetime.now(timezone.utc).isoformat(),'source_hashes':current,'prior_deployment_manifest':str(prior_path)}
manifest_path=out/'c04-cpu-candidate-source.json'
assert not manifest_path.exists()
manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
patch=''.join(difflib.unified_diff(before.read_text(encoding='utf-8').splitlines(True),
    (root/relative).read_text(encoding='utf-8').splitlines(True),fromfile='a/'+relative,tofile='b/'+relative))
(out/'c04-classification.patch').write_text(patch,encoding='utf-8')
destination=out/'c04-six-development-replay.json'
subprocess.run([sys.executable,str(root/'runs/v021-r3-repair/20261030/evaluation/run_cpu_boundaries.py'),
    '--product-freeze',str(manifest_path),'--ack-frozen-build','--output',str(destination)],check=True,cwd=root)
result=json.loads(destination.read_text(encoding='utf-8'))
assert result['counts']=={'planned':6,'pass':6,'failure':0,'setup_or_error':0},result['counts']
print(json.dumps({'source_sha256':current[relative],'development_counts':result['counts'],'old_failure_preserved':True}))
