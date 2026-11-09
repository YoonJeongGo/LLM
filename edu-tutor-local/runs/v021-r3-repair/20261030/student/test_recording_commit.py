"""Saved-file gate fixtures only; no DB, model or browser."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import pytest

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
spec=importlib.util.spec_from_file_location('collector_commit_fixture',BASE/'collect_journeys.py')
collector=importlib.util.module_from_spec(spec);spec.loader.exec_module(collector)

def fixture(tmp_path):
    path=tmp_path/'actual.json'
    record={'recording_mode':'incremental_worker_journal_v1','status':'COMPLETED'}
    path.write_text(json.dumps(record),encoding='utf-8')
    receipt={'type':'finalized','commit_complete':True,'recording_mode':record['recording_mode'],'revision':2,
             'actual_path':str(path),'journal_path':str(path)+'.journal.jsonl',
             'final_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'final_bytes':path.stat().st_size}
    Path(str(path)+'.writer.json').write_text(json.dumps(receipt),encoding='utf-8')
    Path(str(path)+'.journal.jsonl').write_text(json.dumps(receipt)+'\n',encoding='utf-8')
    return path,record,receipt

def test_legacy_record_does_not_require_new_receipt(tmp_path):
    assert collector.recording_commit(tmp_path/'historical.json',{})['mode']=='legacy_full_snapshot'

def test_exact_receipt_and_marker_accept_complete_saved_file(tmp_path):
    path,record,_=fixture(tmp_path)
    assert collector.recording_commit(path,record)['commit_gate']=='verified'

@pytest.mark.parametrize('failure',['missing_receipt','partial_marker','hash_mismatch','marker_mismatch','false_commit','foreign_path'])
def test_completed_looking_file_cannot_bypass_commit_gate(tmp_path,failure):
    path,record,receipt=fixture(tmp_path)
    target=Path(str(path)+'.writer.json')
    if failure=='missing_receipt':target.unlink()
    elif failure=='partial_marker':Path(str(path)+'.journal.jsonl').write_text('{"type":',encoding='utf-8')
    elif failure=='hash_mismatch':path.write_text(json.dumps({**record,'changed':True}),encoding='utf-8')
    elif failure=='marker_mismatch':target.write_text(json.dumps({**receipt,'revision':3}),encoding='utf-8')
    else:
        receipt['commit_complete' if failure=='false_commit' else 'actual_path']=False if failure=='false_commit' else str(tmp_path/'other.json')
        target.write_text(json.dumps(receipt),encoding='utf-8')
        Path(str(path)+'.journal.jsonl').write_text(json.dumps(receipt)+'\n',encoding='utf-8')
    with pytest.raises(ValueError,match='INCOMPLETE_WRITER_COMMIT'):
        collector.recording_commit(path,record)

def test_real_worker_fixture_failed_receipt_is_not_accepted():
    # Result produced by test_evidence_writer's intentional receipt collision.
    paths=sorted((BASE.parent/'logger-repair/tests').glob('run-*/uncommitted.json'))
    assert paths
    path=paths[-1]
    with pytest.raises(ValueError,match='INCOMPLETE_WRITER_COMMIT'):
        collector.recording_commit(path,json.loads(path.read_text(encoding='utf-8')))
