"""GET-only, no-generation deployment and preservation snapshot."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,importlib.util
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).parent
parser=argparse.ArgumentParser()
parser.add_argument('name')
args=parser.parse_args()
target=OUT/args.name
assert target.is_relative_to(OUT) and not target.exists()
spec=importlib.util.spec_from_file_location('prior_probe',ROOT/'runs/finish-v2/20261029/stability-proposal/cache_missing_probe.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
snap=m.snapshot()
jobs=m.require_get('/api/jobs')
budget=m.require_get('/api/resources/budget')
target.mkdir()
values={'snapshot.json':snap,'budget.json':budget,'models.json':m.require_get('/api/models'),
'capabilities.json':m.require_get('/api/capabilities'),'health.json':m.require_get('/api/health')}
for key,value in values.items():
    (target/key).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
summary={'at':datetime.now(timezone.utc).isoformat(),'name':args.name,'active_job_count':sum(j['state'] not in m.TERMINAL for j in jobs),
'ledger_sha256':hashlib.sha256((ROOT/'runs/phase2/current/resource-budget.json').read_bytes()).hexdigest(),
'version':values['health.json']['version'],'model_audio_vision_training_download':0}
(target/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary))

