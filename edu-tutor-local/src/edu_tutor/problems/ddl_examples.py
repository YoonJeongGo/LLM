"""Execute a tiny, model-authored DDL/DML illustration in a disposable DB.

Only reconstructed CREATE TABLE, literal INSERT/UPDATE, ADD COLUMN and DROP
TABLE are executable. This is a new teaching example, never the student's DB
or an inferred replacement for the original problem. Free prose is unreviewed.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
from contextlib import closing

import sqlglot
from sqlglot import exp

LIMITS = {"sql_characters": 8000, "statements": 8, "tables": 3,
          "columns_per_table": 8, "rows_per_table": 20, "string_characters": 128,
          "execution_seconds": 1.0}
TYPES = {"INT": "INTEGER", "INTEGER": "INTEGER", "REAL": "REAL", "FLOAT": "REAL",
         "DOUBLE": "REAL", "TEXT": "TEXT", "NUMERIC": "NUMERIC"}


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,63}", value):
        raise ValueError("예시 식별자는 64자 이하 영문·숫자·밑줄만 지원합니다.")
    if value.casefold().startswith("sqlite_"):
        raise ValueError("SQLite 내부 이름은 예시에 사용할 수 없습니다.")
    return value


def _quoted(value):
    return '"' + _identifier(value) + '"'


def _table(node):
    if (not isinstance(node, exp.Table) or not isinstance(node.this, exp.Identifier)
            or any(v for k,v in node.args.items() if k != "this")):
        raise ValueError("연결 DB·스키마·별칭 없는 예시 표 이름만 지원합니다.")
    return _identifier(node.name)


def _column(node, *, create_constraints=False, source_sql=None):
    if not isinstance(node, exp.ColumnDef) or node.args.get("exists") or node.args.get("constraints") and not create_constraints:
        raise ValueError("예시 열은 제약식 없는 단순 이름과 자료형만 지원합니다.")
    if any(v for k,v in node.args.items() if k not in {"this", "kind", "exists", "constraints"}):
        raise ValueError("지원하지 않는 예시 열 속성입니다.")
    typ = node.args.get("kind")
    if not isinstance(typ, exp.DataType) or typ.expressions:
        raise ValueError("예시 자료형은 INTEGER, REAL, TEXT, NUMERIC만 지원합니다.")
    kind = TYPES.get(typ.sql(dialect="sqlite").upper())
    if kind is None:
        raise ValueError("예시 자료형은 INTEGER, REAL, TEXT, NUMERIC만 지원합니다.")
    constraints=[];seen=set()
    for constraint in node.args.get("constraints") or []:
        if not isinstance(constraint,exp.ColumnConstraint) or any(v for k,v in constraint.args.items() if k!="kind"):
            raise ValueError("이름 있는 제약식 등 확장 제약식은 예시에서 지원하지 않습니다.")
        value=constraint.args.get("kind")
        if type(value) is exp.PrimaryKeyColumnConstraint:
            if value.args.get("desc") is not None or any(v for k,v in value.args.items() if k!="desc"):
                raise ValueError("PRIMARY KEY의 정렬·충돌·확장 옵션은 지원하지 않습니다.")
            item={"kind":"primary_key"}
        elif type(value) is exp.NotNullColumnConstraint and not value.args:
            item={"kind":"not_null"}
        elif type(value) is exp.DefaultColumnConstraint and not any(v for k,v in value.args.items() if k!="this"):
            item={"kind":"default","value":_literal(value.this)}
        else:
            raise ValueError("CREATE 열 제약은 단순 PRIMARY KEY, NOT NULL, 리터럴 DEFAULT만 지원합니다.")
        if item["kind"] in seen:
            raise ValueError("같은 열 제약의 중복 선언은 지원하지 않습니다.")
        seen.add(item["kind"]);constraints.append(item)
    if constraints:
        # Preserve narrowly allowed source type tokens for new constrained
        # columns: INT PRIMARY KEY is not an INTEGER rowid alias, and NUMERIC
        # affinity must not silently turn into REAL after parser normalization.
        end=node.this.meta.get("end")
        declared=re.match(r"\s*(INTEGER|INT|REAL|FLOAT|DOUBLE|TEXT|NUMERIC)\b",source_sql[end+1:],re.I) if isinstance(source_sql,str) and isinstance(end,int) else None
        if not declared:
            raise ValueError("제약식이 있는 열의 원문 자료형을 허용 목록에서 확인해야 합니다.")
        kind=declared.group(1).upper()
    result={"name": _identifier(node.name), "type": kind}
    if constraints:result["constraints"]=constraints
    return result


def _literal(node):
    if isinstance(node, exp.Null):
        return None
    negative = isinstance(node, exp.Neg)
    if negative:
        node = node.this
    if not isinstance(node, exp.Literal) or negative and node.is_string:
        raise ValueError("INSERT 예시는 함수·식·서브쿼리 없이 문자·숫자·NULL 값만 지원합니다.")
    if node.is_string:
        if len(node.this) > LIMITS["string_characters"]:
            raise ValueError("예시 문자열 길이 제한을 초과했습니다.")
        return node.this
    try:
        value = int(node.this) if re.fullmatch(r"\d+", node.this) else float(node.this)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("유한 숫자만 사용할 수 있습니다.") from exc
    if negative:
        value = -value
    if isinstance(value, float) and not math.isfinite(value) or isinstance(value, int) and not -(2**63) <= value < 2**63:
        raise ValueError("SQLite의 유한 숫자 범위를 초과했습니다.")
    return value


def _sql_value(value):
    if value is None:
        return "NULL"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return str(value)


def _plain_column(node):
    if not isinstance(node, exp.Column) or node.table or any(v for k,v in node.args.items() if k != "this"):
        raise ValueError("UPDATE 예시는 표 별칭 없는 원본 열만 지원합니다.")
    return _identifier(node.name)


def _command(node, source_sql=None):
    """Validate all AST nodes first, then create a tiny independent command."""
    if isinstance(node, exp.Create):
        if node.args.get("kind") != "TABLE" or not isinstance(node.this, exp.Schema):
            raise ValueError("CREATE TABLE의 명시적 열 선언만 지원합니다.")
        if any(v for k,v in node.args.items() if k not in {"this", "kind", "exists"}):
            raise ValueError("CREATE AS/임시·가상 표/교체 등의 확장 문법은 지원하지 않습니다.")
        name = _table(node.this.this)
        columns = [_column(c,create_constraints=True,source_sql=source_sql) for c in node.this.expressions]
        if not 1 <= len(columns) <= LIMITS["columns_per_table"]:
            raise ValueError("예시 표 열 개수 제한을 초과했습니다.")
        return {"operation": "create_table", "table": name, "columns": columns,
                "if_not_exists": bool(node.args.get("exists"))}
    if isinstance(node, exp.Insert):
        allowed = {"this", "expression", "is_function"}
        if any(v for k,v in node.args.items() if k not in allowed) or node.args.get("is_function"):
            raise ValueError("INSERT의 기본 VALUES 형식만 지원합니다.")
        target = node.this
        columns = None
        if isinstance(target, exp.Schema):
            columns = [_identifier(c.name) if isinstance(c, exp.Identifier) else _identifier(None) for c in target.expressions]
            target = target.this
        name = _table(target)
        values = node.args.get("expression")
        if not isinstance(values, exp.Values) or not 1 <= len(values.expressions) <= LIMITS["rows_per_table"]:
            raise ValueError("INSERT VALUES의 작은 행 목록만 지원합니다.")
        rows = []
        for row in values.expressions:
            if not isinstance(row, exp.Tuple) or not 1 <= len(row.expressions) <= LIMITS["columns_per_table"]:
                raise ValueError("INSERT 행 너비 제한을 초과했습니다.")
            rows.append([_literal(value) for value in row.expressions])
        return {"operation": "insert_rows", "table": name, "columns": columns, "rows": rows}
    if isinstance(node, exp.Alter):
        if node.args.get("kind") != "TABLE" or any(v for k,v in node.args.items() if k not in {"this", "kind", "actions"}):
            raise ValueError("ALTER TABLE ADD COLUMN만 지원합니다.")
        actions = node.args.get("actions", [])
        if len(actions) != 1:
            raise ValueError("한 문장에서는 열 하나만 추가할 수 있습니다.")
        return {"operation": "add_column", "table": _table(node.this), "column": _column(actions[0])}
    if isinstance(node, exp.Update):
        if any(v for k,v in node.args.items() if k not in {"this", "expressions", "where"}):
            raise ValueError("UPDATE 예시는 단일 표 SET과 선택적인 단순 WHERE만 지원합니다.")
        assignments=[]
        for item in node.expressions:
            if not isinstance(item, exp.EQ):
                raise ValueError("UPDATE SET은 열 = 리터럴 값 형식이어야 합니다.")
            assignments.append({"column": _plain_column(item.this), "value": _literal(item.expression)})
        if not 1 <= len(assignments) <= LIMITS["columns_per_table"] or len({a["column"].casefold() for a in assignments}) != len(assignments):
            raise ValueError("UPDATE의 대상 열은 중복 없이 1~8개여야 합니다.")
        condition=None
        if node.args.get("where"):
            predicate=node.args["where"].this
            if isinstance(predicate, exp.EQ):
                condition={"column": _plain_column(predicate.this), "operator": "=", "value": _literal(predicate.expression)}
            elif isinstance(predicate, exp.Is) and isinstance(predicate.expression, exp.Null):
                condition={"column": _plain_column(predicate.this), "operator": "IS", "value": None}
            else:
                raise ValueError("UPDATE 예시 조건은 열 = 리터럴 또는 열 IS NULL만 지원합니다.")
        return {"operation": "update_values", "table": _table(node.this), "assignments": assignments, "condition": condition}
    if isinstance(node, exp.Drop):
        if node.args.get("kind") != "TABLE" or any(v for k,v in node.args.items() if k not in {"this", "kind", "exists"}):
            raise ValueError("단순 DROP TABLE만 지원합니다.")
        return {"operation": "drop_table", "table": _table(node.this), "if_exists": bool(node.args.get("exists"))}
    raise ValueError("설명용 예시는 CREATE TABLE, INSERT VALUES, 리터럴 UPDATE, ALTER ADD COLUMN, DROP TABLE만 지원합니다.")


def _extract(raw):
    if not isinstance(raw, str) or len(raw) > 30000:
        raise ValueError("예시 응답 길이 제한을 초과했습니다.")
    blocks = []
    for match in re.finditer(r"```([^\r\n`]*)\r?\n(.*?)(```|\Z)",raw,re.S):
        language,body,closing=match.groups()
        language=language.strip().casefold()
        candidate=language=="sql" or not language and re.match(r"^\s*(CREATE|INSERT|UPDATE|ALTER|DROP)\b",body,re.I)
        if candidate:
            if not closing:
                raise ValueError("SQL 예시 코드 블록이 닫히지 않았습니다.")
            blocks.append(body)
    if not blocks:
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            value = None
        if isinstance(value, dict) and isinstance(value.get("sql"), str):
            blocks = [value["sql"]]
        else:
            # Model prose can precede an unfenced but complete SQL example.
            # Take the entire suffix from its first independent command line;
            # never trim trailing prose/unsafe SQL or repair incomplete input.
            start=re.search(r"^[ \t]*(?:CREATE[ \t]+TABLE|INSERT[ \t]+INTO|UPDATE\b|ALTER[ \t]+TABLE|DROP[ \t]+TABLE)\b",raw,re.I|re.M)
            if start:
                suffix=raw[start.start():]
                if not suffix.rstrip().endswith(";"):
                    raise ValueError("백틱 없는 SQL 예시는 마지막 세미콜론까지 완결되어야 합니다. 원문의 뒷부분을 버리거나 보충하지 않습니다.")
                blocks=[suffix]
    if sum(map(len, blocks)) > LIMITS["sql_characters"]:
        raise ValueError("예시 SQL 길이 제한을 초과했습니다.")
    return blocks


def _snapshot(db, known, namespace):
    tables = []
    for name in known:
        # Identifiers come only from the validated command model. These internal
        # introspection SELECTs never expose sqlite_schema to supplied SQL.
        columns = db.execute('SELECT name, type, "notnull", dflt_value, pk FROM pragma_table_info(?)', (name,)).fetchall()
        rows = [list(row) for row in db.execute('SELECT * FROM '+_quoted(name))]
        ident = namespace + '-table-' + name.casefold()
        row_ids = [ident+'-r'+str(i) for i in range(len(rows))]
        column_ids = [ident+'-c-'+c[0].casefold() for c in columns]
        tables.append({"id":ident,"name":name,"columns":[c[0] for c in columns],
                       "column_types":[c[1] for c in columns],"rows":rows,
                       "column_constraints":[{"name":c[0],"not_null":bool(c[2]),"default_sql":c[3],"primary_key_position":c[4]} for c in columns],
                       "row_ids":row_ids,"column_ids":column_ids,
                       "cell_ids":[[r+'-c-'+c[0].casefold() for c in columns] for r in row_ids]})
    return tables


def _execute(db, command, known):
    op, name = command["operation"], command["table"]
    qname = _quoted(name)
    if op == "create_table":
        if name.casefold() not in {n.casefold() for n in known} and len(known) >= LIMITS["tables"]:
            raise ValueError("예시 표 개수 제한을 초과했습니다.")
        definitions=[]
        for column in command['columns']:
            definition=_quoted(column['name'])+' '+column['type']
            for constraint in column.get('constraints',[]):
                definition+=' '+({'primary_key':'PRIMARY KEY','not_null':'NOT NULL'}.get(constraint['kind'])
                    or 'DEFAULT '+_sql_value(constraint['value']))
            definitions.append(definition)
        sql = 'CREATE TABLE '+('IF NOT EXISTS ' if command['if_not_exists'] else '')+qname+' ('+', '.join(definitions)+')'
        db.execute(sql)
        if name.casefold() not in {n.casefold() for n in known}:known.append(name)
    elif op == "insert_rows":
        width = len(command["rows"][0])
        if any(len(row) != width for row in command["rows"]):
            raise ValueError("INSERT 행 너비가 서로 다릅니다.")
        if command["columns"] and len(command["columns"]) != width:
            raise ValueError("INSERT 대상 열과 값 개수가 다릅니다.")
        existing = db.execute('SELECT COUNT(*) FROM '+qname).fetchone()[0]
        if existing + len(command["rows"]) > LIMITS["rows_per_table"]:
            raise ValueError("예시 행 개수 제한을 초과했습니다.")
        prefix = 'INSERT INTO '+qname+(' ('+', '.join(_quoted(c) for c in command['columns'])+')' if command['columns'] else '')+' VALUES '
        db.executemany(prefix+'('+','.join('?' for _ in range(width))+')',command['rows'])
        sql = prefix+', '.join('('+', '.join(_sql_value(v) for v in row)+')' for row in command['rows'])
    elif op == "add_column":
        count = db.execute('SELECT COUNT(*) FROM pragma_table_info(?)',(name,)).fetchone()[0]
        if count >= LIMITS["columns_per_table"]:
            raise ValueError("예시 열 개수 제한을 초과했습니다.")
        column = command["column"]
        sql = 'ALTER TABLE '+qname+' ADD COLUMN '+_quoted(column['name'])+' '+column['type']
        db.execute(sql)
    elif op == "update_values":
        columns={row[0].casefold(): row for row in db.execute('SELECT name, pk FROM pragma_table_info(?)',(name,))}
        assignments=command["assignments"]; condition=command["condition"]
        referenced=[a["column"] for a in assignments]+([condition["column"]] if condition else [])
        if any(c.casefold() not in columns for c in referenced):
            raise ValueError("UPDATE가 원본에 없는 열을 참조합니다.")
        if any(columns[a["column"].casefold()][1] for a in assignments):
            raise ValueError("UPDATE 예시에서 기본키 변경은 행 식별을 바꿀 수 있어 지원하지 않습니다.")
        sql='UPDATE '+qname+' SET '+', '.join(_quoted(a["column"])+" = "+_sql_value(a["value"]) for a in assignments)
        if condition:
            sql+=' WHERE '+_quoted(condition["column"])+" "+condition["operator"]+" "+_sql_value(condition["value"])
        command["matched_rows"]=db.execute(sql).rowcount
    else:
        sql = 'DROP TABLE '+('IF EXISTS ' if command['if_exists'] else '')+qname
        db.execute(sql)
        known[:] = [n for n in known if n.casefold() != name.casefold()]
    return sql+';'


def build_ddl_example(raw_response):
    report = {"status":"not_available","source":"model_authored_sql","label":"설명용 새 예시",
              "problem_role":"separate_illustration_not_original_problem","steps":[],"limits":LIMITS.copy(),
              "execution":{"status":"not_run","dialect":"sqlite","database":":memory:"},
              "human_review":"not_reviewed","free_prose_verification":"not_verified"}
    try:
        blocks = _extract(raw_response)
        if not blocks:
            return {**report,"reason":"실제 모델 응답에 실행할 SQL 예시가 없습니다. 예시를 만들어 넣지 않았습니다."}
        report["source_sql_blocks"] = blocks
        nodes = [(n,block) for block in blocks for n in sqlglot.parse(block,read='sqlite') if n is not None]
        if not 1 <= len(nodes) <= LIMITS["statements"]:
            raise ValueError("예시 SQL 문장 개수 제한을 초과했습니다.")
        # Validate every statement before executing any of them.
        commands = [_command(node,block) for node,block in nodes]
        namespace = 'example-'+hashlib.sha256('\n'.join(blocks).encode()).hexdigest()[:12]
        started = time.monotonic()
        known = []
        with closing(sqlite3.connect(':memory:')) as db:
            db.enable_load_extension(False)
            db.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED,0)
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH,100000)
            db.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH,10000)
            db.setlimit(sqlite3.SQLITE_LIMIT_COLUMN,16)
            db.set_progress_handler(lambda: int(time.monotonic()-started > LIMITS['execution_seconds']),100)
            for i,command in enumerate(commands):
                if time.monotonic()-started > LIMITS['execution_seconds']:
                    raise ValueError("예시 SQL 실행 시간 제한을 초과했습니다.")
                before = _snapshot(db,known,namespace)
                sql = _execute(db,command,known)
                after = _snapshot(db,known,namespace)
                b = next((t for t in before if t['name'].casefold()==command['table'].casefold()),None)
                a = next((t for t in after if t['name'].casefold()==command['table'].casefold()),None)
                effects = {'table_count_before':len(before),'table_count_after':len(after),
                           'rows_before':len(b['rows']) if b else 0,'rows_after':len(a['rows']) if a else 0,
                           'columns_before':len(b['columns']) if b else 0,'columns_after':len(a['columns']) if a else 0}
                op=command['operation']
                if op=='create_table':
                    narration=f"설명용 새 예시입니다. CREATE TABLE 실행 뒤 {command['table']} 표에는 열 {effects['columns_after']}개와 행 {effects['rows_after']}개가 있습니다."
                elif op=='insert_rows':
                    narration=f"INSERT는 이 예시의 행을 {effects['rows_before']}개에서 {effects['rows_after']}개로 늘렸습니다. 열은 {effects['columns_after']}개로 그대로입니다."
                elif op=='add_column':
                    narration=f"ALTER TABLE은 이 예시의 열을 {effects['columns_before']}개에서 {effects['columns_after']}개로 늘렸습니다. 행은 {effects['rows_after']}개로 그대로입니다."
                elif op=='update_values':
                    if not a or not b or a['columns']!=b['columns'] or len(a['rows'])!=len(b['rows']):
                        raise ValueError("UPDATE 전후의 행과 열을 안정적으로 연결하지 못했습니다.")
                    changed=[[r,c] for r,(old,new) in enumerate(zip(b['rows'],a['rows'])) for c,(left,right) in enumerate(zip(old,new)) if left!=right]
                    effects.update(matched_rows=command['matched_rows'],changed_cells=changed,
                                   changed_rows=len({r for r,c in changed}))
                    narration=(f"UPDATE는 이 예시의 행 {effects['rows_after']}개와 열 {effects['columns_after']}개를 유지했습니다. "
                        +(f"값이 달라진 곳은 {effects['changed_rows']}개 행의 {len(changed)}개 칸입니다." if changed else "실행 전후 값이 달라진 칸은 없습니다."))
                else:
                    narration=f"DROP TABLE 실행 뒤 이 예시의 표 개수는 {effects['table_count_before']}개에서 {effects['table_count_after']}개가 됐습니다."
                report['steps'].append({'id':namespace+'-step-'+str(i),'operation':op,'sql':sql,
                    'before':before,'after':after,'table_name':command['table'],'effects':effects,
                    'narration':narration,'label':'설명용 새 예시','execution_status':'executed_in_disposable_sqlite'})
        report.update(status='verified',namespace=namespace)
        report['execution'].update(status='executed',statement_count=len(commands),elapsed_seconds=time.monotonic()-started)
        return report
    except (ValueError,TypeError,KeyError,sqlite3.Error,sqlglot.errors.ParseError) as exc:
        partial = report.pop('steps',[])
        return {**report,'status':'blocked','steps':[], 'partial_steps_audit_only':partial,
                'reason':str(exc),'execution':{**report['execution'],'status':'blocked_or_failed'}}
