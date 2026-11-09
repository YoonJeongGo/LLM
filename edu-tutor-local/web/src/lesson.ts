import validate from "./validate-lesson.js";
export type Slot = "main" | "left" | "right" | "bottom" | "overlay";
export type Timing = { start: number; end: number };
export type Layout = { x: number; y: number; width: number; height: number };
export type CellSelection = {
  table_element_id: string;
  table_name?: string;
  column_name?: string;
  row_id: string;
  column_id: string;
  cell_id: string;
  row_index: number;
  column_index: number;
  value: string | number | boolean | null;
};
export type BoardElement = {
  type: "text" | "equation" | "table" | "code";
  element_id: string;
  slot: Slot;
  text?: string;
  latex?: string;
  columns?: string[];
  rows?: (string | number | boolean | null)[][];
  caption?: string;
  language?: string;
  code?: string;
  row_ids?: string[];
  column_ids?: string[];
  cell_ids?: string[][];
  table_name?: string;
  layout?: Layout;
  timing?: Timing;
};
export type Highlight = {
  type: "highlight";
  target_element_id: string;
  row_indices?: number[];
  column_indices?: number[];
  style: "outline" | "underline" | "background";
  element_id?: string;
  cell_ids?: string[];
  timing?: Timing;
};
export type Arrow = {
  type: "arrow";
  element_id: string;
  from_element_id: string;
  to_element_id: string;
  timing?: Timing;
};
export type Shape = {
  type: "line" | "arrow" | "rect" | "ellipse" | "circle" | "brace";
  element_id: string;
  slot?: Slot;
  geometry: Record<string, number>;
  orientation?: "left" | "right" | "top" | "bottom";
  stroke?: "chalk" | "accent" | "warning";
  stroke_width?: number;
  timing?: Timing;
  draw_progress?: number;
};
export type Action =
  | BoardElement
  | Highlight
  | Arrow
  | Shape
  | { type: "clear"; target: string; timing?: Timing };
export const isShape = (action: Action): action is Shape =>
  "geometry" in action;
export type LessonStep = {
  id: string;
  title: string;
  speech: string;
  board_actions: Action[];
  gesture: {
    kind: "idle" | "look_board" | "point" | "write" | "explain";
    target_element_id: string | null;
  };
};
export type Lesson = {
  schema_version: "1.0";
  lesson_id: string;
  title: string;
  goal: string;
  question_text: string;
  problem_source: string;
  provenance:
    "demo_fixture" | "model_generated" | "human_authored" | "tool_derived";
  source_refs: { document_id: string; chunk_id: string; label: string }[];
  verification: { status: string; scope: string; limitations: string[] };
  steps: LessonStep[];
  final_summary: string;
  problem_revision?: number;
  source_message_id?: string;
  source_photo_id?: string;
  evidence_ref?: {
    message_id: string;
    problem_revision: number;
    mode: "original" | "hypothesis" | "concept_example";
  };
};
export type Scene = {
  elements: BoardElement[];
  highlights: Highlight[];
  arrows: Arrow[];
  shapes: Shape[];
};
export function parseLesson(value: unknown): Lesson {
  if (!validate(value))
    throw new Error(
      `강의 계획 형식 오류: ${validate.errors
        ?.map((e) => `${e.instancePath} ${e.message}`)
        .slice(0, 3)
        .join(", ")}`,
    );
  const plan = value as Lesson;
  const elements = new Map<string, Action>();
  for (const step of plan.steps) {
    for (const action of step.board_actions) {
      if (action.timing && action.timing.end < action.timing.start)
        throw new Error("판서 종료 시점은 시작 시점보다 빠를 수 없습니다.");
      const bounds =
        "layout" in action
          ? action.layout
          : isShape(action) && "width" in action.geometry
            ? (action.geometry as Layout)
            : undefined;
      if (
        bounds &&
        (bounds.x + bounds.width > 1.000001 ||
          bounds.y + bounds.height > 1.000001)
      )
        throw new Error("판서 좌표가 정규화된 칠판 범위를 벗어났습니다.");
      if (isShape(action) && action.type === "circle") {
        const { cx, cy, radius } = action.geometry;
        if (
          cx - radius < 0 ||
          cx + radius > 1 ||
          cy - radius < 0 ||
          cy + radius > 1
        )
          throw new Error("원의 좌표가 칠판 범위를 벗어났습니다.");
      }
      if (action.type === "clear") {
        if (action.target === "all") elements.clear();
        else elements.delete(action.target);
        continue;
      }
      if (action.type === "highlight") {
        const target = elements.get(action.target_element_id);
        if (!target) throw new Error("알 수 없는 강조 대상입니다.");
        if (target.type === "table") {
          if (
            action.row_indices?.some((index) => index >= target.rows!.length) ||
            action.column_indices?.some(
              (index) => index >= target.columns!.length,
            )
          )
            throw new Error("강조할 셀이 표 범위를 벗어났습니다.");
          if (
            action.cell_ids?.some((id) => !target.cell_ids?.flat().includes(id))
          )
            throw new Error("알 수 없는 강조 셀 ID입니다.");
        }
        continue;
      }
      if (action.type === "arrow" && !isShape(action)) {
        if (
          !elements.has(action.from_element_id) ||
          !elements.has(action.to_element_id)
        )
          throw new Error("알 수 없는 화살표 대상입니다.");
        continue;
      }
      if (action.type === "table") {
        if (action.rows!.some((row) => row.length !== action.columns!.length))
          throw new Error("표의 열과 행 너비가 다릅니다.");
        if (
          (action.row_ids && action.row_ids.length !== action.rows!.length) ||
          (action.column_ids &&
            action.column_ids.length !== action.columns!.length) ||
          (action.cell_ids &&
            (action.cell_ids.length !== action.rows!.length ||
              action.cell_ids.some(
                (row) => row.length !== action.columns!.length,
              ) ||
              new Set(action.cell_ids.flat()).size !==
                action.cell_ids.flat().length))
        )
          throw new Error("표의 안정적 ID가 셀 구조와 다릅니다.");
        if (
          (action.row_ids &&
            new Set(action.row_ids).size !== action.row_ids.length) ||
          (action.column_ids &&
            new Set(action.column_ids).size !== action.column_ids.length)
        )
          throw new Error("행과 열의 ID는 각각 고유해야 합니다.");
      }
      elements.set(action.element_id, action);
    }
    if (
      step.gesture.target_element_id &&
      !elements.has(step.gesture.target_element_id)
    )
      throw new Error("알 수 없는 몸짓 대상입니다.");
  }
  return plan;
}
export const emptyScene = (): Scene => ({
  elements: [],
  highlights: [],
  arrows: [],
  shapes: [],
});
export function applyAction(scene: Scene, action: Action): Scene {
  if (action.type === "clear")
    return action.target === "all"
      ? emptyScene()
      : {
          elements: scene.elements.filter(
            (e) => e.element_id !== action.target,
          ),
          highlights: scene.highlights.filter(
            (e) =>
              e.target_element_id !== action.target &&
              e.element_id !== action.target,
          ),
          arrows: scene.arrows.filter(
            (e) =>
              e.from_element_id !== action.target &&
              e.to_element_id !== action.target &&
              e.element_id !== action.target,
          ),
          shapes: scene.shapes.filter(
            (shape) => shape.element_id !== action.target,
          ),
        };
  if (action.type === "highlight")
    return {
      ...scene,
      highlights: [
        ...scene.highlights.filter(
          (e) => e.target_element_id !== action.target_element_id,
        ),
        action,
      ],
    };
  if (isShape(action))
    return {
      ...scene,
      shapes: [
        ...scene.shapes.filter(
          (shape) => shape.element_id !== action.element_id,
        ),
        action,
      ],
    };
  if (action.type === "arrow")
    return {
      ...scene,
      arrows: [
        ...scene.arrows.filter((e) => e.element_id !== action.element_id),
        action,
      ],
    };
  return {
    ...scene,
    elements: [
      ...scene.elements.filter((e) => e.element_id !== action.element_id),
      action,
    ],
  };
}
export function replayScene(plan: Lesson, step: number, progress = 1): Scene {
  let scene = emptyScene();
  for (let i = 0; i <= Math.min(step, plan.steps.length - 1); i++) {
    const actions = plan.steps[i].board_actions;
    actions.forEach((action, index) => {
      const fraction =
        i === step
          ? actionProgress(action, index, actions.length, progress)
          : 1;
      if (fraction > 0)
        scene = applyAction(
          scene,
          isShape(action) ? { ...action, draw_progress: fraction } : action,
        );
    });
  }
  return scene;
}
export function actionProgress(
  action: Action,
  index: number,
  total: number,
  progress: number,
) {
  const time = Math.max(0, Math.min(1, progress));
  const start = action.timing?.start ?? index / total,
    end = action.timing?.end ?? (index + 1) / total;
  if (start === end) return time >= start ? 1 : 0;
  return Math.max(0, Math.min(1, (time - start) / (end - start)));
}
export type Playback = {
  step: number;
  playing: boolean;
  epoch: number;
  progress: number;
  interrupted: boolean;
};
export type PlaybackEvent =
  | {
      type: "next" | "previous" | "play" | "pause" | "interrupt" | "return";
      total?: number;
    }
  | { type: "seek"; step: number; progress?: number }
  | { type: "restore"; step: number; progress: number }
  | { type: "ended"; epoch: number }
  | { type: "tick"; epoch: number; progress: number };
export const initialPlayback: Playback = {
  step: 0,
  playing: false,
  epoch: 0,
  progress: 1,
  interrupted: false,
};
export function playbackReducer(
  state: Playback,
  event: PlaybackEvent,
): Playback {
  switch (event.type) {
    case "interrupt":
      return {
        ...state,
        playing: false,
        interrupted: true,
        epoch: state.epoch + 1,
      };
    case "return":
      return {
        ...state,
        playing: false,
        interrupted: false,
        epoch: state.epoch + 1,
      };
    case "pause":
      return { ...state, playing: false };
    case "play":
      return { ...state, playing: true };
    case "next":
      return {
        ...state,
        step: Math.min(state.step + 1, (event.total ?? state.step + 2) - 1),
        progress: 1,
        playing: false,
        epoch: state.epoch + 1,
      };
    case "previous":
      return {
        ...state,
        step: Math.max(0, state.step - 1),
        progress: 1,
        playing: false,
        epoch: state.epoch + 1,
      };
    case "seek":
      return {
        ...state,
        step: event.step,
        progress: event.progress ?? 1,
        playing: false,
        epoch: state.epoch + 1,
      };
    case "restore":
      return {
        ...state,
        step: event.step,
        progress: event.progress,
        playing: false,
        epoch: state.epoch + 1,
      };
    case "tick":
      return event.epoch === state.epoch && state.playing
        ? { ...state, progress: Math.min(1, Math.max(0, event.progress)) }
        : state;
    case "ended":
      return event.epoch === state.epoch ? { ...state, playing: false, progress: 1 } : state;
  }
}
export function shouldSubmit(
  event: {
    key: string;
    shiftKey: boolean;
    isComposing?: boolean;
    keyCode?: number;
  },
  composing: boolean,
) {
  return (
    event.key === "Enter" &&
    !event.shiftKey &&
    !event.isComposing &&
    !composing &&
    event.keyCode !== 229
  );
}
