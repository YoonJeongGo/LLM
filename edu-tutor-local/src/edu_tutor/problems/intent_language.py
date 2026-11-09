"""Bounded student-language adapter for one SQLite table.

Only original student text and confirmed schema enter here. Candidate model SQL,
reference answers and evaluation IDs never enter the adapter. Labelled clauses
and a small set of complete Korean sentence forms are supported; unconsumed text
is rejected instead of dropping an extra requirement.
"""
from __future__ import annotations

import re
import sqlglot
from sqlglot import exp

IDENT = r"[A-Za-z_][A-Za-z_0-9]{0,63}"
NUMBER = r"-?(?:\d+(?:\.\d*)?|\.\d+)"
ATOM = rf"(?:{NUMBER}|'(?:[^']|'')*'|NULL)"
AGG = rf"(?:COUNT|SUM|AVG|MIN|MAX)\s*\(\s*(?:DISTINCT\s+)?(?:{IDENT}|\*)\s*\)"
EXPR = rf"(?:{AGG}|{IDENT})"


def _outside_literals(text):
    """Keep positions while excluding SQL string values from language markers."""
    return re.sub(r"'(?:[^']|'')*'",lambda m:' '*len(m[0]),text)


def _identifier(text, table):
    lookup = {c["name"].casefold(): c["name"] for c in table["columns"]}
    name = lookup.get(text.strip().casefold())
    if name is None:
        raise ValueError(f"원본에 없는 열입니다: {text.strip()}")
    return name


def _split_list(text):
    # Commas inside aggregate calls are deliberately unsupported.
    return [x.strip() for x in re.split(r"\s*(?:,|와\s+|과\s+|및\s+)\s*", text) if x.strip()]


def _trim_request(text):
    text = text.strip().strip(".?!。 ")
    text = re.sub(
        r"\s*(?:을|를)?\s*(?:순서대로\s*)?(?:(?:조회|출력|계산|설명|작성|정렬)(?:해\s*(?:주세요|줘)|하세요)|"
        r"보여\s*(?:주세요|줘)|구(?:해\s*(?:주세요|줘)|하세요)|알려\s*(?:주세요|줘))\s*$", "", text)
    return text.strip().strip(".?!。 ")


def _selection(text, table, groups):
    text = _trim_request(text)
    count_words = {"한":1, "두":2, "세":3, "네":4, "다섯":5, "여섯":6, "일곱":7, "여덟":8, "아홉":9, "열":10}
    counted = re.fullmatch(r"(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|\d+)\s*(?:개(?:의)?\s*)?열(?:을|를)?",text)
    if counted:
        count = count_words.get(counted[1], int(counted[1]) if counted[1].isdigit() else None)
        if groups or count != len(table['columns']):
            raise ValueError("어느 원본 열을 출력할지 열 이름과 순서를 명시해 주세요.")
        return [c['name'] for c in table['columns']], []
    text = re.sub(r"\s*(?:SQL|결과|열)(?:을|를)?\s*$", "", text, flags=re.I).strip()
    text = re.sub(r"(?:을|를)\s*$", "", text).strip()
    if text in {"*", "모든 열", "전체 열"}:
        if groups:
            raise ValueError("그룹 결과의 출력 열을 명시해 주세요.")
        return [c["name"] for c in table["columns"]], []
    # Korean aggregate labels stay tied to an explicitly named original column.
    null_modifier = bool(re.search(r"NULL(?:을\s*제외한|이\s*아닌)",text,re.I))
    text = re.sub(r"NULL(?:을\s*제외한|이\s*아닌)\s*", "", text, flags=re.I)
    text = re.sub(rf"({IDENT})(?:의)?\s*(평균|합계|총합|최솟값|최소값|최댓값|최대값|개수)",
        lambda m: {"평균":"AVG","합계":"SUM","총합":"SUM","최솟값":"MIN","최소값":"MIN",
                   "최댓값":"MAX","최대값":"MAX","개수":"COUNT"}[m[2]]+"("+m[1]+")", text)
    text = re.sub(r"(?:전체\s*)?행\s*(?:수|개수)", "COUNT(*)", text)
    text = re.sub(r"\s*(?:과|와)\s*(?=(?:COUNT|SUM|AVG|MIN|MAX)\s*\()", ", ", text, flags=re.I)
    parts = _split_list(text)
    if not parts:
        raise ValueError("출력할 원본 열 또는 집계와 그 순서를 명시해 주세요.")
    columns, aggregates = [], []
    aggregate_started = False
    for item in parts:
        match = re.fullmatch(rf"(COUNT|SUM|AVG|MIN|MAX)\s*\(\s*(DISTINCT\s+)?({IDENT}|\*)\s*\)", item, re.I)
        if match:
            aggregate_started = True
            column = "*" if match[3] == "*" else _identifier(match[3], table)
            if column == "*" and (match[1].lower() != "count" or match[2]):
                raise ValueError("별표는 COUNT(*)에서만 지원합니다.")
            aggregates.append({"function":match[1].lower(), "column":column, "distinct":bool(match[2])})
        elif re.fullmatch(IDENT, item):
            if aggregate_started:
                raise ValueError("그룹 열을 앞에, 집계를 뒤에 두는 명시적 출력 순서만 지원합니다.")
            columns.append(_identifier(item, table))
        else:
            if re.search(IDENT+r"\s*\(",_outside_literals(item)):
                raise ValueError("현재 미지원인 출력 함수 또는 계산식입니다: "+item)
            raise ValueError("출력 열·집계 표현을 명확히 확인하지 못했습니다: "+item)
    if len(columns) != len(set(columns)):
        raise ValueError("출력 열의 중복 지정은 지원하지 않습니다.")
    if aggregates:
        if null_modifier and (any(a['column']=='*' for a in aggregates)
                or len({a['column'] for a in aggregates}) != 1):
            raise ValueError("NULL을 제외할 대상 열과 행 조건을 명시해 주세요. COUNT(*)나 서로 다른 열에 그 조건을 임의로 적용하지 않습니다.")
        if columns and columns != groups:
            raise ValueError("집계와 함께 출력할 열은 명시한 그룹 열과 순서가 같아야 합니다.")
        if any(a["function"] != "count" and
               next(c for c in table["columns"] if c["name"] == a["column"])["type"] == "TEXT"
               for a in aggregates):
            raise ValueError("숫자 집계는 원본 숫자 열을 지정해 주세요.")
        return [], aggregates
    if groups:
        raise ValueError("그룹 요청에 계산할 집계를 명시해 주세요.")
    if null_modifier:
        raise ValueError("NULL을 제외할 행 조건과 대상 열을 따로 명시해 주세요.")
    return columns, []


def _condition(text, table):
    """Translate explicit Korean comparisons, then parse the entire predicate."""
    value = text.strip()
    # "A인 행 중 B인 행" means A AND (B), including an OR inside B.
    # Split only an outside-literal, explicit row-scope connector.
    nested = list(re.finditer(r"\s*행\s*중\s*,?\s*", _outside_literals(value)))
    if nested:
        if len(nested) > 2:
            raise ValueError("현재 미지원: 세 단계보다 깊은 행 조건의 문장 연결입니다.")
        parts=[]; start=0
        for boundary in nested:
            parts.append(value[start:boundary.start()]); start=boundary.end()
        parts.append(value[start:])
        if any(not part.strip() for part in parts):
            raise ValueError("행 중 앞뒤의 조건 또는 비교값이 빠졌습니다.")
        return " AND ".join("("+_condition(part,table)+")" for part in parts)
    value = re.sub(r"\s*(?:인\s*행|인\s*경우|인|인\s*것)\s*$", "", value)
    value = re.sub(r"\s*(?:만|을|를)\s*$", "", value)
    value = re.sub(r"\b널\b", "NULL", value, flags=re.I)
    absent=re.fullmatch(rf"({IDENT})(?:이|가)\s*",value)
    if absent and any(c["name"].casefold()==absent[1].casefold() for c in table["columns"]):
        raise ValueError("조건의 비교값이 빠졌습니다.")
    absent_threshold=re.fullmatch(rf"({IDENT})(?:이|가)?\s*(?:큰|작은)",value)
    if absent_threshold and any(c["name"].casefold()==absent_threshold[1].casefold() for c in table["columns"]):
        raise ValueError("크거나 작음을 비교할 기준값이 빠졌습니다. 비교 기준값을 명시해 주세요.")
    # Do not replace words inside quoted string values.
    strings = []
    def protect(m):
        strings.append(m[0])
        return f"__LITERAL_{len(strings)-1}__"
    value = re.sub(r"'(?:[^']|'')*'", protect, value)
    operand = rf"(?:{EXPR})"
    literal = rf"(?:{NUMBER}|__LITERAL_\d+__|NULL)"
    # Bare words are literals only after a confirmed TEXT column and an
    # explicit copula. Never infer a missing value from source rows or SQL.
    def text_literal(match):
        column=next((c for c in table["columns"] if c["name"].casefold()==match[1].casefold()),None)
        if column is None:return match[0]
        name=column["name"]
        word=match[2]
        if column["type"]!="TEXT" or word.upper()=="NULL" or word.startswith("__LITERAL_"):
            return match[0]
        if any(c["name"].casefold()==word.casefold() for c in table["columns"]):
            raise ValueError("비교 대상이 문자값인지 다른 원본 열인지 모호합니다. 문자값이라면 따옴표로 확인해 주세요.")
        strings.append("'"+word.replace("'","''")+"'")
        return name+"가 __LITERAL_"+str(len(strings)-1)+"__"+match[3]
    value=re.sub(rf"({IDENT})(?:이|가)\s*([A-Za-z_][A-Za-z_0-9]*|[가-힣]+?)(이고|이거나|인|$)(?=\s|[,)]|$)",
                 text_literal,value)
    comparative={"이상":">=","이하":"<=","초과":">","미만":"<"}
    # A shared subject is permitted only in this complete adjacent structure.
    # Parentheses preserve the subgroup when it follows "행 중".
    value=re.sub(rf"({operand})(?:이|가)\s*({literal})\s*(이거나|또는|이고|그리고)\s*({literal})\s*(이상|이하|초과|미만)",
        lambda m:"("+m[1]+" = "+m[2]+(" OR " if m[3] in {"이거나","또는"} else " AND ")+m[1]+" "+comparative[m[5]]+" "+m[4]+")", value,flags=re.I)
    # Inclusive comparisons must be consumed before '-거나' as boolean OR.
    value=re.sub(rf"({operand})(?:이|가)?\s*({literal})(?:보다)?\s*(크거나|작거나)\s*같(은|다|고)",
        lambda m:m[1]+(" >= " if m[3]=="크거나" else " <= ")+m[2]+(" AND " if m[4]=="고" else ""),value,flags=re.I)
    value=re.sub(rf"({operand})(?:이|가)?\s*({literal})\s*보다\s*(크|작)(거나|고|다)",
        lambda m:m[1]+(" > " if m[3]=="크" else " < ")+m[2]+({"거나":" OR ","고":" AND ","다":""}[m[4]]),value,flags=re.I)
    value = re.sub(rf"({operand})(?:이|가)\s*NULL(?:이)?\s*아닌", r"\1 IS NOT NULL", value, flags=re.I)
    value = re.sub(rf"({operand})(?:이|가)\s*NULL(?:인)?", r"\1 IS NULL", value, flags=re.I)
    value = re.sub(rf"({operand})(?:이|가)?\s*(양수|음수)(?:인)?",
                   lambda m: m[1]+(" > 0" if m[2]=="양수" else " < 0"), value, flags=re.I)
    value = re.sub(rf"({operand})(?:이|가)?\s*({literal})\s*이상\s*({literal})\s*이하",
                   r"(\1 >= \2 AND \1 <= \3)", value, flags=re.I)
    comparator = {"이상":">=", "이하":"<=", "초과":">", "미만":"<",
                  "보다 큰":">", "보다 작은":"<", "와 같은":"=", "과 같은":"=",
                  "와 다른":"!=", "과 다른":"!="}
    value = re.sub(rf"({operand})(?:이|가)?\s*({literal})\s*(보다\s+큰|보다\s+작은|와\s+같은|과\s+같은|와\s+다른|과\s+다른|이상|이하|초과|미만)",
        lambda m:m[1]+" "+comparator[re.sub(r"\s+"," ",m[3])]+" "+m[2],value,flags=re.I)
    value = re.sub(rf"({operand})(?:이|가)\s*({literal})(?:이|가)?\s*아닌", r"\1 != \2", value, flags=re.I)
    value = re.sub(rf"({operand})(?:이|가)\s*({literal})(?:인|이고|이거나)?",
                   lambda m: m[1]+" = "+m[2]+(" OR " if m[0].endswith("이거나") else " AND " if m[0].endswith("이고") else ""),value,flags=re.I)
    value = re.sub(r"그리고|이면서|이며|이고", " AND ", value)
    value = re.sub(r"또는|이거나", " OR ", value)
    value = re.sub(r"\s*인\s*(?=AND|OR|$)", " ", value, flags=re.I)
    for i, literal_text in enumerate(strings):
        value = value.replace(f"__LITERAL_{i}__",literal_text)
    try:
        statements = sqlglot.parse("SELECT 1 WHERE "+value, read="sqlite")
        if len(statements)!=1:
            raise ValueError("조건은 하나의 식이어야 합니다.")
        query=statements[0]
        if not isinstance(query, exp.Select) or not query.args.get("where") or any(
            v for k,v in query.args.items() if k not in {"expressions","where"}):
            raise ValueError("조건 이외의 SQL 절을 조건에 넣을 수 없습니다.")
        condition=query.args["where"].this
        allowed=(exp.And,exp.Or,exp.Not,exp.Paren,exp.EQ,exp.NEQ,exp.GT,exp.GTE,exp.LT,exp.LTE,
                 exp.Is,exp.Null,exp.Column,exp.Identifier,exp.Literal,exp.Neg,exp.Count,exp.Sum,
                 exp.Avg,exp.Min,exp.Max,exp.Star,exp.Distinct)
        for node in condition.walk():
            if not isinstance(node,allowed):
                raise ValueError("이 조건 연산은 현재 지원하지 않습니다: "+type(node).__name__)
            if isinstance(node,exp.Column):
                if node.table:
                    raise ValueError("원본 열 이름만으로 조건을 지정해 주세요.")
                node.set("this",exp.to_identifier(_identifier(node.name,table)))
        if not isinstance(condition,(exp.And,exp.Or,exp.Not,exp.Paren,exp.EQ,exp.NEQ,exp.GT,exp.GTE,
                                     exp.LT,exp.LTE,exp.Is)):
            raise ValueError("조건에 비교 연산과 비교할 값을 명시해 주세요.")
        return condition.sql(dialect="sqlite")
    except sqlglot.errors.ParseError as exc:
        outside=_outside_literals(text).strip()
        if re.search(r"[가-힣]",outside) and not re.search(r"(?:[<>=!]+|보다|이상|이하|초과|미만|그리고|또는|이고|이거나|(?:크|작)(?:거나|고))\s*$",outside):
            raise ValueError("현재 미지원: 원문의 한국어 조건 연결 표현을 모두 해석하지 못했습니다. 입력값 누락으로 단정하지 않습니다.") from exc
        raise ValueError("조건의 연산 또는 비교값이 빠졌거나 모호합니다.") from exc


def _order(text, table):
    text = _trim_request(text)
    text = re.sub(r"(?:으로|로)\s*$", "", text).strip()
    result=[]
    for item in _split_list(text):
        m=re.fullmatch(rf"({EXPR})\s*(오름차순|내림차순|ASC|DESC|순서)(?:으로|로)?", item, re.I)
        if not m:
            # Bare ORDER BY-style original columns have SQLite's default ASC.
            if not re.fullmatch(IDENT,item):
                raise ValueError("정렬 열과 ASC/DESC 또는 오름차순/내림차순을 순서대로 명시해 주세요.")
            key=_identifier(item,table)
            direction="asc"
        else:
            key=m[1]
            direction="desc" if m[2].casefold() in {"desc","내림차순"} else "asc"
            if re.fullmatch(IDENT,key):
                key=_identifier(key,table)
            else:
                _,items=_selection(key,table,[])
                if len(items)!=1:
                    raise ValueError("정렬 집계는 하나의 명시적 집계식이어야 합니다.")
                a=items[0]
                key=a["function"].upper()+"("+("DISTINCT " if a["distinct"] else "")+a["column"]+")"
        result.append({"column":key,"direction":direction})
    if not result or len(result)>5 or len({x["column"].casefold() for x in result})!=len(result):
        raise ValueError("정렬 기준은 중복 없이 1~5개를 지정해 주세요.")
    return result


LABEL = re.compile(r"(?P<label>그룹\s*조건|행\s*조건|출력\s*열|정렬\s*기준|그룹\s*기준|"
                   r"GROUP\s+BY|ORDER\s+BY|HAVING|WHERE|출력|선택\s*열|조회\s*열|조건|그룹|정렬)\s*[:：]",re.I)
LABEL_KEYS={"그룹조건":"having","행조건":"where","출력열":"select","정렬기준":"order","그룹기준":"group",
            "groupby":"group","orderby":"order","having":"having","where":"where","출력":"select",
            "선택열":"select","조회열":"select","조건":"where","그룹":"group","정렬":"order"}


def _labelled(question,table):
    unordered=list(re.finditer(r"(?:^|[.;])\s*(?:정렬|결과\s*순서)(?:은|는|을|를)?\s*"
        r"(?:지정|요청|보장)하지\s*않습니다\s*(?=[.;]|$)",_outside_literals(question)))
    for note in reversed(unordered):
        question=question[:note.start()]+question[note.end():]
    matches=list(LABEL.finditer(question))
    if not matches:
        return None
    prefix=question[:matches[0].start()].strip(" .;\n")
    prefix=re.sub(r"(?i)^SQLite(?:의)?\s*[.:]?\s*","",prefix).strip()
    # Accept a declaration only when it names this confirmed table. Do not
    # discard arbitrary introductions: they may carry another row condition.
    table_name=re.escape(table['name'])
    declaration=(rf"(?:{table_name}\s*(?:표|테이블)?\s*(?:(?:을|를)\s*사용(?:합니다|하세요)|에서\s*조회합니다)"
                 rf"|(?:원본\s*|주어진\s*|다음\s*)?(?:표|테이블)\s*{table_name}(?:을|를)\s*사용(?:합니다|하세요))")
    prefix=prefix.strip(" .;\n")
    if prefix and not (re.fullmatch(declaration,prefix,re.I) or re.fullmatch(r"(?:다음\s*)?(?:요청|조건|문제|SQL|조회)(?:을|를|입니다|작성)?\s*",prefix,re.I)):
        raise ValueError("절 앞의 추가 요청을 해석하지 못했습니다. 출력·행 조건·그룹·정렬 절을 분리해 주세요.")
    fields={}
    for i,m in enumerate(matches):
        key=LABEL_KEYS[re.sub(r"\s+","",m["label"]).lower()]
        if key in fields:
            raise ValueError("같은 조건 절이 두 번 있습니다. 하나로 합쳐 확인해 주세요.")
        end=matches[i+1].start() if i+1<len(matches) else len(question)
        value=question[m.end():end].strip().strip(";.\n ")
        if i==len(matches)-1:
            # A separate request for an explanation is not another SQL
            # condition. The complete, bounded phrase must match; literals,
            # extra columns, LIMITs and qualifiers remain and fail parsing.
            explanation=(r"(?:(?:요청|조건)에\s*맞는\s*)?(?:SQL|쿼리)(?:과|와|및)\s*"
                         r"(?:(?:원본\s*)?행에서\s*결과까지의\s*)?"
                         r"(?:계산|처리|풀이)\s*과정(?:을)?\s*"
                         r"설명(?:해\s*(?:주세요|줘)|하세요)")
            value=re.sub(r"[.;]\s*"+explanation+r"\s*$","",value,flags=re.I).strip()
        if not value:
            raise ValueError("필요한 "+m["label"]+" 값이 빠졌습니다.")
        fields[key]=value
    if "select" not in fields:
        raise ValueError("출력할 열 또는 집계를 명시해 주세요.")
    if unordered and "order" in fields:
        raise ValueError("정렬을 지정하지 않는다는 문장과 정렬 기준이 충돌합니다. 원하는 순서를 확인해 주세요.")
    groups=[_identifier(x,table) for x in _split_list(fields.get("group",""))]
    if len(groups)!=len(set(groups)):
        raise ValueError("그룹 열은 중복 없이 지정해 주세요.")
    columns,aggregates=_selection(fields["select"],table,groups)
    return {"table":table["name"],"aggregates":aggregates,"select_columns":columns,
            "group_by":groups,"where":_condition(fields["where"],table) if "where" in fields else None,
            "having":_condition(fields["having"],table) if "having" in fields else None,
            "order_by":_order(fields["order"],table) if "order" in fields else []}


def _sentence_order(text, table):
    """Consume complete ordering clauses and check each tie reference."""
    ordered=[]
    for part in _split_list(text):
        named=re.match(rf"같은\s+({IDENT})(?:에서는|에서|은|는)\s*",part,re.I)
        inside=re.match(r"그\s*안에서는\s*",part)
        counted=re.match(r"(둘\s*다|두\s*값(?:이)?|세\s*값(?:이)?|네\s*값(?:이)?)\s*같으면\s*",part)
        tied=re.match(r"동점이면\s*",part)
        if named:
            if not ordered or named[1].casefold()!=ordered[-1]["column"].casefold():
                raise ValueError("동점 조건의 열이 바로 앞 정렬 기준과 다릅니다. 정렬 우선순위를 확인해 주세요.")
            part=part[named.end():]
        elif counted:
            count=3 if counted[1].startswith("세") else 4 if counted[1].startswith("네") else 2
            if len(ordered)!=count:
                raise ValueError("같다는 값의 개수와 앞서 명시한 정렬 기준 수가 다릅니다. 어느 기준의 동점인지 확인해 주세요.")
            part=part[counted.end():]
        elif inside or tied:
            if not ordered:
                raise ValueError("앞 정렬 기준 없이 동점 범위를 정할 수 없습니다. 먼저 기준 열을 명시해 주세요.")
            part=part[(inside or tied).end():]
        match=re.fullmatch(rf"({EXPR})(?:은|는|이|가)?\s*(오름차순|내림차순|ASC|DESC)(?:으로|로)?",part,re.I)
        if not match:
            raise ValueError("현재 미지원: 정렬 문장의 남은 연결 표현을 해석하지 못했습니다: "+part)
        ordered.extend(_order(match[1]+" "+match[2],table))
    if not ordered or len(ordered)>5 or len({x["column"].casefold() for x in ordered})!=len(ordered):
        raise ValueError("정렬 기준은 중복 없이 1~5개를 지정해 주세요.")
    return ordered


def _sentence_intent(question,table):
    """Bounded multi-sentence adapter; every sentence must be consumed.

    This extracts only student clauses. It does not inspect a candidate SQL,
    table values, results or evaluation identifiers, and delegates all scalar
    predicates/selections to the existing strict adapters.
    """
    if not re.search(r"출력\s*열(?:은|는)|열(?:을|를)\s*(?:이\s*)?순서(?:로|대로)",question):
        return None
    sentence_bounds=list(re.finditer(r"[.!?。](?:\s+|$)",_outside_literals(question)))
    sentences=[]; start=0
    for boundary in sentence_bounds:
        sentences.append(question[start:boundary.start()].strip());start=boundary.end()
    if question[start:].strip():sentences.append(question[start:].strip())
    sentences=[s for s in sentences if s]
    if not sentences:return None
    table_name=re.escape(table["name"])
    request=r"(?:해\s*(?:줘|주세요)|하세요)"
    show=r"(?:보여\s*(?:줘|주세요)|출력"+request+r")"
    explanation=r"(?:원본\s*)?행(?:이|의)\s*조건(?:을)?\s*통과하는\s*과정(?:과|와)\s*최종\s*순서(?:를|을)?\s*설명"+request
    procedure=r"(?:원본에서\s*결과까지의\s*)?(?:계산\s*|풀이\s*|처리\s*)?과정(?:을|를)?\s*설명"+request
    fields={}
    def set_field(key,value):
        if key in fields:
            raise ValueError("같은 요청 절이 두 번 있습니다. 원문에서 어느 조건을 사용할지 확인해 주세요.")
        if not value.strip():
            raise ValueError("요청 절의 값이 빠졌습니다: "+key)
        fields[key]=value.strip()
    for sentence in sentences:
        intro=rf"(?:SQLite에서\s*)?{table_name}(?:을|를)\s*조회{request}"
        if re.fullmatch(intro,sentence,re.I):continue
        sentence=re.sub(rf"^(?:SQLite(?:에서|의)?\s+)?{table_name}(?:\s*표)?에서\s*","",sentence,flags=re.I)
        if re.fullmatch(explanation,sentence,re.I) or re.fullmatch(procedure,sentence,re.I):continue
        mixed=re.fullmatch(rf"(.+)\s*행(?:을|만)?\s*(?:고르고|골라서|선택하고)\s*,?\s*(.+?)\s*열(?:을|를)\s*(?:이\s*)?순서(?:로|대로)\s*{show}",sentence,re.I)
        if mixed:
            set_field("where",mixed[1]);set_field("select",mixed[2]);continue
        rows=re.fullmatch(r"(.+)\s*행(?:을|만)?\s*(?:찾아|골라|보여|조회해)\s*(?:줘|주세요)",sentence,re.I)
        if rows:set_field("where",rows[1]);continue
        select=re.fullmatch(r"(?:출력|선택|조회)\s*열(?:은|는)\s*(.+?)(?:야|입니다|이다)",sentence,re.I)
        if select:set_field("select",select[1]);continue
        ordering=re.fullmatch(rf"(.+?)\s*정렬(?:{request}|하는\s*(?:SQLite\s*)?(?:SQL|쿼리)(?:과|와)\s*{procedure})",sentence,re.I)
        if ordering:set_field("order",ordering[1]);continue
        # Never discard a final sentence just because it contains 'explain'.
        raise ValueError("현재 미지원: 원문에서 해석하지 못한 문장 형식이 남았습니다: "+sentence)
    if "select" not in fields:
        raise ValueError("출력할 열 또는 집계와 그 순서가 빠졌습니다.")
    columns,aggregates=_selection(fields["select"],table,[])
    return {"table":table["name"],"aggregates":aggregates,"select_columns":columns,"group_by":[],
            "where":_condition(fields["where"],table) if "where" in fields else None,"having":None,
            "order_by":_sentence_order(fields["order"],table) if "order" in fields else []}


def _natural(question,table):
    sentences=_sentence_intent(question,table)
    if sentences is not None:return sentences
    q=re.sub(r"(?i)^\s*SQLite\s*[.:]?\s*","",question).strip(" .")
    q=re.sub(r"^"+re.escape(table["name"])+r"(?:\s*표)?(?:에서|의)\s*","",q,flags=re.I)
    # The language adapter only consumes the complete sentence, never selects
    # isolated keywords while silently forgetting the remainder.
    q=re.sub(r"하고\s*선택\s*이유를\s*설명(?:해\s*(?:주세요|줘)|하세요)\s*[.?!]?\s*$","하세요",q).strip()
    q=_trim_request(q)
    q=re.sub(r"(?:을|를)?\s*조회하고\s*$","",q).strip()
    where=None
    nonnull_sort = re.match(rf"^NULL을\s*제외하고\s+({IDENT})\s*(?=오름차순|내림차순)",q,re.I)
    if nonnull_sort:
        column = _identifier(nonnull_sort[1],table)
        where = column + ' IS NOT NULL'
        q = re.sub(r'^NULL을\s*제외하고\s+','',q,flags=re.I)
    row_match=re.match(r"^(.*?)\s*행(?!\s*(?:수|개수))(?:만)?(?:을)?(?:\s*대상으로|\s*에서|\s*의)?\s*(.*)$",q)
    if row_match:
        predicate=row_match[1].strip()
        if not predicate:
            raise ValueError("남길 행의 조건을 명시해 주세요.")
        where=_condition(predicate,table)
        q=row_match[2].strip()
        note=re.match(r'^\(\s*NULL\s*제외\s*\)(?:의)?\s*',q,re.I)
        if note:
            parsed=sqlglot.parse_one(where,read='sqlite')
            while isinstance(parsed,(exp.Paren,exp.Not)):
                parsed=parsed.this
            columns=list(parsed.find_all(exp.Column))
            if not isinstance(parsed,(exp.EQ,exp.NEQ,exp.GT,exp.GTE,exp.LT,exp.LTE)) or len(columns)!=1 or parsed.find(exp.Null):
                raise ValueError("NULL 제외 부연의 대상 열과 조건을 명시해 주세요.")
            q=q[note.end():]
    groups=[]
    gm=re.search(rf"({IDENT})\s*별(?:로)?\s*",q)
    if gm:
        groups=[_identifier(gm[1],table)]
        q=q[:gm.start()]+q[gm.end():]
    order=[]
    order_pattern=re.compile(rf"({EXPR})\s*(오름차순|내림차순|순서)(?:으로|로)?",re.I)
    matches=list(order_pattern.finditer(q))
    if matches:
        # "same X" is a reference to the immediately preceding order key,
        # not filler text. Preserve/reject a different or unknown column.
        for tie in re.finditer(r"같은\s+("+IDENT+r")(?:은|는)",q):
            previous=[m for m in matches if m.end()<=tie.start()]
            following=[m for m in matches if m.start()>=tie.end()]
            if not previous or not following or previous[-1][1].casefold()!=tie[1].casefold():
                raise ValueError("동점 조건의 열이 바로 앞 정렬 기준과 다릅니다. 정렬 우선순위를 확인해 주세요.")
        for m in matches:
            order.extend(_order(m[0],table))
        for m in reversed(matches):
            q=q[:m.start()]+" "+q[m.end():]
        # These connectors carry priority only in the order of the explicit
        # keys above. An unknown condition/column remains unconsumed and fails.
        q=re.sub(r"동점이면|동점은|같은\s+"+IDENT+r"(?:은|는)", " ",q)
        if len(matches)>1:
            q=re.sub(r"같은\s*그룹(?:은|는)"," ",q)
        q=re.sub(r"(?:으로|로)?\s*정렬(?:하고)?", " ",q)
    else:
        dm=re.search(r"(오름차순|내림차순)(?:으로|로)?",q)
        if dm:
            q=q[:dm.start()]+q[dm.end():]
            provisional=re.sub(r"(?:을|를)\s*$","",q).strip(" ,")
            if not re.fullmatch(IDENT,provisional):
                raise ValueError("어느 열로 정렬할지 명시해 주세요.")
            order=_order(provisional+" "+dm[1],table)
    q=q.strip(" ,")
    # Remove particles immediately before a removed ordering clause.
    q=re.sub(r"(?:을|를)\s*(?:,\s*)?$","",q).strip(" ,")
    columns,aggregates=_selection(q,table,groups)
    return {"table":table["name"],"aggregates":aggregates,"select_columns":columns,
            "group_by":groups,"where":where,"having":None,"order_by":order}


def infer_select_intent(problem,question):
    """Return (None,None) only when the legacy aggregate adapter should run."""
    visible=_outside_literals(question)
    for label,pattern in (
        ('JOIN',r'(?<![A-Za-z_0-9])JOIN(?![A-Za-z_0-9])'),
        ('CTE(WITH)',r'(?<![A-Za-z_0-9])(?:CTE|WITH)(?![A-Za-z_0-9])'),
        ('윈도우',r'(?<![A-Za-z_0-9])(?:LEAD|LAG|ROW_NUMBER|DENSE_RANK|RANK|NTILE|FIRST_VALUE|LAST_VALUE)\s*(?:\(|를\s*(?:이용|사용)|함수|윈도우|창)|윈도우\s*(?:함수|연산)|창\s*함수|(?<![A-Za-z_0-9])OVER\s*\('),
    ):
        if re.search(pattern,visible,re.I):
            return None,f"현재 미지원: {label} 연산의 원문 의도·중간 계산은 이번 단일 표 수업 범위에 포함하지 않습니다."
    triggered=bool(LABEL.search(question) or re.search(r"정렬|오름차순|내림차순|순서로|"
        r"(?:양수|음수|이상|이하|초과|미만|NULL인|아닌)\s*(?:인\s*)?행(?!\s*(?:수|개수))|"
        r"행(?:만)?(?:의|에서|을\s*대상)|(?:열|[A-Za-z_0-9])(?:을|를)\s*조회",question,re.I))
    if not triggered:
        return None,None
    if len(problem["tables"])!=1:
        return None,"현재 미지원: 원본 단일 표의 SELECT·조건·정렬·집계만 설명합니다. JOIN/복수 표는 제외합니다."
    table=problem["tables"][0]
    try:
        intent=_labelled(question,table)
        if intent is None:
            intent=_natural(question,table)
        if intent["having"] and not intent["aggregates"]:
            raise ValueError("그룹 조건은 집계 요청과 함께 명시해 주세요.")
        if not intent["aggregates"] and any("(" in o["column"] for o in intent["order_by"]):
            raise ValueError("일반 행 조회를 집계식으로 정렬할 수 없습니다.")
        return intent,"bounded_language_aggregate_v2" if intent["aggregates"] else "bounded_language_select_v2"
    except (ValueError,TypeError) as exc:
        return None,"입력 의도 확인 필요: "+str(exc)

