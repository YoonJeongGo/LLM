export type EvaluationItem = {
  id: string;
  question?: string;
  text: string;
  finish_reason?: string;
  output_tokens?: number;
  latency_seconds?: number;
  peak_vram_bytes?: number;
  sql_match?: boolean;
  sql_result?: { status?: string; match?: boolean };
};
export type EvaluationArtifact = {
  run_id: string;
  artifact: string;
  report: {
    status?: string;
    adapter?: string | null;
    dataset_sha256?: string;
    protocol?: Record<string, unknown>;
    items?: EvaluationItem[];
  };
};
export function comparisonItems(
  left?: EvaluationArtifact,
  right?: EvaluationArtifact,
) {
  if (!left || !right || left.run_id === right.run_id) return [];
  const a = left.report,
    b = right.report;
  if (
    !a.dataset_sha256 ||
    a.dataset_sha256 !== b.dataset_sha256 ||
    a.status !== "completed" ||
    b.status !== "completed"
  )
    return [];
  const keys = ["version", "max_new_tokens", "do_sample", "rag"];
  if (
    keys.some(
      (key) =>
        a.protocol?.[key] === undefined ||
        a.protocol?.[key] !== b.protocol?.[key],
    )
  )
    return [];
  return (a.items || []).flatMap((item) => {
    const match = b.items?.find((other) => other.id === item.id);
    return match ? [{ id: item.id, left: item, right: match }] : [];
  });
}
