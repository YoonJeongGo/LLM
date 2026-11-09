"""File-only post-execution audit. Does not import product code or call APIs/models.

Run only after actual outputs have completed. Private answers never feed inputs.
An automatic text match is an evidence locator, NOT a semantic/human pass.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3

import sqlglot
from sqlglot import exp

BASE = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_inputs(base=BASE):
    frozen = read(base / "freeze.json")
    for name, expected in frozen["files"].items():
        if sha(base / name) != expected:
            raise ValueError("Frozen evaluation input changed: " + name)
    return frozen, read(base / "public.json"), read(base / "private-oracle.json")


def unique_object(pairs):
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise ValueError("duplicate JSON key")
        obj[k] = v
    return obj


def candidates(raw):
    """Independent bounded extraction; ambiguity is kept, not first-candidate picked."""
    if not isinstance(raw, str) or len(raw) > 60000:
        return {"status": "MISSING_OR_OVERSIZE", "sql": [], "explanations": []}
    decoder = json.JSONDecoder(object_pairs_hook=unique_object)
    sqls, explanations, errors = [], [], []
    for pos in [m.start() for m in re.finditer(r"\{", raw)]:
        try:
            value, _ = decoder.raw_decode(raw[pos:])
        except ValueError as exc:
            if "duplicate JSON key" in str(exc):
                errors.append(str(exc))
            continue
        if isinstance(value, dict) and isinstance(value.get("sql"), str):
            sqls.append(value["sql"].strip())
            if isinstance(value.get("explanation"), str):
                explanations.append(value["explanation"])
    for body in re.findall(r"```\s*sql\s*\n(.*?)```", raw, flags=re.S | re.I):
        sqls.append(body.strip())
    if not sqls and raw.lstrip().upper().startswith("SELECT "):
        sqls.append(raw.strip())
    sqls = list(dict.fromkeys(sqls))
    return {"status": "AMBIGUOUS" if errors or len(sqls) > 1 else "ONE" if sqls else "NOT_EXTRACTED",
            "sql": sqls, "explanations": list(dict.fromkeys(explanations)), "errors": errors}


def canonical(node):
    if isinstance(node, exp.Paren):
        return canonical(node.this)
    if isinstance(node, (exp.And, exp.Or)):
        def terms(value):
            if isinstance(value, type(node)):
                return terms(value.this) + terms(value.expression)
            if isinstance(value, exp.Paren):
                return terms(value.this)
            return [canonical(value)]
        return [node.key, sorted(terms(node), key=lambda v: json.dumps(v, sort_keys=True))]
    if isinstance(node, exp.Identifier):
        return ["identifier", node.name.casefold()]
    if isinstance(node, exp.Ordered):
        # SQLite's omitted direction is ASC; sqlglot stores None vs False.
        return [node.key, {**{k: canonical(v) for k, v in sorted(node.args.items()) if v is not None},
                           "desc": bool(node.args.get("desc"))}]
    if isinstance(node, exp.Expression):
        return [node.key, {k: canonical(v) for k, v in sorted(node.args.items()) if v is not None}]
    if isinstance(node, list):
        return [canonical(v) for v in node]
    return node


def sql_check(sql, expected, table, *, check_variants=True):
    result = {"sql": sql}
    try:
        parsed = sqlglot.parse(sql, read="sqlite")
        if len(parsed) != 1 or not isinstance(parsed[0], exp.Select):
            raise ValueError("only one SELECT is evaluated")
        if parsed[0].args.get("with_") or list(parsed[0].find_all(exp.Join)) or list(parsed[0].find_all(exp.Subquery)):
            raise ValueError("outside this frozen single-table oracle audit")
        refs = list(parsed[0].find_all(exp.Table))
        if len(refs) != 1 or refs[0].name.casefold() != table["name"].casefold():
            raise ValueError("source table mismatch")
        expected_ast = sqlglot.parse_one(expected["query"], read="sqlite")
        result["normalized_intent_match"] = canonical(parsed[0]) == canonical(expected_ast)
        con = sqlite3.connect(":memory:")
        try:
            quoted = lambda v: '"' + v.replace('"', '""') + '"'
            con.execute("CREATE TABLE " + quoted(table["name"]) + " (" + ", ".join(quoted(c["name"]) + " " + c["type"] for c in table["columns"]) + ")")
            con.executemany("INSERT INTO " + quoted(table["name"]) + " VALUES (" + ",".join("?" for _ in table["columns"]) + ")", table["rows"])
            con.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION} else sqlite3.SQLITE_DENY)
            remaining = [200]
            def progress():
                remaining[0] -= 1
                return remaining[0] <= 0
            con.set_progress_handler(progress, 1000)
            cursor = con.execute(sql)
            rows = [list(row) for row in cursor.fetchmany(1001)]
            if len(rows) > 1000:
                raise ValueError("oracle audit row bound exceeded")
            actual = {"columns": [d[0] for d in cursor.description], "rows": rows}
        finally:
            con.close()
        result.update(result=actual, result_match=actual == expected["result"])
        result["status"] = ("CORRECT_SQL_AND_RESULT" if result["normalized_intent_match"] and result["result_match"]
                            else "RESULT_MATCH_INTENT_EQUIVALENCE_PENDING" if result["result_match"] else "INCORRECT_RESULT")
        if check_variants and result["status"] == "RESULT_MATCH_INTENT_EQUIVALENCE_PENDING":
            contrast = numeric_boundary_counterexample(sql, expected, table)
            result["counterexample_search"] = contrast
            if contrast.get("found"):
                result["status"] = "INTENT_MISMATCH_COUNTEREXAMPLE"
    except Exception as exc:
        result.update(status="INVALID_OR_OUTSIDE_AUDIT", error=f"{type(exc).__name__}: {exc}")
    return result


def numeric_boundary_counterexample(sql, expected, table):
    """CPU-only hypothetical data, never changes the student's frozen input."""
    literals = set()
    for query in (sql, expected["query"]):
        for node in sqlglot.parse_one(query, read="sqlite").find_all(exp.Literal):
            if not node.is_string:
                try:
                    number = float(node.this)
                    if number.is_integer() and abs(number) < 100000:
                        literals.update([int(number) - 1, int(number), int(number) + 1])
                except ValueError:
                    pass
    checked = 0
    for ri, row in enumerate(table["rows"]):
        for ci, column in enumerate(table["columns"]):
            if column["type"].upper() not in {"INTEGER", "REAL", "NUMERIC"}:
                continue
            domain = sorted(literals | {0, -1, 1})
            for value in domain:
                if value == row[ci]:
                    continue
                checked += 1
                altered = copy.deepcopy(table)
                altered["rows"][ri][ci] = value
                oracle_result = sql_check(expected["query"], expected, altered, check_variants=False).get("result")
                observed = sql_check(sql, {**expected, "result": oracle_result}, altered, check_variants=False)
                if oracle_result is not None and observed.get("result") is not None and observed["result"] != oracle_result:
                    return {"found": True, "checked_variants": checked, "kind": "separate_hypothetical_numeric_boundary_counterexample",
                            "source_row_index": ri, "column": column["name"], "original_value": row[ci], "hypothetical_value": value,
                            "expected_result": oracle_result, "candidate_result": observed["result"], "original_question_or_table_mutated": False}
                if checked >= 128:
                    return {"found": False, "checked_variants": checked, "limit": 128, "equivalence_proven": False}
    return {"found": False, "checked_variants": checked, "equivalence_proven": False}


def normalize_message(value):
    # Support raw actual.json messages and the collector's exported answers.
    if value.get("role") == "user" and "question_text" in value:
        return {**(value.get("question_fields") or {}), **value, "content": value["question_text"]}
    if "app_display" not in value:
        return value
    raw = value.get("raw_model") or {}
    return {**value, **(value.get("app_display") or {}), "content": value.get("question_text", (value.get("app_display") or {}).get("content")),
            "raw_model_response": raw.get("response"), "model_attempts": raw.get("attempts"),
            "generation_snapshot": raw.get("generation_snapshot"), "problem": value.get("working_problem")}


def records(actual, collected=None):
    messages = {m["id"]: normalize_message(m) for m in actual.get("actual_messages", []) if m.get("id")}
    lessons = {}
    if actual.get("actual_lesson", {}).get("id"):
        lessons[actual["actual_lesson"]["id"]] = actual["actual_lesson"]
    for response in actual.get("responses", []):
        value = response.get("value")
        if "/lessons" in response.get("path", "") and isinstance(value, dict) and value.get("id"):
            lessons[value["id"]] = value
        if response.get("path", "").endswith("/messages") and isinstance(value, list):
            messages.update({m["id"]: normalize_message(m) for m in value if m.get("id")})
    if collected:
        messages.update({m["id"]: normalize_message(m) for m in collected.get("answers", []) if m.get("id")})
        lessons.update({v["id"]: v for v in collected.get("lessons", []) if v.get("id")})
    return list(messages.values()), list(lessons.values())


def text_evidence(lesson):
    rows = []
    for step in (lesson.get("plan") or {}).get("steps", []):
        rows.append({"step_id": step.get("id"), "type": "speech", "text": step.get("speech", "")})
        for i, action in enumerate(step.get("board_actions", [])):
            if action.get("type") in {"text", "code", "equation", "table"}:
                rows.append({"step_id": step.get("id"), "type": "board_" + action["type"], "action_index": i,
                             "text": json.dumps(action, ensure_ascii=False)})
    return rows


def requirements_review(expected, phase, source, lesson, actual, reached):
    rows = text_evidence(lesson)
    audit = lesson.get("explanation_fulfillment") or {}
    output = []
    for req in expected["requirements"][phase]:
        if req["id"] == "resume":
            initial = actual.get("actual_lesson", {}).get("id")
            event = next((e for e in actual.get("events", []) if e.get("type") == "lesson_resumed" and e.get("lesson_record_id") == initial), None)
            status = "AUTOMATED_EVENT_PASS" if event else "NOT_REACHED" if not reached else "NO_RESUME_EVENT"
            output.append({**req, "automatic_status": status, "event": event, "human_review": "H_PENDING"})
            continue
        tokens = []
        for index in req.get("source_rows", []):
            tokens.extend([str(source["rows"][index][0]), f"원본 {index + 1}행", f"{index + 1}행"])
        if not tokens:
            tokens = (["정렬", "오름차순", "내림차순"] if "sort" in req["id"] else
                      ["SUM", "COUNT", "빈 입력", "빈 표"] if "empty" in req["id"] else
                      ["조건", "TRUE", "UNKNOWN"] if "condition" in req["id"] or "where" in req["id"] else
                      [c["name"] for c in source["columns"]])
        found = [row for row in rows if any(t.casefold() in row["text"].casefold() for t in tokens)]
        output.append({**req, "automatic_status": "NOT_REACHED" if not reached else "EVIDENCE_LOCATED_NOT_SEMANTIC_PASS" if found else "NO_TEXT_MATCH_DETECTED",
                       "matching_text": found, "full_semantic_verdict": "PENDING_POSTRUN_TEXT_REVIEW",
                       "human_review": "H_PENDING"})
    return {"requirements": output, "product_claimed_audit_not_independent_pass": audit,
            "all_actual_speech_and_board": rows, "notice": "Keyword evidence locates actual material only. It cannot prove explanation completeness, truth or listening quality."}


def cycle_actual(actual, cycle_index):
    """Keep a later repeat from supplying the primary cycle's missing resume."""
    cycles = actual.get("followup_cycles") or []
    cycle = next((v for v in cycles if v.get("index") == cycle_index), None)
    if cycle is None:
        return ({**actual, "events": []} if cycle_index > 1 else actual), None
    start = cycle.get("start_event_index")
    if not isinstance(start, int) or start < 0:
        raise ValueError("Cycle has no valid recorded event boundary")
    ends = [v["start_event_index"] for v in cycles if isinstance(v.get("start_event_index"), int) and v["start_event_index"] > start]
    end = min(ends) if ends else len(actual.get("events", []))
    return {**actual, "events": actual.get("events", [])[start:end]}, cycle


def select_user(users, messages, lessons, cycle, excluded_request_ids):
    available = [u for u in users if u.get("request_id") not in excluded_request_ids]
    if cycle:
        lesson_id = cycle.get("supplement_id") or (cycle.get("first_supplement_playing") or {}).get("lesson_record_id")
        lesson = next((v for v in lessons if v.get("id") == lesson_id), None)
        answer = next((m for m in messages if lesson and m.get("id") == lesson.get("source_message_id") and m.get("role") == "assistant"), None)
        linked = [u for u in available if answer and u.get("request_id") == answer.get("request_id")]
        if len(linked) == 1:
            return linked[0], "EXACT_CYCLE_LESSON_MESSAGE_REQUEST_LINK"
    if len(available) == 1:
        return available[0], "UNIQUE_EXACT_QUESTION_REQUEST"
    return None, "NO_SUBMITTED_MATCH" if not available else "AMBIGUOUS_REQUEST_MATCH"


def grade_question(spec, expected, phase, actual, messages, lessons, collected=None, *, cycle_index=1, excluded_request_ids=()):
    question = spec["question"] if phase == "initial" else spec["followup"]["question"]
    users = [m for m in messages if m.get("role") == "user" and m.get("content") == question]
    scoped_actual, cycle = cycle_actual(actual, cycle_index) if phase == "followup" else (actual, None)
    user, linkage = select_user(users, messages, lessons, cycle, excluded_request_ids)
    answer = next((m for m in messages if user and m.get("role") == "assistant" and m.get("request_id") == user.get("request_id")), None)
    job = next((j for j in actual.get("owned_jobs", []) if user and j.get("request_id") == user.get("request_id") and j.get("kind") == "chat"), None)
    lesson = next((v for v in lessons if answer and v.get("source_message_id") == answer.get("id")), {})
    played = [e for e in scoped_actual.get("events", []) if e.get("type") == "audio_playing" and e.get("lesson_record_id") == lesson.get("id")]
    linked_playback = [p for p in (collected or {}).get("playback", []) if p.get("lesson_id") == lesson.get("id")
                       and p.get("valid_explanation_by_record_linkage") is True]
    raw = candidates((answer or {}).get("raw_model_response"))
    raw["checks"] = [sql_check(sql, expected, spec["tables"][0]) for sql in raw["sql"]]
    raw["model_attempts"] = []
    for attempt in (answer or {}).get("model_attempts") or []:
        extracted = candidates(attempt.get("text"))
        raw["model_attempts"].append({"attempt": attempt.get("attempt"), "incomplete": attempt.get("incomplete"),
            "checks": [sql_check(s, expected, spec["tables"][0]) for s in extracted["sql"]], "extraction": extracted["status"],
            "metadata": attempt.get("generation_snapshot")})
    evidence = (answer or {}).get("evidence") or {}
    status = "AMBIGUOUS_REQUEST_MATCH" if linkage == "AMBIGUOUS_REQUEST_MATCH" else "NOT_REACHED" if not user else "SUBMITTED_NO_ASSISTANT" if not answer else "APP_ANSWER_WITHOUT_PLAYABLE_LESSON" if not lesson.get("speech_allowed") else "LESSON_NOT_OBSERVED_PLAYING" if not played else "ACTUAL_LESSON_PLAYING"
    return {"id": spec["id"] + ("-initial" if phase == "initial" else "-followup"), "phase": phase, "question": question,
        "status": status, "submitted": user is not None, "user_matches": len(users), "user_message_id": (user or {}).get("id"),
        "request_linkage": linkage, "cycle_evidence": cycle,
        "request_id": (user or {}).get("request_id"), "assistant_message_id": (answer or {}).get("id"), "job": job,
        "raw_model": raw, "raw_response": (answer or {}).get("raw_model_response"),
        "raw_explanation_error_review": {"status": "PENDING_POSTRUN_TEXT_REVIEW", "actual_text": raw["explanations"], "human_review": "H_PENDING"},
        "app": {"content": (answer or {}).get("content"), "evidence_status": evidence.get("status"),
                "support_status": evidence.get("support_status"), "intent": evidence.get("intent"), "reasons": evidence.get("reasons"),
                "sql_origin": evidence.get("sql_origin"), "correction": evidence.get("app_correction"),
                "independent_sql_check": sql_check(evidence["sql"], expected, spec["tables"][0]) if evidence.get("sql") else None,
                "result_matches_oracle": evidence.get("result") == expected["result"] if evidence.get("result") is not None else None,
                "lesson_id": lesson.get("id"), "speech_allowed": lesson.get("speech_allowed"), "lesson_reason": lesson.get("reason"),
                "plan_present": bool(lesson.get("plan")), "audio_playing_events": played,
                "linked_playback_records": linked_playback,
                "actual_speech_support_not_human_audition": bool(linked_playback) if collected is not None else None,
                "playback_linkage_status": "COLLECTOR_PROVIDED" if collected is not None else "NOT_COLLECTED"},
        "explanation": requirements_review(expected, phase, spec["tables"][0], lesson, scoped_actual, bool(answer)),
        "actual_generation_snapshot": (answer or {}).get("generation_snapshot"), "human_review": "H_PENDING"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", type=Path, default=BASE)
    p.add_argument("--version-dir", type=Path, required=True)
    p.add_argument("--collected-report", type=Path)
    p.add_argument("--outputs-finalized", action="store_true", required=True)
    p.add_argument("--cohort", choices=["independent-first-attempt", "development-regression"], required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError("Never overwrite an earlier assessment")
    version = read(args.version_dir / "execution-version.json")
    public_input = read(args.input_dir / "public.json")
    # Validate terminal output files BEFORE opening the private expected answers.
    actuals = {}
    for case_id in (item["id"] for item in public_input["journeys"]):
        path = args.version_dir / case_id / "actual.json"
        if not path.exists():
            actuals[case_id] = None
            continue
        actual = read(path)
        if actual.get("status") == "RUNNING" or not actual.get("completed_at"):
            raise ValueError("Output still running/not finalized: " + case_id)
        actuals[case_id] = (path, actual)
    frozen, public, oracle = checked_inputs(args.input_dir)
    if version.get("input_sha256") != frozen["files"]["public.json"]:
        raise ValueError("Execution version did not use the frozen public input")
    output = {"at": datetime.now(timezone.utc).isoformat(), "cohort": args.cohort, "version": version.get("version"),
              "source": str(args.version_dir), "questions": [], "repeat_stability": [], "cases": [], "human_review": "H_PENDING", "readiness": "NOT_READY"}
    for spec in public["journeys"]:
        pair = actuals[spec["id"]]
        if pair is None:
            output["cases"].append({"id": spec["id"], "status": "NO_EXECUTION_RECORD"})
            for phase in ["initial", "followup"]:
                output["questions"].append({"id": spec["id"] + "-" + phase, "phase": phase, "submitted": False, "status": "NOT_REACHED", "human_review": "H_PENDING"})
            continue
        path, actual = pair
        if actual.get("spec") != spec:
            raise ValueError("Actual question changed from frozen input: " + spec["id"])
        if actual.get("attempt") and args.cohort == "independent-first-attempt":
            raise ValueError("An explicitly named retry belongs in development-regression")
        repeat_declared = version.get("repeat_followup_case_id") == spec["id"]
        if actual.get("repeat_followup") and (not repeat_declared or args.cohort != "development-regression"):
            raise ValueError("Repeated followup must be preregistered development stability evidence")
        if repeat_declared and actual.get("question_plan") != (version.get("expected_question_plan") or {}).get(spec["id"]):
            raise ValueError("Actual repeat plan differs from frozen plan")
        collected_path = args.collected_report / (spec["id"] + ".json") if args.collected_report else None
        collected = read(collected_path) if collected_path and collected_path.exists() else None
        messages, lessons = records(actual, collected)
        integrity = actual.get("source_unchanged_at_end") is True and actual.get("source_hashes") == version.get("source_hashes")
        output["cases"].append({"id": spec["id"], "actual_json": str(path), "actual_sha256": sha(path),
            "harness_status": actual.get("status"), "harness_failure": actual.get("failure"), "source_integrity": integrity,
            "timings": (collected or {}).get("timings"), "playback_checks": (collected or {}).get("evidence_requirements"),
            "screenshots": actual.get("screenshots"), "lessons": lessons})
        for phase in ["initial", "followup"]:
            grade = grade_question(spec, oracle["cases"][spec["id"]], phase, actual, messages, lessons, collected)
            grade["source_integrity"] = integrity
            output["questions"].append(grade)
        if repeat_declared:
            primary = output["questions"][-1]
            repeat = grade_question(spec, oracle["cases"][spec["id"]], "followup", actual, messages, lessons, collected,
                                    cycle_index=2, excluded_request_ids=[primary.get("request_id")])
            repeat.update(id=spec["id"] + "-repeat-followup", phase="repeat_stability", source_integrity=integrity,
                          excluded_from_primary_accuracy_denominator=True)
            output["repeat_stability"].append(repeat)
    qs = output["questions"]
    def metrics(group):
        eligible = [q for q in group if q.get("source_integrity") is True]
        raw_correct = sum(q.get("raw_model", {}).get("status") == "ONE" and len(q.get("raw_model", {}).get("checks", [])) == 1
                          and q["raw_model"]["checks"][0]["status"] == "CORRECT_SQL_AND_RESULT" for q in eligible)
        reached = sum(q.get("app", {}).get("actual_speech_support_not_human_audition") is True for q in eligible)
        app_correct = sum(q.get("app", {}).get("result_matches_oracle") is True and
                          (q["app"].get("independent_sql_check") or {}).get("status") == "CORRECT_SQL_AND_RESULT" for q in eligible)
        return {"planned_denominator": len(group), "submitted": sum(q.get("submitted") is True for q in group),
                "raw_sql_and_result_proved": raw_correct, "app_sql_and_result_proved": app_correct,
                "substantive_lesson_reached": reached, "not_reached": sum(q["status"] == "NOT_REACHED" for q in group),
                "source_integrity_eligible": len(eligible)}
    output["metrics"] = {"all": metrics(qs), "initial": metrics([q for q in qs if q["phase"] == "initial"]),
                          "followup": metrics([q for q in qs if q["phase"] == "followup"]),
                          "coverage_semantic_pass_count": None, "cpu_boundary_cases_excluded": frozen["counts"].get("separate_cpu_boundaries", 0),
                          "repeat_stability_excluded": len(output["repeat_stability"]),
                          "notice": "Counts are for the frozen small purposive question set. Text coverage remains pending actual-text adjudication; no population accuracy or human-quality claim."}
    output["lineage"] = {"input_freeze_sha256": sha(args.input_dir / "freeze.json"), "public_sha256": sha(args.input_dir / "public.json"),
                         "private_oracle_sha256": sha(args.input_dir / "private-oracle.json"), "execution_version_sha256": sha(args.version_dir / "execution-version.json"),
                         "tool_sha256": sha(Path(__file__))}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"saved": str(args.output), "metrics": output["metrics"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
