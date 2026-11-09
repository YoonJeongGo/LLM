"""Distinguish SQLite validity, bounded parser support and educational purpose."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT/'src'))
from edu_tutor.problems.ddl_examples import build_ddl_example
from edu_tutor.lessons.concepts import checked_concept_plan
import sqlglot

source_path = ROOT/'runs/finish-v2/20261029/stored-j02-actual-repair/result.json'
source_bytes = source_path.read_bytes()
source = json.loads(source_bytes)
attempt = source['new_lesson']['generation']['example_model_attempts'][1]
raw = attempt['text']
match = re.fullmatch(r'```sql\s*\n(.*?)\n```', raw, re.S)
assert match
sql = match[1]
assert len(sql) < 8000
db = sqlite3.connect(':memory:')
db.set_progress_handler(lambda: 1, 20000)
db.set_authorizer(lambda action,*args: sqlite3.SQLITE_DENY if action in {
    sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH} else sqlite3.SQLITE_OK)
db.executescript(sql)
columns = [row[1] for row in db.execute('PRAGMA table_info(books)').fetchall()]
rows = [list(row) for row in db.execute('SELECT * FROM books').fetchall()]
assert columns == ['title','author','year','genre']
assert rows == [['1984','George Orwell',1949,'Fiction']]
db.close()

# An exact local diagnostic derivative, never written to a source message or
# sent to the app. The already-inspected three lines have trailing comments;
# no SQL literal contains '--'. Preserve the original raw input separately.
without_comments = '\n'.join(line.split('--',1)[0].rstrip() for line in sql.splitlines())
assert "'--" not in sql and '"--' not in sql
derived_raw = '```sql\n' + without_comments + '\n```'
raw_report = build_ddl_example(raw)
derived_report = build_ddl_example(derived_raw)
assert raw_report['status'] == 'blocked'
assert derived_report['status'] == 'verified'
message = deepcopy(source['source_message'])
message['content'] = derived_raw
message['raw_model_response'] = derived_raw
question = source['source_lesson']['plan']['question_text']
checked = checked_concept_plan(message,question,'cpu-j02-comment-diagnostic',
    required_operations=('add_column','update_values'))
assert checked['status']=='verification_stopped'
assert checked['pedagogic_evidence']['missing_operations']==['add_column']
assert checked['speech_allowed'] is False

trace_db = sqlite3.connect(':memory:')
trace = []
buffer = ''
for line in sql.splitlines(keepends=True):
    buffer += line
    if sqlite3.complete_statement(buffer):
        before = [list(row) for row in trace_db.execute('SELECT * FROM books').fetchall()] if trace else []
        trace_db.execute(buffer)
        after = [list(row) for row in trace_db.execute('SELECT * FROM books').fetchall()]
        trace.append({'sql_with_original_comments':buffer,'before':before,'after':after})
        buffer = ''
assert not buffer.strip()
trace_db.close()
assert len(trace)==3
assert trace[1]['after']==[['1984','George Orwell',1949,None]]
assert trace[2]['after']==rows
assert source_path.read_bytes()==source_bytes

out = ROOT/'runs/finish-v2/20261029/education/old-j02-repair-sql-cpu.json'
assert not out.exists()
report = {'at':datetime.now(timezone.utc).isoformat(),
    'scope':'CPU diagnostic only; no production parser extension, no model, no source-record mutation',
    'source':source_path.relative_to(ROOT).as_posix(),'source_sha256':hashlib.sha256(source_bytes).hexdigest(),
    'raw_model_text_preserved':raw,'raw_sql_exact':sql,'sqlite_version':sqlite3.sqlite_version,
    'raw_sql_executes_in_sqlite':True,'database':':memory:','sqlite_columns':columns,'sqlite_rows':rows,
    'original_comment_statement_trace':trace,
    'sqlglot_ast_types_with_comments':[type(node).__name__ for node in sqlglot.parse(sql,read='sqlite') if node is not None],
    'bounded_parser_original':{'status':raw_report['status'],'reason':raw_report.get('reason')},
    'diagnostic_only_comment_removed_sql':without_comments,
    'bounded_parser_without_comments':{'status':derived_report['status'],'operations':[s['operation'] for s in derived_report['steps']]},
    'educational_check_without_comments':checked['pedagogic_evidence'],
    'conclusion':'The repair SQL is valid SQLite including its comments and changes one stored cell. The current bounded parser rejects its comment-only AST node. Removing comments only for diagnosis still fails the required ALTER/add_column comparison: putting genre directly in CREATE does not demonstrate adding a column to an existing table.',
    'new_model_calls':0,'new_tts':0,'production_files_changed':0,'final80_opened':False,
    'human_review':'H_PENDING',
    'source_code_hashes':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in [
        'src/edu_tutor/problems/ddl_examples.py','src/edu_tutor/lessons/concepts.py','src/edu_tutor/lessons/verified.py']}}
out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'artifact':out.relative_to(ROOT).as_posix(),'raw_sqlite':'PASS','bounded_original':raw_report['status'],
    'bounded_diagnostic_without_comments':derived_report['status'],'pedagogic_missing':checked['pedagogic_evidence']['missing_operations'],
    'ast_types':report['sqlglot_ast_types_with_comments'],'model_calls':0},ensure_ascii=False,indent=2))
