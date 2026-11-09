"""Bounded teaching requests, kept separate from the original SQL conditions.

This parser knows no answers, table values or evaluation IDs. Unrecognized
comparison targets remain explicit unmet requests, not silently ignored text.
"""
from __future__ import annotations

import re

NULL = r"(?:NULL|널)"
ZERO = r"(?<![A-Za-z_0-9])(?:0|영)(?![0-9])"
EMPTY = r"(?:빈\s*(?:입력|표|테이블)|입력\s*(?:행|값)(?:이|이\s*하나도)?\s*없|행이\s*하나도\s*없)"
COMPARE = r"비교|대조|차이|달라|다르|구분"
WINDOW = r"(?<![A-Za-z_0-9])(?:LEAD|LAG|ROW_NUMBER|DENSE_RANK|RANK|NTILE|FIRST_VALUE|LAST_VALUE)\s*(?:\(|를\s*(?:이용|사용)|함수|윈도우|창)|윈도우\s*(?:함수|연산)|창\s*함수|\bOVER\s*\("


def visible_text(text):
    return re.sub(r"'(?:[^']|'')*'", lambda m: " " * len(m[0]), text)


def source_row_references(question, table):
    """Resolve exact source strings only; never create a filter or guess a name.

    Quoted literals can report an absent value precisely. Unquoted strings
    must actually occur in source cells and have a complete word/particle
    boundary. A value appearing in several rows remains ambiguous.
    """
    if not table:
        return [], question
    locations = {}
    for ri, row in enumerate(table["rows"]):
        for ci, value in enumerate(row):
            if isinstance(value, str) and value:
                locations.setdefault(value, []).append((ri, ci))
    spans = []
    for match in re.finditer(r"(['\"])([^'\"]+)\1", question):
        value = match[2]
        if value.casefold() in {"null", "널", "0", "영"} and value not in locations:
            continue
        spans.append((match.start(), match.end(), value))
    for value in locations:
        if value.casefold() in {"null", "널", "0", "영"}:
            continue
        pattern = (r"(?<![\w])" + re.escape(value) +
                   r"(?=$|\s|[.,?!]|(?:인\s*)?행|(?:와도|과도|와|과|도|의|은|는|를|을)(?=$|\s|[.,?!]|NULL|널|0|비교|대조|차이|행))")
        for match in re.finditer(pattern, question):
            if not any(start <= match.start() < end for start, end, _ in spans):
                spans.append((match.start(), match.end(), value))
    references = []
    for value in dict.fromkeys(value for _, _, value in sorted(spans)):
        cells = locations.get(value, [])
        rows = sorted({ri for ri, _ in cells})
        references.append({"literal": value, "status": "unique" if len(rows) == 1 else "ambiguous" if rows else "missing",
            "row_indices": rows, "row_ids": [table["row_ids"][ri] for ri in rows],
            "cell_ids": [table["cell_ids"][ri][ci] for ri, ci in cells]})
    normalized = question
    for start, end, _ in sorted(spans, reverse=True):
        normalized = normalized[:start] + "원본" + normalized[end:]
    return references, normalized


def requested_explanations(question, *, supplementary=False, source_table=None):
    q = visible_text(question)
    compare = bool(re.search(COMPARE, q))
    references, comparison_text = source_row_references(question, source_table) if supplementary and compare else ([], question)
    kinds = []
    if supplementary and re.search(r"포함|제외|남(?:아|았|는|는가)|통과|조건|이유|왜|어째서", q):
        kinds.append("row_inclusion")
    if re.search(NULL, q, re.I) and (compare or re.search(r"(?:NULL|널).*(?:의미|행은|경우는|라면)", q, re.I)
                                    or supplementary and re.search(r"(?:NULL|널).*설명", q, re.I)):
        kinds.append("null_comparison")
    if re.search(ZERO, q, re.I) and compare:
        kinds.append("zero_comparison")
    if re.search(EMPTY, q, re.I):
        kinds.append("empty_input")
    if supplementary and compare and (re.search(r"원본\s*\d+\s*행", q) or references):
        kinds.append("row_comparison")
    if supplementary and re.search(r"정렬|순서|우선순위|동점|먼저|앞|뒤", q):
        kinds.append("ordering")
    unsupported = []
    for reference in references:
        if reference["status"] == "missing":
            unsupported.append(f"비교 대상 확인 필요: 원본 표에 문자값 {reference['literal']!r}이 없습니다. 실제 비교할 행을 확인해 주세요.")
        elif reference["status"] == "ambiguous":
            unsupported.append(f"비교 대상 확인 필요: 문자값 {reference['literal']!r}이 원본 " +
                               ", ".join(str(i+1) for i in reference["row_indices"]) + "행에 있습니다. 어느 행인지 지정해 주세요.")
    if re.search(WINDOW, q, re.I):
        unsupported.append("현재 미지원: 윈도우 함수의 설명·계산은 이 수업 범위에 포함하지 않습니다.")
    if (supplementary and compare and re.search(r"행|값|음수|양수", q)
            and not re.search(r"(?<![A-Za-z_0-9])(?:COUNT|SUM|AVG|MIN|MAX)(?![A-Za-z_0-9])", q, re.I)
            and not any(k in kinds for k in ("null_comparison", "zero_comparison", "empty_input", "row_comparison"))):
        unsupported.append("현재 미지원: 이 보충 설명의 행 비교는 원본 NULL·0 비교만 처리합니다. 요청한 다른 비교 대상은 아직 설명하지 못합니다.")
    elif compare and re.search(r"(?:음수|양수|문자열|다른\s*표)(?:인|의|와|과|\s|행)", q):
        unsupported.append("현재 미지원: NULL·0 이외에 요청한 비교 대상까지 이 설명으로 검증하지 못합니다.")
    if supplementary and compare:
        # A recognized NULL clause must not hide a second unhandled operand.
        # Only explicit source-row numbers and NULL/0 are resolved here. Keep
        # arbitrary value/name selection behind a precise clarification.
        operand_text = visible_text(comparison_text)
        # These refer to the unchanged predicate and the existing sort tie
        # rule, not a new, unidentified "same row" comparison target.
        operand_text = re.sub(r"같은\s*행\s*조건", "조건", operand_text)
        operand_text = re.sub(r"값이\s*같은\s*행들(?:의)?\s*순서", "동점 순서", operand_text)
        operands = re.sub(r"원본\s*\d+\s*행|\d+\s*(?:순위|차\s*정렬)", " ", operand_text)
        numbers = re.findall(r"(?<![A-Za-z_0-9])[-+]?\d+(?:\.\d+)?(?![A-Za-z_0-9])", operands)
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", comparison_text)
        row_labels = re.findall(r"([A-Za-z_0-9가-힣]+)\s*행", operands)
        allowed_labels = {"null", "null인", "널", "널인", "0", "0인", "영", "영인", "이", "그",
                          "선택한", "선택", "해당", "원본", "원본인", "현재", "비교할", "고른", "모든", "전체", "입력"}
        connected = re.sub(r"(?:다른\s*)?원본\s*\d+\s*행", "원본행", operand_text)
        after = re.findall(r"(?:NULL|널|0)(?:인)?\s*(?:행|값)?\s*(?:과|와|하고|및|랑)\s*(?:의\s*)?([A-Za-z_0-9가-힣]+)", connected, re.I)
        before = re.findall(r"([A-Za-z_0-9가-힣]+?)(?:과|와|하고|및|랑)\s*(?:NULL|널|0)(?![0-9])", connected, re.I)
        allowed_after = ("비교", "대조", "차이", "구분", "의차이", "의비교", "의구분", "의대조", "다른점",
                         "선택", "이행", "이", "해당", "원본", "현재", "정렬", "null", "널", "0", "영")
        unresolved_connected = (any(not word.casefold().startswith(allowed_after) for word in after)
                                or any(word.casefold().removesuffix("행").removesuffix("값") not in allowed_labels
                                       and word.casefold() not in {"행", "값", "정렬", "순서", "이유", "조건", "뜻", "의미", "포함", "제외", "차이"} for word in before))
        if (any(float(n) != 0 for n in numbers)
                or any(s.strip().casefold() not in {"null", "널", "0", "영"} for s in quoted)
                or any(label.casefold() not in allowed_labels for label in row_labels) or unresolved_connected):
            unsupported.append("비교 대상 확인 필요: NULL·0 또는 원본 행 번호 이외의 값·이름으로 지정한 행은 아직 연결하지 못했습니다. 비교할 원본 행 번호를 지정해 주세요.")
    return {"version": "bounded_explanation_requests_v1", "requested": list(dict.fromkeys(kinds)), "source_row_references": references,
            "unsupported": unsupported, "full_free_language_verified": False}


def split_explanation_tail(question):
    """Remove only complete, separate supported teaching clauses from SQL intent.

    A WHERE operand, quoted value, filter verb, sorting direction or unknown
    words cannot disappear under an 'explain' marker. The entire original text
    remains in ProblemInput and is separately handled by the lesson renderer.
    """
    atoms = r"(?:NULL|널|0|영)(?:\s*(?:인\s*)?(?:행|값)(?:들)?)?"
    null_zero = rf"{atoms}(?:\s*(?:과|와|하고|및|/|·)\s*{atoms})?\s*(?:의\s*)?(?:차이|비교|구분|의미)"
    empty = r"(?:빈\s*(?:입력|표|테이블)(?:일\s*때)?|입력\s*행이\s*없을\s*때)(?:의\s*|\s*)(?:결과|차이|의미)"
    ending = r"\s*(?:도|를|을|까지)?\s*(?:설명해\s*(?:주세요|줘)|알려\s*(?:주세요|줘)|설명하세요)\s*[.?!。]*"
    clause = re.compile(rf"\s*(?:또한\s*|추가로\s*)?(?:{null_zero}|{empty}){ending}\s*", re.I)
    # Only trailing independently delimited clauses. Never split decimal dots
    # or semicolons inside quoted SQL values.
    visible = visible_text(question)
    boundaries = [m for m in re.finditer(r"[;；\n]+|(?<=[.!?])\s+|\s+그리고\s+", visible)]
    end = len(question)
    removed = []
    for boundary in reversed(boundaries):
        if boundary.end() >= end:
            continue
        tail = question[boundary.end():end]
        if not clause.fullmatch(tail):
            break
        removed.insert(0, tail.strip())
        end = boundary.start()
    return question[:end].rstrip(), removed
