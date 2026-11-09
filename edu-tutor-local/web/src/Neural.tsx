import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BrainCircuit,
  Expand,
  Minus,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Save,
  Square,
} from "lucide-react";
import { api, errorText, post, statusLabel, streamEvents } from "./api";
import Metrics from "./Metrics";
import {
  activeNeuralRun,
  belongsToRun,
  boundedEvents,
  displayMode,
  eventCursor,
  neuralEventLabel,
  sampleTone,
} from "./neuralEvents";
import type {
  NeuralEvent,
  NeuralNode,
  NeuralRun,
  NeuralStructure,
  ObservationMode,
} from "./neuralEvents";
import "./neural.css";

type View = {
  events: NeuralEvent[];
  latest: Record<string, NeuralEvent>;
  samples: Record<string, NeuralEvent>;
  tokenEvents: NeuralEvent[];
  input?: NeuralEvent;
  text: string;
  outputCount?: number;
  received: number;
  latestReceived?: string;
  latestDisplayed?: string;
  latestObserved?: string;
};
const emptyView = (): View => ({
  events: [],
  latest: {},
  samples: {},
  tokenEvents: [],
  text: "",
  received: 0,
});
const glossary = [
  ["토큰", "모델이 글을 처리하는 작은 단위입니다. 글자 수와 다릅니다."],
  ["층/블록", "숫자를 변환하는 계산 단계입니다."],
  ["활성값", "해당 입력을 계산하면서 나온 중간 숫자입니다."],
  ["가중치", "학습으로 조정되는 모델 내부 숫자입니다."],
  ["추론", "현재 가중치를 사용해 답변을 생성합니다."],
  ["학습", "손실에 따라 학습 가능한 가중치를 갱신합니다."],
];
function fmt(value: unknown, suffix = "") {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toLocaleString("ko-KR", { maximumFractionDigits: 3 })}${suffix}`
    : "미측정";
}
function date(value?: string) {
  return value
    ? new Date(value).toLocaleString("ko-KR", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
        fractionalSecondDigits: 3,
      })
    : "미측정";
}
function shape(value: any) {
  return Array.isArray(value?.shape)
    ? `[${value.shape.join(" × ")}]`
    : "미측정";
}
function safeStructure(value: any): NeuralStructure | null {
  return value &&
    Array.isArray(value.nodes) &&
    value.nodes.every((n: any) => typeof n.path === "string")
    ? value
    : null;
}
function nodeLabel(node: NeuralNode, blocks: NeuralNode[]) {
  return node.role === "block"
    ? `블록 ${blocks.findIndex((n) => n.path === node.path)}`
    : ({
        embedding: "임베딩",
        normalization: "출력 정규화",
        output_scores: "출력 점수",
      }[node.role] ?? node.type);
}
function Graph({
  structure,
  selected,
  choose,
  recent,
  live,
  replaying,
  reduceMotion,
}: {
  structure: NeuralStructure;
  selected: string;
  choose: (path: string) => void;
  recent: Set<string>;
  live: boolean;
  replaying: boolean;
  reduceMotion: boolean;
}) {
  const [zoom, setZoom] = useState(0.85);
  const viewport = useRef<HTMLDivElement>(null);
  const drag = useRef<{
    x: number;
    y: number;
    left: number;
    top: number;
  } | null>(null);
  const blocks = structure.nodes.filter((n) => n.role === "block");
  const nodes: NeuralNode[] = [
    { path: "__input__", role: "input", type: "입력 텍스트 / 토큰" },
    ...structure.nodes,
    { path: "__selection__", role: "selection", type: "생성 루프 · 토큰 선택" },
    { path: "__result__", role: "result", type: "누적 디코딩 · 결과" },
  ];
  const width = 1000,
    height = Math.ceil(nodes.length / 4) * 112 + 30;
  function position(index: number) {
    const row = Math.floor(index / 4),
      column = row % 2 ? 3 - (index % 4) : index % 4;
    return { x: 24 + column * 244, y: 20 + row * 112 };
  }
  const fit = useCallback(() => {
    if (viewport.current) {
      setZoom(
        Math.max(
          0.25,
          Math.min(1, (viewport.current.clientWidth - 12) / width),
        ),
      );
      viewport.current.scrollTo({ left: 0, top: 0 });
    }
  }, []);
  useEffect(() => {
    if ((viewport.current?.clientWidth ?? 0) < 600) setZoom(0.85);
    else fit();
  }, [fit, structure.nodes.length]);
  return (
    <section className="card neural-graph-card">
      <div className="card-heading">
        <div>
          <h2>블록 수준 구조 요약</h2>
          <p className="fine-print">
            실제 모듈 {structure.nodes.length}개 · Transformer 블록{" "}
            {blocks.length}개 · config {structure.layer_count ?? "확인 불가"}개
          </p>
        </div>
        <div className="neural-tools">
          <button
            className="button secondary"
            onClick={() => setZoom((z) => Math.max(0.25, z - 0.15))}
            aria-label="구조도 축소"
          >
            <Minus size={16} />
          </button>
          <span>{Math.round(zoom * 100)}%</span>
          <button
            className="button secondary"
            onClick={() => setZoom((z) => Math.min(2, z + 0.15))}
            aria-label="구조도 확대"
          >
            <Plus size={16} />
          </button>
          <button className="button secondary" onClick={fit}>
            <Expand size={16} />
            화면 맞춤
          </button>
        </div>
      </div>
      <p className="neural-hint">
        {replaying
          ? "REPLAY · 기록 시각에 따라 저장된 호출 구간을 강조합니다."
          : live
            ? "최근 수신한 실제 호출 구간을 강조합니다."
            : "정적 구조입니다. 진행 중인 GPU 연산을 나타내지 않습니다."}{" "}
        빈 공간을 끌거나 스크롤해 이동하고 층을 선택하세요.
      </p>
      <div
        className={`neural-viewport ${reduceMotion ? "reduce-motion" : ""}`}
        ref={viewport}
        data-testid="neural-graph"
        tabIndex={0}
        aria-label="실제 모델 블록 구조도, 화살표 키 또는 스크롤로 이동"
        onPointerDown={(event) => {
          if (
            (event.target as Element).closest("button") ||
            event.button !== 0 ||
            !viewport.current
          )
            return;
          drag.current = {
            x: event.clientX,
            y: event.clientY,
            left: viewport.current.scrollLeft,
            top: viewport.current.scrollTop,
          };
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          if (!drag.current || !viewport.current) return;
          viewport.current.scrollLeft =
            drag.current.left - event.clientX + drag.current.x;
          viewport.current.scrollTop =
            drag.current.top - event.clientY + drag.current.y;
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
      >
        <div style={{ width: width * zoom, height: height * zoom }}>
          <div
            className="neural-canvas"
            style={{ width, height, transform: `scale(${zoom})` }}
          >
            <svg
              width={width}
              height={height}
              className="neural-edges"
              aria-hidden="true"
            >
              <defs>
                <marker
                  id="neural-arrow"
                  viewBox="0 0 8 8"
                  refX="7"
                  refY="4"
                  markerWidth="6"
                  markerHeight="6"
                  orient="auto"
                >
                  <path d="M0,0 L8,4 L0,8" fill="currentColor" />
                </marker>
              </defs>
              {nodes.slice(0, -1).map((node, index) => {
                const from = position(index),
                  to = position(index + 1),
                  sameRow = from.y === to.y;
                const d = sameRow
                  ? `M${from.x + (to.x > from.x ? 216 : 0)},${from.y + 38} L${to.x + (to.x > from.x ? 0 : 216)},${to.y + 38}`
                  : `M${from.x + 108},${from.y + 76} L${to.x + 108},${to.y}`;
                const verified = structure.edges?.some(
                  (e) => e.from === node.path && e.to === nodes[index + 1].path,
                );
                return (
                  <path
                    key={node.path}
                    d={d}
                    fill="none"
                    stroke={
                      (live || replaying) &&
                      recent.has(node.path) &&
                      recent.has(nodes[index + 1].path) &&
                      verified
                        ? "#477b5e"
                        : "#a8b7ac"
                    }
                    strokeWidth="2"
                    strokeDasharray={verified ? undefined : "4 3"}
                    markerEnd="url(#neural-arrow)"
                  />
                );
              })}
            </svg>
            {nodes.map((node, index) => {
              const point = position(index),
                conceptual = node.path.startsWith("__");
              const content = (
                <>
                  <strong>{nodeLabel(node, blocks)}</strong>
                  <small>
                    {conceptual ? "생성 입출력 연결 · 설명 표시" : node.path}
                  </small>
                </>
              );
              return conceptual ? (
                <div
                  key={node.path}
                  className="neural-node conceptual"
                  style={{ left: point.x, top: point.y }}
                >
                  {content}
                </div>
              ) : (
                <button
                  key={node.path}
                  className={`neural-node ${selected === node.path ? "selected" : ""} ${(live || replaying) && recent.has(node.path) ? "observed" : ""}`}
                  style={{ left: point.x, top: point.y }}
                  onClick={() => choose(node.path)}
                  aria-pressed={selected === node.path}
                  aria-label={`${nodeLabel(node, blocks)} · ${node.path} 선택`}
                  title={`${node.type} · 실제 경로 ${node.path}. 층은 숫자를 변환하는 계산 단계입니다.`}
                >
                  {content}
                </button>
              );
            })}
          </div>
        </div>
      </div>
      <p className="fine-print">
        실선: 설치된 forward로 확인한 블록 경로 · 점선: 입력·생성 결과의 설명용
        연결. 점과 선은 개별 뉴런이나 전체 가중치가 아닙니다.{" "}
        {structure.graph_notice}
      </p>
    </section>
  );
}
function LayerDetail({
  node,
  call,
  sample,
  selectedForSampling,
  toggleSampling,
  disabled,
}: {
  node?: NeuralNode;
  call?: NeuralEvent;
  sample?: NeuralEvent;
  selectedForSampling: boolean;
  toggleSampling: () => void;
  disabled: boolean;
}) {
  if (!node)
    return (
      <section className="card" data-testid="neural-layer-detail">
        <h2>층 상세</h2>
        <p className="fine-print">
          실제 모델 구조가 확인되면 층을 선택할 수 있습니다.
        </p>
      </section>
    );
  const p = call?.payload,
    info = sample?.sampling_info;
  return (
    <section className="card neural-detail" data-testid="neural-layer-detail">
      <div className="card-heading">
        <h2>선택한 층</h2>
        <span className="badge muted-badge">
          {call ? "실제 호출 기록" : "구조 정보"}
        </span>
      </div>
      <code className="neural-path">{node.path}</code>
      <p>{node.type}</p>
      <dl className="neural-facts">
        <div>
          <dt>입력 shape</dt>
          <dd>{shape(p?.input)}</dd>
        </div>
        <div>
          <dt>출력 shape</dt>
          <dd>{shape(p?.output)}</dd>
        </div>
        <div>
          <dt>dtype / 장치</dt>
          <dd>
            {p?.output?.dtype ?? "미측정"} / {p?.output?.device ?? "미측정"}
          </dd>
        </div>
        <div>
          <dt>호출 횟수 / 생성 step</dt>
          <dd>
            {fmt(p?.call_count)} / {fmt(p?.step)}
          </dd>
        </div>
        <div>
          <dt>호스트 호출 구간</dt>
          <dd>{fmt(p?.host_elapsed_ms, " ms")}</dd>
        </div>
        <div>
          <dt>GPU 완료 시간</dt>
          <dd>{fmt(p?.gpu_elapsed_ms, " ms")}</dd>
        </div>
      </dl>
      <p className="fine-print">
        Python 훅의 호스트 관측 시각입니다. GPU는 비동기로 실행하므로 호출
        반환과 GPU 완료 시각은 다릅니다.
      </p>
      {node.verified_flow && (
        <details>
          <summary>확인된 블록 내부 경로</summary>
          <ol className="neural-flow">
            {node.verified_flow.map((name, i) => (
              <li key={i}>
                {{
                  input_layernorm: "입력 정규화",
                  self_attn: "Attention · 문맥 계산",
                  residual_add: "잔차 더하기",
                  post_attention_layernorm: "다음 정규화",
                  mlp: "MLP · 숫자 변환",
                }[name] ?? name}
              </li>
            ))}
          </ol>
          <p className="fine-print">
            설치된 forward 소스로 확인한 설명입니다. 내부 연산별 소요
            시간·활성값은 미측정입니다.
          </p>
          {node.components?.map((component) => (
            <p key={component.path}>
              <code>{component.path}</code> · {component.type}
            </p>
          ))}
        </details>
      )}
      {node.role === "block" && (
        <label className="neural-check">
          <input
            type="checkbox"
            checked={selectedForSampling}
            disabled={disabled}
            onChange={toggleSampling}
          />
          상세 표본 대상에 포함 (최대 2개 층)
        </label>
      )}
      <h3>활성값 · 작은 실제 표본</h3>
      {sample && Array.isArray(sample.payload.values) ? (
        <>
          <p className="fine-print">
            마지막 유효 토큰의 앞쪽 성분 · batch {info?.batch_index ?? "미측정"}
            , 토큰 index {info?.token_index ?? "미측정"}, 전체 시퀀스 index{" "}
            {info?.sequence_token_index ?? "미측정"} · 생성 step{" "}
            {sample.payload.step}
          </p>
          <p className="fine-print">
            방법: {info?.method ?? "미측정"} · {info?.every_steps ?? "미측정"}{" "}
            step 간격 · {sample.observed_at}
          </p>
          <div
            className="neural-samples"
            aria-label="활성값 표본, 색 범위 모든 층 공통 -4부터 +4"
          >
            {sample.payload.values
              .slice(0, 32)
              .map((value: number, i: number) => (
                <div
                  key={i}
                  style={{ background: sampleTone(value) }}
                  title={`성분 ${info?.component_indices?.[i] ?? i}: ${value}`}
                >
                  <small>{info?.component_indices?.[i] ?? i}</small>
                  <strong>{fmt(value)}</strong>
                </div>
              ))}
          </div>
          <p className="fine-print">
            공통 색 범위 −4(파랑) ~ 0 ~ +4(갈색), 범위 밖은 색만 포화됩니다.
            숫자는 실제 값입니다. 표본 평균 {fmt(sample.payload.sample_mean)} ·
            CPU 전송·통계{" "}
            {fmt(sample.payload.sample_cpu_transfer_and_stats_ms, " ms")}. 전체
            층의 평균·단어의 뜻·확신을 나타내지 않습니다.
          </p>
        </>
      ) : (
        <p className="neural-empty">
          미측정 · 상세 계측을 켜고 해당 층을 선택한 실행에서만 보입니다. 기록에
          없는 값은 만들지 않습니다.
        </p>
      )}
    </section>
  );
}

export default function Neural({ authenticated }: { authenticated: boolean }) {
  const [server, setServer] = useState<any>(null),
    [run, setRun] = useState<NeuralRun | null>(null);
  const runRef = useRef<NeuralRun | null>(null),
    epoch = useRef(0),
    serverInstance = useRef<string | undefined>(undefined);
  const [structure, setStructure] = useState<NeuralStructure | null>(null),
    [view, setView] = useState<View>(emptyView);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [text, setText] = useState("");
  const [busy, setBusy] = useState(false),
    [connected, setConnected] = useState(false),
    [paused, setPaused] = useState(false);
  const [observationMode, setObservationMode] =
      useState<ObservationMode>("light"),
    [selected, setSelected] = useState("");
  const [selectedLayers, setSelectedLayers] = useState<string[]>([]),
    [sampleEvery, setSampleEvery] = useState(16),
    [intervalMs, setIntervalMs] = useState(250);
  const [maxTokens, setMaxTokens] = useState(128),
    [adapter, setAdapter] = useState("base"),
    [adapters, setAdapters] = useState<any[]>([]);
  const [panel, setPanel] = useState<"inference" | "training">("inference");
  const [includeSensitive, setIncludeSensitive] = useState(false),
    [records, setRecords] = useState<any[]>([]);
  const [replay, setReplay] = useState<any>(null),
    [replayPlaying, setReplayPlaying] = useState(false),
    [replaySpeed, setReplaySpeed] = useState(1),
    [replayIndex, setReplayIndex] = useState(0);
  const replayCursor = useRef(0);
  const [reduceMotion, setReduceMotion] = useState(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const [sequenceGaps, setSequenceGaps] = useState(0),
    [uiDropped, setUiDropped] = useState(0),
    [reconnect, setReconnect] = useState(0),
    [clock, setClock] = useState(Date.now());
  const cursor = useRef(0),
    pending = useRef<NeuralEvent[]>([]),
    lastLive = useRef(0),
    rendered = useRef<View>(emptyView());
  const replayRef = useRef<any>(null),
    pausedRef = useRef(false),
    alive = useRef(true);
  pausedRef.current = paused;
  replayRef.current = replay;
  const assignRun = useCallback((value: NeuralRun | null) => {
    runRef.current = value;
    setRun(value);
  }, []);
  const resetView = useCallback(() => {
    pending.current = [];
    cursor.current = 0;
    lastLive.current = 0;
    rendered.current = emptyView();
    setView(emptyView());
    setSequenceGaps(0);
    setUiDropped(0);
    setPaused(false);
  }, []);
  const chooseRun = useCallback(
    (value: NeuralRun) => {
      if (runRef.current?.run_id !== value.run_id) {
        resetView();
        setObservationMode(value.observation_mode ?? "light");
        setSelectedLayers(value.selected_layers ?? []);
        setSampleEvery(value.sample_every_steps ?? 16);
        setAdapter(value.adapter_id ?? "base");
      }
      epoch.current = Math.max(epoch.current, value.generation_epoch);
      assignRun(value);
      const actual = safeStructure(value.structure);
      if (actual) setStructure(actual);
    },
    [assignRun, resetView],
  );
  const refresh = useCallback(async () => {
    if (!authenticated) return;
    const value = await api<any>("/neural/state");
    if (!alive.current) return;
    if (
      serverInstance.current &&
      serverInstance.current !== value.server_instance
    ) {
      pending.current = [];
      lastLive.current = 0;
      setConnected(false);
      assignRun(null);
      setNotice(
        "서버가 다시 시작되었습니다. 이전 실행은 현재 실행으로 표시하지 않습니다.",
      );
    }
    serverInstance.current = value.server_instance;
    setServer(value);
    setRecords(value.records ?? []);
    if (replayRef.current) return;
    if (
      value.active_run &&
      (!runRef.current ||
        !activeNeuralRun(runRef.current) ||
        runRef.current.run_id === value.active_run.run_id)
    )
      chooseRun(value.active_run);
    else if (runRef.current && activeNeuralRun(runRef.current)) {
      const current = await api<NeuralRun>(
        `/neural/runs/${runRef.current.run_id}`,
      );
      if (alive.current && current.run_id === runRef.current?.run_id)
        assignRun(current);
    }
    const actual =
      safeStructure(runRef.current?.structure) ??
      safeStructure(value.structure);
    if (actual) setStructure(actual);
  }, [authenticated, assignRun, chooseRun]);
  useEffect(() => {
    alive.current = true;
    if (!authenticated) return;
    void refresh().catch((e) => setError(errorText(e)));
    api<any>("/adapters")
      .then((value) => {
        if (alive.current) setAdapters(value.adapters ?? []);
      })
      .catch(() => undefined);
    const timer = setInterval(() => {
      void refresh().catch((e) => {
        if (alive.current) {
          setConnected(false);
          setError(errorText(e));
        }
      });
    }, 2500);
    return () => {
      alive.current = false;
      clearInterval(timer);
    };
  }, [authenticated, refresh]);
  useEffect(() => {
    if (!structure?.nodes.length) return;
    if (!structure.nodes.some((node) => node.path === selected))
      setSelected(
        structure.nodes.find((node) => node.role === "block")?.path ??
          structure.nodes[0].path,
      );
    setSelectedLayers((previous) =>
      previous.filter((path) =>
        structure.nodes.some(
          (node) => node.path === path && node.role === "block",
        ),
      ),
    );
  }, [structure, selected]);

  const enqueue = useCallback(
    (event: NeuralEvent) => {
      const checked = eventCursor(event, cursor.current, runRef.current);
      if (!checked.accepted) return;
      cursor.current = checked.sequence;
      if (checked.gaps) setSequenceGaps((n) => n + checked.gaps);
      const received = { ...event, ui_received_at: new Date().toISOString() };
      if (pending.current.length >= 2048) {
        pending.current.shift();
        setUiDropped((n) => n + 1);
      }
      pending.current.push(received);
      const observed = Date.parse(event.observed_at ?? "");
      if (
        event.source === "live_worker" &&
        activeNeuralRun(runRef.current) &&
        Math.abs(Date.now() - observed) < 5000
      )
        lastLive.current = Date.now();
      if (event.event_type === "structure") {
        const actual = safeStructure(event.payload);
        if (actual) setStructure(actual);
      }
      if (
        (event.event_type === "observer_state" &&
          event.payload.state === "disabled") ||
        event.event_type === "observer_error" ||
        event.event_type === "summary"
      ) {
        if (runRef.current)
          assignRun({ ...runRef.current, observer_enabled: false });
        lastLive.current = 0;
      }
      if (
        event.event_type === "observer_state" &&
        event.payload.state === "observing" &&
        runRef.current
      )
        assignRun({ ...runRef.current, observer_enabled: true });
      if (["state", "run_state"].includes(event.event_type)) {
        const state = event.payload.state ?? event.payload.run?.state;
        if (typeof state === "string" && runRef.current)
          assignRun({
            ...runRef.current,
            state,
            resident: event.payload.resident ?? runRef.current.resident,
          });
      }
    },
    [assignRun],
  );
  useEffect(() => {
    if (!authenticated || !run?.run_id || replay) return;
    const target = { ...run },
      controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    setConnected(false);
    void streamEvents<NeuralEvent>(
      `/neural/runs/${encodeURIComponent(target.run_id)}/events?after=${cursor.current}`,
      (event) => {
        if (!belongsToRun(event, runRef.current) || controller.signal.aborted)
          return;
        if (event.event_type === "snapshot") {
          if (
            event.payload.server_instance &&
            serverInstance.current &&
            event.payload.server_instance !== serverInstance.current
          ) {
            controller.abort();
            setNotice(
              "이전 서버의 연결을 종료했습니다. 상태를 새로 확인하세요.",
            );
            return;
          }
          const current = event.payload.run as NeuralRun;
          if (
            current &&
            current.run_id === target.run_id &&
            current.generation_epoch === target.generation_epoch
          )
            assignRun(current);
          const actual = safeStructure(event.payload.structure);
          if (actual) setStructure(actual);
          setConnected(true);
          return;
        }
        if (event.event_type === "heartbeat") return;
        setConnected(true);
        enqueue(event);
      },
      controller.signal,
    )
      .catch((e) => {
        if (!controller.signal.aborted) {
          setError(errorText(e));
          setConnected(false);
        }
      })
      .finally(() => {
        if (controller.signal.aborted || !alive.current) return;
        setConnected(false);
        lastLive.current = 0;
        void api<NeuralRun>(`/neural/runs/${target.run_id}`)
          .then((current) => {
            if (
              controller.signal.aborted ||
              runRef.current?.run_id !== target.run_id
            )
              return;
            assignRun(current);
            if (activeNeuralRun(current))
              timer = setTimeout(() => setReconnect((n) => n + 1), 2000);
          })
          .catch((e) => {
            if (!controller.signal.aborted) setError(errorText(e));
          });
      });
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
      setConnected(false);
    };
    // A state-only update must not create a second subscriber for this run.
  }, [authenticated, run?.run_id, replay?.id, reconnect, enqueue, assignRun]);

  const displayEvents = useCallback((events: NeuralEvent[]) => {
    if (!events.length) return;
    const value = {
      ...rendered.current,
      latest: { ...rendered.current.latest },
      samples: { ...rendered.current.samples },
    };
    const now = new Date().toISOString();
    const displayed = events.map((event) => ({
      ...event,
      ui_displayed_at: now,
    }));
    for (const event of displayed) {
      if (event.event_type === "block_call" && event.module_path)
        value.latest[event.module_path] = event;
      if (event.event_type === "activation_sample" && event.module_path)
        value.samples[event.module_path] = event;
      if (event.event_type === "input_tokens") value.input = event;
      if (event.event_type === "token") {
        // Token decoding may end in an incomplete UTF-8 byte sequence. Keep
        // IDs as measurements; the visible answer follows the established
        // TextIteratorStreamer output events exactly.
        value.outputCount = event.payload.output_token_count;
        value.tokenEvents = [...value.tokenEvents, event].slice(-128);
      }
      if (event.event_type === "delta") value.text += event.payload.text ?? "";
      if (
        event.event_type === "output" &&
        typeof event.payload.text === "string"
      )
        value.text = event.payload.text;
    }
    value.events = boundedEvents(value.events, displayed);
    value.received += events.length;
    value.latestReceived = events[events.length - 1].ui_received_at;
    value.latestDisplayed = now;
    value.latestObserved = events[events.length - 1].observed_at;
    rendered.current = value;
    setView(value);
  }, []);
  useEffect(() => {
    const timer = setInterval(() => {
      setClock(Date.now());
      if (!pausedRef.current && !replayRef.current && pending.current.length)
        displayEvents(pending.current.splice(0));
    }, intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs, displayEvents]);
  useEffect(() => {
    if (!replay || !replayPlaying) return;
    const events = (replay.events ?? []) as NeuralEvent[];
    if (replayCursor.current >= events.length) {
      setReplayPlaying(false);
      return;
    }
    const start = performance.now();
    const baseTime =
      Date.parse(
        events[Math.max(0, replayCursor.current - 1)]?.observed_at ?? "",
      ) || 0;
    const tick = () => {
      const dueTime = baseTime + (performance.now() - start) * replaySpeed;
      const due: NeuralEvent[] = [];
      while (replayCursor.current < events.length && due.length < 2048) {
        const next = events[replayCursor.current];
        if ((Date.parse(next.observed_at ?? "") || baseTime) > dueTime) break;
        due.push({ ...next, ui_received_at: new Date().toISOString() });
        if (next.event_type === "structure") {
          const actual = safeStructure(next.payload);
          if (actual) setStructure(actual);
        }
        replayCursor.current++;
      }
      displayEvents(due);
      setReplayIndex(replayCursor.current);
      if (replayCursor.current >= events.length) setReplayPlaying(false);
    };
    tick();
    const timer = setInterval(tick, intervalMs);
    return () => clearInterval(timer);
  }, [replay, replayPlaying, replaySpeed, intervalMs, displayEvents]);

  async function start() {
    if (!text.trim() || busy || activeNeuralRun(run)) return;
    if (observationMode === "detail" && !selectedLayers.length) {
      setError(
        "구조도에서 상세 표본을 볼 층을 1~2개 선택해 주세요. 구조가 없다면 먼저 경량 실행으로 확인하세요.",
      );
      return;
    }
    if (
      observationMode === "detail" &&
      (adapter === "base"
        ? !!structure?.adapter
        : !structure?.adapter?.includes(adapter))
    ) {
      setError(
        "현재 구조와 선택한 어댑터가 다릅니다. 먼저 해당 어댑터로 경량 실행해 실제 경로를 확인한 뒤 상세 층을 선택하세요.",
      );
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    setReplay(null);
    resetView();
    try {
      const value = await post<NeuralRun>("/neural/runs", {
        text,
        observation_mode: observationMode,
        selected_layers: selectedLayers,
        sample_every_steps: sampleEvery,
        max_new_tokens: maxTokens,
        request_id: crypto.randomUUID(),
        generation_epoch: ++epoch.current,
        update_interval_ms: intervalMs,
        adapter_id: adapter,
      });
      chooseRun(value);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function toggleObservation() {
    if (!run || !activeNeuralRun(run)) return;
    setBusy(true);
    setError("");
    try {
      const enabled =
        run.observer_enabled === false || run.observation_mode === "off";
      const value = await post<NeuralRun>(
        `/neural/runs/${run.run_id}/observation`,
        {
          enabled,
          ...(enabled
            ? { mode: observationMode === "off" ? "light" : observationMode }
            : {}),
          selected_layers: selectedLayers,
          sample_every_steps: sampleEvery,
          update_interval_ms: intervalMs,
          generation_epoch: run.generation_epoch,
        },
      );
      if (value.run_id) assignRun(value);
      else assignRun({ ...run, observer_enabled: enabled });
      if (!enabled) lastLive.current = 0;
      setNotice(
        enabled
          ? "관측을 요청했습니다. 실제 새 이벤트가 수신되면 LIVE로 표시합니다."
          : "관측을 껐습니다. 모델의 답변 생성은 계속됩니다.",
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function cancel() {
    if (!run) return;
    try {
      const value = await post<NeuralRun>(`/neural/runs/${run.run_id}/cancel`, {
        generation_epoch: run.generation_epoch,
      });
      if (value.run_id) assignRun(value);
      setNotice("모델 작업 취소를 요청했습니다.");
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function save() {
    if (!run) return;
    setBusy(true);
    setError("");
    try {
      await post(`/neural/runs/${run.run_id}/save`, {
        include_sensitive: includeSensitive,
      });
      setNotice(
        includeSensitive
          ? "원문·토큰·값 표본을 포함해 선택한 기록을 저장했습니다."
          : "원문·토큰·값 표본을 제외한 기록을 저장했습니다.",
      );
      const value = await api<any>("/neural/records");
      setRecords(value.records ?? []);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function loadReplay(id: string) {
    if (!id) return;
    setBusy(true);
    setError("");
    try {
      const value = await api<any>(`/neural/records/${encodeURIComponent(id)}`);
      resetView();
      setReplay({ ...value, id });
      replayCursor.current = 0;
      setReplayIndex(0);
      setReplayPlaying(false);
      const actual = safeStructure(value.structure);
      if (actual) setStructure(actual);
      if (value.run) assignRun(value.run);
      setNotice("저장한 실제 이벤트 재생입니다. 현재 GPU 실행이 아닙니다.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  const mode = displayMode({
    replay: !!replay,
    run,
    connected,
    structure,
    recent: clock - lastLive.current < 5000,
    paused,
  });
  const active = activeNeuralRun(run),
    nodes = structure?.nodes ?? [],
    selectedNode = nodes.find((node) => node.path === selected);
  const recent = useMemo(
    () =>
      new Set(
        view.events
          .slice(-180)
          .filter(
            (event) =>
              event.event_type === "block_call" &&
              event.module_path &&
              clock - Date.parse(event.ui_received_at ?? "") < 1100,
          )
          .map((event) => event.module_path!),
      ),
    [view.events, clock],
  );
  const tokenCount = view.outputCount ?? run?.metadata?.output_tokens;
  const output = view.text || run?.output_text || "";
  const latestForward = [...view.events]
    .reverse()
    .find((event) => event.event_type === "forward");
  const summary = [...view.events]
    .reverse()
    .find((event) => event.event_type === "summary");
  const aggregated =
    run?.aggregated_events ?? summary?.payload.aggregated_events;
  const finish = run?.metadata?.finish_reason;
  const measuredInterval =
    summary?.payload.module_event_every_steps ??
    [...view.events]
      .reverse()
      .find((event) => event.event_type === "block_call")?.sampling_info
      ?.every_steps;
  const eventRows = view.events
    .filter(
      (event) =>
        !["block_call", "delta", "structure"].includes(event.event_type),
    )
    .slice(-100)
    .reverse();
  const receiveLag =
    view.latestReceived && view.latestObserved
      ? Date.parse(view.latestReceived) - Date.parse(view.latestObserved)
      : undefined;
  const renderLag =
    view.latestDisplayed && view.latestReceived
      ? Date.parse(view.latestDisplayed) - Date.parse(view.latestReceived)
      : undefined;

  if (!authenticated)
    return (
      <div className="page-content neural-page">
        <h1>신경망 보기</h1>
        <section className="card">
          <BrainCircuit size={30} />
          <h2>로컬 서버 연결이 필요합니다</h2>
          <p>
            설정에서 관리 토큰으로 연결하면 실제 모델 구조와 인증된 현재 요청의
            계측을 볼 수 있습니다.
          </p>
        </section>
      </div>
    );
  return (
    <div
      className={`page-content neural-page ${reduceMotion ? "reduce-motion" : ""}`}
    >
      <div className="section-heading">
        <div>
          <div className="eyebrow">관리자 · 텍스트 LLM 관측</div>
          <h1>신경망 보기</h1>
          <p>
            실제 계산 호출과 토큰 생성 기록을 살펴봅니다. 생각·의도나 정답의
            이유를 읽는 화면은 아닙니다.
          </p>
        </div>
        <button
          className="button secondary"
          onClick={() =>
            refresh()
              .then(() => setError(""))
              .catch((e) => setError(errorText(e)))
          }
        >
          <RefreshCw size={16} />
          현재 상태 확인
        </button>
      </div>
      {server?.fixture && (
        <p className="notice">
          CPU 합성 UI fixture · 실제 GPU 계측 증거가 아닙니다.
        </p>
      )}
      {error && (
        <div className="neural-error" role="alert">
          {error}
          <button className="button subtle" onClick={() => setError("")}>
            닫기
          </button>
        </div>
      )}
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      <section className="card neural-status">
        <div className="neural-status-line">
          <span
            className={`neural-mode mode-${mode.toLowerCase()}`}
            data-testid="neural-mode"
          >
            {mode}
          </span>
          <strong>
            {replay
              ? "저장한 실제 기록 재생"
              : active
                ? statusLabel(run?.state)
                : "현재 신경망 관측 요청 없음"}
          </strong>
          <span>
            {replay
              ? `기록 시각 ${date(replay.created_at)}`
              : mode === "LIVE"
                ? "호스트에서 관측한 호출 · 최근 이벤트 수신"
                : paused
                  ? "화면 표시 일시정지 · 모델은 계속 실행"
                  : active
                    ? run?.observer_enabled === false
                      ? "관측 꺼짐 · 모델은 계속 실행"
                      : "새 관측 수신 대기 또는 연결 중단"
                    : structure
                      ? server?.gpu_lease?.active
                        ? "캐시된 구조 · 현재 작업은 계측 범위 밖"
                        : "캐시된 구조 · 텍스트 모델 미상주"
                      : "실제 구조 정보 없음"}
          </span>
        </div>
        <dl className="neural-facts status-facts">
          <div>
            <dt>모델 / revision</dt>
            <dd>
              {run?.model_id ??
                structure?.model_id ??
                server?.model?.model_id ??
                "확인 중"}
              <small>
                {run?.revision ??
                  structure?.revision ??
                  server?.model?.revision ??
                  "미확인"}
              </small>
              <small>
                텍스트 모델 상주:{" "}
                {replay
                  ? "과거 기록"
                  : run?.resident === true
                    ? "worker에서 확인"
                    : run?.resident === false ||
                        server?.gpu_lease?.active === false
                      ? "아니오"
                      : "미확인"}{" "}
                · 로딩: {run?.state === "loading" ? "진행 중" : "현재 없음"}
              </small>
            </dd>
          </div>
          <div>
            <dt>어댑터 / 장치</dt>
            <dd>
              {run
                ? (run.adapter_id ?? structure?.adapter ?? "기반 모델")
                : structure
                  ? (structure.adapter ?? "기반 모델 · 어댑터 없음")
                  : "실측 어댑터 미확인"}
              <small>
                {run
                  ? "이 관측 실행의 어댑터"
                  : structure
                    ? "마지막 확인 구조의 어댑터"
                    : "다음 실행 선택과 실측 정보는 별개입니다."}
              </small>
              <small>
                {structure?.device
                  ? `${structure.device} · ${active && mode === "LIVE" ? "실제 계측 장치" : "마지막 확인 장치"}`
                  : "장치 미측정"}
              </small>
            </dd>
          </div>
          <div>
            <dt>요청 / 작업</dt>
            <dd>
              {run?.request_id ?? "현재 요청 없음"}
              <small>
                {run?.job_id ?? "작업 없음"} · epoch{" "}
                {run?.generation_epoch ?? "—"}
              </small>
            </dd>
          </div>
          <div>
            <dt>run / 출처</dt>
            <dd data-testid="neural-run-id">
              {run?.run_id ?? "없음"}
              <small>
                {replay
                  ? "saved_actual · REPLAY"
                  : active && mode === "LIVE"
                    ? "live_worker"
                    : structure
                      ? "캐시 · 마지막 실측 구조"
                      : "미확인"}{" "}
                · {date(structure?.observed_at)}
              </small>
            </dd>
          </div>
        </dl>
        {server?.gpu_lease?.active && !active && (
          <p className="fine-print">
            현재 GPU lease:{" "}
            {String(
              server.gpu_lease.kind ??
                server.gpu_lease.purpose ??
                server.gpu_lease.job_id ??
                "다른 작업",
            )}
            . 비전·음성 작업의 내부는 이 화면에서 관측하지 않습니다.
          </p>
        )}
        <p className="fine-print">
          LIVE는 새 이벤트를 수신한 상태이며 매 순간의 GPU 상태를 보장하지
          않습니다. STATIC은 캐시 구조, STALE은 관측 중단·대기, UNAVAILABLE은
          정보 없음입니다.
        </p>
      </section>
      <div className="neural-tabs" role="tablist" aria-label="신경망 관측 영역">
        <button
          role="tab"
          aria-selected={panel === "inference"}
          onClick={() => setPanel("inference")}
        >
          추론 · 구조와 토큰
        </button>
        <button
          role="tab"
          aria-selected={panel === "training"}
          onClick={() => setPanel("training")}
        >
          학습 지표
        </button>
      </div>
      {panel === "training" ? (
        <section className="card">
          <h2>학습 지표 · 기존 기록 연결</h2>
          <p>
            {server?.training?.current?.length
              ? "현재 학습 작업 · 기존 training worker callback 지표"
              : "현재 학습 작업 없음"}
          </p>
          <p className="fine-print">
            이 화면에서 새 학습을 시작하지 않습니다. optimizer step은 실제
            가중치 갱신 횟수이며 microbatch나 checkpointing 재계산 호출 수와
            다릅니다.
          </p>
          {(server?.training?.current ?? []).map((job: any) => (
            <TrainingRecord key={job.id} job={job} historical={false} />
          ))}
          <h3>과거 학습 기록</h3>
          {(server?.training?.history ?? []).length ? (
            server.training.history.map((job: any) => (
              <TrainingRecord key={job.id} job={job} historical />
            ))
          ) : (
            <p className="neural-empty">과거 학습 지표를 찾지 못했습니다.</p>
          )}
          <p className="fine-print">
            {server?.training?.gradient_note ??
              "층별 활성값·gradient·가중치 변화는 과거 기록에서 재구성하지 않습니다. 없는 값은 미측정입니다."}
            {server?.training?.gradient_source}
            {server?.training?.step_note}
          </p>
        </section>
      ) : (
        <>
          <section className="card neural-controls">
            <div className="card-heading">
              <h2>질문으로 계산 관찰</h2>
              <span className="badge muted-badge">디스크 기록 기본 꺼짐</span>
            </div>
            <label htmlFor="neural-question">관찰할 질문</label>
            <textarea
              id="neural-question"
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="예: COUNT(*)와 COUNT(열)의 차이를 짧게 설명해 줘."
              maxLength={12000}
              rows={3}
            />
            <div className="neural-options">
              <label>
                계측 수준
                <select
                  aria-label="계측 수준"
                  value={observationMode}
                  onChange={(event) =>
                    setObservationMode(event.target.value as ObservationMode)
                  }
                  disabled={active || !!replay}
                >
                  <option value="off">꺼짐 · 성능 비교용</option>
                  <option value="light">기본 경량 · 호출·토큰</option>
                  <option value="detail">선택 층 상세 · 작은 값 표본</option>
                </select>
              </label>
              <label>
                어댑터
                <select
                  aria-label="관측 어댑터"
                  value={adapter}
                  onChange={(event) => {
                    setAdapter(event.target.value);
                    setSelectedLayers([]);
                    setNotice(
                      "어댑터를 바꿨습니다. 실제 구조 경로를 경량 실행으로 확인한 뒤 상세 층을 다시 선택하세요.",
                    );
                  }}
                  disabled={active || !!replay}
                >
                  <option value="base">기반 모델</option>
                  {adapters.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.id}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                최대 새 토큰
                <input
                  aria-label="최대 새 토큰"
                  type="number"
                  min={1}
                  max={128}
                  value={maxTokens}
                  onChange={(event) =>
                    setMaxTokens(
                      Math.max(
                        1,
                        Math.min(128, Number(event.target.value) || 1),
                      ),
                    )
                  }
                  disabled={active}
                />
              </label>
              <label>
                화면 갱신
                <select
                  aria-label="화면 갱신 간격"
                  value={intervalMs}
                  onChange={(event) =>
                    setIntervalMs(Number(event.target.value))
                  }
                >
                  <option value={100}>100 ms</option>
                  <option value={250}>250 ms</option>
                  <option value={500}>500 ms</option>
                  <option value={1000}>1000 ms</option>
                </select>
              </label>
            </div>
            {observationMode === "detail" && (
              <div className="neural-detail-config">
                <label>
                  표본 간격
                  <select
                    value={sampleEvery}
                    onChange={(event) =>
                      setSampleEvery(Number(event.target.value))
                    }
                    disabled={active}
                  >
                    <option value={8}>8 step</option>
                    <option value={16}>16 step</option>
                    <option value={32}>32 step</option>
                  </select>
                </label>
                <p>
                  선택 층 {selectedLayers.length}/2:{" "}
                  {selectedLayers.join(", ") ||
                    "구조도에서 층을 선택한 뒤 ‘상세 표본 대상’에 체크하세요."}
                  <small>
                    마지막 유효 토큰의 최대 32개 성분만 CPU로 옮깁니다.
                    전송·통계 비용이 추가됩니다.
                  </small>
                </p>
              </div>
            )}
            <div className="neural-actions">
              <button
                className="button primary"
                onClick={() => void start()}
                disabled={!text.trim() || busy || active || !!replay}
              >
                <Play size={16} />
                질문 보내고 관찰
              </button>
              <button
                className="button secondary"
                onClick={() => setPaused((value) => !value)}
                disabled={!run || !!replay}
              >
                {paused ? <Play size={16} /> : <Pause size={16} />}화면만{" "}
                {paused ? "계속 보기" : "일시정지"}
              </button>
              <button
                className="button secondary"
                onClick={() => void toggleObservation()}
                disabled={
                  busy || !active || !!replay || run?.observation_mode === "off"
                }
              >
                {run?.observer_enabled === false ||
                run?.observation_mode === "off"
                  ? "관측 켜기"
                  : "관측 끄기"}
              </button>
              <button
                className="button secondary danger"
                onClick={() => void cancel()}
                disabled={!active || !!replay}
              >
                <Square size={14} />
                모델 작업 취소
              </button>
            </div>
            <p className="fine-print">
              화면 일시정지는 GPU 작업을 멈추지 않습니다. 관측 끄기 버튼은 같은
              작업을 보는 모든 브라우저에 적용됩니다. 관측 끄기·마지막 브라우저
              연결 종료는 훅을 정리하고 답변 생성은 계속합니다. 생성 취소는 별도
              버튼입니다. 원문은 이 인증된 화면의 메모리에서만 표시되며 자동
              저장하지 않습니다.
            </p>
          </section>
          <div className="neural-workspace">
            {structure ? (
              <Graph
                structure={structure}
                selected={selected}
                choose={setSelected}
                recent={recent}
                live={mode === "LIVE" && !paused}
                replaying={!!replay && replayPlaying}
                reduceMotion={reduceMotion}
              />
            ) : (
              <section className="card neural-structure-empty">
                <BrainCircuit size={40} />
                <h2>아직 확인된 실제 구조가 없습니다</h2>
                <p>
                  기본 경량 모드로 짧은 질문을 보내면 그 실행이 로드한 모델
                  객체의 구조를 읽습니다. 층 개수나 활성값을 임의로 만들지
                  않습니다.
                </p>
              </section>
            )}
            <LayerDetail
              node={selectedNode}
              call={view.latest[selected]}
              sample={view.samples[selected]}
              selectedForSampling={selectedLayers.includes(selected)}
              disabled={
                active ||
                !!replay ||
                (!selectedLayers.includes(selected) &&
                  selectedLayers.length >= 2)
              }
              toggleSampling={() =>
                setSelectedLayers((paths) =>
                  paths.includes(selected)
                    ? paths.filter((path) => path !== selected)
                    : paths.length < 2
                      ? [...paths, selected]
                      : paths,
                )
              }
            />
          </div>
          {structure && (
            <details className="card neural-structure-meta">
              <summary>구조 근거·파라미터 집계 기준</summary>
              <dl className="neural-facts">
                <div>
                  <dt>래퍼 / 기반 클래스</dt>
                  <dd>
                    {structure.wrapper_type} / {structure.base_type}
                    <small>{structure.base_path || "최상위 객체"}</small>
                  </dd>
                </div>
                <div>
                  <dt>중복 제외 저장 요소</dt>
                  <dd>
                    {fmt(structure.parameter_counts?.total)}
                    <small>
                      기반 {fmt(structure.parameter_counts?.base)} · 어댑터{" "}
                      {fmt(structure.parameter_counts?.adapter)}
                    </small>
                  </dd>
                </div>
                <div>
                  <dt>requires_grad 설정 요소</dt>
                  <dd>
                    {fmt(structure.parameter_counts?.trainable)}
                    <small>
                      설정값이며 현재 실제 학습 중이라는 뜻이 아닙니다.
                    </small>
                  </dd>
                </div>
                <div>
                  <dt>확인한 forward</dt>
                  <dd>
                    {structure.forward_evidence?.implementation ?? "미확인"}
                    <small>
                      Transformers{" "}
                      {structure.forward_evidence?.transformers_version ??
                        "미확인"}{" "}
                      · SHA256 {structure.forward_evidence?.sha256 ?? "미확인"}
                    </small>
                  </dd>
                </div>
              </dl>
              <p className="fine-print">{structure.parameter_count_notice}</p>
              <p className="fine-print">
                모듈 트리는 완전한 계산 그래프가 아닙니다. full hidden
                states·attention·전체 어휘 점수는 저장하지 않으며 미측정
                항목으로 둡니다.
              </p>
            </details>
          )}
          <section className="card">
            <div className="card-heading">
              <h2>토큰 생성 · 실제 tokenizer ID</h2>
              <span className="badge muted-badge">
                출력 {fmt(tokenCount)}개
              </span>
            </div>
            <p className="neural-finish" data-testid="neural-finish">
              종료 이유:{" "}
              {finish === "eos"
                ? "EOS · 정상 생성 종료"
                : finish === "length_or_timeout"
                  ? "토큰·시간 제한으로 중단 · 부분 출력"
                  : finish === "cancelled"
                    ? "취소 · 부분 출력"
                    : (finish ?? (active ? "생성 진행 중" : "미측정"))}
            </p>
            <p className="neural-output" data-testid="neural-output">
              {output ||
                "아직 표시할 생성 원문이 없습니다. 원문 제외 기록에는 원문이 없습니다."}
            </p>
            <details className="neural-profile">
              <summary>이번 실행의 시간·메모리 측정</summary>
              <dl className="neural-facts">
                <div>
                  <dt>모델 로딩 / 입력·관측 준비</dt>
                  <dd>
                    {fmt(run?.metadata?.model_load_seconds, " s")} /{" "}
                    {fmt(run?.metadata?.preparation_seconds, " s")}
                  </dd>
                </div>
                <div>
                  <dt>생성 호스트 경과 시간</dt>
                  <dd>{fmt(run?.metadata?.generation_seconds, " s")}</dd>
                </div>
                <div>
                  <dt>첫 토큰 후 기존 중단 callback까지</dt>
                  <dd>
                    {fmt(run?.metadata?.first_token_latency_seconds, " s")}
                  </dd>
                </div>
                <div>
                  <dt>생성 처리량 · 토큰/생성 시간</dt>
                  <dd>
                    {fmt(
                      run?.metadata?.generation_seconds > 0
                        ? run?.metadata?.output_tokens /
                            run?.metadata?.generation_seconds
                        : undefined,
                      " token/s",
                    )}
                  </dd>
                </div>
                <div>
                  <dt>최대 CUDA 할당 / 예약</dt>
                  <dd>
                    {fmt(
                      typeof run?.metadata?.peak_vram_bytes === "number"
                        ? run.metadata.peak_vram_bytes / 1024 ** 2
                        : undefined,
                      " MiB",
                    )}{" "}
                    /{" "}
                    {fmt(
                      typeof run?.metadata?.peak_vram_reserved_bytes ===
                        "number"
                        ? run.metadata.peak_vram_reserved_bytes / 1024 ** 2
                        : undefined,
                      " MiB",
                    )}
                  </dd>
                </div>
                <div>
                  <dt>값 표본 CPU 전송·통계</dt>
                  <dd>
                    {fmt(
                      run?.metadata?.observation
                        ?.sample_cpu_transfer_and_stats_ms ??
                        summary?.payload.sample_cpu_transfer_and_stats_ms,
                      " ms",
                    )}
                  </dd>
                </div>
              </dl>
              <p className="fine-print">
                각 실행은 새 worker입니다. 첫 callback 구간에는 입력 처리·초기
                CUDA 준비가 포함됩니다. 독립 워밍업 시간과 GPU 커널 완료 시간은
                미측정입니다. 상세 값 표본의 CPU 전송에는 제한된 동기화 비용이
                포함될 수 있습니다. 이 기록만으로 관측 부하가 10% 이하라고
                보장하지 않습니다.
              </p>
            </details>
            <div className="neural-token-strip" aria-label="생성 토큰 ID">
              {view.tokenEvents.flatMap((event) =>
                (event.payload.token_ids ?? []).map(
                  (id: number, index: number) => (
                    <span
                      className={
                        event.payload.special_tokens?.[index]
                          ? "special-token"
                          : ""
                      }
                      key={`${event.sequence_no}-${index}`}
                      title={`실제 토큰 ID ${id}, 생성 step ${event.payload.step}, ${event.payload.special_tokens?.[index] ? "특수 토큰" : "일반 토큰"}`}
                    >
                      {id}
                      {event.payload.special_tokens?.[index] ? " · 특수" : ""}
                    </span>
                  ),
                ),
              )}
            </div>
            <details>
              <summary>
                입력 토큰 ID{" "}
                {view.input
                  ? `· ${view.input.payload.token_count}개`
                  : "· 미측정 또는 저장 제외"}
              </summary>
              <p className="neural-id-list">
                {view.input?.payload.token_ids
                  ?.map(
                    (id: number, index: number) =>
                      `${id}${view.input?.payload.special_tokens?.[index] ? "(특수)" : ""}`,
                  )
                  .join(" · ") || "미측정 / 저장 제외"}
              </p>
            </details>
            <p className="fine-print">
              본문은 기존 TextIteratorStreamer의 증분 문자열을 그대로 표시합니다. 토큰의 미완성 누적 디코딩으로 덮어쓰지 않습니다. 토큰 하나를 한 글자로
              계산하지 않습니다. KV cache는 이전 문맥의 계산 결과를
              재사용합니다. 한 토큰 입력도 첫 호출이면 prefill입니다.
            </p>
            <p className="fine-print">
              마지막 모델 호출:{" "}
              {latestForward?.phase === "prefill"
                ? "입력 처리 (prefill)"
                : latestForward?.phase === "decode"
                  ? "이어쓰기 (decode)"
                  : "미측정"}{" "}
              · 입력 길이 {fmt(latestForward?.payload.input_sequence_length)} ·
              앞선 cache 길이 {fmt(latestForward?.payload.cache_length_before)}{" "}
              · cache 재사용{" "}
              {latestForward
                ? latestForward.payload.cache_reused
                  ? "예"
                  : "아니오"
                : "미측정"}
              {latestForward?.payload.recomputes_context
                ? " · 캐시 없이 문맥 재계산"
                : ""}
            </p>
          </section>
          <section className="card neural-timeline">
            <div className="card-heading">
              <h2>계측 타임라인</h2>
              <span data-testid="neural-event-count">
                화면 수신 {view.received.toLocaleString()}개
              </span>
            </div>
            <div className="neural-metrics">
              <div>
                <small>backend / worker 유실</small>
                <strong>
                  {fmt(run?.dropped_events ?? 0)} /{" "}
                  {fmt(run?.worker_dropped_events ?? 0)}
                </strong>
              </div>
              <div>
                <small>순번 간격 / UI 버퍼 유실</small>
                <strong>
                  {sequenceGaps} / {uiDropped}
                </strong>
              </div>
              <div>
                <small>이벤트 → UI 수신</small>
                <strong>{fmt(receiveLag, " ms")}</strong>
              </div>
              <div>
                <small>UI 수신 → 표시</small>
                <strong>{fmt(renderLag, " ms")}</strong>
              </div>
            </div>
            <p className="fine-print">
              시계 차이를 포함한 관측 지연이며 정확히 {intervalMs}ms를 보장하지
              않습니다. 화면은 최근 600개, 아래 표는 주요 이벤트 최근
              100개입니다. 집계로 생략한 층 이벤트: {fmt(aggregated)}. 이 기록의
              층 이벤트 간격: {fmt(measuredInterval)} generation step. 현재
              기본값은 4이며 호출 횟수는 훅이 설치된 동안의 실제 누적입니다.
              토큰·forward 이벤트는 별도입니다. 생략은 계산 생략을 뜻하지
              않습니다.
            </p>
            <p className="fine-print">
              backend 관측 {date(view.latestObserved)} · UI 수신{" "}
              {date(view.latestReceived)} · UI 표시 {date(view.latestDisplayed)}
            </p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>순번</th>
                    <th>관측 시각 / 출처</th>
                    <th>단계 · 이벤트</th>
                    <th>생성 step / 설명</th>
                  </tr>
                </thead>
                <tbody>
                  {eventRows.map((event) => (
                    <tr key={`${event.run_id}-${event.sequence_no}`}>
                      <td>{event.sequence_no}</td>
                      <td>
                        {date(event.observed_at)}
                        <small>
                          {event.source} · {event.timing_kind ?? "미측정"}
                        </small>
                      </td>
                      <td>
                        {event.phase ?? "—"} ·{" "}
                        {neuralEventLabel(event.event_type)}
                      </td>
                      <td>
                        {event.payload.step ?? "—"}
                        {event.payload.state ? ` · ${event.payload.state}` : ""}
                        {event.event_type === "token"
                          ? ` · ID ${(event.payload.token_ids ?? []).join(", ")}`
                          : ""}
                        {event.payload.message
                          ? ` · ${event.payload.message}`
                          : ""}
                        <small>{event.module_path}</small>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!eventRows.length && (
                <p className="neural-empty">실제 수신한 이벤트가 없습니다.</p>
              )}
            </div>
          </section>
          <section className="card">
            <div className="card-heading">
              <h2>기록 저장·재생</h2>
              <span className="badge muted-badge">
                회차 20 MB · 전체 200 MB
              </span>
            </div>
            <label className="neural-check">
              <input
                type="checkbox"
                checked={includeSensitive}
                onChange={(event) => setIncludeSensitive(event.target.checked)}
              />
              원문·토큰 ID·활성값 표본의 영구 보관에 별도 동의
            </label>
            <p className="fine-print">
              기본 저장은 식별자와 메트릭만 포함합니다. 한도에 도달하면 저장을
              중지하고 기존 파일은 삭제하지 않습니다. 현재 메모리 버퍼에 남은
              기록만 저장됩니다.
            </p>
            <div className="neural-actions">
              <button
                className="button secondary"
                onClick={() => void save()}
                disabled={!run || busy || !!replay}
              >
                <Save size={16} />
                현재 기록 저장
              </button>
              <label>
                저장 기록 선택
                <select
                  aria-label="저장 기록 선택"
                  value={replay?.id ?? ""}
                  disabled={busy || active}
                  onChange={(event) => void loadReplay(event.target.value)}
                >
                  <option value="">재생할 실제 기록 선택</option>
                  {records.map((record) => (
                    <option value={record.id} key={record.id}>
                      {date(record.created_at)} · {record.run_id} ·{" "}
                      {record.include_sensitive ? "원문 포함" : "원문 제외"}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {replay && (
              <div className="neural-replay">
                <strong>REPLAY · {replay.run_id ?? replay.run?.run_id}</strong>
                <p>
                  {date(replay.created_at)} · 실제 저장 이벤트{" "}
                  {replay.events?.length ?? 0}개 중 {replayIndex}개 ·{" "}
                  {replay.include_sensitive
                    ? "선택 저장한 원문 포함"
                    : "원문·토큰·활성값 제외"}
                </p>
                <div className="neural-actions">
                  <button
                    className="button primary"
                    onClick={() => {
                      if (replayIndex >= (replay.events?.length ?? 0)) {
                        resetView();
                        replayCursor.current = 0;
                        setReplayIndex(0);
                      }
                      setReplayPlaying((p) => !p);
                    }}
                  >
                    {replayPlaying ? <Pause size={16} /> : <Play size={16} />}
                    기록 {replayPlaying ? "일시정지" : "재생"}
                  </button>
                  <label>
                    재생 속도
                    <select
                      aria-label="재생 속도"
                      value={replaySpeed}
                      onChange={(event) =>
                        setReplaySpeed(Number(event.target.value))
                      }
                    >
                      <option value={0.25}>0.25x</option>
                      <option value={1}>1x</option>
                    </select>
                  </label>
                  <button
                    className="button secondary"
                    onClick={() => {
                      setReplay(null);
                      setReplayPlaying(false);
                      assignRun(null);
                      resetView();
                      void refresh().catch((e) => setError(errorText(e)));
                    }}
                  >
                    현재 상태로 돌아가기
                  </button>
                </div>
                <p className="fine-print">
                  과거 이벤트의 기록 시각 간격으로 재생합니다. 중간값이 없으면
                  미측정으로 남습니다. GPU 계산을 느리게 실행하는 기능이
                  아닙니다.
                </p>
              </div>
            )}
          </section>
        </>
      )}
      <section className="card neural-help">
        <div className="card-heading">
          <h2>용어와 표시 기준</h2>
          <label className="neural-check">
            <input
              type="checkbox"
              checked={reduceMotion}
              onChange={(event) => setReduceMotion(event.target.checked)}
            />
            애니메이션 감소
          </label>
        </div>
        <dl className="neural-glossary">
          {glossary.map(([term, explanation]) => (
            <div key={term}>
              <dt title={explanation}>{term}</dt>
              <dd>{explanation}</dd>
            </div>
          ))}
        </dl>
        <p className="fine-print">
          오류가 나면 관측 끄기를 선택하거나 기존 대화·강의실로 이동하세요.
          수업과 관측은 분리되어 있습니다. 모델 작업을 멈추려면 취소 버튼을
          사용하세요.
        </p>
      </section>
    </div>
  );
}

function TrainingRecord({
  job,
  historical,
}: {
  job: any;
  historical: boolean;
}) {
  const metrics = Array.isArray(job.metrics) ? job.metrics : [];
  const latest = metrics[metrics.length - 1];
  return (
    <details className="neural-training" open={!historical}>
      <summary>
        {historical ? "과거 학습 기록" : "현재 학습 작업"} · {job.id} ·{" "}
        {statusLabel(job.state ?? job.status)}
      </summary>
      <p className="fine-print">
        {job.created_at ?? "시각 미기록"} · 출처: 기존 training worker callback
        저장 지표
      </p>
      <dl className="neural-facts">
        <div>
          <dt>optimizer step</dt>
          <dd>{fmt(latest?.step)}</dd>
        </div>
        <div>
          <dt>microbatch</dt>
          <dd>
            {fmt(
              latest?.actual_microbatches ??
                latest?.microbatch ??
                latest?.micro_step,
            )}
          </dd>
        </div>
        <div>
          <dt>층별 활성값 / gradient</dt>
          <dd>미측정 / 미측정</dd>
        </div>
        <div>
          <dt>gradient 기록 의미</dt>
          <dd>
            {latest?.grad_norm !== undefined
              ? "기존 callback grad_norm · unscale 후 clipping 전 전체 norm (설치된 단일 GPU Trainer 경로)"
              : "grad_norm 미측정"}
          </dd>
        </div>
      </dl>
      <Metrics records={metrics} />
    </details>
  );
}
