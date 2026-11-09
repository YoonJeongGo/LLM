"""SQLite execution and explicitly bounded intent/calculation evidence.

No reference answers or question IDs are consulted. Tables supplied by the user
are the only numerical inputs. SQL execution is not an intent verdict.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import time
from functools import cmp_to_key

import sqlglot
from sqlglot import exp

from edu_tutor.evaluation.sql_sandbox import execute_sql, compare_results
from .sql_response import extract_sql_candidate, SQL_EXTRACTION_PROTOCOL
from .models import canonical, identified_table, derive_hypothesis, infer_basic_intent


def quote(name):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,63}", name):
        raise ValueError("지원하지 않는 식별자입니다.")
    return '"' + name + '"'


def fixture(problem):
    return {"tables": [{"name": t["name"], "columns": [{"name": c["name"], "type": c["type"]} for c in t["columns"]],
                        "rows": t["rows"]} for t in problem["tables"]]}


def aggregate_spec(expression):
    value = expression.this if isinstance(expression, exp.Alias) else expression
    if not isinstance(value, (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)):
        return None
    operand = value.this
    distinct = isinstance(operand, exp.Distinct)
    if distinct:
        if len(operand.expressions) != 1:
            return None
        operand = operand.expressions[0]
    while isinstance(operand, exp.Paren):
        operand = operand.this
    # Only this SQLite predicate has a proved, row-local 0/1 interpretation.
    # Preserve SUM as SUM: on empty input it is NULL, not COUNT's zero.
    if (isinstance(value, exp.Sum) and not distinct and isinstance(operand, exp.Not)
            and isinstance(operand.this, exp.Is) and isinstance(operand.this.this, exp.Column)
            and isinstance(operand.this.expression, exp.Null)):
        column = operand.this.this.name
        return {"function": "sum", "column": column, "distinct": False,
                "input_transform": "is_not_null_indicator", "input_expression": column + " IS NOT NULL"}
    column = "*" if isinstance(operand, exp.Star) else operand.name if isinstance(operand, exp.Column) else None
    if column is None or column == "*" and not isinstance(value, exp.Count):
        return None
    return {"function": type(value).__name__.lower(), "column": column, "distinct": distinct}


def _unaliased(node):
    while isinstance(node, (exp.Alias, exp.Paren, exp.Where, exp.Having)):
        node = node.this
    return node


def _spec_key(spec):
    return (spec["function"], spec["column"].casefold(), bool(spec.get("distinct")), spec.get("input_transform"))


def _aliases(query, table):
    names = {column["name"].casefold() for column in table["columns"]}
    aliases = {}
    for item in query.expressions:
        if isinstance(item, exp.Alias):
            name = item.alias.casefold()
            if name in aliases:
                raise ValueError("중복 출력 별칭은 조건·정렬 근거에서 지원하지 않습니다.")
            value = _unaliased(item)
            if name in names and (not isinstance(value, exp.Column) or value.name.casefold() != name):
                raise ValueError("원본 열과 다른 식에 같은 별칭을 붙인 조건·정렬은 모호하여 지원하지 않습니다.")
            aliases[name] = value
    return aliases


def _resolve(node, query, table, *, alias=False, ordinal=False):
    node = _unaliased(node)
    if ordinal and isinstance(node, exp.Literal) and not node.is_string and node.this.isdigit():
        index = int(node.this)
        if not 1 <= index <= len(query.expressions):
            raise ValueError("정렬 위치가 SELECT 출력 범위를 벗어났습니다.")
        node = _unaliased(query.expressions[index - 1])
    if alias and isinstance(node, exp.Column) and not node.table:
        node = _aliases(query, table).get(node.name.casefold(), node)
    return node


def _column_name(node, query, table):
    names = {column["name"].casefold(): column["name"] for column in table["columns"]}
    if not isinstance(node, exp.Column) or node.name.casefold() not in names or isinstance(node.this, exp.Star):
        raise ValueError("조건·출력·정렬에 원본에 없는 열이 있습니다.")
    source = query.args["from_"].this
    if node.table and node.table.casefold() != source.alias_or_name.casefold():
        raise ValueError("열의 표 별칭이 확인한 원본 표와 다릅니다.")
    if node.args.get("db") or node.args.get("catalog"):
        raise ValueError("외부 스키마로 한정된 열은 지원하지 않습니다.")
    return names[node.name.casefold()]


def _scalar_key(node, query, table, *, alias=False, aggregates=False):
    node = _resolve(node, query, table, alias=alias)
    if isinstance(node, exp.Column):
        return ("column", _column_name(node, query, table).casefold())
    spec = aggregate_spec(node)
    if spec and aggregates:
        if spec["column"] != "*":
            column = next(node.find_all(exp.Column), None)
            _column_name(column, query, table)
        return ("aggregate", *_spec_key(spec))
    if isinstance(node, exp.Null):
        return ("null",)
    if isinstance(node, exp.Literal):
        if node.is_string:
            return ("text", node.this)
        try:
            value = float(node.this) if any(x in node.this.lower() for x in (".", "e")) else int(node.this)
        except ValueError as exc:
            raise ValueError("유한 숫자 상수만 지원합니다.") from exc
        if not math.isfinite(value):
            raise ValueError("유한 숫자 상수만 지원합니다.")
        return ("number", value)
    if isinstance(node, exp.Neg):
        value = _scalar_key(node.this, query, table)
        if value[0] != "number":
            raise ValueError("음수 표기는 숫자 상수에만 지원합니다.")
        return ("number", -value[1])
    raise ValueError("지원 범위는 원본 열·유한 상수·확인한 집계입니다. 함수·산술·윈도우 식은 지원하지 않습니다.")


_COMPARISONS = {exp.EQ: "eq", exp.NEQ: "ne", exp.GT: "gt", exp.GTE: "ge", exp.LT: "lt", exp.LTE: "le"}
_REVERSE_COMPARISON = {"eq": "eq", "ne": "ne", "gt": "lt", "ge": "le", "lt": "gt", "le": "ge"}


def _predicate_key(node, query, table, *, having=False):
    if node is None:
        return None
    node = _unaliased(node)
    if isinstance(node, (exp.And, exp.Or)):
        kind = type(node)
        def flatten(item):
            item = _unaliased(item)
            if isinstance(item, kind):
                return flatten(item.this) + flatten(item.expression)
            return [_predicate_key(item, query, table, having=having)]
        return ("and" if kind is exp.And else "or", *sorted(flatten(node), key=canonical))
    if isinstance(node, exp.Not):
        return ("not", _predicate_key(node.this, query, table, having=having))
    if isinstance(node, exp.Is) and isinstance(node.expression, exp.Null):
        return ("is_null", _scalar_key(node.this, query, table, alias=having, aggregates=having))
    if type(node) in _COMPARISONS:
        left = _scalar_key(node.this, query, table, alias=having, aggregates=having)
        right = _scalar_key(node.expression, query, table, alias=having, aggregates=having)
        operator = _COMPARISONS[type(node)]
        if canonical(left) > canonical(right):
            left, right, operator = right, left, _REVERSE_COMPARISON[operator]
        return (operator, left, right)
    if isinstance(node, exp.Between):
        value = _scalar_key(node.this, query, table, alias=having, aggregates=having)
        low = _scalar_key(node.args["low"], query, table, alias=having, aggregates=having)
        high = _scalar_key(node.args["high"], query, table, alias=having, aggregates=having)
        return ("between", value, low, high)
    if isinstance(node, exp.In) and not node.args.get("query"):
        value = _scalar_key(node.this, query, table, alias=having, aggregates=having)
        choices = [_scalar_key(item, query, table) for item in node.expressions]
        if not choices or any(item[0] not in {"null", "number", "text"} for item in choices):
            raise ValueError("IN은 명시한 상수 목록만 지원합니다.")
        return ("in", value, *sorted(set(choices), key=canonical))
    raise ValueError("조건 근거는 비교·IS NULL/IS NOT NULL·AND/OR/NOT·상수 BETWEEN/IN만 지원합니다.")


def _projection_keys(query, table):
    return [_scalar_key(item, query, table, aggregates=True) for item in query.expressions]


def _order_keys(query, table):
    result = []
    for term in (query.args.get("order").expressions if query.args.get("order") else []):
        node = _resolve(term.this, query, table, alias=True, ordinal=True)
        result.append((_scalar_key(node, query, table, aggregates=True), bool(term.args.get("desc")),
                       bool(term.args.get("nulls_first"))))
    return result


def bounded_query(sql, problem):
    if problem.get("dialect", "sqlite") != "sqlite":
        raise ValueError("이 계산 근거는 SQLite에서만 검증합니다.")
    statements = sqlglot.parse(sql, read="sqlite")
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise ValueError("논리 단계 계산 범위는 단일 SELECT입니다.")
    query = statements[0]
    if any(query.args.get(key) for key in ("with_", "joins", "limit", "offset", "distinct")) or any(query.find_all(exp.Subquery)):
        raise ValueError("이 계산 설명은 단일 표 SELECT만 지원합니다. JOIN/CTE/중첩 질의/LIMIT/SELECT DISTINCT는 상세 근거 미지원입니다.")
    temporal_functions={"date","time","datetime","julianday","strftime","time_to_str","ts_or_ds_to_timestamp",
                        "current_date","current_time","current_timestamp"}
    if any((function.name if isinstance(function,exp.Anonymous) else function.sql_name()).casefold() in temporal_functions
           for function in query.find_all(exp.Func)):
        raise ValueError("시간·날짜 함수가 있는 조건은 반복 실행 사이 같은 입력임을 보장할 수 없어 행·그룹 이유를 추적하지 않습니다.")
    source = query.args.get("from_")
    if not source or not isinstance(source.this, exp.Table):
        raise ValueError("원본 표를 확인할 수 없습니다.")
    table = next((t for t in problem["tables"] if t["name"].casefold() == source.this.name.casefold()), None)
    if table is None:
        raise ValueError("SQL이 원본에 없는 표를 참조합니다.")
    if source.this.args.get("db") or source.this.args.get("catalog"):
        raise ValueError("외부 데이터베이스 표는 지원하지 않습니다.")
    if any(query.find_all(exp.Window)):
        raise ValueError("윈도우 함수는 상세 계산 근거 범위에 포함하지 않습니다.")
    expanded = []
    for item in query.expressions:
        if isinstance(item, exp.Star) or isinstance(item, exp.Column) and isinstance(item.this, exp.Star):
            if isinstance(item, exp.Column) and item.table and item.table.casefold() != source.this.alias_or_name.casefold():
                raise ValueError("별표 출력의 표 별칭이 원본과 다릅니다.")
            expanded.extend(exp.column(c["name"], table=source.this.alias_or_name) for c in table["columns"])
        else:
            expanded.append(item)
    query.set("expressions", expanded)
    _aliases(query, table)
    group = query.args.get("group")
    groups = list(group.expressions) if group else []
    if any(not isinstance(item, exp.Column) for item in groups):
        raise ValueError("그룹 식은 원본 열 이름만 지원합니다.")
    group_names = [_column_name(item, query, table) for item in groups]
    if len(set(name.casefold() for name in group_names)) != len(group_names):
        raise ValueError("중복 그룹 열은 지원하지 않습니다.")
    specs = []
    for item in query.expressions:
        spec = aggregate_spec(item)
        if spec:
            specs.append(spec)
        elif not isinstance(_unaliased(item), exp.Column):
            raise ValueError("출력은 원본 열 또는 COUNT/SUM/AVG와 숫자 MIN/MAX만 지원합니다.")
    projection = _projection_keys(query, table)
    if len(set(projection)) != len(projection):
        raise ValueError("동일한 출력 열·집계의 중복 표시는 현재 상세 판서 근거에서 지원하지 않습니다.")
    group_keys = {("column", name.casefold()) for name in group_names}
    if specs and any(key[0] == "column" and key not in group_keys for key in projection):
        raise ValueError("집계와 함께 출력하는 열은 GROUP BY에 명시되어야 합니다.")
    if not specs and (group_names or query.args.get("having")):
        raise ValueError("집계 없는 GROUP BY/HAVING은 현재 상세 근거 범위에 포함하지 않습니다.")
    _predicate_key(query.args.get("where"), query, table)
    having_key = _predicate_key(query.args.get("having"), query, table, having=True)
    order_keys = _order_keys(query, table)
    if specs:
        for term, _, _ in order_keys:
            if term[0] == "column" and term not in group_keys:
                raise ValueError("집계 정렬의 원본 열은 GROUP BY 열이어야 합니다.")
        if having_key:
            for column in query.args["having"].find_all(exp.Column):
                resolved = _resolve(column, query, table, alias=True)
                if isinstance(resolved, exp.Column) and column.find_ancestor(exp.AggFunc) is None:
                    if _scalar_key(resolved, query, table) not in group_keys:
                        raise ValueError("HAVING의 원본 열은 GROUP BY 열이어야 합니다.")
    return query, table, specs, group_names


def normalized_clause(clause):
    if clause is None:
        return ""
    value = clause.copy()
    for column in value.find_all(exp.Column):
        column.set("table", None)
    for ident in value.find_all(exp.Identifier):
        ident.set("this", ident.name.casefold())
    return value.sql(dialect="sqlite", normalize=True)


def intent_sql(intent):
    aggregates = intent.get("aggregates", [])
    columns = [quote(name) for name in (intent.get("group_by", []) if aggregates else intent.get("select_columns", []))]
    for i, item in enumerate(aggregates):
        function = item["function"].upper()
        if function not in {"COUNT", "SUM", "AVG", "MIN", "MAX"}:
            raise ValueError("지원하지 않는 집계 연산입니다.")
        operand = "*" if item["column"] == "*" else quote(item["column"])
        if item.get("distinct"):
            operand = "DISTINCT " + operand
        columns.append(f"{function}({operand}) AS result_{i + 1}")
    if not columns:
        raise ValueError("출력할 원본 열 또는 집계가 필요합니다.")
    sql = "SELECT " + ", ".join(columns) + " FROM " + quote(intent["table"])
    for key, keyword in (("where", " WHERE "), ("group_by", " GROUP BY "), ("having", " HAVING ")):
        value = intent.get(key)
        if value:
            sql += keyword + (", ".join(quote(x) for x in value) if key == "group_by" else value)
    if intent.get("order_by"):
        terms = []
        for item in intent["order_by"]:
            name = item["column"]
            if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,63}", name):
                term = quote(name)
            else:
                expression = sqlglot.parse_one(name, read="sqlite")
                if not aggregate_spec(expression):
                    raise ValueError("정렬 기준은 원본 열 또는 명시한 집계식이어야 합니다.")
                term = expression.sql(dialect="sqlite")
            direction = item.get("direction", "asc").upper()
            if direction not in {"ASC", "DESC"}:
                raise ValueError("정렬 방향은 ASC 또는 DESC입니다.")
            terms.append(term + " " + direction)
        sql += " ORDER BY " + ", ".join(terms)
    return sql


def intent_unavailable_status(reason):
    """Separate incomplete student intent from an explicit unsupported scope.

    This only classifies a failed original-question parse. It never accepts a
    candidate, supplies a missing operand, or changes the supported SQL subset.
    """
    reason = str(reason or "")
    if re.search(r"미지원|지원하지\s*않|지원하지\s*못|지원\s*범위\s*밖|현재\s*지원.*아닙", reason):
        return "unsupported"
    if (reason.startswith(("입력 의도 확인 필요:", "입력 의도 충돌:"))
            or re.search(r"모호|빠졌|빠진|누락|명시해\s*주세요|지정해\s*주세요|확인해\s*주세요|확인해야", reason)):
        return "needs_input"
    return "unsupported"


def check_intent(sql, problem, question, *, inferred=None):
    intent, scope = inferred if inferred is not None else infer_basic_intent(problem, question)
    if not intent:
        return {"status": intent_unavailable_status(scope), "scope": scope}, None
    try:
        candidate, table, specs, groups = bounded_query(sql, problem)
        expected, expected_table, expected_specs, expected_groups = bounded_query(intent_sql(intent), problem)
        def spec_key(items):
            return [_spec_key(s) for s in items]
        candidate_keys = spec_key(specs)
        expected_keys = spec_key(expected_specs)
        equivalence = []
        if scope == "bounded_language_group_average":
            if candidate.args.get("order"):
                raise ValueError("그룹 평균의 정렬 검증은 지원하지 않습니다. 모델이 추가한 ORDER BY도 자동 수용하지 않습니다.")
            projected_groups = [item.name.casefold() for item in candidate.expressions if isinstance(item, exp.Column)]
            if projected_groups != [name.casefold() for name in expected_groups] or len(candidate.expressions) != 2:
                raise ValueError("각 평균을 구분할 원본 그룹 열이 SELECT 결과에 정확히 한 번 포함되어야 합니다.")
        compared_where = candidate.args.get("where")
        # COUNT(DISTINCT c) already excludes NULL. Removing only this same-column
        # predicate changes neither count nor empty-input behavior. Grouped
        # queries are excluded: the filter could erase all-NULL groups.
        if (len(specs) == len(expected_specs) == 1 and candidate_keys == expected_keys
                and specs[0]["function"] == "count" and specs[0]["distinct"]
                and specs[0]["column"] != "*" and not groups and not expected_groups
                and expected.args.get("where") is None and candidate.args.get("having") is None
                and expected.args.get("having") is None and compared_where is not None):
            predicate = compared_where.this
            if (isinstance(predicate, exp.Not) and isinstance(predicate.this, exp.Is)
                    and isinstance(predicate.this.this, exp.Column) and isinstance(predicate.this.expression, exp.Null)
                    and predicate.this.this.name.casefold() == specs[0]["column"].casefold()):
                equivalence.append({"kind": "count_distinct_same_column_nonnull_filter",
                    "column": specs[0]["column"], "status": "all_inputs_match_including_empty",
                    "scope": "단일 COUNT DISTINCT의 동일 열 IS NOT NULL만; 그룹·다른 조건은 동치 처리하지 않음"})
                compared_where = None
        if len(specs) == len(expected_specs):
            for index, (given, requested) in enumerate(zip(specs, expected_specs)):
                if (given.get("input_transform") == "is_not_null_indicator"
                        and requested["function"] == "count" and not requested["distinct"]
                        and given["column"].casefold() == requested["column"].casefold()
                        and not groups and not expected_groups):
                    trace = "SELECT COUNT(*) AS input_rows FROM " + candidate.args["from_"].this.sql(dialect="sqlite")
                    if candidate.args.get("where"):
                        trace += " " + candidate.args["where"].sql(dialect="sqlite")
                    input_size = execute_sql(trace, fixture(problem))
                    if input_size["status"] != "executed":
                        raise ValueError("조건식 집계의 입력 행 수를 안전하게 확인하지 못했습니다.")
                    count = input_size["rows"][0][0]
                    equivalence.append({"column": given["column"], "candidate_expression": "SUM(" + given["input_expression"] + ")",
                        "requested_expression": "COUNT(" + requested["column"] + ")", "input_row_count": count,
                        "status": "nonempty_input_match" if count else "empty_input_mismatch",
                        "scope": "현재 확정한 입력과 조건에서만 비교; SUM 원문을 COUNT로 바꾸지 않음",
                        "empty_input": {"sum_is_not_null": None, "count_column": 0}})
                    if count:
                        candidate_keys[index] = expected_keys[index]
        same = (table["name"].casefold() == expected_table["name"].casefold()
                and candidate_keys == expected_keys
                and [x.casefold() for x in groups] == [x.casefold() for x in expected_groups]
                and _predicate_key(compared_where, candidate, table) == _predicate_key(expected.args.get("where"), expected, expected_table)
                and _predicate_key(candidate.args.get("having"), candidate, table, having=True)
                    == _predicate_key(expected.args.get("having"), expected, expected_table, having=True)
                and _order_keys(candidate, table) == _order_keys(expected, expected_table))
        candidate_projection = _projection_keys(candidate, table)
        expected_projection = _projection_keys(expected, expected_table)
        aggregate_position = 0
        for index, key in enumerate(candidate_projection):
            if key[0] == "aggregate":
                # Preserve only the already bounded SUM-indicator equivalence.
                candidate_projection[index] = ("aggregate", *candidate_keys[aggregate_position])
                aggregate_position += 1
        same = same and candidate_projection == expected_projection
        return {"status": "supported_match" if same else "mismatch", "scope": scope,
                "requested": intent, "candidate_aggregates": specs,
                "input_bound_equivalence": equivalence,
                "reason": "원문에서 확인한 출력 열·집계·조건·그룹·정렬 구조가 후보 SQL과 일치합니다." if same else
                    "빈 입력의 SUM(열 IS NOT NULL)은 NULL이며 요청한 COUNT(열)의 0과 다릅니다." if any(e["status"] == "empty_input_mismatch" for e in equivalence) else
                    "실행 가능 여부와 별개로 출력 열·집계 대상·NULL 처리·조건·그룹·정렬 중 요청과 다른 부분이 있습니다."}, intent
    except (ValueError, sqlglot.errors.ParseError) as exc:
        return {"status": "unsupported", "scope": scope, "reason": str(exc)}, intent


def _aggregate_logical_evidence(sql, problem, namespace, final_result=None):
    query, table, specs, group_names = bounded_query(sql, problem)
    display = identified_table(problem, table, namespace=namespace)
    names = [c["name"] for c in table["columns"]]
    lookup = {name.casefold(): i for i, name in enumerate(names)}
    if any(s["column"] != "*" and s["column"].casefold() not in lookup for s in specs):
        raise ValueError("집계 열이 원본에 없습니다.")
    source = query.args["from_"].this
    rowid = next((name for name in ("_rowid_", "rowid", "oid") if name.casefold() not in lookup), None)
    if rowid is None:
        raise ValueError("안정적인 행 추적에 필요한 내부 식별자가 모두 가려져 있습니다.")
    qualifier = quote(source.alias_or_name)
    trace = "SELECT " + qualifier + "." + rowid + " - 1 AS row_index FROM " + source.sql(dialect="sqlite")
    if query.args.get("where"):
        trace += " " + query.args["where"].sql(dialect="sqlite")
    filtered = execute_sql(trace, fixture(problem))
    if filtered["status"] != "executed":
        raise ValueError("WHERE 행 추적 실패: " + filtered.get("error", ""))
    indices = [int(row[0]) for row in filtered["rows"]]
    indicator_checks = {}
    for spec in specs:
        if spec.get("input_transform") != "is_not_null_indicator" or spec["column"].casefold() in indicator_checks:
            continue
        column = names[lookup[spec["column"].casefold()]]
        indicator_sql = "SELECT " + qualifier + "." + rowid + " - 1 AS row_index, " + qualifier + "." + quote(column) + " IS NOT NULL AS indicator FROM " + source.sql(dialect="sqlite")
        if query.args.get("where"):
            indicator_sql += " " + query.args["where"].sql(dialect="sqlite")
        actual_inputs = execute_sql(indicator_sql, fixture(problem))
        expected_inputs = [[index, int(table["rows"][index][lookup[column.casefold()]] is not None)] for index in indices]
        if not compare_results(actual_inputs, {"columns": ["row_index", "indicator"], "rows": expected_inputs,
                "row_order": "unordered", "numeric_abs_tolerance": 0}):
            raise ValueError("독립 1/0 조건값과 SQLite 행별 조건 계산이 일치하지 않습니다.")
        indicator_checks[column.casefold()] = {"status": "sqlite_indicator_match", "sql": indicator_sql,
                                               "rows": expected_inputs}
    groups = {}
    for index in indices:
        row = table["rows"][index]
        key = tuple(row[lookup[name.casefold()]] for name in group_names)
        groups.setdefault(key, []).append(index)
    if not group_names and not groups:
        groups[()] = []
    aggregates, computed_rows = [], []
    for number, (key, members) in enumerate(groups.items()):
        group_id = display["id"] + "-group-" + hashlib.sha256(canonical(key).encode()).hexdigest()[:10]
        results = []
        for position, spec in enumerate(specs):
            column = spec["column"]
            col = None if column == "*" else lookup[column.casefold()]
            indicator = spec.get("input_transform") == "is_not_null_indicator"
            included = members if col is None or indicator else [i for i in members if table["rows"][i][col] is not None]
            values = [int(table["rows"][i][col] is not None) if indicator else 1 if col is None else table["rows"][i][col] for i in included]
            if spec["distinct"]:
                unique = []
                seen = []
                for index, value in zip(included, values):
                    if value not in seen:
                        seen.append(value)
                        unique.append(index)
                included, values = unique, seen
            count = len(values)
            if spec["function"] in {"sum", "avg"} and any(not isinstance(v, (int, float)) for v in values):
                raise ValueError("SUM/AVG 중간 계산은 숫자 열만 지원합니다.")
            if spec["function"] in {"min", "max"} and (table["columns"][col]["type"] not in {"INTEGER", "REAL", "NUMERIC"}
                    or any(type(v) not in {int, float} for v in values)):
                raise ValueError("MIN/MAX 중간 계산은 숫자 열만 지원합니다. 문자열·혼합 자료형의 SQLite 정렬 규칙은 이 설명 범위에 포함하지 않습니다.")
            total = sum(values) if values and spec["function"] in {"sum", "avg"} else None
            if spec["function"] == "count":
                value = count
            elif spec["function"] == "sum":
                value = total
            elif spec["function"] == "avg":
                value = total / count if count else None
            else:
                value = (min(values) if spec["function"] == "min" else max(values)) if values else None
            results.append(value)
            aggregate = {"id": f"{group_id}-aggregate-{position}", "group_id": group_id, "group_values": list(key),
                **spec, "included_values": values, "count": count, "sum": total, "result": value,
                "included_row_ids": [display["row_ids"][i] for i in included],
                "included_cell_ids": [] if col is None else [display["cell_ids"][i][col] for i in included],
                "excluded_null_cell_ids": [] if col is None or indicator else [display["cell_ids"][i][col] for i in members if table["rows"][i][col] is None]}
            if indicator:
                aggregate["input_rows"] = [{"row_id": display["row_ids"][i], "cell_id": display["cell_ids"][i][col],
                    "source_value": table["rows"][i][col], "value": int(table["rows"][i][col] is not None)} for i in members]
                aggregate["input_trace_check"] = indicator_checks[column.casefold()]
            aggregates.append(aggregate)
        row, aggregate_index = [], 0
        for item in query.expressions:
            if aggregate_spec(item):
                row.append(results[aggregate_index]); aggregate_index += 1
            else:
                name = _unaliased(item).name.casefold()
                row.append(key[[g.casefold() for g in group_names].index(name)])
        computed_rows.append(row)
    unfiltered = query.copy()
    unfiltered.set("having", None)
    unfiltered.set("order", None)
    intermediate = execute_sql(unfiltered.sql(dialect="sqlite"), fixture(problem))
    expected = {"columns": intermediate.get("columns", []), "rows": computed_rows, "row_order": "unordered", "numeric_abs_tolerance": 1e-8}
    if not compare_results(intermediate, expected):
        raise ValueError("독립 집계 계산과 SQLite 중간 결과가 일치하지 않습니다.")
    # Preserve the original projection and HAVING aliases while adding group
    # keys for provenance. Matching only displayed result values is ambiguous
    # when two different groups have the same aggregate result.
    survival_query = query.copy()
    group_expressions = query.args["group"].expressions if group_names else [exp.Literal.number(1)]
    survival_query.set("expressions", [item.copy() for item in query.expressions] + [
        exp.alias_(item.copy(), f"__teaching_group_{i}") for i, item in enumerate(group_expressions)])
    survival = execute_sql(survival_query.sql(dialect="sqlite"), fixture(problem))
    if survival["status"] != "executed":
        raise ValueError("HAVING 그룹 추적 실패: " + survival.get("error", ""))
    width = len(query.expressions)
    final_result = final_result or execute_sql(sql, fixture(problem))
    # sqlglot spells IS NOT NULL as NOT ... IS NULL. SQLite uses the SQL
    # spelling as an unaliased output label, so identical AST projections can
    # have different labels in the tracing query. Bind only proven identical
    # projection positions to the untouched original query's output labels.
    if (query.expressions != survival_query.expressions[:width]
            or len(final_result.get("columns", [])) != width):
        raise ValueError("추적 질의의 출력 위치를 원본 SELECT와 연결하지 못했습니다.")
    projection_binding = {"status": "same_ast_projection_positions", "original_columns": final_result["columns"],
                          "trace_columns": survival["columns"][:width]}
    projected = {"status":"executed", "columns":final_result["columns"],
                 "rows":[row[:width] for row in survival["rows"]]}
    if not compare_results(projected, {"columns":final_result.get("columns", []),
            "rows":final_result.get("rows", []), "row_order":"ordered" if query.args.get("order") else "unordered", "numeric_abs_tolerance":1e-8}):
        raise ValueError("그룹 추적과 원본 SELECT 결과가 일치하지 않습니다.")
    surviving_keys = {tuple(row[width:]) if group_names else () for row in survival["rows"]}
    intermediate["columns"] = list(final_result["columns"])
    where = query.args.get("where")
    return {"kind": "logical_teaching_steps_not_physical_execution", "table_id": display["id"],
            "where_sql": where.sql(dialect="sqlite") if where else None,
            "where_columns": list(dict.fromkeys(names[lookup[column.name.casefold()]] for column in where.find_all(exp.Column))) if where else [],
            "filtered_row_ids": [display["row_ids"][i] for i in indices],
            "group_columns": group_names, "groups": [{"values": list(key), "row_ids": [display["row_ids"][i] for i in members],
                "having_passed": key in surviving_keys} for key, members in groups.items()],
            "aggregates": aggregates, "before_having": intermediate,
            "ordered_group_values": [list(row[width:]) if group_names else [] for row in survival["rows"]],
            "projection_binding": projection_binding,
            "having_sql": query.args["having"].sql(dialect="sqlite") if query.args.get("having") else None}



def _strict_table_values(table):
    for column_index, column in enumerate(table["columns"]):
        for row in table["rows"]:
            value = row[column_index]
            if value is None:
                continue
            if column["type"] == "TEXT" and not isinstance(value, str):
                raise ValueError("TEXT 열의 숫자 자동 변환은 독립 중간 계산에서 지원하지 않습니다.")
            if column["type"] != "TEXT" and (type(value) not in {int, float} or not math.isfinite(value)):
                raise ValueError("숫자 열의 혼합 자료형은 독립 중간 계산에서 지원하지 않습니다.")


def _scalar_value(key, row, lookup, aggregate_values=None):
    kind = key[0]
    if kind == "column":
        return row[lookup[key[1]]]
    if kind == "aggregate":
        if aggregate_values is None or tuple(key[1:]) not in aggregate_values:
            raise ValueError("조건·정렬에서 참조하는 집계의 독립 계산 근거가 없습니다.")
        return aggregate_values[tuple(key[1:])]
    if kind == "null":
        return None
    if kind in {"text", "number"}:
        return key[1]
    raise ValueError("지원하지 않는 값 계산입니다.")


def _comparison(operator, left, right):
    if left is None or right is None:
        return None
    numeric = type(left) in {int, float} and type(right) in {int, float}
    textual = isinstance(left, str) and isinstance(right, str)
    if not numeric and not textual:
        raise ValueError("비교의 문자열·숫자 강제 변환은 추정하지 않습니다. 같은 자료형의 조건을 확인하세요.")
    return {"eq": lambda: left == right, "ne": lambda: left != right,
            "gt": lambda: left > right, "ge": lambda: left >= right,
            "lt": lambda: left < right, "le": lambda: left <= right}[operator]()


def _key_sql(key):
    kind = key[0]
    if kind == "column":
        return quote(key[1])
    if kind == "aggregate":
        _, function, column, distinct, transform = key
        operand = quote(column) if column != "*" else "*"
        if transform:
            operand += " IS NOT NULL"
        return function.upper() + "(" + ("DISTINCT " if distinct else "") + operand + ")"
    if kind == "null":
        return "NULL"
    if kind == "text":
        return "'" + key[1].replace("'", "''") + "'"
    if kind == "number":
        return str(key[1])
    if kind == "is_null":
        return _key_sql(key[1]) + " IS NULL"
    if kind == "not":
        return "NOT (" + _key_sql(key[1]) + ")"
    if kind in {"and", "or"}:
        return "(" + (" " + kind.upper() + " ").join(_key_sql(part) for part in key[1:]) + ")"
    if kind == "between":
        return _key_sql(key[1]) + " BETWEEN " + _key_sql(key[2]) + " AND " + _key_sql(key[3])
    if kind == "in":
        return _key_sql(key[1]) + " IN (" + ", ".join(_key_sql(x) for x in key[2:]) + ")"
    return _key_sql(key[1]) + " " + {"eq": "=", "ne": "<>", "gt": ">", "ge": ">=", "lt": "<", "le": "<="}[kind] + " " + _key_sql(key[2])


def _evaluate_predicate(key, row, lookup, aggregate_values=None, comparisons=None):
    if key is None:
        return True
    kind = key[0]
    if kind in {"and", "or"}:
        parts = [_evaluate_predicate(item, row, lookup, aggregate_values, comparisons) for item in key[1:]]
        if kind == "and":
            return False if False in parts else None if None in parts else True
        return True if True in parts else None if None in parts else False
    if kind == "not":
        part = _evaluate_predicate(key[1], row, lookup, aggregate_values, comparisons)
        value = None if part is None else not part
        if comparisons is not None:
            comparisons.append({"sql": _key_sql(key), "left": part, "right": None,
                                "truth": value, "operator": "not"})
        return value
    left = _scalar_value(key[1], row, lookup, aggregate_values)
    if kind == "is_null":
        right, value = None, left is None
    elif kind == "between":
        right = [_scalar_value(k, row, lookup, aggregate_values) for k in key[2:]]
        parts = [_comparison("ge", left, right[0]), _comparison("le", left, right[1])]
        value = False if False in parts else None if None in parts else True
    elif kind == "in":
        right = [_scalar_value(k, row, lookup, aggregate_values) for k in key[2:]]
        parts = [_comparison("eq", left, item) for item in right]
        value = True if True in parts else None if None in parts else False
    else:
        right = _scalar_value(key[2], row, lookup, aggregate_values)
        value = _comparison(kind, left, right)
    if comparisons is not None:
        comparisons.append({"sql": _key_sql(key), "left": left, "right": right, "truth": value, "operator": kind})
    return value


def _independent_rows(query, table, display):
    _strict_table_values(table)
    lookup = {column["name"].casefold(): i for i, column in enumerate(table["columns"])}
    predicate = _predicate_key(query.args.get("where"), query, table)
    rows = []
    for index, row in enumerate(table["rows"]):
        comparisons = []
        truth = _evaluate_predicate(predicate, row, lookup, comparisons=comparisons)
        rows.append({"row_id": display["row_ids"][index], "index": index, "truth": truth,
                     "included": truth is True, "comparisons": comparisons})
    return rows


def _order_terms(query, table):
    return [{"column": _key_sql(key).replace('"', ''), "direction": "DESC" if desc else "ASC",
             "nulls_first": nulls_first} for key, desc, nulls_first in _order_keys(query, table)]


def _order_compare(left, right, order):
    for index, (_, desc, nulls_first) in enumerate(order):
        first, second = left[index], right[index]
        if first is None or second is None:
            comparison = 0 if first is second else (-1 if first is None else 1) * (1 if nulls_first else -1)
        elif type(first) in {int, float} and type(second) in {int, float} or isinstance(first, str) and isinstance(second, str):
            comparison = (first > second) - (first < second)
            if desc:
                comparison = -comparison
        else:
            raise ValueError("정렬의 혼합 자료형·특수 COLLATE는 독립 근거 범위 밖입니다.")
        if comparison:
            return comparison
    return 0


def _checked_order(actual_ids, expected_ids, values, order):
    if len(actual_ids) != len(expected_ids) or set(actual_ids) != set(expected_ids):
        raise ValueError("독립 조건 계산과 SQLite에 남은 원본 행·그룹이 다릅니다.")
    if order and any(_order_compare(values[a], values[b], order) > 0 for a, b in zip(actual_ids, actual_ids[1:])):
        raise ValueError("다중 정렬의 독립 비교와 SQLite 순서가 일치하지 않습니다.")
    ties = {}
    for identity in actual_ids:
        ties.setdefault(canonical(values[identity]), []).append(identity)
    return [members for members in ties.values() if order and len(members) > 1]


def _projection_logical_evidence(query, table, problem, namespace, final_result):
    display = identified_table(problem, table, namespace=namespace)
    names = [column["name"] for column in table["columns"]]
    lookup = {name.casefold(): i for i, name in enumerate(names)}
    evaluated = _independent_rows(query, table, display)
    kept = [row["index"] for row in evaluated if row["included"]]
    keys = _projection_keys(query, table)
    projection_columns = [names[lookup[key[1]]] for key in keys]
    expected_rows = [[table["rows"][index][lookup[key[1]]] for key in keys] for index in kept]
    if not compare_results(final_result, {"columns": final_result["columns"], "rows": expected_rows,
                                          "row_order": "unordered", "numeric_abs_tolerance": 1e-8}):
        raise ValueError("독립 WHERE·출력 열 계산과 SQLite 최종 행이 일치하지 않습니다.")
    rowid = next((name for name in ("_rowid_", "rowid", "oid") if name.casefold() not in lookup), None)
    if rowid is None:
        raise ValueError("안정적인 행 추적에 필요한 내부 식별자가 모두 가려져 있습니다.")
    trace = query.copy()
    source = query.args["from_"].this
    row_expression = exp.Sub(this=exp.column(rowid, table=source.alias_or_name), expression=exp.Literal.number(1))
    trace.set("expressions", [item.copy() for item in query.expressions] + [exp.alias_(row_expression, "__teaching_row_index")])
    tracked = execute_sql(trace.sql(dialect="sqlite"), fixture(problem))
    if tracked["status"] != "executed":
        raise ValueError("SELECT 원본 행 추적 실패: " + tracked.get("error", ""))
    width = len(keys)
    queues = {}
    for row in tracked["rows"]:
        queues.setdefault(canonical(row[:width]), []).append(int(row[width]))
    actual_indices = []
    for row in final_result["rows"]:
        queue = queues.get(canonical(row))
        if not queue:
            raise ValueError("출력 행을 원본 행 추적과 연결하지 못했습니다.")
        actual_indices.append(queue.pop(0))
    order = _order_keys(query, table)
    values = {index: [_scalar_value(key, table["rows"][index], lookup) for key, _, _ in order] for index in kept}
    ties = _checked_order(actual_indices, kept, values, order)
    where = query.args.get("where")
    result_ids = [display["row_ids"][index] for index in actual_indices]
    return {"kind": "projection_teaching_steps", "table_id": display["id"],
            "where_sql": where.sql(dialect="sqlite") if where else None,
            "where_columns": list(dict.fromkeys(_column_name(c, query, table) for c in where.find_all(exp.Column))) if where else [],
            "filtered_row_ids": [display["row_ids"][i] for i in kept],
            "row_evaluations": evaluated, "projection_columns": projection_columns,
            "ordered_row_ids": result_ids, "result_row_ids": result_ids,
            "order_by": _order_terms(query, table), "ordering_guaranteed": bool(order),
            "order_ties": [{"row_ids": [display["row_ids"][i] for i in tie], "values": values[tie[0]]} for tie in ties],
            "tie_order_guaranteed": False,
            "before_order": {"columns": final_result["columns"], "rows": expected_rows,
                             "row_ids": [display["row_ids"][i] for i in kept]},
            "group_columns": [], "groups": [], "aggregates": [], "having_sql": None,
            "projection_binding": {"status": "independent_source_columns_and_sqlite_row_trace",
                                   "original_columns": final_result["columns"], "source_columns": projection_columns},
            "independent_checks": ["where_three_valued_logic", "source_projection", "result_multiset",
                                   "source_row_binding", "sqlite_binary_multi_order"],
            "scope": "SQLite single-table source columns, explicit predicates and multi-key ordering. No ORDER BY means no promised row order; equal complete sort keys have no promised tie order."}


def _compute_aggregate(spec_key, members, table, lookup):
    function, column, distinct, transform = spec_key
    ci = None if column == "*" else lookup[column]
    values = [int(row[ci] is not None) if transform else 1 if ci is None else row[ci] for row in members]
    values = [value for value in values if value is not None]
    if distinct:
        values = list(dict.fromkeys(values))
    if function == "count":
        return len(values)
    if any(type(value) not in {int, float} for value in values):
        raise ValueError("HAVING/ORDER BY 집계의 독립 계산은 숫자 열만 지원합니다.")
    if not values:
        return None
    if function == "sum":
        return sum(values)
    if function == "avg":
        return sum(values) / len(values)
    return min(values) if function == "min" else max(values)


def _aggregate_keys_in(key):
    if key is None:
        return []
    if key[0] == "aggregate":
        return [tuple(key[1:])]
    return [found for item in key[1:] if isinstance(item, tuple) for found in _aggregate_keys_in(item)]


def _group_identity(values):
    # SQLite INTEGER/NUMERIC affinity may emit 0 for a supplied 0.0. This is
    # the same numeric group, but a JSON spelling comparison would split it.
    return canonical([int(value) if isinstance(value, float) and value.is_integer() else value for value in values])


def logical_evidence(sql, problem, namespace, final_result=None):
    query, table, specs, group_names = bounded_query(sql, problem)
    final_result = final_result or execute_sql(sql, fixture(problem))
    if not specs:
        return _projection_logical_evidence(query, table, problem, namespace, final_result)
    display = identified_table(problem, table, namespace=namespace)
    evaluations = _independent_rows(query, table, display)
    logical = _aggregate_logical_evidence(sql, problem, namespace, final_result)
    filtered = [row["row_id"] for row in evaluations if row["included"]]
    if set(filtered) != set(logical["filtered_row_ids"]):
        raise ValueError("독립 WHERE의 TRUE/FALSE/UNKNOWN 계산과 SQLite 행 추적이 다릅니다.")
    lookup = {column["name"].casefold(): i for i, column in enumerate(table["columns"])}
    row_lookup = {row_id: table["rows"][i] for i, row_id in enumerate(display["row_ids"])}
    having = _predicate_key(query.args.get("having"), query, table, having=True)
    projection = _projection_keys(query, table)
    order = _order_keys(query, table)
    needed = set(_aggregate_keys_in(having))
    for key in projection + [term[0] for term in order]:
        needed.update(_aggregate_keys_in(key))
    expected_ids, before_rows, order_values, group_evaluations = [], [], {}, []
    for group in logical["groups"]:
        members = [row_lookup[row_id] for row_id in group["row_ids"]]
        representative = [None] * len(lookup)
        for name, value in zip(group_names, group["values"]):
            representative[lookup[name.casefold()]] = value
        aggregates = {key: _compute_aggregate(key, members, table, lookup) for key in needed}
        comparisons = []
        truth = _evaluate_predicate(having, representative, lookup, aggregates, comparisons)
        if (truth is True) != group["having_passed"]:
            raise ValueError("독립 HAVING 조건과 SQLite의 그룹 포함 결과가 다릅니다.")
        group_evaluations.append({"group_values": group["values"], "truth": truth,
                                 "included": truth is True, "comparisons": comparisons})
        if truth is True:
            key = _group_identity(group["values"])
            expected_ids.append(key)
            before_rows.append([_scalar_value(item, representative, lookup, aggregates) for item in projection])
            order_values[key] = [_scalar_value(item, representative, lookup, aggregates) for item, _, _ in order]
    if not compare_results(final_result, {"columns": final_result["columns"], "rows": before_rows,
                                          "row_order": "unordered", "numeric_abs_tolerance": 1e-8}):
        raise ValueError("독립 그룹·HAVING·출력 계산과 SQLite 결과가 다릅니다.")
    actual_ids = [_group_identity(values) for values in logical["ordered_group_values"]]
    ties = _checked_order(actual_ids, expected_ids, order_values, order)
    logical.update(row_evaluations=evaluations, having_evaluations=group_evaluations,
                   order_by=_order_terms(query, table), ordering_guaranteed=bool(order), tie_order_guaranteed=False,
                   before_order={"columns": final_result["columns"], "rows": before_rows},
                   order_ties=[{"group_values": [json.loads(key) for key in tie],
                                "values": order_values[tie[0]]} for tie in ties],
                   independent_checks=["where_three_valued_logic", "aggregate_values", "having_three_valued_logic",
                                       "result_multiset", "sqlite_binary_multi_order"])
    return logical


def verify_answer(problem, raw_response, question, hypothesis=None):
    started = time.perf_counter()
    timings = {"extraction": 0.0, "intent": 0.0, "execution": 0.0, "logical_trace": 0.0}
    base = copy.deepcopy(problem)
    scope_problem, hypothesis_value = derive_hypothesis(base, hypothesis) if hypothesis else (base, None)
    scenario = "hypothesis" if hypothesis_value else "original"
    evidence = {"id": "evidence-" + hashlib.sha256(canonical({"problem": base, "hypothesis": hypothesis_value, "question": question}).encode()).hexdigest()[:20],
        "problem_id": base["id"], "problem_revision": base["revision"], "task_kind":base["task_kind"], "scenario": scenario, "hypothesis": hypothesis_value,
        "input": {"status": "user_confirmed" if base["confirmed"] else "unconfirmed", "source": base["source"]},
        "schema": {"status": "not_checked"}, "execution": {"status": "not_run", "dialect": base["dialect"]},
        "calculation": {"status": "not_checked"}, "intent": {"status": "not_checked"},
        "expected_result_check": {"status": "not_available", "reason": "실사용 문제에 독립 정답이 제공되지 않았습니다."},
        "explanation": {"status": "not_verified"}, "human_review": "not_reviewed",
        "original_tables": [identified_table(base, t) for t in base["tables"]],
        "working_tables": [identified_table(scope_problem, t, namespace=scenario) for t in scope_problem["tables"]],
        "result": None, "logical_steps": None, "status": "needs_input", "can_repair": False, "reasons": [],
        "support_status": "needs_input"}
    def finish():
        timings["total"] = round(time.perf_counter() - started, 6)
        evidence["timings_seconds"] = {key: round(value, 6) for key, value in timings.items()}
        return evidence
    def stop(reason, status="needs_input", repair=False):
        evidence.update(status=status, reasons=[reason], can_repair=repair)
        if status == "needs_input":
            evidence["support_status"] = "needs_input"
        elif evidence["schema"].get("status") == "failed":
            evidence["support_status"] = "invalid_candidate_or_mismatch"
        elif status in {"unsupported", "concept_unverified"} or evidence["intent"].get("status") == "unsupported":
            evidence["support_status"] = "unsupported_intent"
        else:
            evidence["support_status"] = "invalid_candidate_or_mismatch"
        return finish()
    if base["task_kind"] == "concept":
        return stop("일반 설명은 자동 진실성 검증 대상이 아닙니다. 새 예시는 설명용으로 표시합니다.", "concept_unverified")
    if not base["confirmed"]:
        return stop("원본 표·SQL·조건을 확인하고 확정해 주세요.")
    if base["missing_conditions"]:
        return stop("필요한 조건: " + "; ".join(base["missing_conditions"]))
    if base["dialect"] != "sqlite":
        return stop(f"{base['dialect']} 문제는 SQLite로 정확성을 검증하지 않습니다. DBMS에 맞는 실행 결과 또는 조건이 필요합니다.", "unsupported")
    if not base["tables"]:
        return stop("수치 결과를 계산할 원본 표의 열 이름·자료형·행 값이 필요합니다.")
    supplied = base["task_kind"] in {"query_result", "explain_error"}
    if supplied:
        sql = base.get("query")
        if not sql:
            # Aggregate requests with no supplied SQL can still be computed
            # from an unambiguous, bounded requested intent.
            section = time.perf_counter()
            intent, reason = infer_basic_intent(base, base["raw_text"])
            timings["intent"] += time.perf_counter() - section
            if not intent:
                return stop("실행할 원문 SQL이 필요합니다. " + reason)
            try:
                sql = intent_sql(intent)
            except (ValueError, sqlglot.errors.ParseError) as exc:
                return stop("원문의 명확한 출력·조건을 확인해 주세요. " + str(exc))
            evidence["intent"] = {"status": "supported_match", "scope": reason, "requested": intent}
            evidence["sql_origin"] = "application_from_confirmed_bounded_intent"
        else:
            evidence["intent"] = {"status": "given_query_result", "scope": "학생이 제공한 SQL 자체의 실행 결과. 그 SQL이 다른 자연어 목적에 맞는지는 별개입니다."}
            evidence["sql_origin"] = "unchanged_user_query"
    else:
        # A missing student operand/aggregate target cannot be repaired from
        # whatever SQL the model happened to emit. Classify it before candidate
        # extraction or execution, preserving all raw response data upstream.
        section = time.perf_counter()
        original_intent = infer_basic_intent(base, base["raw_text"])
        timings["intent"] += time.perf_counter() - section
        if not original_intent[0] and intent_unavailable_status(original_intent[1]) == "needs_input":
            evidence["intent"] = {"status": "needs_input", "scope": original_intent[1]}
            return stop(original_intent[1])
        section = time.perf_counter()
        try:
            evidence["sql_extraction_protocol"] = SQL_EXTRACTION_PROTOCOL
            sql = extract_sql_candidate(raw_response)
        except ValueError:
            timings["extraction"] += time.perf_counter() - section
            return stop("모델 SQL 후보를 명확히 추출하지 못했습니다.", "stopped", True)
        timings["extraction"] += time.perf_counter() - section
        evidence["sql_origin"] = "model_candidate"
        section = time.perf_counter()
        evidence["intent"], _ = check_intent(sql, base, base["raw_text"], inferred=original_intent)
        timings["intent"] += time.perf_counter() - section
    evidence["sql"] = sql
    section = time.perf_counter()
    actual = execute_sql(sql, fixture(scope_problem), dialect=base["dialect"])
    timings["execution"] += time.perf_counter() - section
    evidence["execution"] = {**actual, "dialect": base["dialect"]}
    if actual["status"] != "executed":
        evidence["schema"] = {"status": "failed", "reason": actual.get("error")}
        return stop("원문 스키마에서 SQL을 실행하지 못했습니다: " + actual.get("error", actual["status"]), "stopped", not supplied)
    evidence["schema"] = {"status": "resolved_by_sqlite_prepare", "scope": "별칭·CTE를 포함한 SQLite 이름 해석과 안전한 실행"}
    if evidence["intent"]["status"] not in {"given_query_result", "supported_match"}:
        return stop(evidence["intent"].get("reason", evidence["intent"].get("scope", "질문 의도 확인 불가")), "stopped", evidence["intent"]["status"] == "mismatch")
    evidence["result"] = {"columns": actual["columns"], "rows": actual["rows"]}
    section = time.perf_counter()
    try:
        evidence["logical_steps"] = logical_evidence(sql, scope_problem, scenario, actual)
        projection = evidence["logical_steps"]["kind"] == "projection_teaching_steps"
        evidence["calculation"] = {"status": "independent_projection_match" if projection else "independent_aggregate_match",
            "scope": "원본 조건의 3값 논리·출력 열·다중 정렬을 독립 계산하여 SQLite와 비교" if projection else
                "원본 WHERE·집계·HAVING·다중 정렬을 별도 계산하여 SQLite 결과와 비교"}
        evidence["support_status"] = "verified_lesson_evidence"
    except (ValueError, KeyError, sqlglot.errors.ParseError) as exc:
        evidence["calculation"] = {"status": "outside_supported_trace", "reason": str(exc)}
        evidence["support_status"] = "verified_no_plan"
    timings["logical_trace"] += time.perf_counter() - section
    evidence.update(status="verified", can_repair=False)
    evidence["explanation"] = {"status": "tool_derived_numeric_statements_only", "scope": "수치·표·조건·정렬·집계 대사만 공유 근거에서 생성. 모델 자유 설명 전체는 검증하지 않음."}
    return finish()


def display_answer(evidence):
    if evidence["status"] != "verified":
        return "확인 필요: " + " ".join(evidence["reasons"])
    prefix = "설명용 새 가정의 결과입니다. 원래 문제의 값은 바꾸지 않았습니다.\n" if evidence["scenario"] == "hypothesis" else "확정한 원본 문제를 기준으로 도구가 계산한 결과입니다. 모델 초안과 구분합니다.\n"
    if evidence.get("app_correction"):
        prefix += "모델 SQL에 질문 의도와 다른 부분이 있어 앱이 확인된 연산으로 다시 구성했습니다. 원시 답변과 오류 기록은 보존했습니다.\n"
    if evidence.get("raw_model_explanation", {}).get("status") == "detected_contradiction":
        prefix += "모델 초안의 결과·개념 모순을 그대로 읽지 않고 확인한 계산 근거로 설명합니다.\n"
    result = evidence["result"]
    lines = [" | ".join(result["columns"])]
    lines.extend(" | ".join("NULL" if v is None else str(v) for v in row) for row in result["rows"])
    if not result["rows"]:
        lines.append("결과 행이 없습니다.")
    sql = "```sql\n" + evidence["sql"] + "\n```\n" if evidence.get("task_kind") == "write_sql" else ""
    return prefix + sql + "\n".join(lines)
