"""Read-only baseline/final audit for no-generation latency work."""
import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/student-latency/20261027'
TABLES = ('sessions','messages','jobs','documents','chunks','photos','lessons','datasets','audit','evaluation_reviews')
MUTABLE_EVIDENCE = 'runs/student-experience/20261027/index.html'

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def snapshot():
    files = {}
    for part in ('runs/student-experience', 'runs/neural', 'runs/phase2', 'release', 'src/edu_tutor/neural', 'web/src/NeuralView.tsx', 'web/src/neuralEvents.ts'):
        base = ROOT / part
        paths = [base] if base.is_file() else base.rglob('*')
        for p in paths:
            if p.is_file() and '__pycache__' not in p.parts:
                files[p.relative_to(ROOT).as_posix()] = digest(p)
    for name in ('.local/phase2-policy.json',):
        files[name] = digest(ROOT/name)
    tables = {}
    with sqlite3.connect((ROOT/'.local/tutor.sqlite3').as_uri()+'?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        for table in TABLES:
            rows = db.execute(f'SELECT * FROM {table} ORDER BY id').fetchall()
            encoded = json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode('utf-8')
            tables[table] = {'rows':len(rows),'sha256':hashlib.sha256(encoded).hexdigest()}
    ledger = json.loads((ROOT/'runs/phase2/current/resource-budget.json').read_text(encoding='utf-8'))
    counts = {'requests':len(ledger['requests']), 'seconds':sum(r['charged_seconds'] for r in ledger['requests']),
              'audio':sum(r['new_audio_clips'] for r in ledger['requests']), 'vision':sum(r['vision_requests'] for r in ledger['requests']),
              'reserved':sum(r['status']=='reserved' for r in ledger['requests'])}
    models = {}
    for p in (ROOT/'.local/models').rglob('*'):
        if p.is_file():
            st=p.stat();models[p.relative_to(ROOT).as_posix()]={'bytes':st.st_size,'mtime_ns':st.st_mtime_ns}
    return {'at':datetime.now(timezone.utc).isoformat(),'files':files,'database':tables,'budget':counts,'model_file_metadata':models}

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('before','after'));args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    report=snapshot()
    if args.mode=='before':
        path=OUT/'preservation-before.json'
        if path.exists():raise SystemExit('Baseline exists; never overwrite it.')
        for name in ('STATUS.json','HANDOFF.md','docs/STUDENT_EXPERIENCE.md',MUTABLE_EVIDENCE):
            (OUT/('before-'+Path(name).name)).write_bytes((ROOT/name).read_bytes())
    else:
        path=OUT/'preservation-after.json'
        old=json.loads((OUT/'preservation-before.json').read_text(encoding='utf-8'))
        changed=[n for n,h in old['files'].items() if report['files'].get(n)!=h]
        report['comparison']={'old_file_count':len(old['files']),'changed':changed,'allowed_existing_gallery_change_only':all(n==MUTABLE_EVIDENCE for n in changed),
            'database_exactly_unchanged':report['database']==old['database'],'budget_exactly_unchanged':report['budget']==old['budget'],
            'models_metadata_unchanged':report['model_file_metadata']==old['model_file_metadata'],
            'gallery_original_backup_matches':digest(OUT/'before-index.html')==old['files'][MUTABLE_EVIDENCE]}
        report['status']='PASS' if all(v for v in report['comparison'].values() if isinstance(v,bool)) else 'REVIEW_REQUIRED'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'path':str(path),'status':report.get('status','BASELINE_SAVED'),'files':len(report['files']),'rows':sum(t['rows'] for t in report['database'].values()),'budget':report['budget'],'comparison':report.get('comparison')},ensure_ascii=False))
