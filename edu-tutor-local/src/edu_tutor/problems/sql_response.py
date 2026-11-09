"""Phase-2 response formatting support, separate from the frozen v1 extractor.

This only extracts a candidate. The caller must still perform the existing
isolated SQL execution, schema and intent checks before accepting an answer.
"""
from __future__ import annotations

import json
import re

from edu_tutor.evaluation.sql_sandbox import extract_sql as _legacy_extract_sql

SQL_EXTRACTION_PROTOCOL = "v021_sql_response_v3_json_prefix_plain_suffix"
_JSON_FENCE = re.compile(
    r"[ \t\r\n]*```[ \t]*json[ \t]*\r?\n(.*?)\r?\n[ \t]*```[ \t\r\n]*",
    re.IGNORECASE | re.DOTALL,
)
_STATEMENT_TOKEN = re.compile(
    r"\b(?:SELECT|WITH|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|ATTACH|DETACH|"
    r"PRAGMA|VACUUM|REPLACE|EXPLAIN|BEGIN|COMMIT|ROLLBACK)\b", re.IGNORECASE)
_ALLOWED_KEYS = {"sql", "explanation", "schema_version"}


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("ambiguous_parse: duplicate JSON key")
        value[key] = item
    return value


def _invalid_constant(value):
    raise ValueError("ambiguous_parse: non-JSON numeric constant")


def _plain_suffix(text):
    """Allow prose/table/inline identifiers, never another code candidate.

    This deliberately rejects standalone SQL statement words even when they
    might be prose. It does not interpret a second statement or pick one.
    """
    if (any(marker in text for marker in ("{", "}", "```", "~~~"))
            or text.lstrip().startswith(("[", '"'))
            or _STATEMENT_TOKEN.search(text)
            or any(ord(c) < 32 and c not in "\t\r\n" for c in text)):
        raise ValueError("ambiguous_parse: suffix contains structured data or another SQL candidate")
    stripped = text.strip()
    if stripped:
        try:
            json.loads(stripped, parse_constant=_invalid_constant)
        except ValueError:
            pass
        else:
            raise ValueError("ambiguous_parse: second JSON value")


def parse_json_response(output, *, require_sql=True):
    """Return one unmodified JSON object and its bounded, untrusted prose tail."""
    if isinstance(output, dict):
        value, suffix = output, ""
    elif isinstance(output, str) and len(output) <= 60000:
        stripped = output.lstrip()
        match = _JSON_FENCE.fullmatch(output)
        try:
            if match:
                value = json.loads(match.group(1), object_pairs_hook=_unique_object,
                                   parse_constant=_invalid_constant)
                suffix = ""
            elif stripped.startswith("{"):
                value, end = json.JSONDecoder(object_pairs_hook=_unique_object,
                    parse_constant=_invalid_constant).raw_decode(stripped)
                suffix = stripped[end:]
                _plain_suffix(suffix)
            else:
                raise ValueError("not a complete JSON response object")
        except (ValueError, TypeError) as exc:
            raise ValueError("ambiguous_parse: invalid object or untrusted structured suffix") from exc
    else:
        raise ValueError("ambiguous_parse")
    if not isinstance(value, dict) or set(value) - _ALLOWED_KEYS:
        raise ValueError("ambiguous_parse: disallowed JSON fields")
    if require_sql and (not isinstance(value.get("sql"), str) or not value["sql"].strip()):
        raise ValueError("ambiguous_parse: SQL candidate missing")
    return value, suffix


def extract_sql_candidate(output):
    """Extract one candidate; a prose tail is never SQL or verified speech."""
    if isinstance(output, dict) or isinstance(output, str) and output.lstrip().startswith("{"):
        value, _ = parse_json_response(output)
        return _legacy_extract_sql(value)
    if not isinstance(output, str) or len(output) > 60000:
        raise ValueError("ambiguous_parse")
    if _JSON_FENCE.fullmatch(output):
        value, _ = parse_json_response(output)
        return _legacy_extract_sql(value)
    # Preserve the prior single SQL-fence form while rejecting another
    # candidate outside that fence. The frozen evaluation extractor is intact.
    sql = _legacy_extract_sql(output)
    block = re.search(r"```[^\n]*\n.*?```", output, re.DOTALL)
    if block is None:
        raise ValueError("ambiguous_parse")
    _plain_suffix(output[:block.start()] + output[block.end():])
    return sql
