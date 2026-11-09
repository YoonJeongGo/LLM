"""Conservative format checks on transcription text, not an OCR accuracy score."""
from __future__ import annotations

import re


CHECK_VERSION = 1
PREFIX = "자동 형식 점검, 원문 확인 필요: "
_COMPARISON_END = re.compile(r"(>=|<=|<>|!=|=|>|<)\s*;?\s*$")
_SQL_CONTEXT = re.compile(r"\b(?:SELECT|WHERE|HAVING|ON|AND|OR)\b", re.IGNORECASE)
_CUTOFF_NOTE = re.compile(r"\[[^\]\n]*(?:조건|선택지)[^\]\n]*(?:잘려|잘린|잘렸)[^\]\n]*\]")
_CLAUSE_START = re.compile(r"^(?:FROM|WHERE|GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT|UNION|AND|OR)\b", re.IGNORECASE)
_RHS_START = re.compile(r"^(?:[-+]?\d|['\"(?:]|NULL\b|[A-Za-z_][\w.]*)", re.IGNORECASE)


def missing_condition_warnings(text: str) -> list[str]:
    """Flag only obvious cuts; ordinary SQL validity is deliberately unchecked.

    A value on the following line can complete a comparison, so valid multiline
    expressions such as ``salary >=\n1000`` are not reported as missing.
    """
    lines = text.splitlines()
    warnings = []
    context_seen = False
    for number, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        context_seen = context_seen or bool(_SQL_CONTEXT.search(stripped))
        comparison = _COMPARISON_END.search(stripped)
        if not context_seen or not comparison:
            continue
        following = next((item.strip() for item in lines[number + 1:] if item.strip()), "")
        continuation = bool(_RHS_START.match(following)) and not _CLAUSE_START.match(following)
        if not continuation:
            warnings.append(PREFIX + f"SQL 비교 연산자 {comparison.group(1)} 뒤의 값 또는 식이 보이지 않습니다. 빠진 조건을 입력하세요.")
    if _CUTOFF_NOTE.search(text):
        warnings.append(PREFIX + "조건 또는 선택지가 잘렸다는 안내가 있습니다. 잘린 부분의 원문을 입력하세요.")
    return list(dict.fromkeys(warnings))


def check_transcription(candidate: dict) -> dict:
    """Return a copy with derived warnings; never rewrite the recognized text."""
    value = dict(candidate)
    original = value.get("original_text", value.get("question", ""))
    warnings = missing_condition_warnings(original)
    value["missing_conditions"] = list(dict.fromkeys([*value.get("missing_conditions", []), *warnings]))
    value["format_check"] = {"kind": "deterministic_transcription_check", "version": CHECK_VERSION,
                             "warnings": warnings, "recognition_accuracy": "not_established"}
    return value
