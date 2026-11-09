"""Frozen small diagnostics, separated public inputs/oracles and API-only runner.

These are self-authored diagnostic/development questions, never a private benchmark.
No training, model download, direct model worker or adapter promotion occurs here.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import time
from urllib.parse import urlsplit
from uuid import uuid4

from .comparison import compare_results_v2
from .phase2_audit import digest, write_json
from .sql_sandbox import execute_sql, extract_sql


def _table(name, columns, rows):
    return {"name": name, "columns": [{"name": n, "type": t} for n, t in columns], "rows": rows}


def _expected(columns, rows, ordered=False):
    return {"columns": columns, "rows": rows, "row_order": "ordered" if ordered else "multiset",
            "numeric_abs_tolerance": 1e-9, "numeric_rel_tolerance": 0}


def authored_cases():
    """Freeze all questions and independent expectations before any new inference."""
    readings = _table("readings", [("measure", "INTEGER")], [[5], [None], [15], [5]])
    samples = _table("samples", [("v", "INTEGER")], [[7], [None], [11], [0]])
    visits = _table("visits", [("id", "INTEGER"), ("team", "TEXT"), ("score", "INTEGER")],
                    [[1, "A", 80], [2, "A", None], [3, "A", 40], [4, "B", 90], [5, "B", 85], [6, "C", None]])
    bag = _table("bag", [("v", "INTEGER")], [[2], [2], [None], [1], [4]])
    devices = _table("devices", [("id", "INTEGER")], [[10], [20], [30]])
    events = _table("events", [("device_id", "INTEGER"), ("reading", "INTEGER")], [[10, 3], [10, 8], [20, None]])
    stock = _table("stock", [("category", "TEXT"), ("amount", "REAL")], [["K", 2.5], ["K", None], ["L", 7.5]])
    return [
        {"id": "N01", "category": "concept", "task_type": "concept", "dialect": "sqlite",
         "student_prompt": "사원 한 명의 행을 넣는 INSERT와 전화번호 칸을 추가하는 ALTER TABLE은 어떻게 달라? DDL과 DML을 짧게 구분해 줘.",
         "tables": [], "oracle": {"rubric": ["INSERT는 행 데이터 추가/DML", "ALTER TABLE은 구조 변경/DDL", "필요한 예시는 설명용 새 예시라고 표시"], "human_review": "not_reviewed"}},
        {"id": "N02", "category": "concept", "task_type": "concept", "dialect": "sqlite",
         "student_prompt": "SQLite에서 NULL은 숫자 0이나 빈 문자열과 같은 값이야? IS NULL과 = NULL을 구분해서 설명해 줘.",
         "tables": [], "oracle": {"rubric": ["NULL은 0/빈 문자열과 다름", "= NULL은 TRUE가 아니라 UNKNOWN/NULL", "NULL 검사는 IS NULL"], "human_review": "not_reviewed"}},
        {"id": "N03", "category": "concept", "task_type": "concept", "dialect": "sqlite",
         "student_prompt": "그룹 평균이 60 이상인 팀을 고를 때 WHERE와 HAVING은 어떻게 나눠 써? 논리적 설명 순서와 실제 DB 내부 실행 순서도 같은지 알려 줘.",
         "tables": [], "oracle": {"rubric": ["WHERE는 그룹 이전 개별 행 조건", "HAVING은 집계된 그룹 조건", "논리적 설명 순서가 물리 실행 계획 보장은 아님"], "human_review": "not_reviewed"}},
        {"id": "N04", "category": "concept", "task_type": "concept", "dialect": "sqlite",
         "student_prompt": "LEFT JOIN에서 오른쪽 표의 점수 조건을 ON에 쓰는 것과 WHERE에 쓰는 것은 왜 달라질 수 있어? 실제 표가 없으니 원리를 설명해 줘.",
         "tables": [], "oracle": {"rubric": ["ON은 매칭 조건", "WHERE는 JOIN 뒤 결과 행을 거름", "오른쪽 NULL 행의 탈락 가능성과 왼쪽 보존 차이", "주어지지 않은 숫자 답을 원래 결과로 만들지 않음"], "human_review": "not_reviewed"}},
        {"id": "N05", "category": "query", "task_type": "write_sql", "dialect": "sqlite", "tables": [readings],
         "student_prompt": "전체 행 수와 measure 값이 NULL 아닌 행 수를 순서대로 구하는 SQL을 써 줘. 출력 별칭은 row_count, value_count로 해 줘.",
         "oracle": {"reference_sql": "SELECT COUNT(*) AS row_count, COUNT(measure) AS value_count FROM readings",
                    "expected": _expected(["row_count", "value_count"], [[4, 3]]), "columns_required": True}},
        {"id": "N06", "category": "query", "task_type": "explain_given_sql", "dialect": "sqlite", "tables": [samples],
         "student_prompt": "학생이 준 SQL의 결과를 계산하고 평균 분모에 NULL이 포함되는지 짧게 설명해 줘.",
         "question_sql": "SELECT SUM(v) AS total, COUNT(v) AS present, AVG(v) AS mean FROM samples",
         "oracle": {"reference_sql": "SELECT SUM(v) AS total, COUNT(v) AS present, AVG(v) AS mean FROM samples",
                    "expected": _expected(["total", "present", "mean"], [[18, 3, 6.0]]), "columns_required": True,
                    "rubric": ["평균 분모는 NULL 제외 3", "평균은 18/3=6"], "human_review": "not_reviewed"}},
        {"id": "N07", "category": "query", "task_type": "write_sql", "dialect": "sqlite", "tables": [visits],
         "student_prompt": "score가 70 이상인 행만 남긴 뒤, 남은 사람이 두 명 이상인 team과 그 인원 수를 구해 줘. team 오름차순, 별칭은 team, n으로 해 줘.",
         "oracle": {"reference_sql": "SELECT team, COUNT(*) AS n FROM visits WHERE score>=70 GROUP BY team HAVING COUNT(*)>=2 ORDER BY team",
                    "expected": _expected(["team", "n"], [["B", 2]], True), "columns_required": True}},
        {"id": "N08", "category": "query", "task_type": "explain_given_sql", "dialect": "sqlite", "tables": [bag],
         "student_prompt": "학생 SQL의 결과 행을 계산해 줘. 중복 행은 그대로 두고 출력 순서는 상관없어.",
         "question_sql": "SELECT v FROM bag WHERE v>=2 OR v IS NULL",
         "oracle": {"reference_sql": "SELECT v FROM bag WHERE v>=2 OR v IS NULL",
                    "expected": _expected(["v"], [[2], [2], [None], [4]]), "columns_required": True}},
        {"id": "N09", "category": "query", "task_type": "write_sql", "dialect": "sqlite", "tables": [devices, events],
         "student_prompt": "이벤트 없는 장치도 0으로 포함해서 장치별 이벤트 행 수를 구해 줘. reading이 NULL인 이벤트도 한 건이야. 출력 열은 id, event_count이며 id 순서로 정렬해 줘.",
         "oracle": {"reference_sql": "SELECT d.id, COUNT(e.device_id) AS event_count FROM devices d LEFT JOIN events e ON d.id=e.device_id GROUP BY d.id ORDER BY d.id",
                    "expected": _expected(["id", "event_count"], [[10, 2], [20, 1], [30, 0]], True), "columns_required": True}},
        {"id": "N10", "category": "query", "task_type": "write_sql", "dialect": "sqlite", "tables": [stock],
         "student_prompt": "category가 Z인 행의 COUNT(*), SUM(amount), AVG(amount)를 순서대로 계산하는 SQL을 써 줘. 별칭은 n, total, mean으로 해 줘.",
         "oracle": {"reference_sql": "SELECT COUNT(*) AS n, SUM(amount) AS total, AVG(amount) AS mean FROM stock WHERE category='Z'",
                    "expected": _expected(["n", "total", "mean"], [[0, None, None]]), "columns_required": True}},
        {"id": "N11", "category": "missing_or_dbms", "task_type": "explain_given_sql", "dialect": "sqlite", "tables": [],
         "student_prompt": "이 SQL 결과 몇이야? 표의 실제 행은 아직 보내지 않았어. 정확한 숫자를 알려면 필요한 것을 말해 줘.",
         "question_sql": "SELECT COUNT(score) AS valued FROM exam",
         "oracle": {"rubric": ["exam의 실제 score 값/행이 필요함", "NULL 제외 규칙은 설명 가능", "정확한 개수는 만들어내지 않음"], "human_review": "not_reviewed"}},
        {"id": "N12", "category": "missing_or_dbms", "task_type": "concept", "dialect": "oracle", "tables": [],
         "student_prompt": "Oracle용 SELECT NVL(NULL, '없음') FROM dual; 을 SQLite에서 실행해 실패했어. 그러면 Oracle에서도 틀린 SQL이라고 단정해도 돼? 검증 범위를 구분해 줘.",
         "oracle": {"rubric": ["SQLite 실패로 Oracle 오류를 단정하지 않음", "Oracle 실제 실행은 하지 않았다고 구분", "DBMS 고유 함수/dual 차이 설명"], "human_review": "not_reviewed"}},
    ]


def freeze_diagnostics(directory):
    directory = Path(directory)
    public_path, oracle_path, manifest_path = (directory / n for n in ("questions.json", "oracles.json", "manifest.json"))
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (digest(public_path), digest(oracle_path)) != (manifest["questions_sha256"], manifest["oracles_sha256"]):
            raise ValueError("Frozen diagnostics changed; preserve originals and use a new version")
        return manifest
    if public_path.exists() or oracle_path.exists():
        raise ValueError("Partial diagnostic files exist; inspect them before freezing")
    cases = authored_cases()
    public = [{key: value for key, value in case.items() if key != "oracle"} for case in cases]
    oracles = {case["id"]: case["oracle"] for case in cases}
    verification = []
    for case in cases:
        oracle = case["oracle"]
        if "reference_sql" not in oracle:
            continue
        actual = execute_sql(oracle["reference_sql"], {"tables": case["tables"]})
        comparison = compare_results_v2(actual, oracle["expected"], columns_required=oracle["columns_required"])
        verification.append({"id": case["id"], "actual": actual, "comparison": comparison})
        if not comparison["match"]:
            raise ValueError(f"Independent diagnostic expected result failed: {case['id']}")
    write_json(public_path, {"version": 1, "scope": "new_small_diagnostic_not_private_holdout", "questions": public})
    write_json(oracle_path, {"version": 1, "model_input": "FORBIDDEN", "oracles": oracles})
    manifest = {"version": 1, "frozen_at": datetime.now(timezone.utc).isoformat(),
                "status": "frozen_before_inference", "total": 12,
                "categories": dict(Counter(case["category"] for case in cases)),
                "questions_sha256": digest(public_path), "oracles_sha256": digest(oracle_path),
                "authorship": "assistant_self_authored_original_diagnostic", "human_review": "not_reviewed",
                "reference_replay": verification, "training_use": "forbidden_this_iteration",
                "after_results_code_changes": "If findings guide implementation changes, relabel this bundle development; do not claim untouched holdout"}
    write_json(manifest_path, manifest)
    return manifest


def public_prompt(question):
    """Allowlisted input construction; oracle/reference/expected fields are ignored."""
    lines = [f"DBMS: {question['dialect']}."]
    for table in question.get("tables", []):
        columns = ",".join(column["name"] for column in table["columns"])
        lines.append(f"{table['name']}({columns})=" + json.dumps(table["rows"], ensure_ascii=False))
    lines.append(question["student_prompt"])
    if question.get("question_sql"):
        lines.append("학생이 준 SQL: " + question["question_sql"])
    if question["category"] == "query" or question.get("split") == "development_regression":
        if question["task_type"] == "write_sql":
            lines.append('응답은 {"sql":"SQL문","explanation":"짧은 설명"} JSON 객체 하나로 주세요.')
        else:
            lines.append('응답은 {"columns":["출력 열"],"rows":[["결과값"]],"explanation":"짧은 설명"} JSON 객체 하나로 주세요. NULL은 JSON null입니다.')
    else:
        lines.append("한국어로 짧게 설명하고, 정확한 값에 필요한 정보가 없으면 구체적으로 질문하세요.")
    return "\n".join(lines)


def request_body(question, mode, request_id, adapter="base"):
    if mode not in {"model_only", "rag_only", "rag_tools"}:
        raise ValueError("Unknown experiment mode")
    prompt = public_prompt(question)
    problem = {"task_kind": {"explain_given_sql": "query_result", "write_sql": "write_sql", "concept": "concept"}[question["task_type"]],
               "dialect": question["dialect"].lower(), "raw_text": prompt, "source": {"kind": "typed"},
               # Synthetic harness fixtures are confirmed as exact test inputs,
               # not as student/teacher or human-reviewed educational content.
               "revision": 1, "confirmed": True,
               "tables": [{"name": t["name"], "columns": [{"name": c["name"], "type": c["type"]} for c in t["columns"]],
                           "rows": t["rows"]} for t in question.get("tables", [])]}
    if question.get("question_sql"):
        problem["query"] = question["question_sql"]
    return {"content": prompt, "request_id": request_id, "use_rag": mode != "model_only",
            "adapter": adapter, "verification_mode": "tools" if mode == "rag_tools" else "model_only", "problem": problem}


def freeze_development(root, directory):
    """Convert the supplied public 18 cases; separate answer data before inference."""
    directory = Path(directory) / "development18"
    public_path, oracle_path, manifest_path = (directory / n for n in ("questions.json", "oracles.json", "manifest.json"))
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (digest(public_path), digest(oracle_path)) != (manifest["questions_sha256"], manifest["oracles_sha256"]):
            raise ValueError("Frozen public development inputs changed")
        return directory, manifest
    source = Path(root) / "docs/source-pack-v02/edu_tutor_next_v02/fixtures/sql_cases_v02.json"
    cases = json.loads(source.read_text(encoding="utf-8"))["cases"]
    questions, oracles = [], {}
    for case in cases:
        public = {key: case[key] for key in ("id", "task_type", "student_prompt", "split", "dialect")}
        public["category"] = "query"
        public["tables"] = [_table(table["name"], table["columns"], table["rows"]) for table in case["tables"]]
        if case.get("question_sql"):
            public["question_sql"] = case["question_sql"]
        questions.append(public)
        oracle = case["oracle"]
        expected = _expected(oracle["expected_columns"], oracle["expected_rows"], oracle["ordered"])
        expected["numeric_abs_tolerance"] = oracle["numeric_tolerance"]
        expected["numeric_rel_tolerance"] = oracle["numeric_tolerance"]
        oracles[case["id"]] = {"reference_sql": oracle["reference_sql"], "expected": expected,
            "columns_required": case["task_type"] == "explain_given_sql",
            "alias_policy": "Given SQL specifies labels. Natural-language write-SQL questions do not prescribe reference aliases."}
    write_json(public_path, {"version": 1, "scope": "provided_public_development_regression", "questions": questions})
    write_json(oracle_path, {"version": 1, "model_input": "FORBIDDEN", "oracles": oracles})
    manifest = {"version": 1, "frozen_at": datetime.now(timezone.utc).isoformat(), "status": "public_development",
                "total": len(questions), "source_sha256": digest(source), "questions_sha256": digest(public_path),
                "oracles_sha256": digest(oracle_path), "human_review": "not_reviewed", "training_use": "forbidden_this_iteration"}
    write_json(manifest_path, manifest)
    return directory, manifest


def _json_response(raw):
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        if isinstance(raw, str) and raw.strip().startswith("```json") and raw.strip().endswith("```"):
            return json.loads(raw.strip()[7:-3].strip())
        raise ValueError("No single JSON object response")


def grade_response(question, oracle, raw, *, grading_protocol="original"):
    if grading_protocol not in {"original", "json_fence_v2"}:
        raise ValueError("Unknown diagnostic grading protocol")
    if "expected" not in oracle:
        return {"status": "rubric_review_pending", "human_review": "not_reviewed", "rubric": oracle["rubric"],
                "reason": "No keyword-only correctness verdict for conceptual/clarification answers"}
    try:
        if question["task_type"] == "write_sql":
            if grading_protocol == "json_fence_v2":
                from edu_tutor.problems.sql_response import extract_sql_candidate
                sql = extract_sql_candidate(raw)
            else:
                sql = extract_sql(raw)
            actual = execute_sql(sql, {"tables": question["tables"]}, dialect=question["dialect"].lower())
        else:
            parsed = _json_response(raw)
            if not isinstance(parsed, dict) or not isinstance(parsed.get("columns"), list) or not isinstance(parsed.get("rows"), list):
                raise ValueError("Response has no columns/rows result")
            sql = None
            actual = {"status": "executed", "columns": parsed["columns"], "rows": parsed["rows"],
                      "provenance": "model_predicted_result_not_executed"}
        if actual.get("status") != "executed":
            return {"status": "execution_error", "sql": sql, "actual": actual,
                    "human_review": "not_reviewed"}
        comparison = compare_results_v2(actual, oracle["expected"], columns_required=oracle.get("columns_required", False))
        return {"status": "correct_result" if comparison["match"] else "incorrect_result", "sql": sql,
                "actual": actual, "comparison": comparison, "explanation_review": "not_reviewed",
                "human_review": "not_reviewed"}
    except (ValueError, KeyError, TypeError) as exc:
        return {"status": "ungradable_format", "error": str(exc)[:300], "human_review": "not_reviewed"}


def _display_result_matches(content, result):
    """Check the actual serialized table, independently of the app formatter.

    The bounded app currently uses one pipe-delimited header and one line per
    row. A changed or ambiguous presentation stays unverified, never guessed.
    SQL may occur elsewhere in the answer, but matching only a number is not
    sufficient to establish a displayed result.
    """
    if not isinstance(content, str) or not isinstance(result, dict):
        return False
    lines = content.splitlines()
    wanted = [" | ".join(result.get("columns", []))]
    wanted += [" | ".join("NULL" if v is None else str(v) for v in row) for row in result.get("rows", [])]
    if not result.get("rows"):
        wanted.append("결과 행이 없습니다.")
    return bool(wanted[0]) and any(lines[index:index+len(wanted)] == wanted for index in range(len(lines)))


def grade_app_response(question, oracle, answer, *, grading_protocol="original"):
    """Distinguish a computed tool result, actual display, and requested task."""
    evidence = answer.get("evidence")
    content = answer.get("content", "")
    if not isinstance(evidence, dict):
        reason = (answer.get("generation_snapshot") or {}).get("finish_reason")
        if reason and reason != "eos":
            return {"status":"truncated_or_incomplete","finish_reason":reason,"human_review":"not_reviewed"}
        return grade_response(question, oracle, content, grading_protocol=grading_protocol)
    state = evidence.get("status")
    if state == "needs_input":
        return {"status": "clarification_needed", "reasons": evidence.get("reasons", []),
                "rubric_review": "not_reviewed", "human_review": "not_reviewed"}
    if state in {"stopped", "unsupported"}:
        return {"status": "safe_stop", "reasons": evidence.get("reasons", []),
                "execution": evidence.get("execution"), "human_review": "not_reviewed"}
    if state != "verified" or "expected" not in oracle:
        return grade_response(question, oracle, content, grading_protocol=grading_protocol)
    result = evidence.get("result")
    if not isinstance(result, dict):
        return {"status": "missing_tool_result", "human_review": "not_reviewed"}
    comparison = compare_results_v2({"status": "executed", **result}, oracle["expected"],
                                    columns_required=oracle.get("columns_required", False))
    shown = _display_result_matches(content, result)
    # Writing SQL and predicting its results are different student tasks.
    sql_shown = question["task_type"] != "write_sql" or (
        isinstance(evidence.get("sql"), str) and evidence["sql"].strip() in content)
    status = ("incorrect_result" if not comparison["match"] else
              "display_mismatch" if not shown else "wrong_task_format" if not sql_shown else "correct_result")
    return {"status": status, "tool_result": result, "comparison": comparison,
            "displayed_result_matches_evidence": shown, "requested_sql_shown": sql_shown,
            "basis": "Independent test oracle after inference; tool output is not model performance",
            "explanation_review": "not_reviewed", "human_review": "not_reviewed"}


def grade_raw_model(question, oracle, answer, *, grading_protocol="original"):
    """Never relabel a corrected app answer as the original model output."""
    raw = answer.get("raw_model_response")
    if not isinstance(raw, str):
        return {"status": "raw_output_unavailable", "human_review": "not_reviewed"}
    snapshot = answer.get("generation_snapshot") or {}
    reason = snapshot.get("finish_reason")
    if reason and reason != "eos":
        return {"status": "truncated_or_incomplete", "finish_reason": reason,
                "partial_response_grade_diagnostic_only": grade_response(question, oracle, raw, grading_protocol=grading_protocol),
                "human_review": "not_reviewed"}
    return grade_response(question, oracle, raw, grading_protocol=grading_protocol)


def run_diagnostics(root, directory, *, mode, run_id, base_url="http://127.0.0.1:8000", max_seconds=1800,
                    ids=None, adapter="base", suite="new12", grading_protocol="json_fence_v2"):
    """Run sequential authenticated chat jobs only; root schedules the GPU window."""
    import httpx
    root, directory = Path(root), Path(directory)
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.port != 8000 or parsed.path not in {"", "/"}:
        raise ValueError("Diagnostics may contact only the authorized local API port 8000")
    if not 1 <= max_seconds <= 5400:
        raise ValueError("Bounded diagnostic run must fit within 90 minutes")
    if not run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in run_id):
        raise ValueError("Unsafe run ID")
    if grading_protocol not in {"original", "json_fence_v2"}:
        raise ValueError("Unknown diagnostic grading protocol")
    if suite == "new12":
        manifest = freeze_diagnostics(directory)
    elif suite == "development18":
        directory, manifest = freeze_development(root, directory)
    else:
        raise ValueError("Unknown diagnostic suite")
    public = json.loads((directory / "questions.json").read_text(encoding="utf-8"))["questions"]
    oracles = json.loads((directory / "oracles.json").read_text(encoding="utf-8"))["oracles"]
    if ids:
        requested = set(ids)
        if requested - {q["id"] for q in public}:
            raise ValueError("Unknown requested diagnostic ID")
        public = [q for q in public if q["id"] in requested]
    output_dir = directory / f"{run_id}-{mode}"
    output_dir.mkdir(parents=True, exist_ok=False)
    report = {"tier": "T2", "status": "running", "mode": mode, "run_id": run_id, "suite": suite,
        "started_at": datetime.now(timezone.utc).isoformat(), "manifest": manifest,
        "generation_protocol": {"transport": "authenticated existing API and GPU job queue", "adapter": adapter,
             "max_request_wall_seconds": 300, "max_run_wall_seconds": max_seconds, "old_256_protocol_comparable": False,
             "max_new_tokens": 512, "do_sample": False, "enable_thinking": False, "context_token_limit": 2048,
             "tool_repair_limit": 1 if mode == "rag_tools" else 0,
             "notice": "Production chat settings, not the old frozen model evaluation; no oracle fields in API requests"},
        "diagnostic_grading_protocol": grading_protocol,
        "sql_extraction_protocol": "phase2_sql_response_v2_json_fence" if grading_protocol == "json_fence_v2" else "legacy_sql_sandbox_frozen_v1",
        "input_confirmation": "Harness confirms the exact synthetic tables/query as test inputs. No human reviewed these questions or answers. No inferred intent or reference SQL is added to write-SQL problems.",
        "human_review": "not_reviewed", "items": [], "pending_ids": [q["id"] for q in public]}
    # The task's source snapshotter excludes credentials, user DBs and weights.
    # Capture once before inference, so later documentation or reruns cannot
    # silently relabel which implementation produced these responses.
    spec = importlib.util.spec_from_file_location("phase2_source_snapshot", root / "scripts/phase2_snapshot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source_snapshot = module.snapshot(root)
    write_json(output_dir / "source-before.json", source_snapshot)
    report["source_sha256"] = source_snapshot["source_sha256"]
    write_json(output_dir / "protocol.json", {"version":1,"frozen_before_inference_at":report["started_at"],
        "mode":mode,"suite":suite,"run_id":run_id,"source_sha256":report["source_sha256"],
        "questions_sha256":manifest["questions_sha256"],"oracles_sha256":manifest["oracles_sha256"],
        "generation_protocol":report["generation_protocol"],"input_confirmation":report["input_confirmation"],
        "diagnostic_grading_protocol":grading_protocol,
        "sql_extraction_protocol":report["sql_extraction_protocol"],
        "requested_ids":[q["id"] for q in public],"model_input_contains_oracles":False,
        "interpretation":"Post-generation numerical-result checks only; prose and human quality remain separately unreviewed."})
    write_json(output_dir / "report.json", report)
    token = (root / ".local/auth-token").read_text(encoding="utf-8").strip()
    started = time.monotonic()
    terminal = {"succeeded", "failed", "cancelled", "interrupted", "blocked"}
    with httpx.Client(base_url=base_url, headers={"Authorization": "Bearer " + token}, trust_env=False,
                      timeout=20, follow_redirects=False) as client:
        def call(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if response.status_code >= 400:
                raise RuntimeError(f"{method} {path}: HTTP {response.status_code}")
            return response.json()
        try:
            report["initial_model_state"] = call("GET", "/api/models")
            for question in public:
                if time.monotonic() - started + 300 > max_seconds:
                    report["status"] = "budget_limited"
                    break
                session = call("POST", "/api/sessions", json={"title": f"v0.2 진단 {mode} {question['id']}"})
                body = request_body(question, mode, uuid4().hex, adapter=adapter)
                # Oracle is intentionally loaded only by the local post-generation grader.
                write_json(output_dir / f"{question['id']}-public-request.json", body)
                begin = time.monotonic()
                submitted = call("POST", f"/api/sessions/{session['id']}/messages", json=body)
                job_id = submitted["job_id"]
                while True:
                    job = call("GET", f"/api/jobs/{job_id}")
                    if job["state"] in terminal:
                        break
                    if time.monotonic() - begin >= 300:
                        call("POST", f"/api/jobs/{job_id}/cancel")
                        job = {**job, "state": "deadline_cancel_requested"}
                        break
                    time.sleep(.5)
                item = {"id": question["id"], "category": question["category"], "session_id": session["id"],
                        "job": job, "request_wall_seconds": time.monotonic() - begin,
                        "cache_or_warmth": "not_assumed; inspect generation_snapshot", "human_review": "not_reviewed"}
                if job["state"] == "succeeded":
                    messages = call("GET", f"/api/sessions/{session['id']}/messages")
                    answer = next(m for m in messages if m["id"] == job["result"]["message_id"])
                    item["answer"] = answer
                    item["raw_model_grade"] = grade_raw_model(question, oracles[question["id"]], answer, grading_protocol=grading_protocol)
                    item["app_display_grade"] = grade_app_response(question, oracles[question["id"]], answer, grading_protocol=grading_protocol)
                    item["app_evidence"] = answer.get("evidence")
                    item["model_plus_rag_primary_before_tools"] = mode != "model_only"
                else:
                    item["raw_model_grade"] = {"status": "request_failed", "human_review": "not_reviewed"}
                    item["app_display_grade"] = {"status": "request_failed", "human_review": "not_reviewed"}
                report["items"].append(item)
                report["pending_ids"].remove(question["id"])
                write_json(output_dir / "report.json", report)
                print(json.dumps({"id": question["id"], "mode": mode, "job_state": job["state"],
                                  "raw_grade": item["raw_model_grade"]["status"], "seconds": round(item["request_wall_seconds"], 3)}), flush=True)
                if job["state"] == "deadline_cancel_requested":
                    report["status"] = "request_timeout"
                    break
                if job["state"] == "blocked" and "예산" in (job.get("error") or ""):
                    report["status"] = "budget_limited"
                    break
            if not report["pending_ids"]:
                report["status"] = "completed"
        except Exception as exc:
            report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            report["finished_at"] = datetime.now(timezone.utc).isoformat()
            report["run_wall_seconds"] = time.monotonic() - started
            report["counts"] = {key: dict(Counter(item[key]["status"] for item in report["items"])) for key in ("raw_model_grade", "app_display_grade")}
            report["coverage"] = {"answerable_query_total": sum(q["category"] == "query" for q in public),
                "answered_query_results": sum(item["category"] == "query" and item["app_display_grade"]["status"] in {"correct_result", "incorrect_result"} for item in report["items"]),
                "definition": "A scored result was produced; correct and incorrect separately reported. Concept/helpfulness coverage needs rubric inspection."}
            report["limitations"] = ["Small self-authored diagnostic or public development cases, not a private holdout or educational certification.",
                "Concept and clarification correctness remain rubric-review-pending; no keyword hit is a human-quality pass.",
                "Tool/evidence correctness, displayed result binding, raw model correctness and prose quality are separate.",
                "Each complete API latency is reported; model warmth is not inferred from request order."]
            write_json(output_dir / "report.json", report)
    return report
