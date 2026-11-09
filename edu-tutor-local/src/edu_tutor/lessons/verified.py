"""Board cells and spoken numbers are rendered from a single evidence object."""
from __future__ import annotations
import copy
import hashlib
import math
import re
from edu_tutor.lessons.plans import validate_plan
from edu_tutor.problems.evidence import display_answer
from edu_tutor.problems.models import canonical


def value_text(value):
    return "NULL" if value is None else str(value)


def aggregate_equation(aggregate):
    """Use only independently checked numeric inputs; never render model LaTeX."""
    function=aggregate["function"]
    if function not in {"sum", "avg"}:
        return None
    def number(value):
        if type(value) not in {int,float} or not math.isfinite(value):
            raise ValueError("검증된 유한 숫자만 수식에 사용할 수 있습니다.")
        text=str(value)
        if "e" in text.lower():
            coefficient,exponent=text.lower().split("e")
            text=coefficient+r"\times 10^{"+str(int(exponent))+"}"
        return "("+text+")" if value<0 else text
    if aggregate["result"] is None:
        return r"\mathrm{"+function.upper()+r"}=\mathrm{NULL}"
    result=number(aggregate["result"])
    if function=="avg":
        if aggregate["count"]<=0:
            raise ValueError("값이 없는 평균을 나눗셈 수식으로 만들 수 없습니다.")
        return r"\frac{"+number(aggregate["sum"])+"}{"+str(aggregate["count"])+"}="+result
    values=aggregate["included_values"]
    terms=" + ".join(number(value) for value in values) if 0<len(values)<=8 else r"\mathrm{SUM}"
    return terms+"="+result


def counted_zero(aggregate):
    return (aggregate["function"] == "count" and aggregate["column"] != "*"
            and any(type(value) in {int, float} and value == 0 for value in aggregate["included_values"]))


def aggregate_key(aggregate):
    return {"function":aggregate["function"].casefold(),"column":aggregate["column"].casefold(),"distinct":aggregate["distinct"]}


def logical_aggregate_speech(logical, table):
    """Explain the proved operations; column positions bind speech to the board."""
    if not logical["aggregates"]:
        return "집계할 그룹이 없어 계산할 결과도 없습니다."
    operations = {}
    for aggregate in logical["aggregates"]:
        key = (aggregate["function"], aggregate["column"].casefold(), aggregate["distinct"])
        operations.setdefault(key, []).append(aggregate)
    names = [name.casefold() for name in table["columns"]]
    parts = []
    for (function, column, distinct), values in operations.items():
        label = "" if column == "*" else f"원본 {names.index(column)+1}열"
        prefix = "중복된 값은 한 번만 사용해 " if distinct else ""
        if function == "count":
            text = "행을 하나씩 세어 전체 행 수를 구합니다." if column == "*" else f"{label}에서 NULL을 제외하고 값이 있는 칸의 개수를 셉니다."
            if any(counted_zero(value) for value in values):text += " 0도 값이므로 포함합니다."
        elif function == "sum":
            text = f"{label}의 NULL을 제외한 값을 더해 합계를 구합니다."
        elif function == "avg":
            text = f"{label}의 NULL을 제외한 값을 더한 뒤, 값의 개수로 나누어 평균을 구합니다."
        elif function in {"min", "max"}:
            text = f"{label}의 NULL을 제외한 숫자를 비교해 " + ("가장 작은 값" if function == "min" else "가장 큰 값") + "을 고릅니다."
        else:
            raise ValueError("검증되지 않은 집계 연산은 대사로 만들 수 없습니다.")
        if function != "count" and any(value["count"] == 0 for value in values):
            text += " 값이 하나도 없는 묶음의 결과는 NULL입니다."
        parts.append(prefix + text)
    return ("각 그룹에서 " if logical["group_columns"] else "이 입력에서 ") + " ".join(parts)


def legacy_logical_speeches(logical, table, result):
    """Exact earlier server-generated wording, for saved-plan binding only."""
    return [f"원본 {len(table['rows'])}행 중 WHERE를 통과한 행은 {len(logical['filtered_row_ids'])}개입니다. 학습용 논리 순서입니다.",
            f"남은 행을 {len(logical['groups'])}개 그룹으로 묶습니다.",
            "각 그룹의 실제 입력값으로 집계하고 SQLite 결과와 대조했습니다.",
            f"HAVING 조건을 적용한 최종 SELECT 결과는 {len(result['rows'])}행입니다."]


def table_action(table, slot="main", caption="확정한 원본 표"):
    return {"type":"table", "element_id":table["id"], "slot":slot, "columns":table["columns"],
            "rows":table["rows"], "row_ids":table["row_ids"], "column_ids":table["column_ids"],
            "cell_ids":table["cell_ids"], "table_name":table["name"], "caption":caption,
            "timing":{"start":0,"end":0}}


def step(ident, title, speech, actions, target, kind="point"):
    return {"id":ident,"title":title,"speech":speech,"board_actions":actions,
            "gesture":{"kind":kind,"target_element_id":target}}


def base_plan(message, question, lesson_id):
    problem=message["problem"]
    plan={"schema_version":"1.0", "lesson_id":lesson_id,"title":"원본 문제 확인", "goal":"원본 조건과 계산 근거를 연결합니다.",
          "question_text":question,"problem_source":"confirmed_image" if problem["source"]["kind"]=="photo" else "typed_user_input",
          "provenance":"tool_derived","source_refs":[],"steps":[],"final_summary":"계산 근거 확인",
          "problem_revision":problem["revision"],"source_message_id":message["id"],
          "evidence_ref":{"message_id":message["id"],"problem_revision":problem["revision"],"mode":message.get("evidence",{}).get("scenario","original")}}
    if problem["source"].get("photo_id"):plan["source_photo_id"]=problem["source"]["photo_id"]
    return plan


def trace_signature(logical):
    """Bind a follow-up to source rows and proved operations, not model prose."""
    from sqlglot import parse_one
    from edu_tutor.problems.evidence import normalized_clause
    fields=("kind","table_id","filtered_row_ids","projection_columns","ordered_row_ids",
            "order_by","group_columns","ordered_group_values","order_ties")
    value={key:logical.get(key) for key in fields}
    for key in ("where_sql","having_sql"):
        clause=logical.get(key)
        value[key]=(normalized_clause(parse_one("SELECT * FROM _source "+clause,read="sqlite").args[key[:-4]])
                    if clause else None)
    value["row_evaluations"]=[{key:row.get(key) for key in ("row_id","index","truth","included")}
                              for row in logical.get("row_evaluations",[])]
    value["aggregate_values"]=[{key:item.get(key) for key in
        ("id","function","column","distinct","group_values","included_row_ids","included_values","result")}
        for item in logical.get("aggregates",[])]
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def traced_table(table, ident, row_ids, columns=None, labels=None, slot="right", caption=""):
    """Keep exact source identities in one-to-one row/column projections."""
    columns=columns or table["columns"]
    lookup={name.casefold():index for index,name in enumerate(table["columns"])}
    selected_columns=[lookup[name.casefold()] for name in columns]
    if len(set(selected_columns))!=len(selected_columns):
        raise ValueError("같은 원본 열을 중복 출력하는 상세 판서는 아직 지원하지 않습니다.")
    rows=[table["row_ids"].index(row_id) for row_id in row_ids]
    return {"type":"table","element_id":ident,"slot":slot,"columns":labels or columns,
        "rows":[[table["rows"][i][j] for j in selected_columns] for i in rows],
        "row_ids":list(row_ids),"column_ids":[table["column_ids"][j] for j in selected_columns],
        "cell_ids":[[table["cell_ids"][i][j] for j in selected_columns] for i in rows],
        "caption":caption,"timing":{"start":0,"end":0}}


def truth_text(value):
    if value is True:return "TRUE"
    if value is False:return "FALSE"
    if value is None:return "UNKNOWN"
    raise ValueError("행 조건의 검증된 TRUE/FALSE/UNKNOWN 값이 필요합니다.")


def condition_trace_board(evidence,logical,table):
    checks=logical.get("row_evaluations",[])
    if (len(checks)!=len(table["rows"]) or
            [(r["row_id"],r["index"]) for r in checks]!=list(zip(table["row_ids"],range(len(table["rows"]))))):
        raise ValueError("모든 원본 행의 조건 결과와 원본 행 번호 연결이 필요합니다.")
    if any(r["included"]!=(r["truth"] is True) for r in checks):
        raise ValueError("조건의 참 값과 남는 행이 일치하지 않습니다.")
    return {"type":"table","element_id":evidence["id"]+"-row-conditions","slot":"bottom",
        "columns":["원본 행","WHERE 결과","남는가"],
        "rows":[[r["index"]+1,truth_text(r["truth"]),"유지" if r["included"] else "제외"] for r in checks],
        "caption":logical.get("where_sql") or "WHERE 없음 · 모든 행 유지","timing":{"start":0,"end":0}}


def ordering_speech(logical, *, brief=False):
    rules=logical.get("order_by") or []
    if not rules:
        if brief:
            return "ORDER BY가 없으므로 행 순서는 보장되지 않습니다."
        return "ORDER BY가 없으므로 결과 행의 순서는 보장되지 않습니다. 화면의 순서는 이번 실행에서 관측한 순서입니다."
    parts=[]
    for index,rule in enumerate(rules):
        direction=rule["direction"].upper()
        if direction not in {"ASC","DESC"}:
            raise ValueError("정렬 방향 근거가 올바르지 않습니다.")
        if brief:
            parts.append(f"{rule['column']}의 "+("오름차순" if direction=="ASC" else "내림차순"))
            continue
        parts.append(f"{index+1}순위는 {rule['column']}의 "+("오름차순" if direction=="ASC" else "내림차순")+
                     (", NULL은 앞에 둡니다." if rule.get("nulls_first") else ", NULL은 뒤에 둡니다."))
    if brief:
        text="정렬 우선순위는 "+", ".join(parts)+"입니다."
        if len(parts)>1:text+=" 앞 값이 같을 때만 다음 기준을 봅니다."
        if logical.get("order_ties"):text+=" 모든 정렬 키가 같은 행끼리 순서는 미지정입니다."
        return text
    text=" ".join(parts)
    if len(parts)>1:text+=" 앞 기준의 값이 같을 때만 다음 기준으로 비교합니다."
    text+=" 모든 정렬 기준이 같은 행끼리의 순서는 따로 정하지 않았습니다."
    return text


def condition_row_speech(logical, table, row_index):
    """Render independently checked truth values; never infer from client text."""
    rows=[row for row in logical.get("row_evaluations",[]) if row["row_id"]==table["row_ids"][row_index]]
    if len(rows)!=1 or rows[0]["index"]!=row_index:
        raise ValueError("선택한 원본 행의 조건 계산 근거가 없습니다.")
    row=rows[0]
    if row["included"] != (row["truth"] is True):
        raise ValueError("행 조건의 참 값과 포함 여부가 일치하지 않습니다.")
    if not logical.get("where_sql"):
        return f"원본 {row_index+1}행은 WHERE 조건이 없어 그대로 남습니다."
    from sqlglot import exp, parse_one
    spoken=[]
    operators={exp.EQ:"같다",exp.NEQ:"다르다",exp.GT:"크다",exp.GTE:"크거나 같다",
               exp.LT:"작다",exp.LTE:"작거나 같다"}
    for item in row.get("comparisons",[]):
        predicate=parse_one("SELECT * FROM _source WHERE "+item["sql"],read="sqlite").args["where"].this
        while isinstance(predicate,exp.Paren):predicate=predicate.this
        negate=isinstance(predicate,exp.Not)
        inner=predicate.this if negate else predicate
        left=item.get("left")
        right=item.get("right")
        if isinstance(inner,exp.Is) and isinstance(inner.expression,exp.Null):
            name=inner.this.name
            spoken.append(f"{name}의 값은 {value_text(left)}이고, NULL"+("이 아니라는" if negate else "이라는")+
                          " 조건의 결과는 "+truth_text(item["truth"])+"입니다.")
        elif type(inner) in operators and not negate:
            name=inner.this.name if isinstance(inner.this,exp.Column) else "왼쪽 값"
            spoken.append(f"{name}의 값 {value_text(left)}이 {value_text(right)}보다 {operators[type(inner)]}는 비교의 결과는 "+
                          truth_text(item["truth"])+"입니다." if type(inner) not in {exp.EQ,exp.NEQ} else
                          f"{name}의 값 {value_text(left)}과 {value_text(right)}이 {operators[type(inner)]}는 비교의 결과는 "+
                          truth_text(item["truth"])+"입니다.")
        else:
            spoken.append(f"판서의 {item['sql']} 조건 결과는 {truth_text(item['truth'])}입니다.")
    connective=""
    where=parse_one("SELECT * FROM _source "+logical["where_sql"],read="sqlite").args["where"].this
    if any(where.find_all(exp.And)):connective+=" AND는 조건이 모두 TRUE여야 TRUE입니다."
    if any(where.find_all(exp.Or)):connective+=" OR는 조건 중 하나라도 TRUE이면 TRUE입니다."
    outcome="남습니다" if row["included"] else "제외됩니다"
    text=f"원본 {row_index+1}행을 확인합니다. "+" ".join(spoken)+connective
    text+=f" 전체 WHERE 결과는 {truth_text(row['truth'])}이므로 이 행은 {outcome}."
    if row["truth"] is None:text+=" NULL을 일반 비교하면 UNKNOWN이 될 수 있고, WHERE는 TRUE인 행만 남깁니다."
    return text


def projection_steps(message,logical,actions,result_board):
    evidence=message["evidence"]
    table=next(t for t in evidence["working_tables"] if t["id"]==logical["table_id"])
    trace=condition_trace_board(evidence,logical,table)
    trace_id=trace["element_id"]
    filtered_id=evidence["id"]+"-project-rows"
    filtered=traced_table(table,filtered_id,logical["ordered_row_ids"],caption="조건을 통과한 원본 행 · 이번 실행의 정렬")
    projection=traced_table(table,result_board["element_id"],logical["ordered_row_ids"],
        logical["projection_columns"],result_board["columns"],slot="bottom",caption="SQLite 최종 결과 · 원본 행과 열 식별자 유지")
    if projection["rows"]!=result_board["rows"]:
        raise ValueError("출력 열과 원본 행의 연결이 SQLite 결과와 다릅니다.")
    selected=[table["row_ids"].index(r) for r in logical["filtered_row_ids"]]
    rule_id=evidence["id"]+"-projection-rule"
    order_id=evidence["id"]+"-order-rule"
    def flow(name,source,target):
        return {"type":"arrow","element_id":evidence["id"]+"-projection-flow-"+name,
                "from_element_id":source,"to_element_id":target}
    where=(f"SQLite에서 각 행의 WHERE 조건을 계산합니다. 원본 {len(table['rows'])}행 중 TRUE인 {len(selected)}행만 남습니다. FALSE와 UNKNOWN은 제외합니다."
           if logical.get("where_sql") else f"WHERE 조건이 없으므로 원본 {len(table['rows'])}행을 모두 남깁니다.")
    return [
        step("s1","원본 행과 조건값",where,actions+[trace,
            {"type":"highlight","target_element_id":table["id"],"row_indices":selected,"style":"background","timing":{"start":0,"end":0}}],table["id"]),
        step("s2","정렬 기준과 원본 행 연결",ordering_speech(logical),
            [{"type":"clear","target":evidence["id"]+"-sql"},{"type":"clear","target":trace_id},filtered,
             {"type":"text","element_id":order_id,"slot":"bottom","text":ordering_speech(logical)},
             flow("rows",table["id"],filtered_id)],filtered_id),
        step("s3","출력 열과 최종 결과",
             "남은 행에서 "+", ".join(logical["projection_columns"])+f" 열을 요청한 순서로 출력합니다. 최종 결과는 {len(projection['rows'])}행입니다. "+
             ("ORDER BY에서 지정한 기준의 순서입니다." if logical.get("order_by") else "ORDER BY가 없으므로 행 순서는 보장되지 않습니다."),
             [{"type":"clear","target":filtered_id},{"type":"clear","target":order_id},projection,
              {"type":"text","element_id":rule_id,"slot":"right","text":"출력 열 순서: "+" → ".join(logical["projection_columns"])+"\n"+ordering_speech(logical)},
              flow("project",table["id"],projection["element_id"])],projection["element_id"])]


def selected_projection_row_step(message,logical,actions,result_board):
    context=message.get("lesson_context") or {}
    scope=context.get("_verified_logical_stage") or {}
    index=scope.get("index")
    if (scope.get("kind")!="server_verified_projection_plan_v1" or type(index) is not int or not 0<=index<3
            or scope.get("step_id")!=f"s{index+1}" or context.get("step")!=index
            or scope.get("stage")!=["where","order","projection"][index]
            or scope.get("source_lesson_id")!=context.get("lesson_id")
            or scope.get("problem_id")!=message["problem"]["id"]
            or scope.get("problem_revision")!=message["problem"]["revision"]
            or scope.get("trace_signature")!=trace_signature(logical)):
        raise ValueError("현재 SELECT 단계와 원본 행의 검증 근거를 연결하지 못했습니다.")
    selected=context.get("selected_cell") or {}
    table=next(t for t in message["evidence"]["working_tables"] if t["id"]==logical["table_id"])
    allowed=scope.get("selectable_tables",{})
    selected_table=selected.get("table_element_id") or table["id"]
    cell=selected.get("cell_id")
    if cell not in allowed.get(selected_table,[]):
        raise ValueError("선택한 셀은 현재 단계의 원본 행에 연결된 셀이 아닙니다.")
    matches=[(i,j) for i,row in enumerate(table["cell_ids"]) for j,ident in enumerate(row) if ident==cell]
    if len(matches)!=1:
        raise ValueError("선택한 셀을 원본에서 확인할 수 없습니다.")
    ri,ci=matches[0]
    row_id=table["row_ids"][ri]
    if selected.get("row_id") not in (None,row_id) or selected.get("column_id") not in (None,table["column_ids"][ci]):
        raise ValueError("선택한 행·열 식별자가 원본과 다릅니다.")
    speech=condition_row_speech(logical,table,ri)
    included=row_id in logical["filtered_row_ids"]
    if included and scope["stage"] in {"order","projection"}:
        speech+=" "+ordering_speech(logical,brief=True)
        if logical.get("order_by"):
            rank=logical["ordered_row_ids"].index(row_id)+1
            speech+=f" 이번 실행에서는 이 원본 행이 {rank}번째에 표시됐습니다."
    if included and scope["stage"]=="projection":
        speech+=" 출력 열은 "+", ".join(logical["projection_columns"])+"입니다."
    if len(speech)>1000:
        raise ValueError("선택 행 설명이 길이 제한을 넘었습니다. 조건이나 정렬 범위를 좁혀 주세요.")
    ident=message["evidence"]["id"]+"-selected-row-reason"
    projection=traced_table(table,result_board["element_id"],logical["ordered_row_ids"],
        logical["projection_columns"],result_board["columns"],slot="bottom",caption="검증한 SELECT 결과")
    if projection["rows"]!=result_board["rows"]:
        raise ValueError("원본 행과 최종 결과를 연결하지 못했습니다.")
    return step("s1","선택한 행의 조건·순서",speech,actions+[
        {"type":"highlight","target_element_id":table["id"],"row_indices":[ri],"cell_ids":[cell],"style":"outline","timing":{"start":0,"end":0}},
        {"type":"text","element_id":ident,"slot":"right","text":speech,"timing":{"start":0,"end":0}},projection],table["id"])


def validated_logical_stage(lesson, source_message, context):
    """Bind a requested index to the server's preserved, known logical plan.

    The API removes the reserved context key supplied by clients before calling
    this helper. A requested index controls teaching scope, never SQL evidence.
    """
    index=context.get("step")
    plan=lesson.get("plan") or {}
    evidence=source_message.get("evidence") or {}
    if (type(index) is not int or index<0 or source_message.get("lesson_context")
            or lesson.get("status")!="verified_tool_plan" or lesson.get("generation",{}).get("source")!="shared_evidence"
            or plan.get("provenance")!="tool_derived" or plan.get("source_message_id")!=source_message.get("id")
            or evidence.get("status")!="verified" or evidence.get("scenario")!="original" or not evidence.get("logical_steps")
            or plan.get("problem_revision")!=source_message["problem"]["revision"]):
        return None
    if (lesson.get("source_message_id",source_message["id"])!=source_message["id"]
            or "problem_revision" in context and (type(context["problem_revision"]) is not int
                or context["problem_revision"]!=source_message["problem"]["revision"])):
        return None
    try:
        expected=generate_verified_plan(source_message,source_message["problem"]["raw_text"],plan.get("lesson_id"))["plan"]
    except (ValueError,KeyError,TypeError):
        return None
    if not expected:
        return None
    logical=evidence["logical_steps"]
    if logical.get("kind")=="projection_teaching_steps":
        if len(expected["steps"])<3 or index>=3 or plan.get("steps")!=expected["steps"]:
            return None
        from edu_tutor.lessons.plans import scene_at
        source_cells={cell for table in evidence["working_tables"] for row in table["cell_ids"] for cell in row}
        scene=scene_at(expected,index)
        selectable={ident:[cell for row in item.get("cell_ids",[]) for cell in row if cell in source_cells]
                    for ident,item in scene["elements"].items() if item["type"]=="table"}
        return {"kind":"server_verified_projection_plan_v1","source_lesson_id":lesson["id"],
            "problem_id":source_message["problem"]["id"],"problem_revision":source_message["problem"]["revision"],
            "index":index,"step_id":plan["steps"][index]["id"],"stage":["where","order","projection"][index],
            "trace_signature":trace_signature(logical),"selectable_tables":selectable}
    if logical.get("order_by"):
        if len(expected["steps"])<5 or index>=5 or plan.get("steps")!=expected["steps"]:
            return None
        return {"kind":"server_verified_ordered_logical_plan_v1","source_lesson_id":lesson["id"],
            "problem_id":source_message["problem"]["id"],"problem_revision":source_message["problem"]["revision"],
            "index":index,"step_id":plan["steps"][index]["id"],"stage":["where","group","aggregate","having","order"][index],
            "trace_signature":trace_signature(logical)}
    direct=(not logical["where_sql"] and not logical["group_columns"] and not logical["having_sql"]
            and 1<=len(logical["aggregates"])<=3 and not any(a.get("input_transform") for a in logical["aggregates"]))
    if direct:
        # These are the existing one-step-per-aggregate plans, not the four
        # WHERE/GROUP/aggregate/HAVING stages. Accept only the exact rebuilt plan.
        if (len(expected["steps"])<len(logical["aggregates"]) or index>=len(logical["aggregates"])
                or plan.get("steps")!=expected["steps"]):
            return None
        aggregate=logical["aggregates"][index]
        return {"kind":"server_verified_direct_aggregate_plan_v1", "source_lesson_id":lesson["id"],
            "problem_id":source_message["problem"]["id"],"problem_revision":source_message["problem"]["revision"],
            "index":index,"step_id":plan["steps"][index]["id"],"stage":"aggregate",
            "aggregate_id":aggregate["id"],"aggregate_key":aggregate_key(aggregate),
            "aggregate_order":[{"id":a["id"],**aggregate_key(a)} for a in logical["aggregates"]]}
    if index>=4 or len(expected["steps"])<4:
        return None
    if plan.get("steps")!=expected["steps"]:
        # Reconstruct only known server versions; never accept arbitrary speech,
        # table values, gestures or timing merely because a plan was saved.
        versions=[copy.deepcopy(expected["steps"])]
        logical=evidence["logical_steps"]
        table=next(t for t in evidence["working_tables"] if t["id"]==logical["table_id"])
        prior=copy.deepcopy(expected["steps"])
        for item,speech in zip(prior,legacy_logical_speeches(logical,table,evidence["result"])):
            item["speech"]=speech
        versions.append(prior)
        prefix=evidence["id"]+"-logical-flow-"
        for version in list(versions):
            no_arrows=copy.deepcopy(version)
            for saved_step in no_arrows:
                saved_step["board_actions"]=[action for action in saved_step["board_actions"]
                    if not (action.get("type")=="arrow" and action.get("element_id", "").startswith(prefix))]
            versions.append(no_arrows)
        if not any(plan.get("steps")==version for version in versions):
            return None
    return {"kind":"server_verified_logical_plan_v1", "source_lesson_id":lesson["id"],
        "problem_id":source_message["problem"]["id"], "problem_revision":source_message["problem"]["revision"],
        "index":index,"step_id":plan["steps"][index]["id"],"stage":["where","group","aggregate","having"][index]}


def direct_aggregate_row_speech(aggregate, table, index):
    """Explain this proved aggregate's input membership, including zero vs NULL."""
    function,column,distinct=(aggregate[k] for k in ("function","column","distinct"))
    expression=f"{function.upper()}({'DISTINCT ' if distinct else ''}{column})"
    result=value_text(aggregate["result"])
    if function not in {"count","sum","avg","min","max"}:
        raise ValueError("이 집계 연산의 선택 행 설명은 지원하지 않습니다.")
    if column=="*":
        if function!="count" or distinct:
            raise ValueError("전체 행의 선택 설명은 COUNT(*)만 지원합니다.")
        return {"speech":f"COUNT(*)는 칸의 값이나 NULL 여부와 관계없이 행을 셉니다. 선택한 원본 {index+1}행도 한 행으로 세므로 전체 결과는 {result}입니다.",
            "focus_cell":None,"contrast_cells":[]}
    ci=next(i for i,name in enumerate(table["columns"]) if name.casefold()==column.casefold())
    value=table["rows"][index][ci]
    included=table["row_ids"][index] in aggregate["included_row_ids"]
    if (value is None and included) or (value is not None and not included and not distinct):
        raise ValueError("선택한 값과 집계 입력 포함 근거가 일치하지 않습니다.")
    intro=f"현재 {expression}에서 원본 {index+1}행의 {column} 값은 {value_text(value)}입니다. "
    contrast=[]
    if value is None:
        reason="NULL이므로 값의 개수를 세지 않습니다. " if function=="count" else "NULL이므로 이 집계의 입력값에서 제외합니다. "
    elif not included:
        reason="NULL은 아니지만 DISTINCT는 같은 값을 한 번만 사용합니다. 이미 같은 값이 있어 이 행 때문에 집계 입력을 늘리지 않습니다. "
    elif function=="count":
        reason=f"{value_text(value)}은 NULL이 아니므로 값 한 개로 셉니다. "
    elif function=="sum":
        reason=("0은 NULL이 아니므로 입력에 포함합니다. 다만 0을 더하므로 합계는 변하지 않습니다. "
                if value==0 else f"이 행의 {value_text(value)}을 합계에 더합니다. ")
    elif function=="avg":
        reason=f"이 행의 {value_text(value)}을 합에 더하고 값의 개수에 한 개를 포함합니다. "
    else:
        reason="NULL이 아닌 값이므로 최솟값·최댓값을 찾는 비교 대상에 포함합니다. "
    if distinct and included:reason+="같은 값이 반복되어도 한 번만 사용합니다. "
    if function=="count":
        others=[i for i,row in enumerate(table["rows"]) if i!=index and (row[ci] is None if value is not None else row[ci] is not None)]
        if others:
            other=others[0];other_value=table["rows"][other][ci];contrast=[table["cell_ids"][other][ci]]
            reason+=(f"반면 원본 {other+1}행은 NULL이므로 세지 않습니다. " if other_value is None
                     else f"반면 원본 {other+1}행의 {value_text(other_value)}은 NULL이 아닌 값입니다. ")
    if function=="avg" and aggregate["count"]:
        conclusion=f"입력값 합계 {value_text(aggregate['sum'])}을 {aggregate['count']}개로 나누면 평균은 {result}입니다."
    elif function=="avg":conclusion="평균을 낼 값이 없으므로 결과는 NULL입니다."
    elif function in {"min","max"}:
        conclusion=("최솟값" if function=="min" else "최댓값")+f" 결과는 {result}입니다."
    else:conclusion=f"{expression} 결과는 {result}입니다."
    return {"speech":intro+reason+conclusion,"focus_cell":table["cell_ids"][index][ci],"contrast_cells":contrast}


def selected_row_step(message, logical, actions, result_board):
    """Explain an identified source row from executed evidence, not model prose.

    Client labels, values and indices are not evidence. Derived result cells are
    intentionally not mapped back to a guessed source row.
    """
    selected=(message.get("lesson_context") or {}).get("selected_cell") or {}
    if not logical:
        raise ValueError("이 SQL은 원본 행의 조건·집계 연결을 검증할 수 없습니다. 지원되는 원본 표와 조건을 확인해 주세요.")
    if any(item.get("input_transform") for item in logical["aggregates"]):
        raise ValueError("조건식 집계의 선택 행 보충 설명은 아직 지원하지 않습니다. 원본 조건값 표를 확인해 주세요.")
    if not selected:
        raise ValueError("어느 행인지 확인할 수 없습니다. 현재 원본 표에서 질문할 행의 셀을 선택해 주세요.")
    context=message.get("lesson_context") or {}
    scope=context.get("_verified_logical_stage") or {}
    ordered=scope.get("kind")=="server_verified_ordered_logical_plan_v1"
    stages=["where","group","aggregate","having"]+(["order"] if ordered else [])
    index_scope=scope.get("index")
    direct=scope.get("kind")=="server_verified_direct_aggregate_plan_v1"
    valid_index=type(index_scope) is int and 0<=index_scope<(len(logical["aggregates"]) if direct else len(stages))
    if (not valid_index or scope.get("step_id")!=f"s{index_scope+1}"
            or scope.get("source_lesson_id")!=context.get("lesson_id")
            or scope.get("problem_id")!=message["problem"]["id"] or scope.get("problem_revision")!=message["problem"]["revision"]):
        raise ValueError("현재 단계를 서버에 저장된 원본 논리 수업과 연결할 수 없습니다. 원본 수업의 해당 단계에서 다시 질문해 주세요.")
    if direct:
        aggregate=logical["aggregates"][index_scope]
        if (logical["where_sql"] or logical["group_columns"] or logical["having_sql"] or len(logical["aggregates"])>3
                or scope.get("stage")!="aggregate" or type(context.get("step")) is not int or context["step"]!=index_scope
                or scope.get("aggregate_id")!=aggregate["id"]
                or scope.get("aggregate_key")!=aggregate_key(aggregate)
                or scope.get("aggregate_order")!=[{"id":a["id"],**aggregate_key(a)} for a in logical["aggregates"]]):
            raise ValueError("현재 집계 단계와 선택 행의 실행 근거가 일치하지 않습니다. 원본 수업에서 다시 선택해 주세요.")
    elif ordered:
        if (not logical.get("order_by") or scope.get("stage")!=stages[index_scope]
                or scope.get("trace_signature")!=trace_signature(logical)):
            raise ValueError("현재 정렬 수업과 선택 행의 계산 근거가 일치하지 않습니다.")
    elif scope.get("kind")!="server_verified_logical_plan_v1" or scope.get("stage")!=stages[index_scope]:
        raise ValueError("현재 단계를 서버에 저장된 원본 논리 수업과 연결할 수 없습니다. 원본 수업의 해당 단계에서 다시 질문해 주세요.")
    stage=scope["stage"]
    table=next(t for t in message["evidence"]["working_tables"] if t["id"]==logical["table_id"])
    if selected.get("table_element_id") not in (None,table["id"]):
        raise ValueError("선택한 셀은 이 계산의 원본 표가 아닙니다. 원본 표의 행을 선택해 주세요.")
    cell=selected.get("cell_id")
    matches=[(i,j) for i,row in enumerate(table["cell_ids"]) for j,ident in enumerate(row) if ident==cell]
    if len(matches)!=1:
        raise ValueError("선택한 셀을 현재 원본에서 확인할 수 없습니다. 원본 표의 행을 다시 선택해 주세요.")
    index,column_index=matches[0]
    row_id=table["row_ids"][index]
    if selected.get("row_id") not in (None,row_id) or selected.get("column_id") not in (None,table["column_ids"][column_index]):
        raise ValueError("선택한 행·열 식별자가 서로 맞지 않습니다. 원본 표에서 셀을 다시 선택해 주세요.")
    values=table["rows"][index]
    lookup={name.casefold():i for i,name in enumerate(table["columns"])}
    columns=list(dict.fromkeys([table["columns"][column_index],*logical.get("where_columns",[])]))
    facts=", ".join(f"{name}={value_text(values[lookup[name.casefold()]])}" for name in columns)
    introduction=f"선택한 원본 {index+1}행은 {facts}입니다. "
    included=row_id in logical["filtered_row_ids"]
    if logical["where_sql"]:
        where_speech=f"{logical['where_sql']} 조건을 " + ("통과하여 집계 입력에 포함됩니다. " if included else "통과하지 못해 집계 입력에서 제외됩니다. ")
    else:
        where_speech="WHERE 조건이 없으므로 이 행도 집계 입력에 포함됩니다. "
    group_speech=""; aggregate_speeches=[]; having_speech=""; result_scope=""; aggregates=[]
    if included:
        groups=[group for group in logical["groups"] if row_id in group["row_ids"]]
        if len(groups)!=1 or "having_passed" not in groups[0]:
            raise ValueError("선택한 행과 최종 그룹을 연결한 실행 근거가 없습니다. 이 답변의 계산 근거를 다시 생성해 주세요.")
        group=groups[0]
        group_label=", ".join(f"{name}={value_text(value)}" for name,value in zip(logical["group_columns"],group["values"]))
        if group_label:group_speech=f"{group_label} 그룹에 속합니다. "
        aggregates=[item for item in logical["aggregates"] if item["group_values"]==group["values"]]
        for item in aggregates:
            expression=f"{item['function'].upper()}({'DISTINCT ' if item['distinct'] else ''}{item['column']})"
            explanation=f"이 그룹의 {expression}는 {value_text(item['result'])}입니다. "
            if item["column"]!="*" and row_id not in item["included_row_ids"]:
                reason="NULL이므로" if values[lookup[item["column"].casefold()]] is None else "중복을 제외하므로"
                explanation+=f"이 행의 {item['column']} 값은 {reason} 해당 집계에 더하지 않습니다. "
            aggregate_speeches.append(explanation)
        if logical["having_sql"]:
            having_speech=f"{logical['having_sql']} 조건을 " + ("통과하여 이 그룹은 최종 결과에 남습니다. " if group["having_passed"] else "통과하지 못해 이 그룹은 최종 결과에서 제외됩니다. ")
        elif group["having_passed"]:
            having_speech="이 그룹은 최종 결과에 남습니다. "
        if logical["group_columns"]:result_scope="최종 표의 한 행은 원본 한 행이 아니라 이 그룹의 집계입니다."
    complete_explanation=introduction+where_speech+group_speech+"".join(aggregate_speeches)+having_speech+result_scope
    if not included or stage=="where":speech=introduction+where_speech
    elif stage=="group":speech=introduction+where_speech+group_speech
    elif stage=="aggregate":speech=introduction+group_speech+"".join(aggregate_speeches)
    elif stage=="order":
        speech=introduction+group_speech+having_speech
        if group["having_passed"]:
            keys=logical.get("ordered_group_values") or []
            if group["values"] not in keys:
                raise ValueError("현재 그룹의 최종 정렬 위치를 확인할 수 없습니다.")
            speech+=ordering_speech(logical,brief=True)+f" 이번 실행에서 이 그룹은 {keys.index(group['values'])+1}번째입니다."
        else:
            speech+="최종 결과에서 제외됐으므로 정렬 대상에도 들어가지 않습니다."
    else:
        # Speak only aggregates used by HAVING; unrelated SELECT values remain
        # in the complete board explanation. Resolve aliases from the same SQL.
        from sqlglot import exp
        from edu_tutor.problems.evidence import aggregate_spec,bounded_query
        query,_,_,_=bounded_query(message["evidence"]["sql"],message["problem"])
        having=query.args.get("having")
        needed=[]
        if having:
            needed=[aggregate_spec(item) for item in having.find_all(exp.AggFunc)]
            aliases={item.alias.casefold():aggregate_spec(item) for item in query.expressions if isinstance(item,exp.Alias)}
            needed.extend(aliases[column.name.casefold()] for column in having.find_all(exp.Column) if column.name.casefold() in aliases)
        def key(item):return (item["function"],item["column"].casefold(),bool(item["distinct"])) if item else None
        available={key(item):text for item,text in zip(aggregates,aggregate_speeches)}
        if any(key(item) not in available for item in needed):
            raise ValueError("HAVING 판단에 쓰인 집계값은 현재 설명 범위에서 확인할 수 없습니다. 해당 집계를 SELECT에 포함한 원본 SQL을 확인해 주세요.")
        needed_text="".join(available[item] for item in dict.fromkeys(key(item) for item in needed))
        speech=introduction+group_speech+needed_text+having_speech+result_scope
    spoken_mapping=""; focus_cell=cell; contrast_cells=[]
    if direct:
        rendered=direct_aggregate_row_speech(logical["aggregates"][index_scope],table,index)
        speech=rendered["speech"];focus_cell=rendered["focus_cell"] or cell;contrast_cells=rendered["contrast_cells"]
    elif not included or stage=="where":
        from edu_tutor.lessons.conditions import simple_where_speech
        source_table=next(t for t in message["problem"]["tables"] if t["name"]==table["name"])
        rendered=simple_where_speech(logical["where_sql"],table,index,included,{c["name"]:c["type"] for c in source_table["columns"]})
        if rendered:
            speech=rendered["speech"]
            focus_cell=rendered["cell_id"]
            spoken_mapping=f"음성의 {rendered['column_position']}열 = 원본 열 {rendered['column_name']}\n"
        elif not logical["where_sql"]:
            speech=f"원본 {index+1}행은 행을 거르는 조건이 없어 집계 입력에 포함됩니다."
        else:
            outcome="통과해 집계 입력에 포함됩니다" if included else "통과하지 못해 집계 입력에서 제외됩니다"
            speech=f"원본 {index+1}행은 판서의 조건을 {outcome}. 이 조건을 한국어로 풀어 설명하는 기능은 지원 범위 밖이므로 원문을 판서에 남겼습니다."
    if len(speech)>1000:
        raise ValueError("선택한 행의 조건 설명이 음성 길이 제한을 초과합니다. 질문할 조건이나 열의 범위를 좁혀 주세요.")
    explanation_id=message["evidence"]["id"]+"-selected-row-reason"
    stage_label={"where":"WHERE","group":"GROUP BY","aggregate":"집계","having":"HAVING·최종 결과","order":"ORDER BY"}[stage]
    if direct:
        item=logical["aggregates"][index_scope]
        stage_label=f"{item['function'].upper()}({'DISTINCT ' if item['distinct'] else ''}{item['column']})"
    combined=actions+[
        {"type":"highlight","target_element_id":table["id"],"row_indices":[index],"cell_ids":list(dict.fromkeys([focus_cell,cell,*contrast_cells])),"style":"outline","timing":{"start":0,"end":0}},
        {"type":"text","element_id":explanation_id,"slot":"right","text":f"현재 음성 범위: {stage_label}\n"+spoken_mapping+"음성 설명: "+speech+"\n전체 계산 근거: "+complete_explanation,"timing":{"start":0,"end":0}},
        result_board]
    return step("s1",stage_label+" · 선택한 원본 행",speech,combined,table["id"])


def conditional_sum_steps(message, logical, actions, result_board):
    """Teach a proved IS NOT NULL predicate without rewriting the model SQL."""
    evidence=message["evidence"]
    conditional=[a for a in logical["aggregates"] if a.get("input_transform")=="is_not_null_indicator"]
    if (message.get("lesson_context") or len(conditional)!=1 or logical["group_columns"]
            or logical["where_sql"] or logical["having_sql"] or len(logical["aggregates"])>2
            or any(a is not conditional[0] and (a["function"]!="count" or a["column"]!="*" or a["distinct"])
                   for a in logical["aggregates"])):
        raise ValueError("조건식 집계의 상세 판서는 WHERE·그룹 없는 SUM(열 IS NOT NULL)과 선택적인 COUNT(*)만 지원합니다. 계산 결과는 기록에 보존하며 이 범위를 넘는 음성은 만들지 않습니다.")
    aggregate=conditional[0]
    table=next(t for t in evidence["working_tables"] if t["id"]==logical["table_id"])
    indicator_id=evidence["id"]+"-condition-inputs"
    rows=[[table["row_ids"].index(item["row_id"])+1,item["source_value"],item["value"]] for item in aggregate["input_rows"]]
    row_ids=[item["row_id"]+"-condition" for item in aggregate["input_rows"]]
    intermediate={"type":"table","element_id":indicator_id,"slot":"right",
        "columns":["원본 행",aggregate["column"],"조건값 (1/0)"],"rows":rows,
        "row_ids":row_ids,"column_ids":[indicator_id+suffix for suffix in ("-source-row","-source-value","-indicator")],
        "cell_ids":[[ident+suffix for suffix in ("-source-row","-source-value","-indicator")] for ident in row_ids],
        "caption":aggregate["input_expression"]+" · 1=참, 0=거짓 · 원본 행 연결","timing":{"start":0,"end":0}}
    initial=copy.deepcopy(actions)
    sql_id=evidence["id"]+"-sql"
    existing_sql=next((a for a in initial if a["type"]=="code" and a["element_id"]==sql_id),None)
    if existing_sql:existing_sql["slot"]="bottom"
    else:initial.append({"type":"code","element_id":sql_id,"slot":"bottom","language":"sql","code":evidence["sql"]})
    initial += [intermediate,{"type":"highlight","element_id":indicator_id+"-source-highlight",
        "target_element_id":table["id"],"row_indices":list(range(len(table["rows"]))),"style":"outline"}]
    first=f"전체 행 수는 NULL도 포함해 {len(table['rows'])}입니다. 조건값은 NULL이면 0, 아니면 1입니다."
    total=aggregate["result"]
    second=(f"1인 행은 {sum(aggregate['included_values'])}개이므로 조건값을 더한 결과는 {value_text(total)}입니다."
            if aggregate["input_rows"] else "입력 행이 없어 더할 조건값이 없습니다. SQLite의 합계 결과는 NULL입니다.")
    return [step("s1","원본 행과 조건값",first,initial,table["id"]),
            step("s2","조건값의 SUM과 최종 결과",second,[{"type":"clear","target":sql_id},
                {"type":"clear","target":indicator_id+"-source-highlight"},
                {"type":"highlight","target_element_id":indicator_id,"column_indices":[2],"style":"background"},result_board],indicator_id)]


def generate_verified_plan(message, question, lesson_id):
    evidence=message["evidence"]
    if evidence["status"]!="verified":
        return {"plan":None,"fallback_text":message["content"],"status":"verification_stopped","reason":"수치·판서·음성으로 내보낼 계산 근거가 없습니다.","speech_allowed":False}
    plan=base_plan(message,question,lesson_id)
    independent=evidence["calculation"]["status"] in {"independent_aggregate_match","independent_projection_match"}
    plan["verification"]={"status":"calculation_checked" if independent else "execution_grounded",
        "scope":"확정한 원본 SQLite 실행 결과와 공유 수치 근거" + (" 및 독립 중간 계산 대조" if independent else ""),
        "limitations":["자연어 설명 전체의 진실성 또는 일반 SQL 의도를 자동 증명하지 않습니다.","실사용 독립 정답 일치 검사는 없으며 사람 검토도 미실시입니다.","논리 단계는 학습용이며 데이터베이스 물리 실행 추적이 아닙니다."]}
    tables=evidence["working_tables"]
    # Bound visible teaching units, not the numerical sandbox's input capacity.
    if any(len(t["rows"])>200 for t in tables):
        return {"plan":None,"fallback_text":message["content"],"status":"verification_stopped","reason":"판서는 표당 200행까지만 지원합니다.","speech_allowed":False}
    actions=[table_action(t, "main" if i==0 else "right", "설명용 새 가정의 표 · 원본은 보존" if evidence["scenario"]=="hypothesis" else "확정한 원본 표") for i,t in enumerate(tables)]
    if evidence.get("task_kind")=="write_sql" and len(tables)==1:
        actions.append({"type":"code","element_id":evidence["id"]+"-sql","slot":"right",
                        "language":"sql","code":evidence["sql"],"timing":{"start":0,"end":0}})
    logical=evidence.get("logical_steps")
    if not logical:
        problem=message.get("problem") or {}
        supplied_query=(problem.get("task_kind")=="query_result" and bool(problem.get("query"))
                        and evidence.get("sql_origin")=="unchanged_user_query"
                        and evidence.get("sql")==problem["query"])
        if not supplied_query:
            reason=evidence.get("calculation",{}).get("reason") or "독립 중간 계산 근거가 없습니다."
            return {"plan":None,"fallback_text":message["content"],"status":"verification_stopped",
                    "reason":"SQL 실행 결과는 확인했지만 상세 수업의 중간 계산을 검증하지 못했습니다: "+reason,
                    "speech_allowed":False,"generation":{"source":"unsupported_intermediate_trace","model_plan_calls":0,"repair_requests":0}}
        plan["verification"]["scope"]="학생이 확정한 원문 SQL의 SQLite 실행 결과만 확인. 조건·계산의 중간 단계는 설명하지 않습니다."
        plan["verification"]["limitations"].append(evidence.get("calculation",{}).get("reason") or "독립 중간 계산 근거가 없습니다.")
    result=evidence["result"]
    result_id=evidence["id"]+"-result"
    result_board={"type":"table","element_id":result_id,"slot":"bottom","columns":result["columns"],"rows":result["rows"],"caption":"최종 SELECT 실행 결과","timing":{"start":0,"end":0}}
    supplementary=bool(message.get("lesson_context"))
    from edu_tutor.problems.explanation_requests import requested_explanations
    from edu_tutor.problems.models import intent_question_text
    requests=requested_explanations(intent_question_text(message["problem"],question),supplementary=supplementary,
        source_table=next((t for t in tables if logical and t["id"]==logical["table_id"]),None))
    def request_failure(reason):
        return {**requests,"status":"unmet","scope":"인식한 설명 요청만 검사; 모델 자유 설명 미검증",
                "items":[{"kind":kind,"status":"unmet","reason":reason} for kind in requests["requested"]]}
    if requests["unsupported"]:
        reason=" ".join(requests["unsupported"])
        return {"plan":None,"fallback_text":message["content"],"status":"verification_stopped","reason":reason,
                "speech_allowed":False,"explanation_fulfillment":request_failure(reason),
                "generation":{"source":"unsupported_requested_explanation","model_plan_calls":0,"repair_requests":0}}
    row_reference=(bool(re.search(r"(?:이|해당|선택한?|원본)\s*행|왜|어째서|이유",question))
                   and bool(re.search(r"포함|제외|통과|빠지|빠져|남아|남았|남는|조건|묶|정렬|순서|먼저|뒤|앞",question)))
    if (supplementary and (message.get("lesson_context") or {}).get("selected_cell")
            and any(kind in requests["requested"] for kind in ("null_comparison","zero_comparison","empty_input","ordering","row_comparison"))):
        row_reference=True
    if logical and logical.get("kind")=="projection_teaching_steps":
        try:
            if supplementary:
                if evidence["scenario"]!="original" or not row_reference:
                    raise ValueError("현재 SELECT 수업의 보충 설명은 원본과 연결된 셀을 선택하고 그 행의 조건·포함·정렬 이유를 질문해 주세요.")
                plan["steps"]=[selected_projection_row_step(message,logical,actions,result_board)]
            else:
                plan["steps"]=projection_steps(message,logical,actions,result_board)
        except (ValueError,KeyError,TypeError) as exc:
            return {"plan":None,"fallback_text":message["content"],"status":"verification_stopped","reason":str(exc),"speech_allowed":False,
                    "explanation_fulfillment":request_failure(str(exc)),
                    "generation":{"source":"projection_trace_needs_input","model_plan_calls":0,"repair_requests":0}}
    elif logical and any(a.get("input_transform")=="is_not_null_indicator" for a in logical["aggregates"]):
        try:
            plan["steps"]=conditional_sum_steps(message,logical,actions,result_board)
        except ValueError as exc:
            return {"plan":None,"fallback_text":message["content"],"status":"verification_stopped","reason":str(exc),
                    "speech_allowed":False,"explanation_fulfillment":request_failure(str(exc)),
                    "generation":{"source":"conditional_sum_scope_needs_input","model_plan_calls":0,"repair_requests":0}}
    elif supplementary and evidence["scenario"]=="original" and row_reference:
        try:
            plan["steps"]=[selected_row_step(message,logical,actions,result_board)]
        except ValueError as exc:
            return {"plan":None,"fallback_text":message["content"],"status":"verification_stopped","reason":str(exc),"speech_allowed":False,
                    "explanation_fulfillment":request_failure(str(exc)),
                    "generation":{"source":"selected_row_needs_input","model_plan_calls":0,"repair_requests":0}}
    elif supplementary and evidence["scenario"]=="original" and logical and (logical["where_sql"] or logical["group_columns"] or logical["having_sql"]):
        return {"plan":None,"fallback_text":message["content"],"status":"verification_stopped",
                "reason":"현재 조건·그룹 수업의 보충 음성은 선택한 원본 행의 포함·제외 이유만 검증합니다. 질문할 원본 행의 셀을 선택하고 그 행의 조건이나 포함 이유를 구체적으로 질문해 주세요. 모델 초안은 답변 기록에 보존됩니다.",
                "speech_allowed":False,"generation":{"source":"supplementary_scope_needs_input","model_plan_calls":0,"repair_requests":0}}
    elif logical and not logical["group_columns"] and len(logical["aggregates"])<=3 and not logical["where_sql"] and not logical.get("order_by"):
        table=next(t for t in tables if t["id"]==logical["table_id"])
        for i,aggregate in enumerate(logical["aggregates"]):
            column=aggregate["column"]; function=aggregate["function"]
            value=value_text(aggregate["result"])
            if function=="count":
                speech=f"카운트 별표는 전체 행을 세어 {value}입니다." if column=="*" else f"{column}의 카운트는 NULL을 제외한 값을 세어 {value}입니다."
                if counted_zero(aggregate):speech+=" 0도 값이므로 포함합니다."
            elif function in {"min", "max"}:
                name="최솟값" if function=="min" else "최댓값"
                speech=(f"{column}에서 NULL을 제외한 숫자의 {name}은 {value}입니다." if aggregate["count"]
                        else f"{column}에 비교할 숫자가 없어 {name} 결과는 NULL입니다.")
            else:
                speech=f"{column}의 합계는 {value}입니다." if function=="sum" else f"{column}의 합계 {value_text(aggregate['sum'])}을 값 {aggregate['count']}개로 나누면 평균 {value}입니다." if aggregate["count"] else f"{column}에 평균을 낼 값이 없어 결과는 NULL입니다."
            if aggregate["distinct"]:speech="중복을 제외합니다. "+speech
            highlight={"type":"highlight","element_id":f"highlight-{i}","target_element_id":table["id"],"style":"background","timing":{"start":0,"end":0}}
            if column=="*":highlight["row_indices"]=[table["row_ids"].index(r) for r in aggregate["included_row_ids"]]
            else:highlight["cell_ids"]=aggregate["included_cell_ids"]
            unit_actions=(actions if i==0 else [{"type":"clear","target":f"highlight-{i-1}"}])+[highlight]
            target=table["id"];gesture_kind="point"
            if i==len(logical["aggregates"])-1:
                unit_actions.append(result_board)
                # SQL-writing lessons already use the right slot for code.
                # Keep that code visible; the supplied-query path can show its
                # final numeric operation in the same existing equation renderer.
                equation=aggregate_equation(aggregate) if independent and evidence.get("task_kind")!="write_sql" else None
                if equation:
                    target=evidence["id"]+"-numeric-equation";gesture_kind="write"
                    unit_actions.append({"type":"equation","element_id":target,"slot":"right","latex":equation})
            plan["steps"].append(step(f"s{i+1}",f"{function.upper()}({column})",speech,unit_actions,target,gesture_kind))
        if supplementary:
            combined=actions+[result_board]
            selected=(message.get("lesson_context") or {}).get("selected_cell") or {}
            cell=selected.get("cell_id")
            validcells={c for t in tables for row in t["cell_ids"] for c in row}
            if cell in validcells:combined.append({"type":"highlight","target_element_id":table["id"],"cell_ids":[cell],"style":"outline","timing":{"start":0,"end":0}})
            else:
                nulls=[c for row,ids in zip(table["rows"],table["cell_ids"]) for v,c in zip(row,ids) if v is None]
                if nulls:combined.append({"type":"highlight","target_element_id":table["id"],"cell_ids":nulls,"style":"outline","timing":{"start":0,"end":0}})
            prefix="설명용 새 가정입니다. " if evidence["scenario"]=="hypothesis" else "NULL인 칸이 있어도 그 행은 존재합니다. "
            speech=prefix+" ".join(s["speech"] for s in plan["steps"])
            whole=next((a for a in logical["aggregates"] if a["function"]=="count" and a["column"]=="*" and not a["distinct"]),None)
            valued=[a for a in logical["aggregates"] if a["function"]=="count" and a["column"]!="*" and not a["distinct"]]
            if whole and len(valued)==1 and len(logical["aggregates"])==2:
                item=valued[0]
                original_table=next(t for t in message["problem"]["tables"] if t["name"]==table["name"])
                original_column=next(c for c in original_table["columns"] if c["name"].casefold()==item["column"].casefold())
                label=original_column.get("label") or item["column"]
                if len(label)>12:label="해당 열"
                prefix="새 가정입니다. " if evidence["scenario"]=="hypothesis" else "값이 없어도 행은 남습니다. "
                speech=prefix+f"전체 행 {value_text(whole['result'])}개, {label} 값 {value_text(item['result'])}개입니다."
                if counted_zero(item):speech+=" 0도 값이므로 포함합니다."
            plan["steps"]=[step("s1","현재 표로 다시 확인",speech,combined,table["id"])]
    elif logical:
        table=next(t for t in tables if t["id"]==logical["table_id"])
        selected=[table["row_ids"].index(r) for r in logical["filtered_row_ids"]]
        row_speech=(f"각 행이 주어진 조건에 맞는지 먼저 확인합니다. 원본 {len(table['rows'])}행 중 {len(selected)}행이 집계에 남습니다."
                    if logical["where_sql"] else f"행을 거르는 조건이 없으므로 원본 {len(table['rows'])}행을 모두 집계에 사용합니다.")
        row_trace=condition_trace_board(evidence,logical,table) if "row_evaluations" in logical else None
        if row_trace and logical["where_sql"]:row_speech+=" 조건값 표에서 TRUE인 행만 남기고 FALSE와 UNKNOWN은 제외합니다."
        plan["steps"].append(step("s1","원본에서 WHERE 적용",row_speech,actions+([row_trace] if row_trace else [])+
            [{"type":"highlight","target_element_id":table["id"],"row_indices":selected,"style":"background","timing":{"start":0,"end":0}}],table["id"]))
        filtered={"type":"table","element_id":evidence["id"]+"-where","slot":"right","columns":table["columns"],"rows":[table["rows"][i] for i in selected],"caption":"WHERE 이후 남은 원본 행"}
        grouping={"type":"table","element_id":evidence["id"]+"-groups","slot":"bottom","columns":[*logical["group_columns"],"포함 행"],"rows":[[*g["values"],", ".join(str(table["row_ids"].index(r)+1) for r in g["row_ids"])] for g in logical["groups"]],"caption":"GROUP BY 묶음 · 원본 행 번호"}
        def flow(name, source, target):
            return {"type":"arrow","element_id":evidence["id"]+"-logical-flow-"+name,
                    "from_element_id":source,"to_element_id":target}
        column_positions={name.casefold():index+1 for index,name in enumerate(table["columns"])}
        group_columns=[f"원본 {column_positions[name.casefold()]}열" for name in logical["group_columns"]]
        group_speech=((", ".join(group_columns)+"의 값이 같은 행끼리 묶습니다. " if len(group_columns)==1 else
                       ", ".join(group_columns)+"의 값 조합이 같은 행끼리 묶습니다. ")+f"이렇게 만든 그룹은 {len(logical['groups'])}개입니다."
                      if group_columns else "따로 나눌 그룹 열이 없으므로 남은 행 전체를 한 묶음으로 계산합니다.")
        plan["steps"].append(step("s2","그룹으로 묶기",group_speech,([{"type":"clear","target":row_trace["element_id"]}] if row_trace else [])+[filtered,grouping,
            flow("where",table["id"],filtered["element_id"]),flow("group",filtered["element_id"],grouping["element_id"])],grouping["element_id"]))
        intermediate={"type":"table","element_id":evidence["id"]+"-aggregate","slot":"right","columns":logical["before_having"]["columns"],"rows":logical["before_having"]["rows"],"caption":"그룹별 집계 · HAVING 이전"}
        plan["steps"].append(step("s3","집계 계산",logical_aggregate_speech(logical,table),[{"type":"clear","target":filtered["element_id"]},intermediate,
            flow("aggregate",grouping["element_id"],intermediate["element_id"])],intermediate["element_id"]))
        final_speech=(f"각 그룹의 집계값이 주어진 조건에 맞는지 확인하고, 맞는 그룹만 남깁니다. 최종 결과는 {len(result['rows'])}행입니다."
                      if logical["having_sql"] else f"그룹을 거르는 조건이 없어 계산한 결과를 모두 보여 줍니다. 최종 결과는 {len(result['rows'])}행입니다.")
        if logical.get("order_by"):
            before=logical["before_order"]
            before_id=evidence["id"]+"-before-order"
            before_board={**result_board,"element_id":before_id,"rows":before["rows"],"caption":"HAVING 이후 · ORDER BY 전의 결과"}
            plan["steps"].append(step("s4","HAVING과 출력 열",final_speech,[{"type":"clear","target":grouping["element_id"]},before_board,
                flow("having",intermediate["element_id"],before_id)],before_id))
            order_id=evidence["id"]+"-order-rule"
            plan["steps"].append(step("s5","그룹 결과의 정렬",ordering_speech(logical),[
                {"type":"clear","target":before_id},{"type":"clear","target":intermediate["element_id"]},result_board,
                {"type":"text","element_id":order_id,"slot":"right","text":ordering_speech(logical)},
                flow("order",table["id"],result_id)],result_id))
        else:
            plan["steps"].append(step("s4","HAVING과 최종 SELECT",final_speech,[{"type":"clear","target":grouping["element_id"]},result_board,
                flow("having",intermediate["element_id"],result_id)],result_id))
    else:
        execution_scope="설명용 새 가정의 표에 학생이 확정한 원문 SQL을 적용한" if evidence["scenario"]=="hypothesis" else "학생이 확정한 원문 SQL의"
        plan["steps"]=[step("s1","확정 원문 SQL의 실행 결과만",f"{execution_scope} SQLite 실행 결과는 {len(result['rows'])}행입니다. 중간 계산 설명은 지원 범위 밖입니다.",actions+[result_board],result_id)]
    plan["title"]=("새 가정의 계산" if evidence["scenario"]=="hypothesis" else "원본 문제의 계산 근거") if logical else "확정 원문 SQL 실행 결과만"
    plan["final_summary"]=display_answer(evidence)
    from edu_tutor.lessons.requested_explanations import complete_requests, UnmetExplanation
    try:
        fulfillment=complete_requests(plan,message,question,requests)
    except UnmetExplanation as exc:
        return {"plan":None,"status":"verification_stopped","reason":str(exc),"speech_allowed":False,
                "fallback_text":message["content"],"explanation_fulfillment":exc.audit,
                "generation":{"source":"unmet_requested_explanation","model_plan_calls":0,"repair_requests":0}}
    validate_plan(plan)
    return {"plan":plan,"status":"verified_tool_plan" if logical else "verified_execution_only_plan","reason":None,"speech_allowed":True,
            "explanation_fulfillment":fulfillment,
            "generation":{"source":"shared_evidence" if logical else "confirmed_user_query_execution_only","model_plan_calls":0,"repair_requests":0}}


def concept_plan(message, question, lesson_id):
    """Directly reuse the actual short model answer, never re-generate numbers."""
    plan=base_plan(message,question,lesson_id)
    plan.update(title="개념 설명",goal="질문의 핵심 개념을 확인합니다.",provenance="model_generated")
    plan["evidence_ref"]["mode"]="concept_example"
    plan["verification"]={"status":"unverified","scope":"실제 모델의 일반 개념 설명; 계산 또는 설명 전체의 정확성은 검증하지 않음",
        "limitations":["사람 검토가 필요합니다.","나오는 예시는 설명용 새 예시이며 학생 원본 문제의 수치 답이 아닙니다."]}
    text=message["content"].strip()
    from edu_tutor.problems.ddl_examples import build_ddl_example
    example=build_ddl_example(message.get("raw_model_response",text)) if message["problem"]["dialect"]=="sqlite" else {"status":"not_available","reason":"다른 DBMS의 동작을 SQLite 예시로 검증하지 않습니다."}
    if example["status"]=="blocked":
        return {"plan":None,"status":"verification_stopped","fallback_text":text,
            "reason":"설명용 SQL 예시 검증 실패: "+example["reason"],"speech_allowed":False,
            "example_evidence":example,"generation":{"source":"blocked_model_authored_example","model_plan_calls":0}}
    if example["status"]=="verified" and len(example["steps"])<=4:
        from edu_tutor.lessons.reference_support import reference_supported_sentence
        reference=reference_supported_sentence(message.get("raw_model_response",text),message.get("sources",[]),
            question=question,dialect=message["problem"]["dialect"])
        plan.update(title="설명용 새 예시 · 구조와 행 변화",provenance="tool_derived")
        plan["verification"]={"status":"execution_grounded","scope":"실제 모델이 작성한 예시 SQL을 격리 SQLite에서 실행한 전후 표와 변화 설명",
            "limitations":["학생 원본 문제의 답이 아니라 명시된 새 예시입니다.","모델의 자유 설명은 검증하지 않았습니다.","다른 DBMS 동작 및 사람의 교육·청취 검토는 미검증입니다."]}
        if reference:
            source=reference["source"]
            plan["source_refs"]=[{"document_id":source["document_id"],"chunk_id":source["chunk_id"],"label":source["source_title"]}]
            plan["verification"]["scope"]+=f"; 개념 인용은 {reference['status']}: "+reference["scope"]
            plan["verification"]["limitations"].append("참고 자료의 내용도 틀릴 수 있으며, 문장 일치는 사실성이나 교육 정확성 보증이 아닙니다.")
            plan["verification"]["limitations"].append(reference["semantic_error_note"])
            quotation=reference["attributed_text"]
            quotation_id="reference-concept-"+lesson_id
            plan["steps"].append(step("s1","참고 자료의 설명",quotation,[
                {"type":"clear","target":"all"},
                {"type":"text","element_id":quotation_id,"slot":"main","text":quotation,"timing":{"start":0,"end":0}}],
                quotation_id,"explain"))
        operation_classification={"create_table":"표의 구조를 다루는 DDL입니다.",
            "add_column":"표의 구조를 다루는 DDL입니다.", "drop_table":"표의 구조를 다루는 DDL입니다.",
            "insert_rows":"행의 데이터를 다루는 DML입니다.", "update_values":"행의 데이터를 다루는 DML입니다."}
        def example_narration(item):
            return item["narration"]+" "+operation_classification[item["operation"]]
        for number,item in enumerate(example["steps"]):
            actions=[{"type":"clear","target":"all"},{"type":"code","element_id":item["id"]+"-sql","slot":"bottom","language":"sql","code":item["sql"]}]
            narration=example_narration(item)
            before=next((t for t in item["before"] if t["name"].casefold()==item["table_name"].casefold()),None)
            after=next((t for t in item["after"] if t["name"].casefold()==item["table_name"].casefold()),None)
            if before:
                previous=copy.deepcopy(before)
                previous["id"]+="-before"
                previous["row_ids"]=[r+"-before" for r in previous["row_ids"]]
                previous["column_ids"]=[c+"-before" for c in previous["column_ids"]]
                previous["cell_ids"]=[[c+"-before" for c in row] for row in previous["cell_ids"]]
                actions.append(table_action(previous,"left","설명용 새 예시 · 실행 전"))
            else:actions.append({"type":"text","element_id":item["id"]+"-empty-before","slot":"left","text":"실행 전: 이 예시 표가 없습니다."})
            if after:actions.append(table_action(after,"right","설명용 새 예시 · 실행 후"))
            else:actions.append({"type":"text","element_id":item["id"]+"-empty-after","slot":"right","text":"실행 후: 이 예시 표가 없습니다."})
            target=after["id"] if after else item["id"]+"-empty-after"
            if after and item["operation"]=="add_column":
                actions.append({"type":"highlight","target_element_id":after["id"],"column_indices":[len(after["columns"])-1],"style":"background"})
            elif after and item["operation"]=="insert_rows":
                actions.append({"type":"highlight","target_element_id":after["id"],"row_indices":list(range(item["effects"]["rows_before"],item["effects"]["rows_after"])),"style":"background"})
            elif after and item["operation"]=="update_values":
                actions.append({"type":"highlight","target_element_id":after["id"],
                    "cell_ids":[after["cell_ids"][r][c] for r,c in item["effects"]["changed_cells"]],"style":"background"})
            operation_title={"create_table":"표 만들기", "insert_rows":"행 넣기", "add_column":"열 추가하기",
                             "update_values":"기존 값 바꾸기", "drop_table":"표 없애기"}.get(item["operation"],"예시 실행")
            plan["steps"].append(step(f"s{number+1+int(reference is not None)}",operation_title,narration,actions,target))
        plan["final_summary"]=(reference["attributed_text"]+" " if reference else "")+"설명용 새 예시. "+" ".join(example_narration(i) for i in example["steps"])
        validate_plan(plan)
        return {"plan":plan,"status":"verified_example_plan","reason":"일반 모델 설명과 별도로 예시 실행 변화만 검증했습니다.",
            "speech_allowed":True,"fallback_text":text,"example_evidence":example,
            "reference_evidence":reference or {"status":"not_supported","reason":"허용된 문장 일치 또는 질문·모델·자료의 기술어 일치를 확인하지 못했습니다.",
                "raw_model_prose_validation":"not_established"},
            "generation":{"source":"executed_model_authored_example","model_plan_calls":0,
                "operation_classification":"ddl_dml_from_executed_operation_v1",
                "reference_source":reference["generation_source"] if reference else None,
                "raw_model_prose_validation":"not_established"}}
    sentences=[s.strip() for s in re.split(r"(?<=[.!?。])\s+|\n+",text) if s.strip()]
    chunks=[]
    for sentence in sentences:
        if chunks and len(chunks[-1])+len(sentence)<220:chunks[-1]+=" "+sentence
        else:chunks.append(sentence)
    if not chunks or len(chunks)>4 or any(len(c)>1000 for c in chunks):
        return {"plan":None,"status":"text_fallback","fallback_text":text,"reason":"짧은 설명 단위 4개를 초과하여 텍스트로 보존합니다.","speech_allowed":False,"example_evidence":example}
    for i,chunk in enumerate(chunks):
        ident=f"concept-{i}"
        plan["steps"].append(step(f"s{i+1}","핵심 설명" if i==0 else "설명 이어서",chunk,
            [{"type":"clear","target":"all"},{"type":"text","element_id":ident,"slot":"main","text":chunk},
             {"type":"text","element_id":ident+"-notice","slot":"bottom","text":"일반 설명 미검증 · 새 예시는 설명용"}],ident,"explain"))
    plan["final_summary"]=text
    validate_plan(plan)
    return {"plan":plan,"status":"structured_unverified","reason":"일반 개념 설명은 검증 전이므로 음성을 준비하지 않습니다.","speech_allowed":False,"example_evidence":example,
            "generation":{"source":"actual_model_answer_units","model_plan_calls":0}}
