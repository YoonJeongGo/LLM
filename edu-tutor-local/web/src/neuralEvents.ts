export type ObservationMode = "off" | "light" | "detail";
export type DisplayMode =
  "LIVE" | "REPLAY" | "STATIC" | "STALE" | "UNAVAILABLE";
export type NeuralEvent = {
  run_id: string;
  request_id: string;
  generation_epoch: number;
  sequence_no: number;
  event_type: string;
  observed_at?: string;
  source?: string;
  module_path?: string | null;
  phase?: string;
  timing_kind?: string;
  payload: Record<string, any>;
  sampling_info?: Record<string, any> | null;
  ui_received_at?: string;
  ui_displayed_at?: string;
};
export type NeuralNode = {
  path: string;
  type: string;
  role: string;
  parameters?: number;
  trainable?: boolean;
  verified_flow?: string[];
  components?: { path: string; type: string }[];
};
export type NeuralStructure = {
  nodes: NeuralNode[];
  edges?: { from: string; to: string; kind: string }[];
  layer_count?: number;
  hidden_size?: number;
  model_id?: string;
  revision?: string;
  adapter?: string | null;
  device?: string;
  dtype?: string;
  source?: string;
  observed_at?: string;
  resident?: boolean;
  graph_kind?: string;
  graph_notice?: string;
  wrapper_type?: string;
  base_path?: string;
  base_type?: string;
  parameter_count_notice?: string;
  parameter_counts?: Record<string, number>;
  forward_evidence?: Record<string, any>;
};
export type NeuralRun = {
  run_id: string;
  job_id: string;
  request_id: string;
  generation_epoch: number;
  model_id?: string;
  revision?: string;
  adapter_id?: string;
  state: string;
  mode?: DisplayMode;
  observation_mode?: ObservationMode;
  observer_enabled?: boolean;
  sequence_no?: number;
  dropped_events?: number;
  worker_dropped_events?: number;
  aggregated_events?: number;
  resident?: boolean;
  selected_layers?: string[];
  sample_every_steps?: number;
  update_interval_ms?: number;
  output_text?: string;
  metadata?: Record<string, any>;
  structure?: NeuralStructure;
  created_at?: string;
  updated_at?: string;
};
export const activeNeuralRun = (run?: NeuralRun | null) =>
  !!run &&
  [
    "queued",
    "loading",
    "running",
    "cancel_requested",
    "cancelling",
    "saving",
  ].includes(run.state);
export function belongsToRun(event: NeuralEvent, run: NeuralRun | null) {
  return (
    !!run &&
    event.run_id === run.run_id &&
    event.request_id === run.request_id &&
    event.generation_epoch === run.generation_epoch
  );
}
export function eventCursor(
  event: NeuralEvent,
  previous: number,
  run: NeuralRun | null,
) {
  if (
    !belongsToRun(event, run) ||
    event.event_type === "snapshot" ||
    event.event_type === "heartbeat"
  )
    return { accepted: false, sequence: previous, gaps: 0 };
  if (!Number.isSafeInteger(event.sequence_no) || event.sequence_no <= previous)
    return { accepted: false, sequence: previous, gaps: 0 };
  return {
    accepted: true,
    sequence: event.sequence_no,
    gaps: Math.max(0, event.sequence_no - previous - 1),
  };
}
export function displayMode({
  replay,
  run,
  connected,
  structure,
  recent,
  paused,
}: {
  replay: boolean;
  run: NeuralRun | null;
  connected: boolean;
  structure: NeuralStructure | null;
  recent: boolean;
  paused?: boolean;
}): DisplayMode {
  if (replay) return "REPLAY";
  if (activeNeuralRun(run))
    return connected &&
      run?.observer_enabled !== false &&
      run?.observation_mode !== "off" &&
      recent &&
      !paused
      ? "LIVE"
      : "STALE";
  return structure?.nodes?.length ? "STATIC" : "UNAVAILABLE";
}
export function boundedEvents(
  rows: NeuralEvent[],
  more: NeuralEvent[],
  limit = 600,
) {
  return [...rows, ...more].slice(-limit);
}
export function sampleTone(value: number, extent = 4): string {
  // Fixed, symmetric range for every layer and run; clipping is only visual.
  const amount = Math.min(Math.abs(value) / extent, 1);
  return value < 0
    ? `rgba(79, 108, 185, ${0.08 + amount * 0.65})`
    : `rgba(173, 105, 43, ${0.08 + amount * 0.65})`;
}
export const neuralEventLabel = (kind: string) =>
  ({
    input_tokens: "입력 토큰",
    forward: "모델 호출",
    block_call: "층 호출",
    activation_sample: "활성값 표본",
    token: "토큰 생성",
    structure: "실제 구조 확인",
    observer_state: "관측 상태",
    observer_error: "관측 오류",
    summary: "계측 종료",
    state: "작업 상태",
    run_state: "작업 상태",
    completed: "완료",
    cancelled: "취소",
    error: "오류",
    metadata: "실행 지표",
    gap: "버퍼 누락 안내",
    output: "생성 결과",
    delta: "문자열 갱신",
  })[kind] ?? kind;
