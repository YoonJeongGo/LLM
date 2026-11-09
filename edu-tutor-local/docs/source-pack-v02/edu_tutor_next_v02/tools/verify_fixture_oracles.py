"""Validate packaged SQL references only. This does not evaluate an LLM or the app.
Run: python edu_tutor_next_v02/tools/verify_fixture_oracles.py
Only reads this package's fixture and creates isolated in-memory SQLite DBs.
"""
from __future__ import annotations
import json
import math
import platform
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Unsafe fixture identifier: {value!r}")
    return '"' + value + '"'

def row_equal(left: list, right: list, tolerance: float) -> bool:
    if len(left) != len(right):
        return False
    for a, b in zip(left, right):
        if a is None or b is None:
            if a is not b:
                return False
        elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if not math.isclose(a, b, rel_tol=tolerance, abs_tol=tolerance):
                return False
        elif a != b:
            return False
    return True

def compare_rows(actual: list, expected: list, ordered: bool, tolerance: float) -> bool:
    if len(actual) != len(expected):
        return False
    if ordered:
        return all(row_equal(a, e, tolerance) for a, e in zip(actual, expected))
    # Multiset comparison: remove one match at a time, preserving duplicate counts.
    pending = list(expected)
    for row in actual:
        match = next((i for i, e in enumerate(pending) if row_equal(row, e, tolerance)), None)
        if match is None:
            return False
        pending.pop(match)
    return not pending

def main() -> int:
    data = json.loads((ROOT / "fixtures/sql_cases_v02.json").read_text(encoding="utf-8"))
    results = []
    for case in data["cases"]:
        con = sqlite3.connect(":memory:")
        try:
            for table in case["tables"]:
                columns = []
                for name, sql_type in table["columns"]:
                    if sql_type not in {"INTEGER", "REAL", "TEXT"}:
                        raise ValueError("Unexpected fixture SQL type")
                    columns.append(f"{identifier(name)} {sql_type}")
                con.execute(f"CREATE TABLE {identifier(table['name'])} ({', '.join(columns)})")
                marks = ", ".join("?" for _ in columns)
                con.executemany(f"INSERT INTO {identifier(table['name'])} VALUES ({marks})", table["rows"])
            oracle = case["oracle"]
            sql = oracle["reference_sql"]
            if not sql.lstrip().upper().startswith("SELECT "):
                raise ValueError("Pack reference must be a SELECT statement")
            cur = con.execute(sql)
            actual = [list(row) for row in cur.fetchall()]
            names = [c[0] for c in cur.description]
            passed = names == oracle["expected_columns"] and compare_rows(actual, oracle["expected_rows"], oracle["ordered"], oracle["numeric_tolerance"])
            results.append({"id":case["id"],"passed":passed,"actual_rows":actual,"columns":names})
        except Exception as exc:
            results.append({"id":case["id"],"passed":False,"error":f"{type(exc).__name__}: {exc}"})
        finally:
            con.close()
    report = {"scope":"Packaged fixture SQL oracle verification only; NOT user app or LLM evaluation", "python":platform.python_version(), "sqlite":sqlite3.sqlite_version, "total":len(results), "passed":sum(r["passed"] for r in results), "results":results}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(r["passed"] for r in results) else 1

if __name__ == "__main__":
    sys.exit(main())
