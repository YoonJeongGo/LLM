"""Independent CPU contracts for SQLite's SUM(column IS NOT NULL).

Expected rows come from a separate stdlib SQLite database, never from the
application's trace, its intent parser, or model-generated prose. These are
development fixtures, not student uploads or a new model accuracy evaluation.
"""
import copy
import json
import sqlite3

import pytest

from edu_tutor.lessons.plans import scene_at
from edu_tutor.lessons.verified import generate_verified_plan
from edu_tutor.problems.evidence import display_answer, verify_answer
from edu_tutor.problems.models import normalize_problem


CASES = [
    pytest.param("practice_checks", "solved", [4, None, 0, 7, None], id="original-five-rows"),
    pytest.param("observations", "amount", [], id="empty-input"),
    pytest.param("observations", "amount", [None, None, None], id="all-null"),
    pytest.param("observations", "amount", [0, 0, None, 0], id="zero-is-not-null"),
    pytest.param("observations", "amount", [-9, -9, None, 0, 12, None], id="negative-and-duplicate-values"),
    pytest.param("observations", "amount", [None], id="single-null"),
    pytest.param("observations", "amount", [0], id="single-zero"),
    pytest.param("inventory_readings", "remaining_units", [15, None, -2, 15, 0, 8, None], id="renamed-and-changed-values"),
]


def problem_for(table, column, values, *, kind="query_result", sql=None, dialect="sqlite"):
    query = sql or f"SELECT COUNT(*) AS total_rows, SUM({column} IS NOT NULL) AS present_rows FROM {table}"
    problem = normalize_problem({
        "task_kind": kind,
        "dialect": dialect,
        "confirmed": True,
        "raw_text": f"SQLite 범위에서 전체 행 수와 {column} 값이 NULL이 아닌 행 수를 이 순서대로 구해 줘.",
        "tables": [{"name": table,
                    "columns": [{"name": "record_name", "type": "TEXT"},
                                {"name": column, "type": "INTEGER"}],
                    "rows": [[f"record_{i}", value] for i, value in enumerate(values)]}],
        **({"query": query} if kind == "query_result" else {}),
    })
    # Deliberately untrusted; a verified lesson must not copy this explanation.
    raw = json.dumps({"sql": query, "explanation": "UNVERIFIED_PROSE_999: COUNT(*) excludes NULL rows."})
    return problem, query, raw


def independent_sqlite(problem, query, *, with_columns=False):
    table = problem["tables"][0]
    name = table["name"]
    column = table["columns"][1]["name"]
    with sqlite3.connect(":memory:") as connection:
        connection.execute(f'CREATE TABLE "{name}" (record_name TEXT, "{column}" INTEGER)')
        connection.executemany(f'INSERT INTO "{name}" VALUES (?, ?)', table["rows"])
        cursor = connection.execute(query)
        columns = [item[0] for item in cursor.description]
        rows = [list(row) for row in cursor]
        inputs = list(connection.execute(
            f'SELECT rowid - 1, "{column}", "{column}" IS NOT NULL FROM "{name}" ORDER BY rowid'))
        counts = list(connection.execute(f'SELECT COUNT(*), COUNT("{column}") FROM "{name}"'))[0]
    result = (rows, inputs, list(counts))
    return (*result, columns) if with_columns else result


def verified_lesson(problem, raw, evidence):
    message = {"id": "cpu-conditional-contract", "problem": problem, "evidence": evidence,
               "content": display_answer(evidence), "raw_model_response": raw}
    before = copy.deepcopy(message)
    lesson = generate_verified_plan(message, problem["raw_text"], "conditional-contract")
    assert message == before, "Producing a plan must not rewrite the source or raw model answer."
    return lesson


@pytest.mark.parametrize("table,column,values", CASES)
def test_query_result_trace_matches_independent_sqlite_and_preserves_source(table, column, values):
    problem, sql, raw = problem_for(table, column, values)
    before = copy.deepcopy(problem)
    expected_rows, expected_inputs, _ = independent_sqlite(problem, sql)
    evidence = verify_answer(problem, raw, problem["raw_text"])

    assert evidence["status"] == "verified"
    assert evidence["calculation"]["status"] == "independent_aggregate_match"
    assert evidence["sql"] == sql
    assert evidence["result"]["rows"] == expected_rows
    assert evidence["execution"]["rows"] == expected_rows
    aggregate = evidence["logical_steps"]["aggregates"][1]
    source = evidence["working_tables"][0]
    assert aggregate["function"] == "sum"
    assert aggregate["column"] == column
    assert aggregate["input_transform"] == "is_not_null_indicator"
    assert aggregate["input_expression"].casefold() == f"{column} IS NOT NULL".casefold()
    assert aggregate["included_values"] == [row[2] for row in expected_inputs]
    assert aggregate["result"] == expected_rows[0][1]
    assert aggregate["sum"] == expected_rows[0][1]
    assert aggregate["included_row_ids"] == source["row_ids"]
    assert aggregate["included_cell_ids"] == [row[1] for row in source["cell_ids"]]
    assert aggregate["input_rows"] == [
        {"row_id": source["row_ids"][i], "cell_id": source["cell_ids"][i][1],
         "source_value": value, "value": indicator}
        for i, value, indicator in expected_inputs
    ]
    assert evidence["original_tables"][0]["rows"] == before["tables"][0]["rows"]
    assert problem == before

    lesson = verified_lesson(problem, raw, evidence)
    assert lesson["speech_allowed"] and lesson["generation"]["model_plan_calls"] == 0
    assert lesson["generation"]["repair_requests"] == 0
    plan = lesson["plan"]
    assert len(plan["steps"]) == 2
    speeches = " ".join(step["speech"] for step in plan["steps"])
    assert "UNVERIFIED_PROSE_999" not in speeches and "excludes NULL rows" not in speeches
    first, last = scene_at(plan, 0), scene_at(plan, 1)
    assert first["elements"][source["id"]]["rows"] == before["tables"][0]["rows"]
    indicator_tables = [element for element in first["elements"].values()
                        if element.get("columns") == ["원본 행", column, "조건값 (1/0)"]]
    assert len(indicator_tables) == 1
    assert indicator_tables[0]["rows"] == [[i + 1, value, indicator] for i, value, indicator in expected_inputs]
    assert f"{column} IS NOT NULL" in indicator_tables[0]["caption"]
    assert last["elements"][evidence["id"] + "-result"]["rows"] == expected_rows
    if not values:
        assert "NULL" in plan["steps"][1]["speech"]
        assert "합계는 0" not in plan["steps"][1]["speech"]
    assert evidence["human_review"] == "not_reviewed"


@pytest.mark.parametrize("table,column,values", CASES)
def test_write_sql_intent_match_is_input_bound_and_empty_input_is_not_count_equivalence(table, column, values):
    problem, sql, raw = problem_for(table, column, values, kind="write_sql")
    before = copy.deepcopy(problem)
    expected_rows, _, count_rows = independent_sqlite(problem, sql)
    evidence = verify_answer(problem, raw, problem["raw_text"])
    assert evidence["execution"]["rows"] == expected_rows
    assert evidence["sql"] == sql and problem == before

    if values:
        assert expected_rows[0] == count_rows
        assert evidence["status"] == "verified"
        assert evidence["intent"].get("input_bound_equivalence")
        assert evidence["result"]["rows"] == expected_rows
        lesson = verified_lesson(problem, raw, evidence)
        assert lesson["speech_allowed"]
        first = scene_at(lesson["plan"], 0)
        assert first["elements"][evidence["id"] + "-sql"]["code"] == sql
    else:
        assert expected_rows == [[0, None]] and count_rows == [0, 0]
        assert evidence["status"] != "verified"
        lesson = verified_lesson(problem, raw, evidence)
        assert lesson["plan"] is None and not lesson["speech_allowed"]


@pytest.mark.parametrize("dialect", ["oracle", "postgresql", "mysql"])
def test_other_dialects_are_not_verified_using_sqlite(dialect):
    problem, _, raw = problem_for("measurements", "amount", [0, None, -1], dialect=dialect)
    before = copy.deepcopy(problem)
    evidence = verify_answer(problem, raw, problem["raw_text"])
    assert evidence["status"] == "unsupported"
    assert evidence["execution"]["status"] == "not_run"
    assert not verified_lesson(problem, raw, evidence)["speech_allowed"]
    assert problem == before


UNSUPPORTED = [
    pytest.param("SUM(amount IS NULL)", id="opposite-null-predicate"),
    pytest.param("SUM(amount > 0)", id="unapproved-value-predicate"),
    pytest.param("SUM(CASE WHEN amount IS NOT NULL THEN 1 ELSE 0 END)", id="case-expression"),
    pytest.param("SUM((amount IS NOT NULL) + 0)", id="arithmetic-wrapper"),
    pytest.param("SUM(DISTINCT (amount IS NOT NULL))", id="distinct-indicators"),
    pytest.param("AVG(amount IS NOT NULL)", id="different-aggregate"),
    pytest.param("SUM(amount IS NOT NULL OR amount = 0)", id="compound-predicate"),
    pytest.param("SUM(missing.amount IS NOT NULL)", id="unknown-qualifier"),
    pytest.param("SUM(unknown_column IS NOT NULL)", id="unknown-column"),
]


@pytest.mark.parametrize("expression", UNSUPPORTED)
def test_unsupported_expression_cannot_become_a_verified_nonnull_count_lesson(expression):
    sql = f"SELECT COUNT(*), {expression} FROM measurements"
    problem, _, raw = problem_for("measurements", "amount", [None, -2, 0, 4], kind="write_sql", sql=sql)
    before = copy.deepcopy(problem)
    evidence = verify_answer(problem, raw, problem["raw_text"])
    assert evidence["status"] != "verified"
    assert evidence["logical_steps"] is None
    lesson = verified_lesson(problem, raw, evidence)
    assert lesson["plan"] is None and not lesson["speech_allowed"]
    assert problem == before and evidence["original_tables"][0]["rows"] == before["tables"][0]["rows"]


@pytest.mark.parametrize("expression", ["SUM(amount > 0)", "SUM(CASE WHEN amount IS NOT NULL THEN 1 ELSE 0 END)"])
def test_unimplemented_given_query_can_show_execution_without_inventing_intermediate_trace(expression):
    sql = f"SELECT COUNT(*), {expression} FROM measurements"
    problem, _, raw = problem_for("measurements", "amount", [None, -2, 0, 4], sql=sql)
    before = copy.deepcopy(problem)
    expected_rows, _, _ = independent_sqlite(problem, sql)
    evidence = verify_answer(problem, raw, problem["raw_text"])
    assert evidence["execution"]["rows"] == expected_rows
    assert evidence["logical_steps"] is None
    assert evidence["calculation"]["status"] == "outside_supported_trace"
    lesson = verified_lesson(problem, raw, evidence)
    if lesson["speech_allowed"]:
        assert lesson["plan"]["verification"]["status"] == "execution_grounded"
        assert "중간 계산 설명은 지원 범위 밖" in lesson["plan"]["steps"][0]["speech"]
    assert problem == before


@pytest.mark.parametrize("kind", ["query_result", "write_sql"])
@pytest.mark.parametrize("sql", [
    "SELECT COUNT(*), SUM(amount IS NOT NULL) FROM measurements",
    "select count(*), sum((amount is not null)) from measurements",
    "SELECT COUNT(*), SUM((AMOUNT IS NOT NULL)) FROM MEASUREMENTS",
])
def test_unaliased_projection_keeps_original_sqlite_columns_across_spelling(kind, sql):
    problem, _, raw = problem_for("measurements", "amount", [None, -2, 0, 4, None], kind=kind, sql=sql)
    before = copy.deepcopy(problem)
    expected_rows, expected_inputs, _, columns = independent_sqlite(problem, sql, with_columns=True)
    evidence = verify_answer(problem, raw, problem["raw_text"])
    assert evidence["status"] == "verified"
    assert evidence["calculation"]["status"] == "independent_aggregate_match"
    assert evidence["sql"] == sql and problem == before
    assert evidence["result"] == {"columns": columns, "rows": expected_rows}
    trace = evidence["logical_steps"]
    assert trace["projection_binding"]["status"] == "same_ast_projection_positions"
    assert trace["projection_binding"]["original_columns"] == columns
    assert trace["aggregates"][1]["included_values"] == [row[2] for row in expected_inputs]
    lesson = verified_lesson(problem, raw, evidence)
    assert lesson["speech_allowed"] and len(lesson["plan"]["steps"]) == 2
    result_board = scene_at(lesson["plan"], 1)["elements"][evidence["id"] + "-result"]
    assert result_board["columns"] == columns and result_board["rows"] == expected_rows
    if kind == "write_sql":
        assert scene_at(lesson["plan"], 0)["elements"][evidence["id"] + "-sql"]["code"] == sql


@pytest.mark.parametrize("suffix", ["; DELETE FROM measurements", "; UPDATE measurements SET amount = 0"])
def test_conditional_support_does_not_admit_multiple_or_mutating_statements(suffix):
    sql = "SELECT COUNT(*), SUM(amount IS NOT NULL) FROM measurements" + suffix
    problem, _, raw = problem_for("measurements", "amount", [0, None, -1], kind="write_sql", sql=sql)
    before = copy.deepcopy(problem)
    evidence = verify_answer(problem, raw, problem["raw_text"])
    assert evidence["status"] == "stopped" and evidence["execution"]["status"] != "executed"
    assert not verified_lesson(problem, raw, evidence)["speech_allowed"]
    assert problem == before
