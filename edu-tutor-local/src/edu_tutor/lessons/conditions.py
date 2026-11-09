"""Bounded Korean speech rendering of already executed WHERE conditions.

This renders syntax and source cell values; SQLite's recorded row membership
remains the authority for TRUE versus FALSE/UNKNOWN. No model prose is used.
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp


def _value(value):
    if value is None:
        return "널"
    if isinstance(value,str):
        return "문자 " + value
    text=str(value)
    return "마이너스 " + text[1:] if text.startswith("-") else text


def simple_where_speech(where_sql,table,row_index,included,column_types=None):
    """Return a literal/column-bound rendering, or None for unsupported syntax.

    Column ordinals refer to the exact visible source table. A supplied boolean
    is never interpreted as a predicate value: callers pass the recorded
    filtered-row membership, including SQL NULL's UNKNOWN rejection.
    """
    if not where_sql:
        return None
    try:
        parsed=sqlglot.parse_one("SELECT * FROM _source "+where_sql,read="sqlite")
    except sqlglot.errors.ParseError:
        return None
    where=parsed.args.get("where")
    if not where:
        return None
    condition=where.this
    while isinstance(condition,exp.Paren):condition=condition.this
    is_not_null=isinstance(condition,exp.Not) and isinstance(condition.this,exp.Is)
    predicate=condition.this if is_not_null else condition
    operators={exp.EQ:"인",exp.NEQ:"이 아닌",exp.GT:"보다 큰",exp.GTE:"이상인",exp.LT:"보다 작은",exp.LTE:"이하인"}
    if not isinstance(predicate.this,exp.Column):
        return None
    column=predicate.this
    matches=[i for i,name in enumerate(table["columns"]) if name.casefold()==column.name.casefold()]
    if len(matches)!=1 or not 0<=row_index<len(table["rows"]):
        return None
    column_index=matches[0]
    operand=predicate.expression
    if isinstance(predicate,exp.Is) and isinstance(operand,exp.Null):
        literal=None
        clause=f"{column_index+1}열이 널"+("이 아닌 조건" if is_not_null else "인 조건")
        operator="is_not_null" if is_not_null else "is_null"
    elif type(predicate) in operators and not is_not_null:
        negative=isinstance(operand,exp.Neg) and isinstance(operand.this,exp.Literal) and not operand.this.is_string
        literal_node=operand.this if negative else operand
        if not isinstance(literal_node,exp.Literal):
            return None
        # Do not describe SQLite text ordering as an ordinary numeric ordering.
        if type(predicate) not in (exp.EQ,exp.NEQ):
            numeric_column=(column_types or {}).get(table["columns"][column_index],"") in {"INTEGER","REAL","NUMERIC"}
            if literal_node.is_string or not numeric_column:
                return None
        literal=("-" if negative else "")+literal_node.this
        spoken_literal=("문자 "+literal) if literal_node.is_string else ("마이너스 " if negative else "")+literal_node.this
        separator=" " if type(predicate) in (exp.GTE,exp.LTE) else ""
        clause=f"{column_index+1}열이 {spoken_literal}"+separator+operators[type(predicate)]+" 조건"
        operator=type(predicate).__name__.lower()
    else:
        return None
    actual=table["rows"][row_index][column_index]
    speech=f"원본 {row_index+1}행의 {column_index+1}열 값은 {_value(actual)}입니다. "
    speech+=clause+("을 만족해 집계 입력에 포함됩니다." if included else "을 만족하지 못해 집계 입력에서 제외됩니다.")
    # A syntactically simple condition may still contain an arbitrarily long
    # literal. Preserve that condition on the board rather than truncate it.
    if len(speech)>180:
        return None
    return {"speech":speech,"column_name":table["columns"][column_index],"column_position":column_index+1,
        "cell_id":table["cell_ids"][row_index][column_index],"actual_value":actual,"literal":literal,
        "operator":operator,"where_sql":where_sql,"included":included,"scope":"executed_simple_where_comparison"}
