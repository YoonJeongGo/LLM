"""Strict dataset contracts. Schema validation is necessary, not expert review."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator


class DatasetError(ValueError):
    pass


def load_records(paths):
    records = []
    for path in paths:
        path = Path(path)
        for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DatasetError(f"{path.name}:{line_number}: invalid JSON") from exc
            records.append(value)
    return records


def _normal(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().casefold()


def _sql_family_shape(record):
    """Catch renamed/numeric variants; metadata alone cannot prove independence."""
    if "expected" not in record:
        return None
    sql = _normal(record["expected"]["sql"])
    sql = re.sub(r"'(?:''|[^'])*'", "'value'", sql)
    sql = re.sub(r"\b\d+(?:\.\d+)?\b", "NUMBER", sql)
    names = {t["name"].lower() for t in record["fixture"]["tables"]}
    names.update(c["name"].lower() for t in record["fixture"]["tables"] for c in t["columns"])
    names.update(re.findall(r"\bas\s+([a-z_][a-z_0-9]*)", sql))
    mapped = {}
    def abstract(match):
        value = match.group(0)
        if value in names:
            return mapped.setdefault(value, f"identifier{len(mapped)}")
        return value
    return re.sub(r"\b[a-z_][a-z_0-9]*\b", abstract, sql).rstrip("; ")


def validate_dataset(paths=None, profile="demo", *, records=None, schema_path=None, enforce_minimums=True):
    if profile not in {"demo", "production"}:
        raise DatasetError("profile must be explicitly demo or production")
    if records is None:
        records = load_records(paths or [])
    if not records:
        raise DatasetError("dataset is empty")
    if schema_path is None:
        schema_path = Path(__file__).resolve().parents[3] / "schemas" / "qa_record.schema.json"
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8-sig"))
    validator = Draft202012Validator(schema)
    seen_ids, seen_questions, seen_answers, family_split, sql_shapes = set(), {}, {}, {}, {}
    counts = Counter()
    for index, record in enumerate(records):
        try:
            json.dumps(record, allow_nan=False)
        except (ValueError, TypeError) as exc:
            raise DatasetError(f"record {index}: nonfinite or non-JSON value") from exc
        errors = sorted(validator.iter_errors(record), key=lambda e: str(list(e.path)))
        if errors:
            raise DatasetError(f"record {index}: schema: {errors[0].message}")
        identity, split = record["id"], record["split"]
        if identity in seen_ids:
            raise DatasetError(f"duplicate id: {identity}")
        seen_ids.add(identity)
        family = record["problem_family_id"]
        if family in family_split and family_split[family] != split:
            raise DatasetError(f"family leakage: {family}")
        family_split[family] = split
        roles = [m["role"] for m in record["messages"]]
        if roles not in (["user", "assistant"], ["system", "user", "assistant"]):
            raise DatasetError(f"{identity}: only a single user/assistant turn is supported")
        for role, seen in (("user", seen_questions), ("assistant", seen_answers)):
            text = _normal(next(m["content"] for m in record["messages"] if m["role"] == role))
            if not text:
                raise DatasetError(f"{identity}: blank {role} content")
            if text in seen:
                raise DatasetError(f"duplicate {role} content: {identity} / {seen[text]}")
            seen[text] = identity
        if record["review_status"] == "rejected":
            raise DatasetError(f"{identity}: rejected record")
        if record["review_status"] == "generated_unreviewed" and not record["demo_only"]:
            raise DatasetError(f"{identity}: generated content must remain demo_only")
        if profile == "production" and (record["review_status"] != "human_reviewed" or record["demo_only"]):
            raise DatasetError(f"{identity}: production requires human_reviewed, demo_only=false")
        if any(not str(record["source"][key]).strip() for key in ("title", "rights_note", "created_by")):
            raise DatasetError(f"{identity}: missing source attribution or rights")
        if ("fixture" in record) != ("expected" in record):
            raise DatasetError(f"{identity}: fixture and expected must appear together")
        if "fixture" in record:
            if record.get("sql_dialect") != "sqlite":
                raise DatasetError(f"{identity}: executable demo dialect must be sqlite")
            tables = record["fixture"]["tables"]
            if len({table["name"].casefold() for table in tables}) != len(tables):
                raise DatasetError(f"{identity}: duplicate table name")
            for table in tables:
                names = [col["name"].casefold() for col in table["columns"]]
                if len(set(names)) != len(names):
                    raise DatasetError(f"{identity}: duplicate column name")
                for row in table["rows"]:
                    if len(row) != len(names):
                        raise DatasetError(f"{identity}: row/column width mismatch")
                    if any(isinstance(value, str) and value.strip().upper() == "NULL" for value in row):
                        raise DatasetError(f"{identity}: use JSON null, not the string NULL")
            expected = record["expected"]
            if any(len(row) != len(expected["columns"]) for row in expected["rows"]):
                raise DatasetError(f"{identity}: expected row/column width mismatch")
            if any(isinstance(v, str) and v.strip().upper() == "NULL" for row in expected["rows"] for v in row):
                raise DatasetError(f"{identity}: expected NULL must be JSON null")
            shape = _sql_family_shape(record)
            if shape in sql_shapes and sql_shapes[shape][0] != split:
                raise DatasetError(f"structural SQL family leakage: {identity} / {sql_shapes[shape][1]}")
            sql_shapes[shape] = (split, identity)
        counts[split] += 1
    if enforce_minimums:
        for split, minimum in {"train": 24, "validation": 8, "test": 12}.items():
            if counts[split] < minimum:
                raise DatasetError(f"{split} requires at least {minimum}, got {counts[split]}")
    canonical = json.dumps(sorted(records, key=lambda r: r["id"]), ensure_ascii=False,
                           sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "valid": True, "profile": profile, "record_count": len(records), "counts": dict(counts),
        "family_count": len(family_split), "sha256": hashlib.sha256(canonical).hexdigest(),
        "human_review": "not_reviewed" if any(r["review_status"] != "human_reviewed" for r in records) else "declared_human_reviewed",
        "note": "Family IDs are declared metadata; semantic near-duplicate review is still required.",
    }
