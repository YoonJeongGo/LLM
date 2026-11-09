"""Bounded requested comparisons rendered from the same proved source rows.

This is not a free-language entailment evaluator. Its audit lists the requests
it recognizes and the exact evidence/steps used, and never approves model prose.
"""
from __future__ import annotations

import copy
import re


class UnmetExplanation(ValueError):
    def __init__(self, reason, audit):
        super().__init__(reason)
        self.audit = audit


def ordering_comparisons(logical, table):
    """Explain adjacent, independently verified source rows, not model prose."""
    from edu_tutor.problems.evidence import _order_compare
    from .verified import value_text

    rules = logical.get("order_by") or []
    if logical.get("kind") != "projection_teaching_steps" or not rules:
        return None
    lookup = {name.casefold(): ci for ci, name in enumerate(table["columns"])}
    columns = [lookup[rule["column"].casefold()] for rule in rules]
    by_id = {rid: ri for ri, rid in enumerate(table["row_ids"])}
    ordered = logical["ordered_row_ids"]
    if len(ordered) != len(set(ordered)) or set(ordered) != set(logical["filtered_row_ids"]):
        raise ValueError("정렬 결과의 원본 행 연결이 조건 통과 행과 다릅니다.")
    order = [(rule["column"], rule["direction"].upper() == "DESC", rule["nulls_first"]) for rule in rules]
    values = {rid: [table["rows"][by_id[rid]][ci] for ci in columns] for rid in ordered}
    # A unique text column may name source rows. Row numbers remain explicit,
    # so names are never guessed from the model response or the question.
    label_column = next((ci for ci in range(len(table["columns"]))
        if table["rows"] and all(isinstance(row[ci], str) for row in table["rows"])
        and len({row[ci] for row in table["rows"]}) == len(table["rows"])), None)

    def label(rid):
        ri = by_id[rid]
        return f"원본 {ri + 1}행" + (f"({table['columns'][label_column]}={value_text(table['rows'][ri][label_column])})"
                                    if label_column is not None else "")

    sentences = []
    null_placement = []
    for index, rule in enumerate(rules):
        null_ids = [rid for rid in ordered if values[rid][index] is None]
        if null_ids:
            scope = "앞 기준이 같은 행 안에서 " if index else ""
            direction = "오름차순" if rule["direction"].upper() == "ASC" else "내림차순"
            placement = "앞" if rule["nulls_first"] else "뒤"
            sentences.append(f"이번 SQLite 정렬의 {rule['column']} {direction}은 {scope}NULL을 {placement}에 둡니다.")
            null_placement.append({"column": rule["column"], "nulls_first": rule["nulls_first"], "source_row_ids": null_ids})
    pairs = []
    for left, right in zip(ordered, ordered[1:]):
        lv, rv = values[left], values[right]
        comparison = _order_compare(lv, rv, order)
        if comparison > 0:
            raise ValueError("행별 정렬 비교가 검증된 SQL 결과 순서와 다릅니다.")
        first = next((i for i, (a, b) in enumerate(zip(lv, rv)) if a != b), None)
        same = ", ".join(f"{rules[i]['column']}={value_text(lv[i])}" for i in range(first if first is not None else len(rules)))
        record = {"before_row_id": left, "after_row_id": right, "left_values": lv, "right_values": rv,
                  "first_different_key": None if first is None else rules[first]["column"],
                  "equal_prefix_length": len(rules) if first is None else first, "order_comparison": comparison,
                  "different_values": "모두 같음" if first is None else value_text(lv[first]) + " / " + value_text(rv[first])}
        if first is None:
            sentence = f"{label(left)}과 {label(right)}은 모든 정렬 키가 같습니다. 두 행 사이 순서는 미지정이며 화면은 이번 실행의 순서입니다."
            record["decision"] = "모든 키 동점 · 서로의 순서 미지정"
        else:
            rule = rules[first]
            direction = "오름차순" if rule["direction"].upper() == "ASC" else "내림차순"
            prefix = f"{same}까지 같고, " if first else ""
            sentence = (f"{label(left)}과 {label(right)}은 {prefix}처음 다른 기준이 {rule['column']}입니다. "
                        f"{value_text(lv[first])}과 {value_text(rv[first])}을 {direction}으로 비교해 원본 {by_id[left] + 1}행이 앞섭니다.")
            record["decision"] = f"{rule['column']} {rule['direction'].upper()} · 원본 {by_id[left] + 1}행 먼저"
        record["equal_prefix"] = same
        record["before_label"] = label(left)
        record["after_label"] = label(right)
        pairs.append(record)
        sentences.append(sentence)
    complete_ties = [pair for pair in pairs if pair["first_different_key"] is None]
    if len(ordered) > 1 and not complete_ties:
        sentences.append("현재 결과에는 모든 정렬 키가 같은 행이 없습니다. 모든 키가 같다면 그 행들 사이 순서는 보장되지 않습니다.")
    elif len(ordered) <= 1:
        sentences.append("현재 결과는 " + str(len(ordered)) + "행이므로 서로 정렬을 비교할 두 행이 없습니다.")
    return {"sentences": sentences, "adjacent_pairs": pairs, "null_placement": null_placement,
            "ordered_source_row_ids": ordered, "complete_tie_pair_count": len(complete_ties),
            "basis": "independently verified original-row order and same SQLite comparison"}


def complete_requests(plan, message, question, request):
    from .verified import (condition_row_speech, ordering_speech,
                           table_action, traced_table, value_text, step)
    from edu_tutor.problems.evidence import execute_sql, fixture, logical_evidence
    from edu_tutor.problems.models import identified_table

    audit = {**request, "status": "fulfilled", "items": [],
             "scope": "명시적으로 인식한 제한된 설명 요청만 검사; 모델 자유 설명은 검증하지 않음"}
    kinds = request["requested"]

    def fail(reason, kind=None):
        audit["status"] = "unmet"
        audit["items"].append({"kind": kind or "unsupported_request", "status": "unmet", "reason": reason})
        raise UnmetExplanation(reason, audit)

    if request["unsupported"]:
        fail(" ".join(request["unsupported"]))
    if not kinds:
        audit["status"] = "no_bounded_request"
        return audit
    evidence = message["evidence"]
    logical = evidence.get("logical_steps")
    if not logical or evidence.get("scenario") != "original":
        fail("요청한 비교 설명에는 확정 원본과 독립 중간 계산 근거가 필요합니다.")
    table = next(t for t in evidence["working_tables"] if t["id"] == logical["table_id"])
    context = message.get("lesson_context") or {}
    selected = context.get("selected_cell") or {}
    matches = [(i, j) for i, row in enumerate(table["cell_ids"]) for j, cell in enumerate(row)
               if cell == selected.get("cell_id")]
    selected_row, selected_column = matches[0] if len(matches) == 1 else (None, None)
    # The caller has already checked current step, source-cell membership and
    # problem/trace binding with selected_row_step/selected_projection_row_step.
    if context and not context.get("_verified_logical_stage"):
        fail("현재 단계와 원본 셀의 서버 검증 연결이 필요합니다.")

    def fulfilled(kind, step_ids, proof):
        audit["items"].append({"kind": kind, "status": "fulfilled", "step_ids": step_ids, "evidence": proof})

    def chunks(text):
        pieces = [s.strip() for s in re.split(r"(?<=[.!?。])\s+", text) if s.strip()]
        result = []
        for piece in pieces:
            if len(piece) > 220:
                fail("한 문장의 설명이 음성 단계 길이를 초과합니다. 조건 범위를 좁혀 주세요.")
            if result and len(result[-1]) + len(piece) + 1 <= 220:
                result[-1] += " " + piece
            else:
                result.append(piece)
        return result

    def append(title, text, actions, target):
        ids = []
        for part in chunks(text):
            ident = f"s{len(plan['steps']) + 1}"
            note = evidence["id"] + "-request-" + ident
            board = copy.deepcopy(actions) + [{"type": "text", "element_id": note,
                                                "slot": "right", "text": part}]
            # Retire the previous spoken note: late steps cannot accumulate a
            # competing explanation at the same board position.
            if len(plan["steps"]):
                board.insert(0, {"type": "clear", "target": evidence["id"] + "-request-" + plan["steps"][-1]["id"]})
            plan["steps"].append(step(ident, title, part, board, target))
            ids.append(ident)
        return ids

    elaborate = any(k in kinds for k in ("null_comparison", "zero_comparison", "empty_input", "row_comparison"))
    if context and selected_row is not None and elaborate:
        # Keep the already-validated cell highlight and exact source table, but
        # separate inclusion/comparison/order into short playable teaching units.
        original = plan["steps"][0]
        original_actions = [a for a in original["board_actions"] if a.get("type") != "text"]
        inclusion = condition_row_speech(logical, table, selected_row)
        if logical.get("kind") != "projection_teaching_steps":
            # Existing aggregate selected-row speech binds the current aggregate
            # and group, not just WHERE membership; retain that checked account.
            inclusion = original["speech"]
        plan["steps"] = []
        ids = append("선택한 원본 행의 포함 이유", inclusion, original_actions, table["id"])
    else:
        ids = [s["id"] for s in plan["steps"]]
    if "row_inclusion" in kinds:
        if selected_row is None:
            fail("포함 이유를 확인할 원본 행의 셀을 선택해 주세요.", "row_inclusion")
        fulfilled("row_inclusion", ids, {"source_row_id": table["row_ids"][selected_row],
                  "source_cell_id": selected.get("cell_id"), "source_stage": context.get("_verified_logical_stage", {}).get("stage")})

    compare_kinds = [k for k in ("null_comparison", "zero_comparison", "row_comparison") if k in kinds]
    if compare_kinds:
        explicit = [i for i, name in enumerate(table["columns"])
                    if re.search(r"(?<![A-Za-z_0-9])" + re.escape(name) + r"(?![A-Za-z_0-9])", question, re.I)]
        # Initial question includes the SQL intent itself. Aggregate arguments
        # are the target; several mentioned predicate/order columns do not pick
        # an arbitrary comparison column.
        relevant = {a["column"].casefold() for a in logical.get("aggregates", []) if a["column"] != "*"}
        if not relevant and logical.get("where_sql"):
            from sqlglot import exp, parse_one
            relevant = {c.name.casefold() for c in parse_one("SELECT * FROM _source " + logical["where_sql"], read="sqlite").find_all(exp.Column)}
        candidates = [i for i, name in enumerate(table["columns"]) if name.casefold() in relevant]
        if compare_kinds == ["row_comparison"] and selected_column is not None:
            ci = selected_column
        elif context and len(explicit) == 1:
            ci = explicit[0]
        elif context and len(explicit) > 1:
            fail("NULL·0을 비교할 열을 하나 지정해 주세요: " + ", ".join(table["columns"][i] for i in explicit), "null_comparison")
        elif selected_column is not None and (not candidates or selected_column in candidates):
            ci = selected_column
        elif len(candidates) == 1:
            ci = candidates[0]
        elif len(table["columns"]) == 1:
            ci = 0
        else:
            fail("NULL·0을 비교할 원본 열이 여러 개입니다. 비교할 열 이름을 지정해 주세요.", compare_kinds[0])
        column = table["columns"][ci]
        null_rows = [i for i, row in enumerate(table["rows"]) if row[ci] is None]
        zero_rows = [i for i, row in enumerate(table["rows"]) if type(row[ci]) in {int, float} and row[ci] == 0]
        specified = {int(n) - 1 for n in re.findall(r"원본\s*(\d+)\s*행", question)}
        references = request.get("source_row_references", [])
        for reference in references:
            if reference["status"] != "unique" or len(reference["row_indices"]) != 1:
                fail("비교할 문자값이 원본의 한 행으로 확인되지 않았습니다.", "row_comparison")
            specified.update(reference["row_indices"])
        # Explicit original-row numbers can narrow a previously ambiguous set.
        # Never reinterpret a displayed, sorted row number as a source index.
        if specified:
            if any(i < 0 or i >= len(table["rows"]) for i in specified):
                fail("비교할 원본 행 번호가 표 범위를 벗어났습니다.", compare_kinds[0])
            references = specified - ({selected_row} if selected_row is not None else set())
            # When the value label explicitly qualifies a numbered row, check
            # that label. Otherwise NULL rows and the named other row are two
            # requests, both of which must be explained.
            qualified_null = {int(n)-1 for n in re.findall(r"(?:NULL|널)(?:인)?\s*원본\s*(\d+)\s*행", question, re.I)}
            qualified_zero = {int(n)-1 for n in re.findall(r"(?:0|영)(?:인)?\s*원본\s*(\d+)\s*행", question)}
            for reference in request.get("source_row_references", []):
                value = re.escape(reference["literal"])
                # A source value can name its row without the noun "행".
                # Accept only a bounded qualifier directly before that exact
                # literal; verify its claimed NULL/0 against the source cell.
                tail = r"['\"]?" + value + r"['\"]?(?=$|\s|[.,?!]|(?:인\s*)?행|(?:와도|과도|와|과|을|를|은|는|도)(?=$|\s|[.,?!]))"
                qualifier = r"(?:인|인데)?\s*(?:(?:빠진|제외된|포함된|남은)\s+)?(?:원본\s*)?"
                if re.search(r"(?<![A-Za-z_0-9])(?:NULL|널)" + qualifier + tail, question, re.I):
                    qualified_null.update(reference["row_indices"])
                if re.search(r"(?<![A-Za-z_0-9])(?:0|영)" + qualifier + tail, question):
                    qualified_zero.update(reference["row_indices"])
            if not qualified_null <= set(null_rows) or not qualified_zero <= set(zero_rows):
                fail("지정한 원본 행의 값이 요청한 NULL·0과 다릅니다. 비교할 원본 행을 확인해 주세요.", compare_kinds[0])
            if qualified_null:
                null_rows = [i for i in null_rows if i in qualified_null]
            if qualified_zero:
                zero_rows = [i for i in zero_rows if i in qualified_zero]
        # A singular deictic ("NULL인 그 행") asks for one known target,
        # unlike an explicit plural comparison. Do not silently answer for
        # every matching row, or let the selected non-NULL anchor resolve it.
        for kind, label, value_pattern, rows in (
                ("null_comparison", "NULL", r"(?:NULL|널)", null_rows),
                ("zero_comparison", "0", r"(?:0|영)", zero_rows)):
            singular = re.search(
                rf"(?<![A-Za-z_0-9])(?:{value_pattern}(?:인)?\s*(?:그|해당)\s*행(?!들)|"
                rf"(?:그|해당)\s*{value_pattern}(?:인)?\s*행(?!들))", question, re.I)
            if kind not in kinds or not singular or len(rows) <= 1:
                continue
            resolved = [ri for ri in rows if ri in specified]
            selected_target = re.search(
                rf"(?:선택한|선택된|고른)\s*(?:(?:그|해당|이)\s*)?{value_pattern}(?:인)?\s*(?:(?:그|해당|이)\s*)?행|"
                rf"{value_pattern}(?:인)?\s*(?:선택한|선택된|고른)\s*(?:(?:그|해당|이)\s*)?행", question, re.I)
            if selected_target and selected_row in rows:
                resolved = [selected_row]
            if len(resolved) != 1:
                fail(f"비교 대상 확인 필요: {column}이 {label}인 행은 원본 " +
                     ", ".join(str(ri + 1) for ri in rows) +
                     "행입니다. '그 행'이 어느 행인지 지정해 주세요.", kind)
            if kind == "null_comparison":
                null_rows = resolved
            else:
                zero_rows = resolved
        comparisons = sorted(set((null_rows if "null_comparison" in kinds else []) +
                                 (zero_rows if "zero_comparison" in kinds else []) +
                                 (list(specified) if "row_comparison" in kinds else [])))
        if len(comparisons) > 4:
            fail(f"{column}에서 비교할 원본 행이 {len(comparisons)}개입니다. 설명할 원본 행 번호를 좁혀 주세요.", compare_kinds[0])
        included_rows = sorted(set(comparisons + ([selected_row] if selected_row is not None else [])))
        contrast = traced_table(table, evidence["id"] + "-comparison-rows",
                               [table["row_ids"][i] for i in included_rows],
                               caption="비교하는 원본 행 번호: " + ", ".join(str(i + 1) for i in included_rows), slot="bottom")
        actions = [table_action(table), contrast]
        if included_rows:
            actions.append({"type": "highlight", "target_element_id": table["id"],
                            "cell_ids": [table["cell_ids"][i][ci] for i in included_rows], "style": "outline"})
        text = f"같은 원본에서 지정한 행의 {column} 값과 조건 결과를 비교합니다."
        if any(k in kinds for k in ("null_comparison", "zero_comparison")):
            text += " NULL은 값이 없음을 나타내고, 숫자 0은 실제 값입니다."
        if "null_comparison" in kinds and not null_rows:
            text += f" 이 원본의 {column} 열에는 NULL인 행이 없습니다. 원본에 없는 NULL행을 만들어 비교하지 않습니다."
        if "zero_comparison" in kinds and not zero_rows:
            text += f" 이 원본의 {column} 열에는 숫자 0인 행이 없습니다."
        step_ids = append("같은 원본의 NULL·0 비교", text, actions, table["id"])
        for ri in included_rows:
            if context and ri == selected_row:
                continue  # The immediately preceding inclusion step proved it.
            row_text = f"원본 {ri + 1}행의 {column} 값은 {value_text(table['rows'][ri][ci])}입니다. "
            row_text += condition_row_speech(logical, table, ri)
            # For aggregates use computed membership in each relevant group,
            # including DISTINCT, instead of a generic NULL-is-always-excluded
            # assertion (COUNT(*) and SUM(IS NOT NULL) differ).
            for agg in logical.get("aggregates", []):
                if agg["column"].casefold() != column.casefold():
                    continue
                group = next((g for g in logical.get("groups", []) if g["values"] == agg.get("group_values")), None)
                if group is not None and table["row_ids"][ri] not in group["row_ids"]:
                    continue
                member = table["row_ids"][ri] in agg["included_row_ids"]
                expression = agg.get("input_expression", column)
                row_text += f" {agg['function'].upper()}({expression})의 계산 입력에는 " + ("포함됩니다." if member else "포함되지 않습니다.")
                if agg.get("input_transform") == "is_not_null_indicator":
                    row_text += f" 이 행의 조건값은 {0 if table['rows'][ri][ci] is None else 1}입니다."
                elif member and agg["function"] == "sum" and table["rows"][ri][ci] == 0:
                    row_text += " 0을 더하므로 합계는 변하지 않습니다."
            step_ids += append("원본 행별 조건과 계산 입력", row_text, actions, table["id"])
        for kind in compare_kinds:
            rows = null_rows if kind == "null_comparison" else zero_rows if kind == "zero_comparison" else sorted(specified)
            fulfilled(kind, step_ids, {"column": column, "source_column_id": table["column_ids"][ci],
                "comparison_row_ids": [table["row_ids"][i] for i in rows],
                "comparison_cell_ids": [table["cell_ids"][i][ci] for i in rows], "source_kind": "original_rows",
                "exact_value_references": request.get("source_row_references", []) if kind == "row_comparison" else []})

    if "ordering" in kinds:
        stage = context.get("_verified_logical_stage", {}).get("stage")
        speech = ordering_speech(logical, brief=True)
        if stage not in {"order", "projection"}:
            speech = "현재 단계 이후의 정렬 기준도 확인합니다. " + speech
        if selected_row is not None and logical.get("kind") == "projection_teaching_steps":
            rid = table["row_ids"][selected_row]
            if rid in logical["ordered_row_ids"] and logical.get("order_by"):
                speech += f" 이번 실행에서 선택한 원본 {selected_row + 1}행은 {logical['ordered_row_ids'].index(rid) + 1}번째입니다."
            elif rid not in logical["filtered_row_ids"]:
                speech += " 선택한 행은 WHERE에서 제외되어 정렬 결과에 들어가지 않습니다."
        if elaborate or stage not in {"order", "projection"} or (selected_row is not None and table["row_ids"][selected_row] not in logical["filtered_row_ids"]):
            ids = append("현재 결과의 정렬 근거", speech, [table_action(table)], table["id"])
        else:
            ids = [s["id"] for s in plan["steps"]]
        detail = ordering_comparisons(logical, table)
        if detail:
            comparison_id = evidence["id"] + "-order-comparisons"
            pair_rows = [[p["before_label"], p["after_label"], p["equal_prefix"] or "없음",
                          p["first_different_key"] or "없음", p["different_values"], p["decision"]] for p in detail["adjacent_pairs"]]
            actions = [table_action(table), {"type": "table", "element_id": comparison_id, "slot": "bottom",
                "columns": ["앞에 표시된 행", "뒤에 표시된 행", "같은 앞 기준", "처음 다른 기준", "앞 / 뒤 값", "정렬 근거"],
                "rows": pair_rows, "caption": "원본 행으로 확인한 정렬 비교 · 완전 동점은 순서 미지정"}]
            ids += append("원본 값으로 확인하는 정렬과 동점", " ".join(detail["sentences"]), actions, table["id"])
        fulfilled("ordering", ids, {"order_by": logical.get("order_by", []), "source_stage": stage,
                                    "original_row_comparisons": detail})

    if "empty_input" in kinds:
        empty = copy.deepcopy(message["problem"])
        for t in empty["tables"]:
            t["rows"] = []
        empty_sql = evidence["sql"]
        requested_aggregates = []
        aggregate_labels = []
        # A separate empty-input question can ask for explicitly named
        # aggregates absent from the original projection. Resolve the entire
        # requested list through the existing bounded selection validator;
        # never mark the original query's zero rows as proof of those calls.
        from edu_tutor.problems.explanation_requests import EMPTY
        from edu_tutor.problems.intent_language import IDENT, _selection
        from edu_tutor.problems.evidence import intent_sql
        empty_clauses = [part for part in re.split(r"[;；\n]|(?<=[.!?。])\s+", question)
                         if re.search(EMPTY, part, re.I)]
        explicit_lists = []
        for clause in empty_clauses:
            start = re.search(IDENT + r"\s*\(", clause)
            if start:
                parts = re.split(r"(?:가|는|은|를|을)?\s*(?:각각\s*)?(?=무엇|어떤|결과|값|의미|반환|구분|비교|설명|알려)", clause[start.start():], maxsplit=1)
                selection = parts[0]
                if len(parts) > 1 and re.search(IDENT + r"\s*\(", parts[1]):
                    fail("빈 입력 집계 요청이 설명 문구 뒤에도 있습니다. 집계 목록을 함께 명시해 주세요.", "empty_input")
                explicit_lists.append(selection.strip().rstrip(".?!。"))
            elif re.search(r"\b(?:COUNT|SUM|AVG|MIN|MAX|TOTAL)\b|중앙값|표준편차|분산", clause, re.I):
                fail("빈 입력에서 요청한 집계 함수와 원본 열을 괄호로 명확히 지정해 주세요.", "empty_input")
        first_empty = re.search(EMPTY, question, re.I)
        if not explicit_lists and first_empty and re.search(IDENT + r"\s*\(", question[first_empty.end():]):
            fail("빈 입력과 비교할 집계 함수 목록을 같은 문장에 명시해 주세요.", "empty_input")
        if explicit_lists:
            if len(explicit_lists) != 1:
                fail("빈 입력에 비교할 집계 목록을 한 구절에 명시해 주세요.", "empty_input")
            try:
                columns, requested_aggregates = _selection(explicit_lists[0], empty["tables"][0], [])
                if columns or not requested_aggregates:
                    raise ValueError("빈 입력 비교는 명시한 집계 함수 목록이 필요합니다.")
                empty_sql = intent_sql({"table": empty["tables"][0]["name"], "aggregates": requested_aggregates})
                aggregate_labels = [a["function"].upper() + "(" + ("DISTINCT " if a.get("distinct") else "") + a["column"] + ")"
                                    for a in requested_aggregates]
            except ValueError as exc:
                fail("빈 입력 집계 요청을 확인하지 못했습니다: " + str(exc), "empty_input")
        result = execute_sql(empty_sql, fixture(empty))
        proof = logical_evidence(empty_sql, empty, "empty-example", result)
        if not proof:
            fail("빈 입력 예시의 독립 계산을 검증하지 못했습니다.", "empty_input")
        empty_table = identified_table(empty, empty["tables"][0], namespace="empty-example")
        result_id = evidence["id"] + "-empty-result"
        actions = [table_action(empty_table, "main", "설명용 새 예시 · 원본과 분리한 빈 입력"),
            {"type": "table", "element_id": result_id, "slot": "bottom", "columns": aggregate_labels or result["columns"],
             "rows": result["rows"], "caption": "요청한 집계를 별도 빈 입력에 실행한 결과" if requested_aggregates else "동일 SQL을 빈 입력에 실행한 결과"}]
        text = ("설명용 새 예시입니다. 원본 표와 SQL은 보존하고, 별도의 빈 표에서 요청한 집계를 계산했습니다. " if requested_aggregates
                else "설명용 새 예시입니다. 원본 표는 보존하고, 같은 열의 입력 행만 모두 없는 표에 같은 SQL을 실행했습니다. ")
        if result["rows"]:
            text += "결과는 " + "; ".join(", ".join(f"{column}은 {value_text(value)}" for column, value in zip(aggregate_labels or result["columns"], row)) for row in result["rows"]) + "입니다."
        else:
            text += "결과는 0행입니다. " + ("GROUP BY는 입력 행이 없어 그룹도 만들지 않습니다." if proof.get("group_columns") else "출력할 결과 행이 없습니다.")
        ids = append("원본과 분리한 빈 입력 비교", text, actions, result_id)
        fulfilled("empty_input", ids, {"source_kind": "separate_empty_input_example", "sql": empty_sql,
            "original_sql_unchanged": evidence["sql"], "requested_aggregates": requested_aggregates,
            "result_rows": result["rows"], "result_columns": result["columns"],
            "result_display_labels": aggregate_labels or result["columns"], "independent_trace": proof})
    if len(plan["steps"]) > 12:
        fail("요청한 비교 설명이 수업 12단계를 넘습니다. 비교할 원본 행이나 조건을 좁혀 주세요.")
    return audit
