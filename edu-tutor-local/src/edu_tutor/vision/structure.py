"""Tentative structures extracted only from actual OCR characters, never images' oracles."""
from __future__ import annotations
import re


def _markdown_table(text):
    """Read one visible grid; inferred affinities remain a confirmation candidate.

    This is deliberately not an OCR correction step: missing cells, multiple
    grids and ambiguous table names are refused instead of being reconstructed.
    """
    lines = text.splitlines()

    def cells(line):
        row=line.strip()
        if row.startswith("|"):
            row=row[1:]
        if row.endswith("|"):
            row=row[:-1]
        return [part.strip() for part in row.split("|")]

    starts = [i for i in range(len(lines) - 1)
              if "|" in lines[i] and "|" in lines[i + 1]
              and all(re.fullmatch(r":?-{3,}:?", part) for part in cells(lines[i + 1]))]
    if not starts:
        return [], [], "no_supported_grid", []
    if len(starts) != 1:
        return [], [], "multiple_grids_require_explicit_table_mapping", []
    start = starts[0]
    names = cells(lines[start])
    if (not names or len(names) != len(cells(lines[start + 1]))
            or any(not re.fullmatch(r"[A-Za-z_]\w*", name, re.ASCII) for name in names)
            or len({name.casefold() for name in names}) != len(names)):
        return [], [], "ambiguous_or_unsupported_column_headers", []
    headings = re.findall(r"^\s*(?:테이블|TABLE)\s*[:：]\s*([A-Za-z_]\w*)\s*$", text, re.I | re.M | re.ASCII)
    sources = re.findall(r"\bFROM\s+([A-Za-z_]\w*)\b", text, re.I | re.ASCII)
    if len(sources) != 1 or re.search(r"\bJOIN\b", text, re.I):
        return [], [], "grid_requires_one_unambiguous_SQL_FROM_table", []
    if headings and (len(headings) != 1 or headings[0].casefold() != sources[0].casefold()):
        return [], [], "visible_table_heading_and_SQL_source_disagree", []
    # A comma-separated FROM list is outside this single-table extraction path.
    if re.search(r"\bFROM\s+[A-Za-z_]\w*(?:\s+(?:AS\s+)?[A-Za-z_]\w*)?\s*,", text, re.I | re.ASCII):
        return [], [], "multiple_SQL_sources_require_explicit_table_mapping", []
    rows = []
    used = []
    for line in lines[start + 2:]:
        if not line.strip():
            break
        if "|" not in line:
            if not re.match(r"\s*(?:```|SELECT\b|WITH\b)", line, re.I):
                return [], used, "ambiguous_grid_boundary_no_partial_table", []
            break
        row = cells(line)
        if len(row) != len(names) or "\\|" in line:
            return [], used, "malformed_grid_row_no_partial_table", []
        if any(not cell or re.search(r"\[[^\]]*\]|\?{2,}", cell) for cell in row):
            return [], used, "missing_or_unreadable_cell_no_value_inferred", []
        rows.append(row)
        used.append(line)
    if not rows or len(rows) > 500:
        return [], used, "grid_empty_or_row_limit_exceeded", []
    columns = []
    parsed_columns = []
    inferences = []
    for index, name in enumerate(names):
        values = [row[index] for row in rows]
        present = [cell for cell in values if cell.upper() != "NULL"]
        integers = bool(present) and all(re.fullmatch(r"[-+]?(?:0|[1-9]\d*)", cell) for cell in present)
        numbers = bool(present) and all(re.fullmatch(r"[-+]?(?:0|[1-9]\d*)(?:\.\d+)?", cell) for cell in present)
        affinity = "INTEGER" if integers else "REAL" if numbers else "TEXT"
        def parse(cell):
            if cell.upper() == "NULL":
                return None
            if affinity == "INTEGER":
                return int(cell)
            if affinity == "REAL":
                return float(cell)
            if len(cell) >= 2 and cell[0] == cell[-1] and cell[0] in "\"'":
                return cell[1:-1].replace(cell[0] * 2, cell[0])
            return cell
        columns.append({"name": name, "type": affinity})
        parsed_columns.append([parse(cell) for cell in values])
        inferences.append({"column": name, "candidate_type": affinity,
                           "basis": "visible_literals" if present else "all_NULL_affinity_unknown",
                           "source_type_visible": False})
    parsed_rows = [list(row) for row in zip(*parsed_columns)]
    return [{"name": sources[0], "columns": columns, "rows": parsed_rows}], used, None, inferences


def structure_candidate(candidate):
    value=dict(candidate)
    text=value.get("original_text",value.get("question",""))
    schemas=[]
    for match in re.finditer(r"\b([A-Za-z_]\w*)\s*\(([^)\n]+)\)",text):
        parts=match.group(2).split(",")
        cols=[]
        for part in parts:
            col=re.fullmatch(r"\s*([A-Za-z_]\w*)\s+(INTEGER|REAL|TEXT|NUMERIC)\s*",part,re.I)
            if not col:break
            cols.append({"name":col.group(1),"type":col.group(2).upper()})
        if len(cols)==len(parts):schemas.append((match,cols))
    extracted=[]; used=[]
    if len(schemas)==1:
        match,columns=schemas[0]
        rows=[]; ambiguous=False
        for line in text[match.end():].splitlines():
            raw=line.strip().strip("|").strip()
            if re.match(r"(?:SELECT|WITH|FROM|WHERE|GROUP|HAVING|ORDER)\b",raw,re.I):break
            if not raw:continue
            if re.fullmatch(r"[|:\s-]+",raw):continue
            raw=raw.strip("()")
            cells=[x.strip() for x in raw.split("|")] if "|" in raw else [x.strip() for x in raw.split(",")] if "," in raw else re.split(r"\s{2,}|\t+",raw)
            if len(cells)!=len(columns) and sum(c["type"]=="TEXT" for c in columns)==1 and len(columns)>1:
                # OCR often collapses column spacing. Only one unquoted TEXT
                # token plus typed numeric cells has an unambiguous boundary.
                tokens=raw.split()
                if len(tokens)==len(columns) and not any(c in raw for c in "'\"(),|[]"):
                    cells=tokens
            if len(cells)!=len(columns):
                if rows:ambiguous=True
                continue
            parsed=[]
            for cell,col in zip(cells,columns):
                if cell.upper()=="NULL":parsed.append(None)
                elif col["type"] in {"INTEGER","REAL","NUMERIC"}:
                    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?",cell):break
                    parsed.append(float(cell) if "." in cell else int(cell))
                else:parsed.append(cell.strip("'\""))
            if len(parsed)==len(columns):rows.append(parsed);used.append(line)
            elif rows:ambiguous=True
        # Do not publish a partial table after silently skipping a broken row.
        if rows and not ambiguous:extracted=[{"name":match.group(1),"columns":columns,"rows":rows[:500]}]
    method="explicit_schema_and_typed_OCR_rows_v2"
    reason=None; inferences=[]
    if not schemas:
        extracted,used,reason,inferences=_markdown_table(text)
        method="single_markdown_grid_with_inferred_affinities_v1"
    sqls=re.findall(r"\b(?:SELECT|WITH)\s+[\s\S]*?;",text,re.I)
    if len(sqls)==1:value["sql"]=sqls[0]
    if extracted:value["tables"]=extracted
    value["structure_extraction"]={"status":"candidate_requires_confirmation" if extracted else "not_extracted",
        "method":method,"source":"actual_original_text",
        "recognized_row_lines":used,"accuracy":"not_established","sql_extracted":len(sqls)==1,
        "reason":reason,"type_inferences":inferences,
        "requires_confirmation":True}
    return value
