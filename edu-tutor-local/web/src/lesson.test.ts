import { describe, it, expect } from "vitest";
import raw from "./lesson.fixture.json";
import {
  applyAction,
  emptyScene,
  initialPlayback,
  parseLesson,
  playbackReducer,
  replayScene,
  shouldSubmit,
} from "./lesson";
import { activeJob } from "./api";
import { aimAvatarArm } from "./avatar";
describe("T0 lesson schema and pure scene replay", () => {
  const lesson = parseLesson(raw);
  it("accepts the contract fixture while retaining its demo provenance", () => {
    expect(lesson.provenance).toBe("demo_fixture");
    expect(lesson.steps).toHaveLength(5);
  });
  it("rejects executable or unknown commands and excessive steps", () => {
    const invalid = structuredClone(raw);
    invalid.steps[0].board_actions = [
      {
        type: "script",
        element_id: "x",
        slot: "main",
        javascript: "alert(1)",
      } as any,
    ];
    expect(() => parseLesson(invalid)).toThrow();
    expect(() =>
      parseLesson({ ...raw, steps: Array(13).fill(raw.steps[0]) }),
    ).toThrow();
  });
  it("reconstructs the same board for previous, replay and JSON snapshot restoration", () => {
    const first = replayScene(lesson, 2);
    const again = replayScene(
      parseLesson(JSON.parse(JSON.stringify(lesson))),
      2,
    );
    expect(again).toEqual(first);
    expect(first.highlights[0].row_indices).toEqual([0, 1, 4]);
    expect(replayScene(lesson, 1).elements.map((e) => e.element_id)).toEqual([
      "original",
      "query",
    ]);
    expect(replayScene(lesson, 4).elements.map((e) => e.element_id)).toEqual([
      "result",
    ]);
    expect(replayScene(lesson, 4).elements[0].rows).toEqual([
      ["개발", 3, 2, 1500, 750],
      ["운영", 3, 2, 1200, 600],
    ]);
  });
  it("applies progressive actions without mutating previous state and clears target references", () => {
    const empty = emptyScene();
    const added = applyAction(empty, {
      type: "text",
      element_id: "a",
      slot: "main",
      text: "본문",
    });
    expect(empty.elements).toHaveLength(0);
    const highlighted = applyAction(added, {
      type: "highlight",
      target_element_id: "a",
      style: "outline",
    });
    expect(applyAction(highlighted, { type: "clear", target: "a" })).toEqual(
      empty,
    );
    expect(replayScene(lesson, 2, 0).elements.map((e) => e.element_id)).toEqual(
      ["original", "query"],
    );
    expect(replayScene(lesson, 2, 0.5).highlights).toHaveLength(1);
    expect(
      replayScene(lesson, 2, 1).elements.some(
        (e) => e.element_id === "dev_avg",
      ),
    ).toBe(true);
  });
});
describe("T0 playback cancellation and input safety", () => {
  it("aims the actual shoulder-hand vector at the board target after resize", () => {
    for (const scale of [1, 0.6, 1.5]) {
      const figure = {
        left: 700,
        top: 150,
        width: 160 * scale,
        height: 220 * scale,
      };
      const target = { x: 300, y: 80 };
      const pose = aimAvatarArm(target, figure);
      const shoulder = {
        x: figure.left + 60 * scale,
        y: figure.top + 117 * scale,
      };
      const handAngle = Math.atan2(
        pose.handY - shoulder.y,
        pose.handX - shoulder.x,
      );
      const targetAngle = Math.atan2(
        target.y - shoulder.y,
        target.x - shoulder.x,
      );
      expect(Math.abs(handAngle - targetAngle)).toBeLessThan(1e-9);
    }
  });
  it("keeps polling during saving and separates requested cancel from stopped", () => {
    expect(activeJob({ id: "job", state: "saving" })).toBe(true);
    expect(
      activeJob({ id: "job", state: "running", cancel_requested: true }),
    ).toBe(true);
    expect(
      activeJob({ id: "job", state: "cancelled", cancel_requested: true }),
    ).toBe(false);
  });
  it("drops stale audio events after interruption while preserving scene position", () => {
    const playing = {
      ...initialPlayback,
      step: 2,
      playing: true,
      progress: 0.4,
    };
    const interrupted = playbackReducer(playing, { type: "interrupt" });
    expect(interrupted.step).toBe(2);
    expect(interrupted.progress).toBe(0.4);
    expect(interrupted.playing).toBe(false);
    expect(
      playbackReducer(interrupted, { type: "tick", epoch: 0, progress: 1 }),
    ).toEqual(interrupted);
    const returned = playbackReducer(interrupted, { type: "return" });
    expect(returned.step).toBe(2);
    expect(returned.interrupted).toBe(false);
    expect(returned.epoch).toBe(2);
  });
  it("clamps next and previous navigation and pauses audio on seek", () => {
    expect(playbackReducer(initialPlayback, { type: "previous" }).step).toBe(0);
    expect(
      playbackReducer(
        { ...initialPlayback, step: 4, playing: true },
        { type: "next", total: 5 },
      ),
    ).toMatchObject({ step: 4, playing: false });
    expect(
      playbackReducer(
        { ...initialPlayback, playing: true },
        { type: "seek", step: 2 },
      ),
    ).toMatchObject({ step: 2, playing: false, epoch: 1 });
  });
  it("restores partial board progress without resuming old audio", () => {
    expect(
      playbackReducer(
        { ...initialPlayback, playing: true },
        { type: "restore", step: 2, progress: 0.4 },
      ),
    ).toMatchObject({ step: 2, progress: 0.4, playing: false, epoch: 1 });
  });
  it("never submits a composing Korean Enter, IME229 or Shift+Enter", () => {
    expect(shouldSubmit({ key: "Enter", shiftKey: false }, false)).toBe(true);
    expect(shouldSubmit({ key: "Enter", shiftKey: true }, false)).toBe(false);
    expect(
      shouldSubmit({ key: "Enter", shiftKey: false, isComposing: true }, false),
    ).toBe(false);
    expect(
      shouldSubmit({ key: "Enter", shiftKey: false, keyCode: 229 }, false),
    ).toBe(false);
    expect(shouldSubmit({ key: "Enter", shiftKey: false }, true)).toBe(false);
  });
});
