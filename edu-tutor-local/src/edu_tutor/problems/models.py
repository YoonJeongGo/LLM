from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Column(Strict):
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z_0-9]{0,63}$")
    type: Literal["INTEGER", "REAL", "TEXT", "NUMERIC"]
    label: str | None = Field(default=None, max_length=100)


class Table(Strict):
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z_0-9]{0,63}$")
    columns: list[Column] = Field(min_length=1, max_length=30)
    rows: list[list[Any]] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def check_rows(self):
        if len({c.name.casefold() for c in self.columns}) != len(self.columns):
            raise ValueError("중복 열 이름은 지원하지 않습니다.")
        for row in self.rows:
            if len(row) != len(self.columns):
                raise ValueError("표의 행 길이와 열 개수가 다릅니다.")
            for value, col in zip(row, self.columns):
                if value is not None and (isinstance(value, (dict, list, bool)) or not isinstance(value, (str, int, float))):
                    raise ValueError("표 값은 문자열, 유한 숫자 또는 NULL이어야 합니다.")
                if isinstance(value, float) and not math.isfinite(value):
                    raise ValueError("유한 숫자만 지원합니다.")
                if isinstance(value, str) and len(value) > 1000:
                    raise ValueError("표의 셀 문자열이 너무 깁니다.")
                if value is not None and col.type in {"INTEGER", "REAL", "NUMERIC"} and not isinstance(value, (int, float)):
                    raise ValueError("숫자 열에는 숫자 또는 NULL을 입력하세요.")
        return self


class Source(Strict):
    kind: Literal["typed", "photo"] = "typed"
    photo_id: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def check_photo_identity(self):
        if (self.kind=="photo") != bool(self.photo_id):
            raise ValueError("사진 출처에는 실제 photo_id가 필요하며 직접 입력 출처에 사진 ID를 붙일 수 없습니다.")
        return self


class Aggregate(Strict):
    function: Literal["count", "sum", "avg", "min", "max"]
    column: str = Field(default="*", max_length=64)
    distinct: bool = False


class OrderTerm(Strict):
    column: str = Field(min_length=1, max_length=200)
    direction: Literal["asc", "desc"] = "asc"


class Intent(Strict):
    table: str = Field(max_length=64)
    aggregates: list[Aggregate] = Field(default_factory=list, max_length=8)
    select_columns: list[str] = Field(default_factory=list, max_length=30)
    order_by: list[OrderTerm] = Field(default_factory=list, max_length=5)
    group_by: list[str] = Field(default_factory=list, max_length=5)
    where: str | None = Field(default=None, max_length=2000)
    having: str | None = Field(default=None, max_length=2000)


class ProblemInput(Strict):
    id: str | None = Field(default=None, max_length=80)
    task_kind: Literal["query_result", "write_sql", "concept", "explain_error"]
    dialect: Literal["sqlite", "oracle", "postgresql", "mysql"] = "sqlite"
    raw_text: str = Field(min_length=1, max_length=12000)
    source: Source = Field(default_factory=Source)
    revision: int = Field(default=1, ge=1)
    confirmed: bool = False
    tables: list[Table] = Field(default_factory=list, max_length=5)
    query: str | None = Field(default=None, max_length=12000)
    missing_conditions: list[str] = Field(default_factory=list, max_length=30)
    intent: Intent | None = None


class Hypothesis(Strict):
    kind: Literal["all_null"]
    table: str = Field(max_length=64)
    column: str = Field(max_length=64)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def normalize_problem(value):
    problem = ProblemInput.model_validate(value).model_dump(exclude_none=True)
    # Existing saved aggregate problems must keep their original canonical
    # representation. New optional fields do not change old speech bindings.
    if problem.get("intent"):
        for key in ("select_columns", "order_by"):
            if not problem["intent"].get(key) and key not in (value.get("intent") or {}):
                problem["intent"].pop(key, None)
    if len({t["name"].casefold() for t in problem["tables"]}) != len(problem["tables"]):
        raise ValueError("중복 표 이름은 지원하지 않습니다.")
    identity = problem["source"] if problem["source"].get("photo_id") else {"raw_text": problem["raw_text"], "source": problem["source"]}
    problem["id"] = "problem-" + hashlib.sha256(canonical(identity).encode()).hexdigest()[:16]
    if len(canonical(problem).encode()) > 200000:
        raise ValueError("구조화 문제 크기 제한을 초과했습니다.")
    return problem


def identified_table(problem, table, *, namespace="original"):
    ident = f"{problem['id']}-{namespace}-{table['name']}"
    row_ids = [f"{ident}-r{i}" for i in range(len(table["rows"]))]
    column_ids = [f"{ident}-c-{c['name']}" for c in table["columns"]]
    return {"id": ident, "name": table["name"], "columns": [c["name"] for c in table["columns"]],
            "rows": copy.deepcopy(table["rows"]), "row_ids": row_ids, "column_ids": column_ids,
            "cell_ids": [[f"{row}-c-{c['name']}" for c in table["columns"]] for row in row_ids]}


def derive_hypothesis(problem, hypothesis):
    value = Hypothesis.model_validate(hypothesis).model_dump()
    derived = copy.deepcopy(problem)
    table = next((t for t in derived["tables"] if t["name"] == value["table"]), None)
    if table is None:
        raise ValueError("새 가정에 지정한 원본 표를 찾을 수 없습니다.")
    names = [c["name"] for c in table["columns"]]
    if value["column"] not in names:
        raise ValueError("새 가정에 지정한 원본 열을 찾을 수 없습니다.")
    index = names.index(value["column"])
    for row in table["rows"]:
        row[index] = None
    return derived, value


def intent_question_text(problem, question):
    """Exclude only exact copies of the confirmed input table from intent.

    The table is still supplied to the model and executed unchanged. Numbers
    and names inside its serialized rows are data, not a WHERE request. A
    different table or malformed JSON stays in scope. Trailing question text
    is never removed, including conditions on the same line as the table.
    """
    declaration = re.compile(r"(?<![A-Za-z_0-9])([A-Za-z_][A-Za-z_0-9]*)[ \t]*\(([^)\r\n]*)\)[ \t]*=[ \t]*")
    spans = []
    decoder = json.JSONDecoder()
    for match in declaration.finditer(question):
        table = next((t for t in problem["tables"] if t["name"].casefold() == match[1].casefold()), None)
        if table is None or [c.strip().casefold() for c in match[2].split(",")] != [c["name"].casefold() for c in table["columns"]]:
            continue
        try:
            rows, length = decoder.raw_decode(question[match.end():])
        except ValueError:
            continue
        end = match.end() + length
        if canonical(rows) != canonical(table["rows"]):
            continue
        spans.append((match.start(), end))
    for start, end in reversed(spans):
        question = question[:start] + " " + question[end:]
    return question


def infer_basic_intent(problem, question):
    """A deliberately bounded language adapter; ambiguity returns no intent."""
    question = intent_question_text(problem, question)
    from .explanation_requests import split_explanation_tail
    question, _ = split_explanation_tail(question)
    from .intent_language import infer_select_intent
    expanded, expanded_scope = infer_select_intent(problem, question)
    if problem.get("intent"):
        if expanded is not None:
            import sqlglot
            def comparable(value):
                value = Intent.model_validate(value).model_dump()
                for key in ("where", "having"):
                    if value.get(key):
                        value[key] = sqlglot.parse_one(value[key], read="sqlite").sql(dialect="sqlite", normalize=True)
                return value
            try:
                if comparable(problem["intent"]) != comparable(expanded):
                    return None, "입력 의도 충돌: 학생 원문의 출력·조건·그룹·정렬과 구조화 의도가 다릅니다. 먼저 원문을 확인해 주세요."
            except (ValueError, sqlglot.errors.ParseError):
                return None, "입력 의도 확인 필요: 구조화 조건을 명확히 해석할 수 없습니다."
        return problem["intent"], "user_structured_intent"
    if expanded is not None or expanded_scope is not None:
        return expanded, expanded_scope
    if re.search(r"정렬|오름차순|내림차순|\bORDER\s+BY\b|상위|하위|최근|마지막|처음|반올림|절사",question,re.I):
        return None,"정렬·행 선택·반올림까지 포함한 자연어 의미 검증은 지원하지 않습니다. 주어진 SQL 결과 과제로 실행 범위를 확인하세요."
    if re.search(r"(?:NULL|널)\s*(?:값\s*)?인|(?:NULL|널)\s*(?:값\s*)?(?:의\s*)?(?:개수|수)|값이\s*없는|점수가\s*없는|비어\s*있는",question,re.I):
        return None,"NULL인 행을 고르는 조건은 COUNT(열)의 NULL 제외와 다릅니다. 원본 WHERE 조건 또는 구조화된 의도를 확인해 주세요."
    if len(problem["tables"]) != 1:
        return None, "범위: 하나의 원본 표를 사용하는 COUNT/SUM/AVG/MIN/MAX 요청만 의미 확인합니다."
    table = problem["tables"][0]
    names = [c["name"] for c in table["columns"]]
    condition_text=question
    for identifier in [table["name"],*names]:
        condition_text=re.sub(r"(?<![A-Za-z_0-9])"+re.escape(identifier)+r"(?![A-Za-z_0-9])","",condition_text,flags=re.I)
    if re.search(r"[<>]=?|\b(?:WHERE|HAVING)\b|\d",condition_text,re.I):
        return None,"숫자·비교 조건이 포함된 요청은 구조화된 조건을 확인해야 합니다. 조건을 생략한 전체 집계를 정답으로 처리하지 않습니다."
    string_values={v for row in table["rows"] for v in row if isinstance(v,str) and v and v.casefold() not in {table["name"].casefold(),*(name.casefold() for name in names)}}
    if any(re.search(r"(?<!\w)"+re.escape(v)+r"(?=$|\W|[을를이가은는의와과]|부서)",question,re.I) for v in string_values):
        return None,"질문에 특정 행 값이 포함되어 있습니다. 전체 집계인지 해당 값의 필터 조건인지 구조화된 의도로 확인해 주세요."
    # One explicit group/measure grammar only. Do not merely remove the
    # group column from all mentions: that could silently drop extra filters.
    if re.search(r"그룹|팀별|부서별|[A-Za-z_][A-Za-z_0-9]*\s*별|각\s*.+별", question, re.I):
        identifier = r"[A-Za-z_][A-Za-z_0-9]{0,63}"
        grouped = re.fullmatch(
            r"\s*(?:SQLite\s*[.:]?\s*)?(?P<group>" + identifier + r")\s*별(?:로)?\s+"
            r"(?:NULL\s*을\s*제외한\s+)?(?P<value>" + identifier + r")\s*(?:의\s*)?평균"
            r"(?:을)?(?:\s*(?:(?:구해|계산해|알려|보여|설명해)\s*(?:주세요|줘)|"
            r"구하는\s*SQL을\s*작성해\s*(?:주세요|줘)))?\s*[.?!]?\s*", question, re.I)
        lookup = {column["name"].casefold(): column for column in table["columns"]}
        if not grouped or any(grouped[key].casefold() not in lookup for key in ("group", "value")):
            return None, "그룹 평균은 원본 그룹열별 원본 숫자열 평균을 명시한 요청만 지원합니다. 추가 조건·정렬·다른 그룹 표현은 구조화된 의도를 확인해 주세요."
        measure = lookup[grouped["value"].casefold()]
        if measure["type"] not in {"INTEGER", "REAL", "NUMERIC"}:
            return None, "그룹 평균의 대상은 원본 숫자 열이어야 합니다."
        return {"table": table["name"], "aggregates": [{"function": "avg", "column": measure["name"], "distinct": False}],
                "group_by": [lookup[grouped["group"].casefold()]["name"]], "where": None, "having": None}, "bounded_language_group_average"
    calls = re.findall(r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\(\s*(DISTINCT\s+)?([A-Za-z_][A-Za-z_0-9]*|\*)\s*\)", question, re.I)
    if calls:
        aggregates = [{"function": f.lower(), "column": col, "distinct": bool(distinct)} for f, distinct, col in calls]
        if any(item["distinct"] and item["column"] == "*" for item in aggregates):
            return None, "SQLite COUNT(DISTINCT *)는 지원하지 않습니다. 중복을 제외할 원본 열을 지정해 주세요."
        if any(a["column"] != "*" and a["column"] not in names for a in aggregates):
            return None, "질문의 집계 열이 원본 스키마에 없습니다."
    else:
        requested = [name for name, pattern in (("avg", r"평균|\bAVG\b"), ("sum", r"합계|총합|\bSUM\b"),
            ("count", r"개수|인원|사람\s*수|행\s*수|몇\s*명|\bCOUNT\b"),
            ("min", r"최솟값|최소값|\bMIN\b"), ("max", r"최댓값|최대값|\bMAX\b")) if re.search(pattern, question, re.I)]
        if len(requested)>1:
            return None, "여러 집계의 대상과 순서를 명시해 주세요. 예: MIN(열), MAX(열)."
        function = requested[0] if requested else None
        if not function:
            return None, "COUNT/SUM/AVG/MIN/MAX 중 구하려는 연산과 대상 열을 확인해 주세요."
        matches = [c["name"] for c in table["columns"] if re.search(r"(?<![A-Za-z_0-9])" + re.escape(c["name"]) + r"(?![A-Za-z_0-9])", question, re.I) or c.get("label") and c["label"] in question]
        nonnull = bool(re.search(r"NULL\s*이?\s*아닌|값이\s*있는|점수가\s*있는|비어\s*있지\s*않|non.?null", question, re.I))
        all_rows=re.search(r"(?:전체|모든)\s*(?:행|사람|인원)\s*(?:의\s*)?(?:수|개수)",question)
        valued_rows=re.search(r"NULL\s*이?\s*아닌|값이\s*있는|점수가\s*있는|비어\s*있지\s*않|non.?null",question,re.I)
        if not matches and (function != "count" or nonnull):
            matches = [c["name"] for c in table["columns"] if c["type"] in {"INTEGER", "REAL", "NUMERIC"} and c["name"].lower() not in {"id", "rowid"}]
        if function == "count" and all_rows and matches and not valued_rows:
            return None, "전체 행 개수와 특정 열 값 개수가 함께 언급되어 있습니다. COUNT(*)와 COUNT(열)의 대상을 명시해 주세요."
        if function == "count" and not nonnull and not matches:
            column = "*"
        elif len(matches) == 1:
            column = matches[0]
        else:
            return None, "집계할 열이 모호합니다. 원본 열 이름을 지정해 주세요."
        aggregates = [{"function": function, "column": column, "distinct": bool(re.search(r"서로\s*다른|중복.*제외|\bDISTINCT\b", question, re.I))}]
        if aggregates[0]["distinct"] and column == "*":
            return None, "중복을 제외할 원본 열을 지정해 주세요. 전체 행을 특정 열의 COUNT DISTINCT로 추정하지 않습니다."
        if function=="count" and all_rows and valued_rows and column!="*" and not aggregates[0]["distinct"]:
            whole={"function":"count","column":"*","distinct":False}
            aggregates=[whole,*aggregates] if all_rows.start()<valued_rows.start() else [*aggregates,whole]
    # Natural-language predicates/grouping need explicit structured intent; do
    # not silently drop a condition and then claim semantic verification.
    if re.search(r"이상|이하|초과|미만|조건|(?:행|사람|인원)만|대상(?:으로|인)|\bWHERE\b|\bHAVING\b|그룹|팀별|부서별|[A-Za-z_][A-Za-z_0-9]*별|각\s*.+별|정렬|오름차순|내림차순|\bORDER\s+BY\b", question, re.I):
        return None, "조건·그룹 요청은 intent.where/group_by/having을 확인한 뒤 검증할 수 있습니다."
    return {"table": table["name"], "aggregates": aggregates, "group_by": [], "where": None, "having": None}, "bounded_language_aggregate"
