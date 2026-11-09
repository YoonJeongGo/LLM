import { describe, it, expect } from "vitest";
import raw from "./lesson.fixture.json";
import {
  parseLesson,
  replayScene,
  playbackReducer,
  initialPlayback,
} from "./lesson";
import type { Shape } from "./lesson";
import { shapePoints, partialPolyline } from "./boardGeometry";
import { typedProblem, emptyProblemDraft } from "./ProblemEditor";

const shapes: Shape[] = [
  {
    type: "line",
    element_id: "line",
    geometry: { x1: 0.1, y1: 0.1, x2: 0.9, y2: 0.7 },
  },
  {
    type: "arrow",
    element_id: "arrow",
    geometry: { x1: 0.1, y1: 0.2, x2: 0.8, y2: 0.8 },
  },
  {
    type: "rect",
    element_id: "rect",
    geometry: { x: 0.2, y: 0.1, width: 0.5, height: 0.4 },
  },
  {
    type: "ellipse",
    element_id: "ellipse",
    geometry: { x: 0.1, y: 0.2, width: 0.6, height: 0.3 },
  },
  {
    type: "circle",
    element_id: "circle",
    geometry: { cx: 0.5, cy: 0.5, radius: 0.3 },
  },
  {
    type: "brace",
    element_id: "brace",
    geometry: { x: 0.1, y: 0.1, width: 0.1, height: 0.7 },
    orientation: "left",
  },
];
function plan() {
  return {
    ...structuredClone(raw),
    steps: [
      {
        id: "unit",
        title: "도형",
        speech: "숫자 좌표 도형",
        gesture: { kind: "write", target_element_id: "line" },
        board_actions: structuredClone(shapes),
      },
    ],
  };
}
describe("v0.2 bounded board and interruption state", () => {
  it("admits all safe shapes while rejecting path strings and outside coordinates", () => {
    expect(parseLesson(plan()).steps[0].board_actions).toHaveLength(6);
    const unsafe = plan();
    (unsafe.steps[0].board_actions[0] as any).svg = "<script/>";
    expect(() => parseLesson(unsafe)).toThrow();
    const outside = plan();
    outside.steps[0].board_actions[4].geometry.cx = 0.99;
    expect(() => parseLesson(outside)).toThrow();
  });
  it("pen tip is the very same partial path endpoint through resize and zoom", () => {
    for (const size of [
      [800, 450],
      [320, 600],
      [1600, 900],
    ])
      for (const shape of shapes) {
        const result = partialPolyline(
          shapePoints(shape, size[0], size[1]),
          0.37,
          size[0],
          size[1],
        );
        expect(result.tip).toEqual(result.points.at(-1));
        expect(
          result.points.every(
            (p) =>
              Number.isFinite(p.x) &&
              Number.isFinite(p.y) &&
              p.x >= 0 &&
              p.y >= 0 &&
              p.x <= size[0] &&
              p.y <= size[1],
          ),
        ).toBe(true);
      }
  });
  it("replays numeric path timing from the audio unit fraction", () => {
    const value = plan();
    value.steps[0].board_actions = [
      { ...shapes[0], timing: { start: 0.2, end: 0.8 } },
    ];
    const parsed = parseLesson(value);
    expect(replayScene(parsed, 0, 0.1).shapes).toHaveLength(0);
    expect(replayScene(parsed, 0, 0.5).shapes[0].draw_progress).toBeCloseTo(
      0.5,
    );
    expect(replayScene(parsed, 0, 0.9).shapes[0].draw_progress).toBe(1);
  });
  it("late completed audio cannot pause a replacement lesson", () => {
    const current = { ...initialPlayback, playing: true, epoch: 5 };
    expect(playbackReducer(current, { type: "ended", epoch: 4 })).toEqual(
      current,
    );
    expect(playbackReducer(current, { type: "ended", epoch: 5 }).playing).toBe(
      false,
    );
  });
  it("duplicate stable row IDs and unknown selected-highlight IDs are rejected", () => {
    const value = structuredClone(raw),
      table: any = value.steps[0].board_actions.find((a) => a.type === "table");
    table.row_ids = table.rows.map(() => "duplicate");
    expect(() => parseLesson(value)).toThrow();
  });
  it("typed input needs confirmation and keeps the raw problem and revision", () => {
    expect(() =>
      typedProblem({ ...emptyProblemDraft, enabled: true }, "주어진 문제"),
    ).toThrow();
    const tables = [
      {
        name: "measurements",
        columns: [{ name: "v", type: "INTEGER" }],
        rows: [[7], [null], [13]],
      },
    ];
    const value = typedProblem(
      {
        ...emptyProblemDraft,
        enabled: true,
        confirmed: true,
        revision: 8,
        tables: JSON.stringify(tables),
        query: "SELECT AVG(v) FROM measurements;",
      },
      "이 SQL 결과는?",
    );
    expect(value).toMatchObject({
      revision: 8,
      raw_text: "이 SQL 결과는?",
      tables,
      confirmed: true,
    });
    expect(value).not.toHaveProperty("expected_rows");
  });
});
