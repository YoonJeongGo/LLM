import { describe, expect, it } from "vitest";
import { commitCell, readTableGrid, validateInputTables } from "./problemTables";
import { emptyProblemDraft, reviseProblemDraft, typedProblem } from "./ProblemEditor";

describe("Student table input, no default problem or answer", () => {
  const table = { name: "source", columns: [{ name: "word", type: "TEXT" }, { name: "amount", type: "REAL" }],
    rows: [["", 0], ["NULL", -2.5], [null, null]] };
  it("starts with no tables and keeps NULL, empty string, literal NULL and numeric zero separate", () => {
    expect(readTableGrid(emptyProblemDraft.tables)).toEqual([]);
    const raw = JSON.stringify([table]);
    expect(validateInputTables(raw)[0].rows).toEqual([["", 0], ["NULL", -2.5], [null, null]]);
    expect(typedProblem({ ...emptyProblemDraft, enabled: true, confirmed: true, tables: raw }, "작성한 원문")?.tables).toEqual([table]);
  });
  it("commits full numbers only and preserves unfinished or invalid numeric drafts", () => {
    for (const raw of ["", "-", "1e", "NULL", "1e9999", "9007199254740993"]) expect(commitCell(raw, "REAL")).toBe(raw);
    expect(commitCell("-0.25", "REAL")).toBe(-0.25);
    expect(commitCell("0", "INTEGER")).toBe(0);
    expect(commitCell("001", "TEXT")).toBe("001");
  });
  it("does not confirm numeric blank or silently replace it with zero/NULL", () => {
    const changed = structuredClone(table); changed.rows[0][1] = "";
    const raw = JSON.stringify([changed]);
    expect(readTableGrid(raw)[0].rows[0][1]).toBe("");
    expect(() => validateInputTables(raw)).toThrow("빈칸은 0이나 NULL");
  });
  it("rejects incomplete schema, duplicate names and malformed rows without changing the JSON draft", () => {
    for (const value of ["[", JSON.stringify([{ name: "", columns: [], rows: [] }]),
      JSON.stringify([{ ...table, columns: [{ name: "a", type: "TEXT" }, { name: "A", type: "TEXT" }] }]),
      JSON.stringify([{ ...table, rows: [[1]] }])]) {
      const original = value;
      expect(() => validateInputTables(value)).toThrow();
      expect(value).toBe(original);
    }
  });
  it("keeps labels and source values; every data edit invalidates confirmation and advances revision", () => {
    const withLabels = { ...table, columns: [{ name: "word", type: "TEXT", label: "원본 이름" }, table.columns[1]] };
    const raw = JSON.stringify([withLabels]);
    const previous = { ...emptyProblemDraft, enabled: true, confirmed: true, revision: 8, tables: raw };
    const next = reviseProblemDraft(previous, { query: "SELECT * FROM source" });
    expect(next).toMatchObject({ confirmed: false, revision: 9, tables: raw });
    expect(previous.confirmed).toBe(true);
    expect(readTableGrid(next.tables)[0].columns[0].label).toBe("원본 이름");
  });
});
