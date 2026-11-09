"""Append a no-generation host snapshot under a new named run directory."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import importlib.util
import json
import hashlib

ROOT=Path(__file__).resolve().parents[3]
BASE=Path(__file__).parent

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',required=True)
    parser.add_argument('--server',required=True)
    args=parser.parse_args()
    out=(BASE/args.out).resolve()
    if not out.is_relative_to(BASE) or out==BASE or out.exists():
        raise ValueError('Use a new child directory; do not overwrite evidence')
    spec=importlib.util.spec_from_file_location('probe',BASE/'stability-proposal/cache_missing_probe.py')
    probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
    snapshot=probe.snapshot()
    ledger=probe.read(ROOT/'runs/phase2/current/resource-budget.json')
    students={ident:probe.require_get('/api/sessions/'+ident+'/budget')
        for ident in ledger.get('student_session_budgets',{})}
    budget=probe.require_get('/api/resources/budget')
    jobs=probe.require_get('/api/jobs')
    records={'snapshot.json':snapshot,'budget.json':budget,'student-budgets.json':students,
        'models.json':probe.require_get('/api/models'),'capabilities.json':probe.require_get('/api/capabilities')}
    out.mkdir()
    for name,value in records.items():
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    summary={'at':datetime.now(timezone.utc).isoformat(),'server':args.server,
        'server_process':probe.read(BASE/(args.server+'-process.json')),
        'active_job_count':sum(j['state'] not in probe.TERMINAL for j in jobs),
        'student_sessions':len(students),'closed_sessions':sum(v['state']=='closed' for v in students.values()),
        'closed_sessions_effective_zero':all(v['state']!='closed' or all(x==0 for x in v['effective_remaining'].values()) for v in students.values()),
        'new_model_speech_vision_calls':0,
        'budget_ledger_sha256':hashlib.sha256((ROOT/'runs/phase2/current/resource-budget.json').read_bytes()).hexdigest()}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
