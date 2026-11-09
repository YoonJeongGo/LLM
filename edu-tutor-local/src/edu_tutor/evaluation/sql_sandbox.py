from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ALLOWED_FUNCTIONS = {"count", "sum", "avg", "min", "max", "total", "coalesce", "ifnull", "nullif", "round",
    "abs", "length", "lower", "upper", "substr", "substring", "trim", "ltrim", "rtrim", "replace",
    "typeof", "date", "time", "datetime", "julianday", "strftime", "iif", "row_number", "rank",
    "dense_rank", "lag", "lead", "first_value", "last_value", "nth_value", "group_concat", "like", "glob"}


def extract_sql(output):
    if isinstance(output, dict) and set(output) <= {"sql", "explanation", "schema_version"} and isinstance(output.get("sql"), str):
        return output["sql"]
    if not isinstance(output, str):
        raise ValueError("ambiguous_parse")
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return extract_sql(parsed)
    blocks = re.findall(r"```([^\n]*)\n(.*?)```", output, re.S)
    if len(blocks) == 1 and blocks[0][0].strip().lower() == "sql":
        return blocks[0][1].strip()
    raise ValueError("ambiguous_parse")


def _name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,63}", value):
        raise ValueError("Invalid fixture identifier")
    return '"' + value + '"'


def _execute(payload):
    sql, fixture = payload["sql"], payload["fixture"]
    if not isinstance(sql, str) or len(sql) > 50000:
        raise ValueError("SQL length limit")
    if not re.match(r"^\s*(SELECT|WITH)\b", sql, re.I):
        raise ValueError("Only SELECT/CTE queries are allowed")
    db = sqlite3.connect(":memory:")
    try:
        db.enable_load_extension(False)
        if hasattr(db, "setlimit"):
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)
            db.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 50_000)
            db.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 100)
            db.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
            db.setlimit(sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 100)
        tables = fixture.get("tables", [])
        if len(tables) > 20:
            raise ValueError("Fixture table limit")
        for table in tables:
            cols = table["columns"]
            if not cols or len(cols) > 50 or len(table["rows"]) > 10000:
                raise ValueError("Fixture row/column limit")
            definitions = []
            for col in cols:
                typ = col["type"].upper()
                if typ not in {"INTEGER", "REAL", "TEXT", "NUMERIC", "BLOB"}:
                    raise ValueError("Invalid fixture type")
                definitions.append(f"{_name(col['name'])} {typ}")
            db.execute(f"CREATE TABLE {_name(table['name'])} ({','.join(definitions)})")
            db.executemany(f"INSERT INTO {_name(table['name'])} VALUES ({','.join('?' for _ in cols)})", table["rows"])
        db.commit()
        db.execute("PRAGMA query_only=ON")
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE}

        def authorize(action, arg1, arg2, _database, _trigger):
            if action in allowed:
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in ALLOWED_FUNCTIONS:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY

        db.set_authorizer(authorize)
        deadline = time.monotonic() + min(float(payload.get("timeout", 2)), 5)
        ticks = 0

        def progress():
            nonlocal ticks
            ticks += 1
            return int(time.monotonic() > deadline or ticks > 20000)

        db.set_progress_handler(progress, 1000)
        cursor = db.execute(sql)  # sqlite rejects multiple statements itself.
        max_rows = min(int(payload.get("max_rows", 1000)), 1000)
        rows = cursor.fetchmany(max_rows + 1)
        if len(rows) > max_rows:
            raise ValueError("Result row limit exceeded")
        result = {"status": "executed", "columns": [c[0] for c in cursor.description], "rows": rows}
        if len(json.dumps(result, ensure_ascii=False).encode()) > 1_000_000:
            raise ValueError("Result byte limit exceeded")
        return result
    finally:
        db.close()


def execute_sql(sql, fixture, timeout=2.0, max_rows=1000, dialect="sqlite"):
    if dialect != "sqlite":
        return {"status": "not_executed", "error": "Only SQLite execution is supported", "columns": [], "rows": []}
    payload = json.dumps({"sql": sql, "fixture": fixture, "timeout": timeout, "max_rows": max_rows}, allow_nan=False)
    if len(payload.encode()) > 2_000_000:
        return {"status": "error", "error": "Input size limit", "columns": [], "rows": []}
    try:
        proc = subprocess.run([sys.executable, "-m", "edu_tutor.evaluation.sql_sandbox", "--worker"],
            input=payload, text=True, encoding="utf-8", capture_output=True, timeout=min(timeout, 5) + 3,
            env={**os.environ, "PYTHONIOENCODING": "utf-8",
                 "PYTHONPATH": str(Path(__file__).resolve().parents[2]) + os.pathsep + os.environ.get("PYTHONPATH", "")},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if proc.returncode:
            return {"status": "error", "error": "SQL worker failed", "columns": [], "rows": []}
        return json.loads(proc.stdout)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": "SQL timeout", "columns": [], "rows": []}


def _equal(a, b, tolerance):
    if a is None or b is None:
        return a is b
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isfinite(a) and math.isfinite(b) and abs(a - b) <= tolerance
    return type(a) is type(b) and a == b


def compare_results(actual, expected):
    if actual.get("status") != "executed" or actual.get("columns") != expected["columns"]:
        return False
    rows, wanted = actual["rows"], expected["rows"]
    if len(rows) != len(wanted):
        return False
    tolerance = expected.get("numeric_abs_tolerance", 0)
    row_equal = lambda x, y: len(x) == len(y) and all(_equal(a, b, tolerance) for a, b in zip(x, y))
    if expected.get("row_order", "unordered") == "ordered":
        return all(row_equal(x, y) for x, y in zip(rows, wanted))
    # Match each row once: preserve duplicate multiplicity.
    unmatched = list(wanted)
    for row in rows:
        for i, candidate in enumerate(unmatched):
            if row_equal(row, candidate):
                unmatched.pop(i)
                break
        else:
            return False
    return True


def evaluate_sql(sql, record):
    actual = execute_sql(sql, record["fixture"], dialect=record.get("sql_dialect", "sqlite"))
    return {**actual, "match": compare_results(actual, record["expected"]), "tier": "T0",
            "human_review": "not_reviewed"}


if __name__ == "__main__" and "--worker" in sys.argv:
    try:
        value = _execute(json.loads(sys.stdin.read(2_000_001)))
    except Exception as exc:
        value = {"status": "timeout" if "interrupted" in str(exc) else "error",
                 "error": str(exc)[:250], "columns": [], "rows": []}
    print(json.dumps(value, ensure_ascii=False, allow_nan=False))
