"""Explicit v2 result comparison; the frozen v1 grader remains unchanged.

Column aliases are required only when the question's contract requires them.
Unordered results preserve duplicate multiplicity, including with numeric tolerances.
This checks one supplied result fixture, not general SQL semantic equivalence.
"""
from __future__ import annotations

import math


def _cell_equal(left, right, absolute, relative):
    if left is None or right is None:
        return left is right
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return (math.isfinite(left) and math.isfinite(right)
                and math.isclose(left, right, abs_tol=absolute, rel_tol=relative))
    return type(left) is type(right) and left == right


def compare_results_v2(actual, expected, *, columns_required=True):
    """Return auditable row/name verdicts, keeping positional column order.

    ``columns_required=False`` permits unspecified result aliases; it never drops,
    reorders or merges columns. Numeric tolerances must be explicitly nonnegative.
    A complete bipartite matching avoids greedy false negatives when tolerance
    intervals overlap. Result sizes retain the sandbox's 1,000-row upper bound.
    """
    absolute = float(expected.get("numeric_abs_tolerance", 0))
    relative = float(expected.get("numeric_rel_tolerance", 0))
    if not all(math.isfinite(value) and value >= 0 for value in (absolute, relative)):
        raise ValueError("Numeric tolerances must be finite and nonnegative")
    order = expected.get("row_order", "unordered")
    if order not in {"ordered", "unordered", "multiset"}:
        raise ValueError("Unknown row ordering policy")
    verdict = {"match": False, "reason": None, "column_names_match": False,
               "rows_match": False, "comparison_policy": {
                   "version": 2, "column_names_required": columns_required,
                   "column_positions_required": True, "row_order": order,
                   "numeric_abs_tolerance": absolute, "numeric_rel_tolerance": relative,
                   "duplicate_multiplicity": "preserved", "null_equals_only_null": True}}
    if actual.get("status") != "executed":
        return {**verdict, "reason": "not_executed"}
    names, wanted_names = actual.get("columns", []), expected["columns"]
    verdict["column_names_match"] = names == wanted_names
    rows, wanted = actual.get("rows", []), expected["rows"]
    width = len(wanted_names)
    if len(names) != width or any(len(row) != width for row in [*rows, *wanted]):
        return {**verdict, "reason": "column_arity_mismatch"}
    if len(rows) != len(wanted):
        return {**verdict, "reason": "row_count_mismatch"}
    if len(rows) > 1000:
        raise ValueError("Comparison row limit exceeded")
    equal = lambda a, b: all(_cell_equal(x, y, absolute, relative) for x, y in zip(a, b))
    if order == "ordered":
        matched = all(equal(left, right) for left, right in zip(rows, wanted))
    else:
        # Exact matches first; the augmenting-path search can still reassign them.
        edges = [[j for j, right in enumerate(wanted) if equal(left, right)] for left in rows]
        assignment = {}

        def augment(start):
            # Iterative search also avoids recursion limits for repeated rows.
            pending = [start]
            seen_left = {start}
            seen_right = set()
            parent = {}
            while pending:
                left = pending.pop()
                for right in edges[left]:
                    if right in seen_right:
                        continue
                    seen_right.add(right)
                    parent[right] = left
                    if right not in assignment:
                        while True:
                            owner = parent[right]
                            old = next((r for r, l in assignment.items() if l == owner), None)
                            assignment[right] = owner
                            if old is None:
                                return True
                            right = old
                    owner = assignment[right]
                    if owner not in seen_left:
                        seen_left.add(owner)
                        pending.append(owner)
            return False

        matched = all(augment(i) for i in sorted(range(len(rows)), key=lambda i: len(edges[i])))
    verdict["rows_match"] = matched
    verdict["match"] = matched and (not columns_required or verdict["column_names_match"])
    verdict["reason"] = ("match" if verdict["match"] else "column_names_mismatch"
                         if matched else "row_values_or_order_mismatch")
    return verdict
