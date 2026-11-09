import { describe, expect, it } from "vitest";
import { applyAction, emptyScene } from "./lesson";

describe("Executed group-flow targets", () => {
  it("removes arrows attached to replaced stages and retains unrelated targets", () => {
    let scene = emptyScene();
    for (const element_id of ["source", "where", "groups", "aggregate", "result"])
      scene = applyAction(scene, { type: "table", element_id, slot: "main", columns: ["x"], rows: [[1]] });
    for (const [element_id, from_element_id, to_element_id] of [
      ["filter", "source", "where"], ["group", "where", "groups"],
      ["calculate", "groups", "aggregate"], ["finish", "aggregate", "result"],
    ]) scene = applyAction(scene, { type: "arrow", element_id, from_element_id, to_element_id });
    scene = applyAction(scene, { type: "clear", target: "where" });
    expect(scene.arrows.map(a => a.element_id)).toEqual(["calculate", "finish"]);
    scene = applyAction(scene, { type: "clear", target: "groups" });
    expect(scene.arrows.map(a => a.element_id)).toEqual(["finish"]);
    expect(scene.arrows.every(a => scene.elements.some(e => e.element_id === a.from_element_id)
      && scene.elements.some(e => e.element_id === a.to_element_id))).toBe(true);
  });
});
