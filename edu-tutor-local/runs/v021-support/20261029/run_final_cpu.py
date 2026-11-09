"""Repeat affected CPU suite after reviewed repairs; no model execution."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
from datetime import datetime,timezone
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).parent
def hashes():
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT/'src/edu_tutor').rglob('*.py'))}
previous=ET.parse(OUT/'cpu-final-v2.xml')
files={ROOT/'tests'/(t.get('classname').split('.')[1]+'.py') for t in previous.iter('testcase')}
files.update((ROOT/'tests').glob('test_v021*.py'))
assert all(p.is_file() for p in files)
name=sys.argv[1]
assert name.replace('-','').isalnum()
log=OUT/(name+'.log'); xml=OUT/(name+'.xml')
assert not log.exists() and not xml.exists()
before=hashes(); start=time.perf_counter()
(OUT/(name+'-source-before.json')).write_text(json.dumps(before,indent=2)+'\n',encoding='utf-8')
env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONUTF8':'0'}
command=[sys.executable,'-m','pytest',*map(str,sorted(files)),'-q','--junitxml='+str(xml),'--basetemp='+str(OUT/(name+'-temp'))]
with log.open('w',encoding='utf-8') as f:
    result=subprocess.run(command,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,env=env)
after=hashes(); suites=ET.parse(xml).getroot()
cases=list(suites.iter('testcase'))
receipt={'at':datetime.now(timezone.utc).isoformat(),'exit_code':result.returncode,
    'elapsed_seconds':time.perf_counter()-start,'tests':len(cases),
    'failures':sum(t.find('failure') is not None for t in cases),
    'errors':sum(t.find('error') is not None for t in cases),
    'source_unchanged':before==after,'file_count':len(files),
    'native_diagnostics':log.read_text(encoding='utf-8').lower().count('windows fatal exception: access violation'),
    'new_model_audio_vision_training_download':0,
    'log':str(log.relative_to(ROOT)),'xml':str(xml.relative_to(ROOT))}
(OUT/(name+'-receipt.json')).write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt),flush=True)
sys.exit(result.returncode if result.returncode else 0 if before==after else 2)
