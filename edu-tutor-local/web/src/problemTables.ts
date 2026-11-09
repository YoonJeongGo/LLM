export const columnTypes = ["TEXT", "INTEGER", "REAL", "NUMERIC"] as const;
export type TableColumn = { name: string; type: (typeof columnTypes)[number]; label?: string };
export type TableCell = string | number | null;
export type InputTable = { name: string; columns: TableColumn[]; rows: TableCell[][] };

// Reading the grid must not normalize or replace an unfinished expert JSON draft.
export function readTableGrid(raw: string): InputTable[] {
  const tables = JSON.parse(raw);
  if (!Array.isArray(tables) || tables.length > 5) throw Error("표는 최대 5개까지 입력할 수 있습니다.");
  for (const table of tables) {
    if (!table || typeof table.name !== "string" || !Array.isArray(table.columns) || table.columns.length > 30
      || !table.columns.every((c: any) => c && typeof c.name === "string" && columnTypes.includes(c.type))
      || !Array.isArray(table.rows) || table.rows.length > 500
      || !table.rows.every((row: unknown) => Array.isArray(row) && row.length === table.columns.length
        && row.every(v => v === null || typeof v === "string" || (typeof v === "number" && Number.isFinite(v)))))
      throw Error("표의 이름·열·행 구조를 고급 JSON 입력에서 확인하세요. 기존 입력은 그대로 보존했습니다.");
  }
  return tables;
}

// Commit only a complete numeric entry on blur. During editing, '-' or '1.'
// remains the exact saved draft string; it never silently becomes zero or NULL.
export function commitCell(value: string, type: TableColumn["type"]): TableCell {
  if (type === "TEXT" || !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value)) return value;
  const number = Number(value);
  if (!Number.isFinite(number) || (Number.isInteger(number) && !Number.isSafeInteger(number))) return value;
  return number;
}

export function validateInputTables(raw: string): InputTable[] {
  const tables = readTableGrid(raw);
  const identifier = /^[A-Za-z_][A-Za-z_0-9]{0,63}$/;
  if (new Set(tables.map(t => t.name.toLowerCase())).size !== tables.length) throw Error("표 이름이 중복되었습니다.");
  for (const [t, table] of tables.entries()) {
    if (!identifier.test(table.name)) throw Error(`표 ${t + 1}의 이름을 영문·숫자·밑줄로 입력하세요. 첫 글자는 영문 또는 밑줄입니다.`);
    if (!table.columns.length) throw Error(`표 ${t + 1}에 열을 추가하세요.`);
    if (new Set(table.columns.map(c => c.name.toLowerCase())).size !== table.columns.length) throw Error(`표 ${t + 1}의 열 이름이 중복되었습니다.`);
    for (const column of table.columns) if (!identifier.test(column.name)) throw Error(`표 ${t + 1}의 열 이름을 영문·숫자·밑줄로 입력하세요.`);
    for (const [r, row] of table.rows.entries()) for (const [c, cell] of row.entries()) {
      if (typeof cell === "string" && cell.length > 1000) throw Error(`표 ${t + 1} ${r + 1}행 ${c + 1}열의 값이 너무 깁니다.`);
      if (cell !== null && table.columns[c].type !== "TEXT" && typeof cell !== "number")
        throw Error(`표 ${t + 1} ${r + 1}행 ${c + 1}열에 숫자를 입력하거나 NULL을 선택하세요. 빈칸은 0이나 NULL로 처리하지 않습니다.`);
    }
  }
  return tables;
}
