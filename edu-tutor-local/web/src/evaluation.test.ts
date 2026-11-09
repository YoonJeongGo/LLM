import { describe, expect, it } from "vitest";
import { comparisonItems } from "./evaluation";
import type { EvaluationArtifact } from "./evaluation";
const report: EvaluationArtifact = {
  run_id: "base",
  artifact: "evaluation.json",
  report: {
    status: "completed",
    dataset_sha256: "same-test-hash",
    protocol: { version: 1, max_new_tokens: 256, do_sample: false, rag: false },
    items: [{ id: "same-question", text: "Actual saved response" }],
  },
};
describe("comparison evidence boundary", () => {
  it("pairs actual matching question IDs under the same frozen conditions", () => {
    expect(
      comparisonItems(report, { ...report, run_id: "adapter" }),
    ).toHaveLength(1);
  });
  it("does not call mismatched data, generation conditions, partial runs or one run a before/after comparison", () => {
    expect(comparisonItems(report, report)).toEqual([]);
    for (const change of [
      { dataset_sha256: "different" },
      { status: "failed" },
      { protocol: { ...report.report.protocol, rag: true } },
      { protocol: undefined },
      { items: [{ id: "another-question", text: "No match" }] },
    ]) {
      expect(
        comparisonItems(report, {
          ...report,
          run_id: "adapter",
          report: { ...report.report, ...change },
        }),
      ).toEqual([]);
    }
  });
});
