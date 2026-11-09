export type ProblemDraft = {
  enabled: boolean;
  task_kind: "query_result" | "write_sql" | "concept" | "explain_error";
  dialect: "sqlite" | "oracle";
  tables: string;
  query: string;
  confirmed: boolean;
  revision: number;
};
export const emptyProblemDraft: ProblemDraft = {
  enabled: false,
  task_kind: "query_result",
  dialect: "sqlite",
  tables: "[]",
  query: "",
  confirmed: false,
  revision: 1,
};
export function typedProblem(draft: ProblemDraft, raw_text: string) {
  if (!draft.enabled) return undefined;
  if (!draft.confirmed)
    throw new Error("원본 표·SQL을 확인한 뒤 확정 표시를 선택하세요.");
  const tables = validateInputTables(draft.tables);
  return {
    task_kind: draft.task_kind,
    dialect: draft.dialect,
    raw_text,
    source: { kind: "typed" },
    revision: draft.revision,
    confirmed: true,
    tables,
    query: draft.query || undefined,
    missing_conditions: [],
  };
}
export function reviseProblemDraft(value: ProblemDraft, patch: Partial<ProblemDraft>): ProblemDraft {
  return { ...value, ...patch, confirmed: false, revision: value.revision + 1 };
}

export default function ProblemEditor({
  value,
  onChange,
}: {
  value: ProblemDraft;
  onChange: (draft: ProblemDraft) => void;
}) {
  const edit = (patch: Partial<ProblemDraft>) => onChange(reviseProblemDraft(value, patch));
  let grid: InputTable[] = [], gridError = "", validationError = "";
  try { grid = readTableGrid(value.tables); }
  catch (error) { gridError = error instanceof Error ? error.message : String(error); }
  try { validateInputTables(value.tables); }
  catch (error) { validationError = error instanceof Error ? error.message : String(error); }
  const changeTables = (change: (tables: InputTable[]) => void) => {
    const next = structuredClone(grid);
    change(next);
    edit({ tables: JSON.stringify(next) });
  };
  const changeCell = (t: number, r: number, c: number, cell: TableCell) => {
    if (grid[t].rows[r][c] !== cell) changeTables(tables => { tables[t].rows[r][c] = cell; });
  };
  return (
    <details className="problem-editor">
      <summary>
        원본 표·SQL 입력{" "}
        <span>
          {value.enabled ? `사용 중 · revision ${value.revision}` : "선택 사항"}
        </span>
      </summary>
      <label className="inline-check">
        <input
          type="checkbox"
          checked={value.enabled}
          onChange={(event) => edit({ enabled: event.target.checked })}
        />{" "}
        이 질문에 원본 표·SQL을 함께 보냅니다
      </label>
      {value.enabled && (
        <>
          <div className="problem-selects">
            <label>
              문제 종류
              <select
                value={value.task_kind}
                onChange={(event) =>
                  edit({
                    task_kind: event.target.value as ProblemDraft["task_kind"],
                  })
                }
              >
                <option value="query_result">주어진 SQL 결과</option>
                <option value="write_sql">질문에 맞는 SQL 작성</option>
                <option value="concept">개념 설명</option>
                <option value="explain_error">원본 SQL 오류 설명</option>
              </select>
            </label>
            <label>
              DBMS
              <select
                value={value.dialect}
                onChange={(event) =>
                  edit({
                    dialect: event.target.value as ProblemDraft["dialect"],
                  })
                }
              >
                <option value="sqlite">SQLite</option>
                <option value="oracle">Oracle (실행 지원 범위 별도)</option>
              </select>
            </label>
          </div>
          <label>
            원본 SQL
            <textarea
              aria-label="문제의 원본 SQL"
              rows={3}
              value={value.query}
              onChange={(event) => edit({ query: event.target.value })}
              placeholder="문제에 SQL이 주어졌을 때 그대로 입력하세요."
            />
          </label>
          <section className="source-table-editor" aria-label="원본 표 편집">
            <h3>원본 표</h3>
            <p className="fine-print">문제에 나온 표를 입력하세요. NULL은 값이 없는 상태이며, 빈 문자열("")과 다릅니다.</p>
            {gridError ? <p role="alert">{gridError}</p> : <>
              {!grid.length && <p className="fine-print">아직 표가 없습니다. 표를 추가한 뒤 열과 행을 입력하세요.</p>}
              {grid.map((table, t) => <fieldset className="source-table-card" key={t}>
                <legend>표 {t + 1}</legend>
                <div className="source-table-toolbar">
                  <label>표 이름<input aria-label={`표 ${t + 1} 이름`} value={table.name}
                    placeholder="영문 표 이름" onChange={e => changeTables(next => { next[t].name = e.target.value; })} /></label>
                  <button type="button" className="text-button danger" onClick={() => changeTables(next => { next.splice(t, 1); })}>표 {t + 1} 삭제</button>
                </div>
                <div className="source-grid-scroll" role="region" aria-label={`표 ${t + 1} 셀 편집`} tabIndex={0}>
                  <table className="source-grid">
                    <thead><tr><th scope="col">행</th>{table.columns.map((column, c) => <th key={c} scope="col">
                      <label>열 {c + 1} 이름<input aria-label={`표 ${t + 1} 열 ${c + 1} 이름`} value={column.name}
                        placeholder="영문 열 이름" onChange={e => changeTables(next => { next[t].columns[c].name = e.target.value; })} /></label>
                      <label>자료형<select aria-label={`표 ${t + 1} 열 ${c + 1} 자료형`} value={column.type}
                        onChange={e => changeTables(next => { next[t].columns[c].type = e.target.value as typeof column.type; })}>
                        {columnTypes.map(type => <option key={type}>{type}</option>)}</select></label>
                      <button type="button" className="text-button" aria-label={`표 ${t + 1} 열 ${c + 1} 삭제`}
                        onClick={() => changeTables(next => { next[t].columns.splice(c, 1); next[t].rows.forEach(row => row.splice(c, 1)); })}>열 삭제</button>
                    </th>)}<th scope="col">행 편집</th></tr></thead>
                    <tbody>{table.rows.map((row, r) => <tr key={r}><th scope="row">{r + 1}</th>{row.map((cell, c) => <td key={c}>
                      <select aria-label={`표 ${t + 1} ${r + 1}행 ${c + 1}열 상태`} value={cell === null ? "null" : "value"}
                        onChange={e => changeCell(t, r, c, e.target.value === "null" ? null : "")}>
                        <option value="value">값 입력</option><option value="null">NULL · 값 없음</option></select>
                      <input aria-label={`표 ${t + 1} ${r + 1}행 ${c + 1}열 값`} value={cell ?? ""} disabled={cell === null}
                        inputMode={table.columns[c].type === "TEXT" ? "text" : "decimal"}
                        placeholder={cell === null ? "NULL" : table.columns[c].type === "TEXT" ? '빈 문자열 ("")' : "숫자 입력"}
                        onChange={e => changeCell(t, r, c, e.target.value)}
                        onBlur={e => { if (cell !== null) changeCell(t, r, c, commitCell(e.target.value, table.columns[c].type)); }} />
                      <small>{cell === null ? "NULL" : cell === "" ? table.columns[c].type === "TEXT" ? '빈 문자열 ("")' : "미입력 · 숫자 또는 NULL 필요" : ""}</small>
                    </td>)}<td><button type="button" className="text-button" aria-label={`표 ${t + 1} ${r + 1}행 삭제`}
                      onClick={() => changeTables(next => { next[t].rows.splice(r, 1); })}>행 삭제</button></td></tr>)}</tbody>
                  </table>
                </div>
                <div className="button-row">
                  <button type="button" className="button secondary" aria-label={`표 ${t + 1} 열 추가`} disabled={table.columns.length >= 30}
                    onClick={() => changeTables(next => { next[t].columns.push({ name: "", type: "TEXT" }); next[t].rows.forEach(row => row.push("")); })}>열 추가</button>
                  <button type="button" className="button secondary" aria-label={`표 ${t + 1} 행 추가`} disabled={!table.columns.length || table.rows.length >= 500}
                    onClick={() => changeTables(next => { next[t].rows.push(table.columns.map(() => "")); })}>행 추가</button>
                </div>
              </fieldset>)}
              <button type="button" className="button secondary" disabled={grid.length >= 5}
                onClick={() => changeTables(next => { next.push({ name: "", columns: [], rows: [] }); })}>표 추가</button>
            </>}
          </section>
          <details className="source-json-editor"><summary>고급: 원본 표 JSON 편집</summary>
          <label>
            원본 표 (JSON)
            <textarea
              aria-label="문제의 원본 표 JSON"
              rows={5}
              value={value.tables}
              onChange={(event) => edit({ tables: event.target.value })}
              spellCheck={false}
            />
          </label>
          <p className="fine-print">
            형식:
            [&#123;"name":"표이름","columns":[&#123;"name":"열이름","type":"INTEGER"&#125;],"rows":[[1],[null]]&#125;].
            자료형은 INTEGER·REAL·TEXT·NUMERIC입니다. NULL은 따옴표 없는 null로
            입력합니다.
          </p>
          </details>
          {!gridError && validationError && <p className="fine-print" role="status">{validationError}</p>}
          <label className="inline-check">
            <input
              type="checkbox"
              checked={value.confirmed}
              disabled={!!validationError}
              onChange={(event) =>
                onChange({ ...value, confirmed: event.target.checked })
              }
            />{" "}
            원문과 비교해 표·값·SQL을 확인했습니다
          </label>
          <p className="fine-print">
            원문 수정은 새 revision입니다. 일반 개념 질문은 이 입력 없이도 할 수
            있습니다.
          </p>
        </>
      )}
    </details>
  );
}
import { columnTypes, commitCell, readTableGrid, validateInputTables } from "./problemTables";
import type { InputTable, TableCell } from "./problemTables";

