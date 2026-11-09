from __future__ import annotations

import copy
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

ASSETS = Path(__file__).parent / "assets"
VALIDATOR = Draft202012Validator(json.loads((ASSETS / "lesson_plan.schema.json").read_text(encoding="utf-8")))


def validate_plan(plan):
    errors = sorted(VALIDATOR.iter_errors(plan), key=lambda e: str(e.path))
    if errors:
        raise ValueError("Invalid lesson: " + "; ".join(e.message[:200] for e in errors[:3]))
    elements = {}
    for step in plan["steps"]:
        for action in step["board_actions"]:
            timing = action.get("timing")
            if timing and timing["end"] < timing["start"]:
                raise ValueError("Board timing ends before it starts")
            bounds = action.get("layout") or (action.get("geometry") if "width" in action.get("geometry", {}) else None)
            if bounds and (bounds["x"] + bounds["width"] > 1.000001 or bounds["y"] + bounds["height"] > 1.000001):
                raise ValueError("Board geometry exceeds normalized bounds")
            if action["type"] == "circle":
                g = action["geometry"]
                if g["cx"]-g["radius"] < 0 or g["cx"]+g["radius"] > 1 or g["cy"]-g["radius"] < 0 or g["cy"]+g["radius"] > 1:
                    raise ValueError("Circle exceeds normalized bounds")
            if action["type"] == "clear":
                if action.get("target") == "all":
                    elements.clear()
                else:
                    elements.pop(action["target"], None)
            elif action["type"] == "highlight":
                if action["target_element_id"] not in elements:
                    raise ValueError("Unknown highlight target")
                target = elements[action["target_element_id"]]
                if target["type"] == "table":
                    if any(index >= len(target["rows"]) for index in action.get("row_indices", [])) or any(index >= len(target["columns"]) for index in action.get("column_indices", [])):
                        raise ValueError("Highlight index outside table")
                    cells = {cell for row in target.get("cell_ids", []) for cell in row}
                    if any(cell not in cells for cell in action.get("cell_ids", [])):
                        raise ValueError("Unknown highlight cell ID")
            elif action["type"] == "arrow" and "geometry" not in action:
                if action["from_element_id"] not in elements or action["to_element_id"] not in elements:
                    raise ValueError("Unknown arrow target")
            else:
                if action["type"] == "table" and any(len(row) != len(action["columns"]) for row in action["rows"]):
                    raise ValueError("Table row width does not match its columns")
                if action["type"] == "table":
                    if "row_ids" in action and len(action["row_ids"]) != len(action["rows"]):
                        raise ValueError("Table row IDs do not match rows")
                    if "column_ids" in action and len(action["column_ids"]) != len(action["columns"]):
                        raise ValueError("Table column IDs do not match columns")
                    if any(len(set(action[field])) != len(action[field]) for field in ("row_ids", "column_ids") if field in action):
                        raise ValueError("Table row and column IDs must be unique")
                    if "cell_ids" in action:
                        cells = [cell for row in action["cell_ids"] for cell in row]
                        if len(action["cell_ids"]) != len(action["rows"]) or any(len(row) != len(action["columns"]) for row in action["cell_ids"]) or len(set(cells)) != len(cells):
                            raise ValueError("Table cell IDs do not match unique cells")
                elements[action["element_id"]] = action
        target = step["gesture"].get("target_element_id")
        if target and target not in elements:
            raise ValueError(f"Unknown lesson target: {target}")
    return plan


def verify_demo_plan(plan):
    """Execute the bundled fixture and compare the displayed final board.

    This proves one fixture's SQL/table consistency, never LLM or teaching quality.
    The imported document's historical verification claim is not trusted.
    """
    from edu_tutor.evaluation.sql_sandbox import compare_results, execute_sql
    validate_plan(plan)
    raw_fixture = (ASSETS / "qa_record.example.json").read_bytes()
    record = json.loads(raw_fixture)
    expected = record["expected"]
    queries = [action["code"] for step in plan["steps"] for action in step["board_actions"]
               if action["type"] == "code" and action["language"] == "sql"]
    displayed_sql_matches = len(queries) == 1 and queries[0].strip() == expected["sql"].strip()
    actual = execute_sql(expected["sql"], record["fixture"], dialect=record["sql_dialect"])
    sql_match = compare_results(actual, {**expected, "numeric_abs_tolerance": 0})
    final = scene_at(plan, len(plan["steps"]) - 1)
    board = final["elements"].get("result", {})
    # Explicit label-to-SQL mapping; matching table width alone is insufficient.
    mapping = {"부서": "dept", "전체 인원": "people", "입력 급여 수": "salary_count",
               "급여 합계": "salary_sum", "급여 평균": "salary_avg"}
    board_columns = [mapping.get(label) for label in board.get("columns", [])]
    board_match = bool(board.get("type") == "table" and sql_match and compare_results(
        {"status": "executed", "columns": board_columns, "rows": board.get("rows", [])},
        {"columns": actual["columns"], "rows": actual["rows"], "row_order": "ordered", "numeric_abs_tolerance": 0}))
    initial = scene_at(plan, 0)["elements"].get("original", {})
    original_match = initial.get("type") == "table" and initial.get("rows") == record["fixture"]["tables"][0]["rows"]
    passed = displayed_sql_matches and sql_match and board_match and original_match and plan["provenance"] == "demo_fixture"
    return {"tier": "T0", "machine_verification": "pass" if passed else "fail", "dialect": "sqlite",
            "checked_at": datetime.now(timezone.utc).isoformat(), "fixture_sha256": hashlib.sha256(raw_fixture).hexdigest(),
            "executed_sql": expected["sql"], "execution": actual, "sql_expected_match": sql_match,
            "displayed_sql_matches_fixture": displayed_sql_matches, "original_table_matches_fixture": original_match,
            "final_board_matches_execution": board_match, "board_column_mapping": mapping,
            "model_inference": "not_run", "human_review": "not_reviewed"}


def checked_demo_plan(plan=None):
    plan = copy.deepcopy(plan) if plan is not None else json.loads((ASSETS / "lesson_plan.example.json").read_text(encoding="utf-8"))
    report = verify_demo_plan(plan)
    passed = report["machine_verification"] == "pass"
    plan["verification"] = {
        "status": "fixture_sql_checked" if passed else "unverified",
        "scope": "현재 앱의 격리 SQLite 실행, 예제 기대 결과, 원본 표와 최종 판서 표의 대조를 통과했습니다." if passed else "현재 앱에서 예제 SQL 또는 판서 결과 대조를 통과하지 못했습니다.",
        "limitations": ["직접 작성한 단일 예제의 SQL과 표만 검사했습니다.", "실제 LLM 생성·GPU·음성·학습 검증이 아닙니다.",
                        "교육 설명 전체의 정확성이나 일반화 성능을 검증하지 않았으며 사람 검토도 수행하지 않았습니다."]}
    for step in plan["steps"]:
        for action in step["board_actions"]:
            if action["type"] == "table" and action["element_id"] == "result":
                action["caption"] = "현재 앱의 SQLite 실행 결과와 대조한 예제" if passed else "SQLite·판서 결과 대조를 통과하지 못한 예제"
    return validate_plan(plan), report


def demo_plan():
    return checked_demo_plan()[0]


def scene_at(plan, step_index, progress=1):
    validate_plan(plan)
    scene = {"elements": {}, "highlights": [], "arrows": []}
    for index, step in enumerate(plan["steps"][:step_index + 1]):
        for action_index, action in enumerate(step["board_actions"]):
            if index == step_index:
                timing = action.get("timing", {"start": action_index / len(step["board_actions"]), "end": (action_index + 1) / len(step["board_actions"])})
                if progress < timing["start"] or (progress == timing["start"] and timing["end"] > timing["start"]):
                    continue
            action = copy.deepcopy(action)
            kind = action["type"]
            if kind == "clear":
                if action.get("target") == "all":
                    scene = {"elements": {}, "highlights": [], "arrows": []}
                else:
                    target = action["target"]
                    scene["elements"].pop(target, None)
                    scene["highlights"] = [item for item in scene["highlights"]
                                           if item.get("target_element_id") != target and item.get("element_id") != target]
                    scene["arrows"] = [item for item in scene["arrows"]
                                       if target not in (item.get("from_element_id"), item.get("to_element_id"), item.get("element_id"))]
            elif kind == "highlight":
                scene["highlights"] = [item for item in scene["highlights"] if item["target_element_id"] != action["target_element_id"]]
                scene["highlights"].append(action)
            elif kind == "arrow" and "geometry" not in action:
                scene["arrows"].append(action)
            else:
                scene["elements"][action["element_id"]] = action
    return scene
