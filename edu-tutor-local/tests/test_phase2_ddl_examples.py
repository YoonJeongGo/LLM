"""A real, tiny SQLite run; these are fixture defenses, not model inference."""
from pathlib import Path

import pytest

from edu_tutor.problems.ddl_examples import build_ddl_example


def example(sql):
    return build_ddl_example('모델이 쓴 설명용 예시\n```sql\n'+sql+'\n```')


def test_create_insert_alter_drop_share_actual_before_after_cells():
    result=example("CREATE TABLE learners (name TEXT, score INTEGER);\n"
        "INSERT INTO learners VALUES ('Kim',80),('Yu',NULL);\n"
        "ALTER TABLE learners ADD COLUMN phone TEXT;\nDROP TABLE learners;")
    assert result['status']=='verified'
    create,insert,alter,drop=result['steps']
    assert create['before']==[] and create['after'][0]['rows']==[]
    assert insert['after'][0]['rows']==[['Kim',80],['Yu',None]]
    assert insert['effects']['columns_before']==insert['effects']['columns_after']==2
    assert alter['effects']['rows_before']==alter['effects']['rows_after']==2
    assert alter['after'][0]['rows']==[['Kim',80,None],['Yu',None,None]]
    assert alter['after'][0]['columns']==['name','score','phone']
    assert alter['before'][0]['id']==alter['after'][0]['id']
    assert alter['before'][0]['row_ids']==alter['after'][0]['row_ids']
    assert alter['before'][0]['cell_ids'][0]==alter['after'][0]['cell_ids'][0][:2]
    assert drop['after']==[] and drop['effects']['table_count_before']==1
    assert all(step['label']=='설명용 새 예시' for step in result['steps'])
    assert result['free_prose_verification']=='not_verified' and result['human_review']=='not_reviewed'


def test_insert_explicit_columns_quoted_literals_and_negative_numbers():
    result=example("CREATE TABLE people (name TEXT, score REAL); INSERT INTO people (score,name) VALUES (-2.5,'O''Brien');")
    assert result['status']=='verified'
    assert result['steps'][-1]['after'][0]['rows']==[["O'Brien",-2.5]]


@pytest.mark.parametrize('unsafe',[
    "ATTACH DATABASE 'escape.sqlite3' AS external;",
    "PRAGMA writable_schema=ON;",
    "SELECT load_extension('evil');",
    "CREATE TABLE x AS SELECT 1;",
    "CREATE VIRTUAL TABLE x USING fts5(text);",
    "CREATE TABLE x (v TEXT DEFAULT (randomblob(1000000000)));",
    "CREATE TABLE x (v TEXT); INSERT INTO x VALUES (readfile('secret.txt'));",
    "CREATE TABLE x (v TEXT); INSERT INTO x SELECT 'unsafe';",
    "CREATE TABLE main.x (v TEXT);",
    "CREATE TABLE x (v TEXT); ALTER TABLE x RENAME TO y;",
    "CREATE TABLE sqlite_secret (v TEXT);",
    "CREATE TABLE x (v TEXT); DELETE FROM x;",
    "CREATE TABLE x (v TEXT); INSERT INTO x VALUES ('ok'); DROP TABLE x; SELECT * FROM sqlite_master;",
])
def test_unsupported_or_malicious_sql_is_rejected_before_any_execution(unsafe):
    result=example(unsafe)
    assert result['status']=='blocked'
    assert result['steps']==[]
    assert result['partial_steps_audit_only']==[]


def test_literal_that_looks_like_sql_remains_data(tmp_path, monkeypatch):
    target=tmp_path/'should-not-exist.sqlite3'
    monkeypatch.chdir(tmp_path)
    payload="'); ATTACH DATABASE 'should-not-exist.sqlite3' AS stolen; --"
    literal="'"+payload.replace("'","''")+"'"
    result=example('CREATE TABLE notes (body TEXT); INSERT INTO notes VALUES ('+literal+');')
    assert result['status']=='verified'
    assert result['steps'][-1]['after'][0]['rows']==[[payload]]
    assert not target.exists()


def test_no_model_sql_never_invents_a_verified_example():
    result=build_ddl_example('DDL은 구조를 바꾸는 명령입니다. INSERT는 행을 추가합니다.')
    assert result['status']=='not_available' and result['steps']==[]
    assert result['execution']['status']=='not_run'


def test_failed_statement_does_not_publish_partial_teaching_plan():
    result=example('CREATE TABLE x (v INTEGER); INSERT INTO absent VALUES (1);')
    assert result['status']=='blocked' and result['steps']==[]
    assert len(result['partial_steps_audit_only'])==1


def test_cumulative_rows_columns_and_statement_caps():
    rows=','.join('('+str(i)+')' for i in range(20))
    assert example('CREATE TABLE x (v INTEGER); INSERT INTO x VALUES '+rows+'; INSERT INTO x VALUES (21);')['status']=='blocked'
    columns=','.join('v'+str(i)+' TEXT' for i in range(8))
    assert example('CREATE TABLE x ('+columns+'); ALTER TABLE x ADD COLUMN excess TEXT;')['status']=='blocked'
    assert example(';'.join('CREATE TABLE x'+str(i)+'(v TEXT)' for i in range(9)))['status']=='blocked'


def test_multiple_sql_blocks_are_one_ordered_example():
    raw='```sql\nCREATE TABLE x (v INTEGER);\n```\n행을 추가합니다.\n```sql\nINSERT INTO x VALUES (7);\n```'
    result=build_ddl_example(raw)
    assert result['status']=='verified' and result['steps'][-1]['after'][0]['rows']==[[7]]


def test_bare_fence_example_is_executed_and_mixed_fences_keep_order():
    raw="설명용 새 예시\n```\nCREATE TABLE people (name TEXT);\n```\n행 추가\n```sql\nINSERT INTO people VALUES ('Alice');\n```\n열 추가\n```\nALTER TABLE people ADD COLUMN score INTEGER;\n```"
    result=build_ddl_example(raw)
    assert result['status']=='verified' and len(result['source_sql_blocks'])==3
    assert [s['operation'] for s in result['steps']]==['create_table','insert_rows','add_column']
    assert result['steps'][-1]['after'][0]['rows']==[['Alice',None]]


@pytest.mark.parametrize('raw',[
    "```\nCREATE TABLE x (v INTEGER;\n```",
    "```\nCREATE TABLE x (v INTEGER); ATTACH DATABASE 'escape.sqlite3' AS external;\n```",
    "```\nCREATE TABLE x (v INTEGER);",
])
def test_malformed_or_unsafe_bare_sql_fence_is_blocked_not_missing(raw):
    result=build_ddl_example(raw)
    assert result['status']=='blocked' and result['steps']==[]
    assert result['partial_steps_audit_only']==[]


def test_non_sql_bare_code_is_not_invented_as_an_example():
    assert build_ddl_example('```\n행을 추가하는 의사 코드\n```')['status']=='not_available'


def test_simple_create_constraints_are_preserved_and_enforced_by_disposable_sqlite():
    result=example("CREATE TABLE students (id INTEGER PRIMARY KEY, name TEXT NOT NULL, age INTEGER DEFAULT 18);"
        "INSERT INTO students (id,name) VALUES (7,'새 예시');")
    assert result['status']=='verified'
    create,insert=result['steps']
    assert '"id" INTEGER PRIMARY KEY' in create['sql']
    assert '"name" TEXT NOT NULL' in create['sql']
    assert '"age" INTEGER DEFAULT 18' in create['sql']
    assert insert['after'][0]['rows']==[[7,'새 예시',18]]
    metadata={c['name']:c for c in create['after'][0]['column_constraints']}
    assert metadata['id']['primary_key_position']==1 and metadata['name']['not_null']
    assert metadata['age']['default_sql']=='18'
    assert result['execution']['database']==':memory:' and result['human_review']=='not_reviewed'
    assert result['free_prose_verification']=='not_verified'


@pytest.mark.parametrize('inserts',[
    "INSERT INTO students (id,name) VALUES (1,NULL);",
    "INSERT INTO students (id,name) VALUES (1,'가'),(1,'나');",
])
def test_new_constraints_are_not_silently_discarded_when_insert_violates_them(inserts):
    result=example("CREATE TABLE students (id INTEGER PRIMARY KEY, name TEXT NOT NULL, age INTEGER DEFAULT 18);"+inserts)
    assert result['status']=='blocked' and result['steps']==[]
    assert len(result['partial_steps_audit_only'])==1


@pytest.mark.parametrize('definition',[
    "v INTEGER DEFAULT (1+2)","v INTEGER DEFAULT (1)","v INTEGER DEFAULT CURRENT_TIMESTAMP",
    "v INTEGER DEFAULT abs(-1)","v INTEGER DEFAULT (SELECT 1)","v TEXT DEFAULT (randomblob(1000000000))",
    "v TEXT DEFAULT readfile('secret')","v INTEGER REFERENCES other(id)","v INTEGER CHECK(v>0)",
    "v INTEGER GENERATED ALWAYS AS (1)","v TEXT COLLATE NOCASE","v INTEGER PRIMARY KEY AUTOINCREMENT",
    "v INTEGER PRIMARY KEY DESC","v INTEGER PRIMARY KEY ASC","v INTEGER UNIQUE",
    "v INTEGER CONSTRAINT named PRIMARY KEY","v TEXT NULL","v INTEGER DEFAULT 1 DEFAULT 2",
    "v INTEGER NOT NULL NOT NULL","v INTEGER DEFAULT 1e999","v INTEGER DEFAULT 9223372036854775808",
    "v TEXT DEFAULT '"+"a"*129+"'",
])
def test_create_constraint_extension_remains_an_explicit_ast_allowlist(definition):
    result=example('CREATE TABLE harmless (v TEXT); CREATE TABLE guarded ('+definition+');')
    assert result['status']=='blocked' and result['steps']==[]
    assert result['partial_steps_audit_only']==[]


@pytest.mark.parametrize('clause',['PRIMARY KEY (v)','FOREIGN KEY (v) REFERENCES other(v)','UNIQUE(v)','CHECK(v>0)'])
def test_table_level_constraints_remain_outside_supported_create_scope(clause):
    result=example('CREATE TABLE guarded (v INTEGER,'+clause+');')
    assert result['status']=='blocked' and result['partial_steps_audit_only']==[]


@pytest.mark.parametrize('constraint',['PRIMARY KEY','NOT NULL','DEFAULT 18'])
def test_add_column_does_not_inherit_create_constraint_support(constraint):
    result=example('CREATE TABLE guarded (v INTEGER); ALTER TABLE guarded ADD COLUMN extra INTEGER '+constraint+';')
    assert result['status']=='blocked' and result['partial_steps_audit_only']==[]


def test_literal_defaults_preserve_null_negative_quoted_text_and_data_that_looks_like_sql():
    payload="'); ATTACH DATABASE 'escaped.sqlite3' AS external; --"
    literal="'"+payload.replace("'","''")+"'"
    result=example("CREATE TABLE defaults (label TEXT DEFAULT "+literal+", amount REAL DEFAULT -2.5, missing INTEGER DEFAULT NULL, marker INTEGER);"
        "INSERT INTO defaults (marker) VALUES (1);")
    assert result['status']=='verified'
    assert result['steps'][-1]['after'][0]['rows']==[[payload,-2.5,None,1]]
    assert result['execution']['statement_count']==2 and len(result['steps'][0]['after'])==1


def test_int_primary_key_is_not_rewritten_as_integer_rowid_alias():
    for declaration,expected in [('INT',None),('INTEGER',1)]:
        result=example('CREATE TABLE keys (id '+declaration+' PRIMARY KEY, label TEXT); INSERT INTO keys (label) VALUES (\'a\');')
        assert result['status']=='verified'
        assert '"id" '+declaration+' PRIMARY KEY' in result['steps'][0]['sql']
        assert result['steps'][-1]['after'][0]['rows']==[[expected,'a']]


def test_numeric_default_affinity_is_not_rewritten_to_real():
    result=example('CREATE TABLE numeric_values (amount NUMERIC DEFAULT 18, marker INTEGER); INSERT INTO numeric_values (marker) VALUES (1);')
    assert result['status']=='verified'
    assert result['steps'][0]['after'][0]['column_types'][0]=='NUMERIC'
    value=result['steps'][-1]['after'][0]['rows'][0][0]
    assert type(value) is int and value==18


def test_complete_unfenced_sql_suffix_after_prose_is_preserved_and_executed():
    suffix="CREATE TABLE learners (id INTEGER PRIMARY KEY, label TEXT DEFAULT 'Unknown', points INTEGER); \nALTER TABLE learners ADD COLUMN grade TEXT;\n"
    raw="DDL 개념 설명은 별도 검토 대상입니다.\n\n설명용 새 예시:\n"+suffix
    result=build_ddl_example(raw)
    assert result['status']=='verified' and result['source_sql_blocks']==[suffix]
    assert [s['operation'] for s in result['steps']]==['create_table','add_column']
    assert result['steps'][-1]['after'][0]['columns']==['id','label','points','grade']
    assert result['free_prose_verification']=='not_verified'


@pytest.mark.parametrize('suffix',[
    "CREATE TABLE x (v INTEGER)",
    "CREATE TABLE x (v INTEGER);\nALTER TABLE x ADD COLUMN",
    "CREATE TABLE x (v INTEGER);\n이제 테이블을 설명합니다.",
    "CREATE TABLE x (v INTEGER);\n이제 테이블을 설명합니다;",
    "CREATE TABLE x (v INTEGER);\nATTACH DATABASE 'escape.sqlite3' AS external;",
    "CREATE TABLE x (v INTEGER);\nSELECT load_extension('evil');",
    "CREATE TABLE x (v INTEGER);\nINSERT INTO x SELECT 1;",
])
def test_unfenced_suffix_is_never_truncated_or_completed_to_hide_a_problem(suffix):
    result=build_ddl_example('설명용 새 예시:\n'+suffix)
    assert result['status']=='blocked' and result['steps']==[]
    assert result['partial_steps_audit_only']==[]
    if suffix.endswith(';'):assert result['source_sql_blocks']==[suffix]


@pytest.mark.parametrize('raw',[
    "CREATE TABLE은 새 표를 만듭니다.",
    "예를 들어 CREATE TABLE x (v INTEGER);",
    "설명: CREATE TABLE x (v INTEGER);\n이것은 SQL의 인라인 인용입니다.",
    "SQL 조각: INSERT INTO x VALUES (1);",
])
def test_inline_sql_prose_is_not_extracted_as_an_independent_example(raw):
    result=build_ddl_example(raw)
    assert result['status']=='not_available' and result['steps']==[]


def test_existing_fence_and_json_extraction_have_priority_over_unfenced_text():
    fenced="```sql\nCREATE TABLE kept (v INTEGER);\n```\nCREATE TABLE ignored (v INTEGER);"
    result=build_ddl_example(fenced)
    assert result['status']=='verified' and len(result['steps'])==1
    assert result['steps'][0]['table_name']=='kept'
    result=build_ddl_example('{"sql":"CREATE TABLE json_example (v INTEGER)","explanation":"SQL field retains its existing format contract."}')
    assert result['status']=='verified' and result['steps'][0]['table_name']=='json_example'
