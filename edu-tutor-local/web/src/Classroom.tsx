import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import { flushSync } from "react-dom";
import { restorePlaybackState } from "./playbackSession";
import type { SavedPlaybackStatus } from "./playbackSession";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  ChevronRight,
  CornerUpLeft,
  Pause,
  Play,
  RefreshCw,
  Send,
  Volume2,
  VolumeX,
} from "lucide-react";
import katex from "katex";
import type { Lesson, BoardElement, Playback, CellSelection } from "./lesson";
import BoardShapes from "./BoardShapes";
import {
  initialPlayback,
  playbackReducer,
  replayScene,
  shouldSubmit,
} from "./lesson";
import { activeJob, api, errorText, protectedBlob, post } from "./api";
import { aimAvatarArm, avatarAnchors, avatarCanvas } from "./avatar";
import { cancelSpeechRequest, lessonEvent } from "./student";
import type { SpeechRequest } from "./student";
import { CacheMissError, OneAhead, cachedStep, prepareCachedSpeech, prepareNextSpeech, sameCachedSpeech, scopedAudioPath, decodeWaveform, validateVisibleSpeech } from "./speechCache";
import type { PreparedSpeech } from "./speechCache";

function Equation({ value }: { value: string }) {
  const html = useMemo(
    () =>
      katex.renderToString(value, {
        throwOnError: false,
        trust: false,
        strict: "error",
        maxExpand: 100,
        maxSize: 10,
        output: "html",
      }),
    [value],
  );
  return (
    <div className="equation" dangerouslySetInnerHTML={{ __html: html }} />
  );
}
// KaTeX's section fills its board slot; aim at the last rendered glyph
// instead of that section's otherwise empty right edge.
function equationGlyphPoint(element: HTMLElement | undefined) {
  const content = element?.querySelector(".equation .katex-html");
  if (!content) return null;
  const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT);
  const nodes: Node[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode())
    if (node.textContent?.trim()) nodes.push(node);
  for (const node of nodes.reverse()) {
    const range = document.createRange();
    range.selectNodeContents(node);
    const bounds = Array.from(range.getClientRects())
      .filter((rect) => rect.width > 0 && rect.height > 0)
      .at(-1);
    if (bounds)
      return { x: bounds.left + bounds.width / 2, y: bounds.top + bounds.height / 2 };
  }
  return null;
}
export function Avatar({
  custom,
  gesture = "idle",
  speaking = false,
  armAngle = 0,
}: {
  custom?: string;
  gesture?: string;
  speaking?: boolean;
  armAngle?: number;
}) {
  if (custom)
    return (
      <img
        className="custom-avatar"
        src={custom}
        alt="사용자 정적 PNG 아바타"
      />
    );
  return (
    <svg
      viewBox={`0 0 ${avatarCanvas.width} ${avatarCanvas.height}`}
      role="img"
      aria-label={`기본 아바타 · ${gesture}`}
      className={`avatar avatar-${gesture}`}
      data-gesture={gesture}
    >
      <ellipse cx="83" cy="208" rx="48" ry="9" fill="#dce8dd" />
      <path d="M58 166 53 204h20l10-38m5 0 5 38h20l-9-40" fill="#243c37" />
      <path d="M48 202h26v8H44q-3-8 4-8m45 0h22l7 8H92z" fill="#192d2a" />
      <path
        d="M58 106Q34 118 38 164l23 11h46l17-12q-1-46-21-58z"
        fill="#dde7ba"
      />
      <path d="m64 108 17 23 19-23v63H62z" fill="#7a977e" />
      <g
        data-testid="avatar-arm"
        transform={`rotate(${gesture === "idle" ? -65 : gesture === "look_board" ? -45 : gesture === "explain" ? 35 : armAngle} ${avatarAnchors.pointer_shoulder.x} ${avatarAnchors.pointer_shoulder.y})`}
      >
        <path
          d="M56 114q-8 18-13 26l-18-12-8 12 30 23q16-11 24-31"
          fill="#dde7ba"
        />
        <path d="m18 130-10-8q-7-3-5 6l11 15 8-7" fill="#f0c4a1" />
        {gesture === "write" && (
          <path d="M14 134 3 113" stroke="#efd58c" strokeWidth="4" />
        )}
      </g>
      <g transform={gesture === "explain" ? "rotate(-45 108 116)" : undefined}>
        <path d="M108 116q12 20 9 35l-9 18-13-6 11-19-8-18" fill="#dde7ba" />
        <path d="m98 161-3 15q4 10 11 2l4-10" fill="#f0c4a1" />
      </g>
      <g
        data-testid="avatar-head"
        transform={
          gesture === "look_board"
            ? "rotate(-12 80 95)"
            : gesture === "point" || gesture === "write"
              ? "rotate(-6 80 95)"
              : undefined
        }
      >
        <path d="M66 86h31v27q-16 14-31 0z" fill="#eab58f" />
        <ellipse cx="80" cy="65" rx="35" ry="39" fill="#f4c8a6" />
        <ellipse cx="45" cy="68" rx="7" ry="10" fill="#f4c8a6" />
        <ellipse cx="115" cy="68" rx="7" ry="10" fill="#f4c8a6" />
        <path
          d="M44 65q-9-33 11-42 19-20 47-2 22 4 14 43l-10-14-3-19q-21 18-51 15z"
          fill="#283d37"
        />
        <path
          d="m57 57 13-1m20 0 13 1"
          stroke="#283d37"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <ellipse cx="64" cy="66" rx="2.5" ry="3.3" fill="#283d37" />
        <ellipse cx="96" cy="66" rx="2.5" ry="3.3" fill="#283d37" />
        <path
          d="M78 66v10h5"
          fill="none"
          stroke="#c99573"
          strokeWidth="2"
          strokeLinecap="round"
        />
        {speaking ? (
          <ellipse cx="81" cy="85" rx="6" ry="5" fill="#79483c" />
        ) : (
          <path
            d="M73 84q8 6 15-1"
            fill="none"
            stroke="#79483c"
            strokeWidth="2"
            strokeLinecap="round"
          />
        )}
        <rect
          x="52"
          y="59"
          width="24"
          height="17"
          rx="6"
          fill="none"
          stroke="#40594d"
          strokeWidth="2"
        />
        <rect
          x="85"
          y="59"
          width="24"
          height="17"
          rx="6"
          fill="none"
          stroke="#40594d"
          strokeWidth="2"
        />
        <path d="M76 64h9" stroke="#40594d" strokeWidth="2" />
      </g>
    </svg>
  );
}
function Element({
  element,
  highlightedRows,
  highlightedColumns,
  highlightStyle,
  highlightedCells,
  selectedCell,
  onSelectCell,
}: {
  element: BoardElement;
  highlightedRows?: number[];
  highlightedColumns?: number[];
  highlightStyle?: string;
  highlightedCells?: string[];
  selectedCell?: CellSelection | null;
  onSelectCell: (cell: CellSelection) => void;
}) {
  return (
    <section
      data-board-element={element.element_id}
      className={`board-element slot-${element.slot} ${highlightStyle && !highlightedRows?.length && !highlightedColumns?.length && !highlightedCells?.length ? "element-highlight" : ""}`}
      style={
        element.layout
          ? {
              position: "absolute",
              left: `${element.layout.x * 100}%`,
              top: `${element.layout.y * 100}%`,
              width: `${element.layout.width * 100}%`,
              minHeight: `${element.layout.height * 100}%`,
            }
          : undefined
      }
    >
      {element.type === "text" && <p>{element.text}</p>}
      {element.type === "equation" && <Equation value={element.latex!} />}
      {element.type === "code" && (
        <>
          <div className="code-label">{element.language?.toUpperCase()}</div>
          <pre>
            <code>
              {element.code?.split("\n").map((line, i) => (
                <span className="code-line" key={i}>
                  <span aria-hidden="true" className="line-number">
                    {i + 1}
                  </span>
                  {line}
                  {"\n"}
                </span>
              ))}
            </code>
          </pre>
        </>
      )}
      {element.type === "table" && (
        <>
          <div className="board-caption">{element.caption || "자료 표"}</div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {element.columns!.map((c, i) => (
                    <th key={i}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {element.rows!.map((row, i) => (
                  <tr
                    key={element.row_ids?.[i] || i}
                    data-row-id={
                      element.row_ids?.[i] || `${element.element_id}:r${i}`
                    }
                    className={
                      highlightedRows?.includes(i) ? "highlight-row" : ""
                    }
                  >
                    {row.map((cell, j) => {
                      const cellId =
                        element.cell_ids?.[i]?.[j] ||
                        `${element.element_id}:r${i}:c${j}`;
                      const selected = selectedCell?.table_element_id === element.element_id && selectedCell?.cell_id === cellId;
                      const cellSelection = {
                        table_element_id: element.element_id,
                        table_name: element.table_name,
                        column_name: element.columns![j],
                        row_id:
                          element.row_ids?.[i] || `${element.element_id}:r${i}`,
                        column_id:
                          element.column_ids?.[j] ||
                          `${element.element_id}:c${j}`,
                        cell_id: cellId,
                        row_index: i,
                        column_index: j,
                        value: cell,
                      };
                      return (
                        <td
                          className={`${highlightedColumns?.includes(j) || highlightedCells?.includes(cellId) ? "highlight-cell" : ""} ${selected ? "selected-cell" : ""}`}
                          key={cellId}
                          data-cell-id={cellId}
                        >
                          <button
                            className="board-cell-button"
                            aria-label={`${element.columns![j]}, ${i + 1}행: ${cell === null ? "NULL" : String(cell)}`}
                            aria-pressed={selected}
                            onClick={() => onSelectCell(cellSelection)}
                          >
                            {cell === null ? (
                              <span className="null-cell">NULL</span>
                            ) : (
                              String(cell)
                            )}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
type Props = {
  lessonRecordId: string;
  lesson: Lesson | null;
  onDemo: () => void;
  onInterrupt: (question: string, context: unknown) => void;
  speechAvailable: boolean;
  customAvatar?: string;
  isSupplement?: boolean;
  onResume?: () => void;
  studentMode?: boolean;
  onComplete?: () => void;
  replayOnly?: boolean;
  replayAutoplay?: boolean;
  replayResumePlaying?: boolean;
  onRegisterStop?: (stop: (() => Promise<void>) | null) => void;
  onSavedSupplement?: (context: any, signal: AbortSignal) => Promise<void>;
};
export default function Classroom({
  lessonRecordId,
  lesson,
  onDemo,
  onInterrupt,
  speechAvailable,
  customAvatar,
  isSupplement = false,
  onResume,
  studentMode = false,
  onComplete,
  replayOnly = false,
  replayAutoplay = false,
  replayResumePlaying = false,
  onRegisterStop,
  onSavedSupplement,
}: Props) {
  const [playback, dispatch] = useReducer(playbackReducer, initialPlayback);
  const [question, setQuestion] = useState("");
  const composing = useRef(false);
  const [muted, setMuted] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [audioUrl, setAudioUrl] = useState<string>();
  const [audioError, setAudioError] = useState("");
  const [audioLoading, setAudioLoading] = useState(false);
  const speechRequest = useRef<SpeechRequest | undefined>(undefined);
  const [continuous, setContinuous] = useState(false);
  const continuousRef = useRef(false);
  const resumeOnce = useRef(false);
  const restoredIntent = useRef({continuous: false, once: false});
  const mounted = useRef(true);
  const playbackStatus = useRef<SavedPlaybackStatus>("paused");
  const playIntent = useRef(0);
  const lastAudio = useRef<HTMLAudioElement | null>(null);
  const clockSample = useRef({ at_ms: 0, media_time: 0 });
  const committedScene = useRef("");
  const nextCached = useRef(new OneAhead<PreparedSpeech>());
  const nextSpeechRequest = useRef<SpeechRequest | undefined>(undefined);
  const ownedSpeechRequests = useRef(new Set<SpeechRequest>());
  const nextGenerationAttempts = useRef(new Set<string>());
  const savedSupplementRequest = useRef<AbortController | undefined>(undefined);
  const autoAttempt = useRef("");
  const autoPlayEpoch = useRef<number | undefined>(undefined);
  const lastEnded = useRef<number | undefined>(undefined);
  const [interrupting, setInterrupting] = useState(false);
  const interruptSequence = useRef(0);
  const audioPosition = useRef(0);
  const [audioEpoch, setAudioEpoch] = useState(0);
  const [mouthOpen, setMouthOpen] = useState(false);
  const [waveform, setWaveform] = useState<number[]>([]);
  const [selectedCell, setSelectedCell] = useState<CellSelection | null>(null);
  const [hypothesis, setHypothesis] = useState(false);
  const [pen, setPen] = useState<{ x: number; y: number } | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const visibleCellTarget = useRef("");
  const handRef = useRef<HTMLDivElement>(null);
  const figureRef = useRef<HTMLDivElement>(null);
  const [armAngle, setArmAngle] = useState(0);
  const [pointer, setPointer] = useState<{
    x1: number;
    y1: number;
    x2: number;
    y2: number;
  } | null>(null);
  const [arrows, setArrows] = useState<
    { id: string; x1: number; y1: number; x2: number; y2: number }[]
  >([]);
  const step = lesson?.steps[playback.step];
  const scene = useMemo(
    () =>
      lesson ? replayScene(lesson, playback.step, playback.progress) : null,
    [lesson, playback.step, playback.progress],
  );
  const restoredLesson = useRef<string | undefined>(undefined);
  const epochRef = useRef(playback.epoch);
  epochRef.current = playback.epoch;
  const snapshot = useRef({lesson, playback, selectedCell});
  snapshot.current = {lesson, playback, selectedCell};
  function savePlayback() {
    const current = snapshot.current;
    if (!current.lesson || !current.playback.epoch) return;
    try {
      localStorage.setItem(`lecture:${current.lesson.lesson_id}`, JSON.stringify({
        step: current.playback.step,
        progress: playbackStatus.current === "completed" ? 1 : current.playback.progress,
        selected_cell: current.selectedCell,
        problem_revision: current.lesson.problem_revision,
        audio_position: audioPosition.current,
        playback_status: playbackStatus.current,
      }));
    } catch { /* Storage failure must not interrupt an already verified clip. */ }
  }
  function event(type: string, detail: Record<string, unknown> = {}) {
    lessonEvent(type, {
      lesson_record_id: lessonRecordId,
      lesson_id: lesson?.lesson_id,
      step_id: step?.id,
      step: playback.step,
      epoch: epochRef.current,
      supplement: isSupplement,
      student_mode: studentMode,
      ...detail,
    });
  }
  useEffect(() => {
    if (!lesson || restoredLesson.current === lesson.lesson_id) return;
    restoredLesson.current = lesson.lesson_id;
    let saved = null;
    try {
      saved = JSON.parse(
        localStorage.getItem(`lecture:${lesson.lesson_id}`) || "null",
      );
    } catch {
      /* invalid local state starts first step */
    }
    const restored = restorePlaybackState(saved, lesson.steps.length, studentMode, replayAutoplay || replayResumePlaying);
    audioPosition.current = restored.audioPosition;
    playbackStatus.current = restored.completed ? "completed" : "paused";
    setSelectedCell(restored.selectedCell);
    continuousRef.current = restored.autoStart && (studentMode || replayAutoplay);
    resumeOnce.current = restored.autoStart && replayResumePlaying;
    restoredIntent.current = {continuous: continuousRef.current, once: resumeOnce.current};
    setContinuous(continuousRef.current);
    dispatch({ type: "restore", step: restored.step, progress: restored.progress });
    setAudioError("");
  }, [lesson]);
  useEffect(() => {
    // A table removed by a board action cannot remain the question target.
    if (
      selectedCell &&
      !scene?.elements.some(
        (element) =>
          element.element_id === selectedCell.table_element_id &&
          element.rows?.some((row, i) =>
            row.some(
              (_, j) =>
                (element.cell_ids?.[i]?.[j] ||
                  `${element.element_id}:r${i}:c${j}`) === selectedCell.cell_id,
            ),
          ),
      )
    )
      setSelectedCell(null);
  }, [scene, selectedCell]);
  useEffect(() => {
    savePlayback();
  }, [lesson, playback.step, playback.epoch, playback.playing, playback.interrupted, selectedCell]);
  useEffect(() => {
    if (!playback.playing) return;
    const epoch = playback.epoch;
    let frame = 0,
      last = -1, checkpoint = 0;
    const update = () => {
      const audio = audioRef.current;
      if (
        audio &&
        epochRef.current === epoch &&
        !audio.paused &&
        mounted.current && audio.currentTime !== last
      ) {
        last = audio.currentTime;
        audioPosition.current = audio.currentTime;
        clockSample.current = { at_ms: performance.now(), media_time: audio.currentTime };
        // Commit board actions and the follow-up geometry layout in this media
        // frame. Deferred React scheduling previously left arrows/text behind.
        flushSync(() => {
          setMouthOpen((waveform[Math.floor(audio.currentTime * 20)] || 0) > 0.015);
          dispatch({ type: "tick", epoch,
            progress: audio.duration ? audio.currentTime / audio.duration : 0 });
        });
        if (performance.now() - checkpoint >= 250) { savePlayback(); checkpoint = performance.now(); }
      }
      frame = requestAnimationFrame(update);
    };
    frame = requestAnimationFrame(update);
    return () => cancelAnimationFrame(frame);
  }, [playback.playing, playback.epoch, audioUrl, waveform]);
  useEffect(() => {
    audioRef.current?.pause();
    setAudioUrl(undefined);
    setMouthOpen(false);
    setAudioLoading(false);
    return () => {
      const pending = speechRequest.current;
      if (!pending?.completed) void cancelSpeechRequest(pending).catch(() => {});
      speechRequest.current = undefined;
    };
  }, [lesson?.lesson_id, playback.step]);
  useLayoutEffect(() => {
    mounted.current = true;
    continuousRef.current = restoredIntent.current.continuous;
    resumeOnce.current = restoredIntent.current.once;
    return () => {
      mounted.current = false;
      playIntent.current++;
      autoPlayEpoch.current = undefined;
      const audio = lastAudio.current;
      const current = snapshot.current;
      if (audio && audio.dataset.stepId === current.lesson?.steps[current.playback.step]?.id)
        audioPosition.current = audio.currentTime;
      if (playbackStatus.current === "playing") playbackStatus.current = "paused";
      savePlayback();
      audio?.pause();
      nextCached.current.clear();
      for (const request of ownedSpeechRequests.current) void cancelSpeechRequest(request).catch(() => {});
      savedSupplementRequest.current?.abort();
      interruptSequence.current++;
      continuousRef.current = false;
      epochRef.current++;
    };
  }, []);
  useEffect(() => {
    nextCached.current.clear();
    savedSupplementRequest.current?.abort();
    return () => { nextCached.current.clear(); savedSupplementRequest.current?.abort(); };
  }, [lesson]);
  useEffect(() => {
    if ((!continuous && !resumeOnce.current) || playback.interrupted || !lesson || !speechAvailable)
      return;
    const key = `${lesson.lesson_id}:${playback.step}:${playback.epoch}`;
    if (autoAttempt.current === key) return;
    autoAttempt.current = key;
    // Wait for restore's epoch before preparing a unit.
    if (!playback.epoch) return;
    void prepareAudio(true);
  }, [
    continuous,
    lesson?.lesson_id,
    playback.step,
    playback.epoch,
    playback.interrupted,
  ]);
  useEffect(
    () => () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    },
    [audioUrl],
  );
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.muted = muted;
      audioRef.current.playbackRate = speed;
    }
  }, [muted, speed, audioUrl]);
  useLayoutEffect(() => {
    const stage = stageRef.current;
    if (!stage || !scene) return;
    const position = () => {
      if (epochRef.current !== playback.epoch) return;
      const root = stage.getBoundingClientRect();
      const elements = Array.from(
        stage.querySelectorAll<HTMLElement>("[data-board-element]"),
      );
      const locate = (id: string) =>
        elements
          .find((e) => e.dataset.boardElement === id)
          ?.getBoundingClientRect();
      const targetElement = elements.find(
        (element) => element.dataset.boardElement === step?.gesture.target_element_id,
      );
      const target = targetElement?.getBoundingClientRect();
      const equationTarget = equationGlyphPoint(targetElement);
      const hand = handRef.current?.getBoundingClientRect();
      const figure = figureRef.current?.getBoundingClientRect();
      const indicatedCellId =
        (selectedCell && selectedCell.table_element_id === step?.gesture.target_element_id ? selectedCell.cell_id : undefined) ||
        scene.highlights.find(
          (highlight) =>
            highlight.cell_ids?.length &&
            highlight.target_element_id === step?.gesture.target_element_id,
        )?.cell_ids?.[0];
      const cellElement = indicatedCellId
        ? Array.from(
            targetElement?.querySelectorAll<HTMLElement>("[data-cell-id]") || [],
          ).find((element) => element.dataset.cellId === indicatedCellId)
        : undefined;
      const tableScroll = cellElement?.closest<HTMLElement>(".table-scroll");
      if (cellElement && tableScroll && !playback.interrupted) {
        // Reveal a changed target or layout inside its table only. Ordinary
        // user scroll events update the pointer without pulling the table back.
        const layoutKey = [
          playback.epoch,
          step?.gesture.target_element_id,
          indicatedCellId,
          innerWidth,
          innerHeight,
          tableScroll.clientWidth,
          getComputedStyle(cellElement).fontSize,
        ].join(":");
        if (visibleCellTarget.current !== layoutKey) {
          visibleCellTarget.current = layoutKey;
          const clip = tableScroll.getBoundingClientRect();
          const cell = cellElement.getBoundingClientRect();
          const left = clip.left + tableScroll.clientLeft;
          const right = left + tableScroll.clientWidth;
          const margin = 4;
          let shift = 0;
          if (cell.width + margin * 2 > tableScroll.clientWidth)
            shift =
              cell.left + cell.width / 2 - (left + tableScroll.clientWidth / 2);
          else if (cell.right > right - margin)
            shift = cell.right - right + margin;
          else if (cell.left < left + margin) shift = cell.left - left - margin;
          if (shift)
            tableScroll.scrollLeft = Math.max(
              0,
              Math.min(
                tableScroll.scrollWidth - tableScroll.clientWidth,
                tableScroll.scrollLeft + shift,
              ),
            );
        }
      } else if (!cellElement) visibleCellTarget.current = "";
      const selectedTarget = cellElement?.getBoundingClientRect();
      const targetPoint =
        step?.gesture.kind === "write" && pen && !equationTarget
          ? pen
          : selectedTarget
            ? {
                x: selectedTarget.left + selectedTarget.width / 2,
                y: selectedTarget.top + selectedTarget.height / 2,
              }
            : equationTarget
              ? equationTarget
              : target
              ? {
                  x: target.right - 14,
                  y: target.top + Math.min(24, target.height / 2),
                }
              : null;
      const arm =
        targetPoint && figure && !customAvatar
          ? aimAvatarArm(targetPoint, figure)
          : null;
      setArmAngle(arm?.angle ?? 0);
      const nextPointer =
        targetPoint && hand
          ? {
              x1: (arm?.handX ?? hand.left + 5) - root.left,
              y1: (arm?.handY ?? hand.top + 5) - root.top,
              x2: targetPoint.x - root.left,
              y2: targetPoint.y - root.top,
            }
          : null;
      setPointer(previous => JSON.stringify(previous) === JSON.stringify(nextPointer) ? previous : nextPointer);
      const nextArrows = scene.arrows.flatMap((a) => {
          const from = locate(a.from_element_id),
            to = locate(a.to_element_id);
          return from && to
            ? [
                {
                  id: a.element_id,
                  x1: from.right - root.left,
                  y1: from.top - root.top + from.height / 2,
                  x2: to.left - root.left,
                  y2: to.top - root.top + to.height / 2,
                },
              ]
            : [];
        });
      setArrows(previous => JSON.stringify(previous) === JSON.stringify(nextArrows) ? previous : nextArrows);
    };
    position();
    const observer = new ResizeObserver(position);
    observer.observe(stage);
    stage
      .querySelectorAll("[data-board-element]")
      .forEach((e) => observer.observe(e));
    window.addEventListener("resize", position);
    document.fonts.addEventListener("loadingdone", position);
    stage.addEventListener("scroll", position, true);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", position);
      document.fonts.removeEventListener("loadingdone", position);
      stage.removeEventListener("scroll", position, true);
    };
  }, [
    scene,
    step,
    customAvatar,
    selectedCell,
    pen,
    playback.epoch,
    playback.interrupted,
  ]);
  useLayoutEffect(() => {
    const stage = stageRef.current, audio = audioRef.current;
    if (!stage || !scene || !mounted.current) return;
    const ids = Array.from(stage.querySelectorAll<HTMLElement>("[data-board-element]")).map(e => e.dataset.boardElement);
    const arrowIds = Array.from(stage.querySelectorAll<SVGElement>("[data-board-arrow]")).map(e => e.dataset.boardArrow);
    const signature = JSON.stringify([playback.epoch, playback.step, ids, arrowIds]);
    if (signature === committedScene.current) return;
    committedScene.current = signature;
    event("scene_commit", { board_element_ids: ids, arrow_ids: arrowIds,
      media_time: audio?.currentTime ?? audioPosition.current, progress: playback.progress,
      clock_sample: clockSample.current, commit_at_ms: performance.now() });
  }, [scene, arrows, playback.epoch]);
  async function play() {
    if (!audioUrl || !mounted.current) return;
    const intent = ++playIntent.current;
    const epoch = epochRef.current,
      audio = audioRef.current;
    if (audio && (audio.ended || playbackStatus.current === "completed")) {
      audio.currentTime = 0;
      audioPosition.current = 0;
    }
    playbackStatus.current = "playing";
    dispatch({ type: "play" });
    try {
      await audio?.play();
      if (!mounted.current || epoch !== epochRef.current || audio !== audioRef.current || intent !== playIntent.current)
        audio?.pause();
    } catch {
      if (!mounted.current || epoch !== epochRef.current || intent !== playIntent.current) return;
      playbackStatus.current = "paused";
      dispatch({ type: "pause" });
      setAudioError(
        "브라우저가 음성 재생을 허용하지 않았습니다. 재생 버튼을 다시 눌러 주세요.",
      );
    }
  }
  function pause() {
    if (playbackStatus.current !== "completed") playbackStatus.current = "paused";
    savedSupplementRequest.current?.abort();
    resumeOnce.current = false;
    playIntent.current++;
    autoPlayEpoch.current = undefined;
    nextCached.current.clear();
    continuousRef.current = false;
    setContinuous(false);
    audioRef.current?.pause();
    setMouthOpen(false);
    dispatch({ type: "pause" });
  }
  function navigate(type: "next" | "previous") {
    pause();
    playbackStatus.current = "paused";
    setSelectedCell(null);
    audioPosition.current = 0;
    dispatch({ type, total: lesson?.steps.length });
  }
  async function interrupt() {
    if (!question.trim() || !lesson || interrupting) return;
    const sequence = ++interruptSequence.current;
    savedSupplementRequest.current?.abort();
    nextCached.current.clear();
    event("interruption_submitted", {
      selected_cell_id: selectedCell?.cell_id,
    });
    continuousRef.current = false;
    playbackStatus.current = "interrupted";
    setContinuous(false);
    autoPlayEpoch.current = undefined;
    epochRef.current++;
    audioRef.current?.pause();
    event("interruption_stopped", {
      audio_paused: audioRef.current?.paused ?? true,
    });
    setMouthOpen(false);
    dispatch({ type: "interrupt" });
    const context = {
      lesson_id: lesson.lesson_id,
      step: playback.step,
      progress: playback.progress,
      element_id: step?.gesture.target_element_id,
      board_snapshot: scene,
      selected_cell: selectedCell,
      problem_revision: lesson.problem_revision,
      audio_position: audioRef.current?.currentTime ?? audioPosition.current,
      audio_paused: true,
      student_lesson: studentMode,
      hypothesis:
        hypothesis && selectedCell
          ? {
              kind: "all_null",
              table: selectedCell.table_name || selectedCell.table_element_id,
              column: selectedCell.column_name || selectedCell.column_id,
            }
          : undefined,
    };
    setInterrupting(true);
    try {
      await cancelAudio();
      if (sequence === interruptSequence.current) {
        if (replayOnly)
          setAudioError("저장된 수업을 멈췄습니다. 질문은 보존했으며 새 답변이나 음성은 생성하지 않았습니다. 연결된 저장 보충 설명이 있으면 해당 버튼으로 들을 수 있습니다.");
        else onInterrupt(question, context);
      }
    } catch (error) {
      setAudioError(
        `기존 음성 작업의 중지를 확인하지 못해 질문을 보존했습니다. ${errorText(error)}`,
      );
    } finally {
      if (sequence === interruptSequence.current) setInterrupting(false);
    }
    // Keep the local question until an explicit next edit, including a server 409.
  }
  async function cancelAudio() {
    autoPlayEpoch.current = undefined;
    setAudioLoading(false);
    await Promise.all([...ownedSpeechRequests.current].map(request => cancelSpeechRequest(request)));
  }
  useEffect(() => {
    onRegisterStop?.(async () => {
      event("lesson_return_requested", { replay_only: replayOnly });
      pause();
      epochRef.current++;
      dispatch({ type: "interrupt" });
      event("lesson_return_stopped", { audio_paused: audioRef.current?.paused ?? true, replay_only: replayOnly });
      await cancelAudio();
    });
    return () => onRegisterStop?.(null);
  }, [onRegisterStop, playback.epoch]);
  function prefetchNext() {
    if (!mounted.current || !continuousRef.current || !lesson || playback.interrupted) return;
    const next = lesson.steps[playback.step + 1];
    if (!next) return;
    const key = `${lessonRecordId}:${next.id}`;
    const trace = (type: string, detail: Record<string, unknown> = {}) =>
      event(type, { ...detail, step_id: next.id, step: playback.step + 1, epoch: audioEpoch, prefetch: true, replay_only: replayOnly });
    nextCached.current.prepare(key, async (signal) => {
      trace("next_cache_prefetch_start");
      const pending: SpeechRequest = { controller: new AbortController() };
      ownedSpeechRequests.current.add(pending);
      const abort = () => { if (!pending.completed) void cancelSpeechRequest(pending).catch(() => {}); };
      signal.addEventListener("abort", abort, { once: true });
      try {
        // A resumed lesson cannot replace an unconfirmed prior cancellation.
        if (!nextSpeechRequest.current?.completed) await cancelSpeechRequest(nextSpeechRequest.current);
        signal.throwIfAborted();
        nextSpeechRequest.current = pending;
        const unit = await prepareNextSpeech(lessonRecordId, next.id, lesson, pending, trace,
          studentMode && !replayOnly && speechAvailable ? () => {
            if (nextGenerationAttempts.current.has(key))
              throw new Error("이미 시도한 다음 음성 작업은 자동으로 다시 생성하지 않습니다. 현재 칠판과 자막을 보존합니다.");
            nextGenerationAttempts.current.add(key);
          } : undefined);
        signal.throwIfAborted();
        trace("next_cache_prefetch_ready", { audio_id: unit.audio.audio_id, generation_requested: !!unit.generationRequested, generated: unit.generated ?? null });
        return unit;
      } finally { signal.removeEventListener("abort", abort); }
    });
  }
  async function openSavedSupplement() {
    if (!onSavedSupplement || !lesson || interrupting) return;
    const wasPlaying = !!audioRef.current && !audioRef.current.paused && !audioRef.current.ended;
    const wasContinuous = continuousRef.current;
    const context = {
      step: playback.step, progress: playback.progress, selected_cell: selectedCell,
      audio_position: audioRef.current?.currentTime ?? audioPosition.current,
      replay_only: true, replay_playing: wasPlaying, replay_continuous: wasContinuous,
    };
    event("saved_supplement_requested", context);
    const sequence = ++interruptSequence.current;
    pause();
    event("saved_supplement_stopped", { audio_paused: audioRef.current?.paused ?? true });
    const controller = new AbortController();
    savedSupplementRequest.current = controller;
    autoPlayEpoch.current = undefined;
    epochRef.current++;
    dispatch({ type: "interrupt" });
    setInterrupting(true);
    try {
      await cancelAudio();
      controller.signal.throwIfAborted();
      if (sequence === interruptSequence.current) await onSavedSupplement(context, controller.signal);
    } catch (error) { if (!controller.signal.aborted) setAudioError(errorText(error)); }
    finally {
      if (savedSupplementRequest.current === controller) savedSupplementRequest.current = undefined;
      if (sequence === interruptSequence.current) setInterrupting(false);
    }
  }
  async function prepareAudio(autoplay = false) {
    if (!mounted.current || !lesson || audioLoading) return;
    setAudioLoading(true);
    setAudioError("");
    const epoch = playback.epoch,
      intent = playIntent.current,
      pending: SpeechRequest = {
        controller: new AbortController(),
        id: undefined as string | undefined,
      };
    speechRequest.current = pending;
    ownedSpeechRequests.current.add(pending);
    try {
      if (step) {
        const trace = (type: string, detail: Record<string, unknown> = {}) => event(type, { ...detail, epoch, replay_only: replayOnly });
        let unit: PreparedSpeech | undefined;
        try {
          unit = await nextCached.current.take(`${lessonRecordId}:${step.id}`, pending.controller.signal);
        } catch (error) {
          // Only cache-only paths reach this fallback; failed synthesis stays a
          // hard error and cannot silently generate again after transition.
          if (replayOnly || !(error instanceof CacheMissError)) throw error;
        }
        const prefetched = !!unit;
        if (unit) {
          const current = await cachedStep(lessonRecordId, step.id, lesson, pending.controller.signal, trace);
          if (!sameCachedSpeech(unit.audio, current))
            throw new Error("문제·판서·음성이 바뀌어 미리 준비한 음성을 폐기했습니다. 새 음성은 생성하지 않았습니다.");
        } else {
          // Initial and resumed student clips use the same current-plan check
          // as saved playback. A cache hit needs no preceding all-step scan.
          try {
            unit = await prepareCachedSpeech(lessonRecordId, step.id, lesson, pending.controller.signal, trace);
          } catch (error) {
            // Only an explicitly absent clip under a valid current binding may
            // enter the existing bounded synthesis path. Corruption, a changed
            // plan, unavailable speech and saved replay remain hard stops.
            if (replayOnly || !(error instanceof CacheMissError) || !error.generationAllowed) throw error;
          }
        }
        if (unit) {
          if (!mounted.current || epoch !== epochRef.current || pending.controller.signal.aborted) return;
          setWaveform([]);
          setAudioUrl(URL.createObjectURL(unit.blob));
          setAudioEpoch(epoch);
          autoPlayEpoch.current = autoplay && intent === playIntent.current && (continuousRef.current || resumeOnce.current) ? epoch : undefined;
          resumeOnce.current = false;
          void unit.waveform.then((peaks) => {
            if (mounted.current && epoch === epochRef.current && !pending.controller.signal.aborted) setWaveform(peaks);
          });
          trace("speech_ready", { cached: unit.generationRequested ? unit.generated === undefined ? null : !unit.generated : true,
            lesson_audio_already_ready: true, prefetched, generation_requested: !!unit.generationRequested,
            generated_ahead: unit.generated ?? null, audio_id: unit.audio.audio_id, binding_fingerprint: unit.audio.binding_fingerprint });
          return;
        }
      }
      let result = await api<any>(`/lessons/${lessonRecordId}/speech`, {
        signal: pending.controller.signal,
      });
      let audio = result.steps?.find(
        (value: any) => value.step_id === step?.id,
      );
      if (!audio && result.binding_fingerprint && step) {
        // Recheck a missing current unit against the visible board before any
        // generation, including a cache that was missing during prefetch.
        try {
          audio = await cachedStep(lessonRecordId, step.id, lesson, pending.controller.signal,
            (type, detail) => event(type, { ...detail, epoch, replay_only: false }));
        } catch (error) {
          if (!(error instanceof CacheMissError)) throw error;
        }
      }
      if (!audio) {
        const budget = await api<any>("/resources/budget", {
          signal: pending.controller.signal,
        });
        pending.controller.signal.throwIfAborted();
        const missing = lesson.steps.filter(
          (unit) =>
            !result.steps?.some((cached: any) => cached.step_id === unit.id),
        ).length;
        if (budget.enabled && budget.new_audio_remaining < 1)
          throw new Error(
            "새 음성 생성 한도를 모두 사용했습니다. 현재 칠판과 자막을 보존합니다.",
          );
        pending.creation = post(`/lessons/${lessonRecordId}/speech`, {
          voice: "default",
          // Small verified plans share one sequential model load. Larger
          // legacy lessons retain the bounded current-unit path.
          ...(autoplay ||
          lesson.steps.length > 4 ||
          (budget.enabled && budget.new_audio_remaining < missing)
            ? { step_id: step?.id }
            : {}),
          request_id: crypto.randomUUID(),
        });
        const started = await pending.creation;
        pending.id = started.job_id;
        if (!mounted.current || pending.controller.signal.aborted || epoch !== epochRef.current) {
          await cancelSpeechRequest(pending);
          return;
        }
        // A complete verified clip can play while later units are prepared.
        // The job remains cancellable; no unverified partial audio is played.
        while (!audio) {
          pending.controller.signal.throwIfAborted();
          const [state, next] = await Promise.all([
            api<any>(`/jobs/${started.job_id}`, {
              signal: pending.controller.signal,
            }),
            api<any>(`/lessons/${lessonRecordId}/speech`, {
              signal: pending.controller.signal,
            }),
          ]);
          audio = next.steps?.find((value: any) => value.step_id === step?.id);
          if (!activeJob(state)) {
            // Keep the completed owner ID for explicit stop/unmount cleanup
            // of an idle reusable worker; the server rejects stale owners.
            pending.completed = true;
            if (!audio)
              throw new Error(
                state.error || "현재 단계의 음성 준비가 완료되지 않았습니다.",
              );
          }
          if (!audio) await new Promise((resolve) => setTimeout(resolve, 350));
        }
      }
      if (!mounted.current || epoch !== epochRef.current || pending.controller.signal.aborted)
        return;
      if (!audio?.audio_url)
        throw new Error("단계 음성 파일을 찾을 수 없습니다.");
      if (audio.binding_fingerprint)
        audio = await validateVisibleSpeech(audio, lessonRecordId, step!.id, lesson, pending.controller.signal, (type, detail) => event(type, { ...detail, epoch }));
      const path = audio.binding_fingerprint
        ? scopedAudioPath(audio, lessonRecordId, step!.id)
        : audio.audio_url.replace(/^\/api/, "");
      if (!audio.binding_fingerprint && !/^\/audio\/[a-f0-9]{64}$/.test(path))
        throw new Error("지원하지 않는 오디오 주소입니다.");
      const fetchStart = performance.now();
      event("audio_fetch_start", { epoch, audio_id: audio.audio_id });
      const blob = await protectedBlob(path, pending.controller.signal);
      event("audio_fetch_end", { epoch, elapsed_ms: performance.now() - fetchStart, audio_id: audio.audio_id });
      if (!mounted.current || epoch !== epochRef.current || pending.controller.signal.aborted) return;
      setWaveform([]);
      void decodeWaveform(blob, (type, detail) => event(type, { ...detail, epoch })).then((peaks) => {
        if (mounted.current && epoch === epochRef.current && !pending.controller.signal.aborted) setWaveform(peaks);
      });
      if (!mounted.current || epoch !== epochRef.current || pending.controller.signal.aborted)
        return;
      setAudioUrl(URL.createObjectURL(blob));
      setAudioEpoch(epoch);
      autoPlayEpoch.current = autoplay && intent === playIntent.current && (continuousRef.current || resumeOnce.current) ? epoch : undefined;
        resumeOnce.current = false;
      event("speech_ready", {
        cached: audio.cache_hit === true,
        lesson_audio_already_ready: !pending.creation,
        audio_id: audio.audio_id,
      });
    } catch (error) {
      if (mounted.current && epoch === epochRef.current && !pending.controller.signal.aborted) {
        setAudioError(errorText(error));
        continuousRef.current = false;
        setContinuous(false);
        event("lesson_blocked", { reason: errorText(error) });
      }
    } finally {
      if (mounted.current && speechRequest.current === pending) {
        setAudioLoading(false);
        if (!pending.id) speechRequest.current = undefined;
      }
    }
  }
  if (!lesson)
    return (
      <div className="empty-classroom">
        <div className="eyebrow">나의 속도로, 한 단계씩</div>
        <h1>이해가 쌓이는 강의실</h1>
        <p>
          대화에서 만든 강의를 칠판과 자막으로 살펴보세요.
          <br />
          모델 없이도 설명용 예시로 판서와 이동을 확인할 수 있습니다.
        </p>
        <div className="empty-board">
          <div>
            <span className="chalk-small">SQL · NULL과 집계 함수</span>
            <div className="chalk-formula">COUNT(*) ≠ COUNT(급여)</div>
            <p>전체 행을 셀까요, 값이 있는 행을 셀까요?</p>
          </div>
          <Avatar />
        </div>
        <button className="button primary" onClick={onDemo}>
          <Play size={16} />
          설명용 예시 열기
        </button>
        <small>데모는 실제 모델이 생성한 답변이 아닙니다.</small>
      </div>
    );
  return (
    <div
      className="classroom"
      data-lesson-record-id={lessonRecordId}
      data-lesson-id={lesson.lesson_id}
      data-step-id={step?.id}
      data-playback-epoch={playback.epoch}
      data-playback-status={playbackStatus.current}
      data-student-mode={studentMode}
      data-replay-only={replayOnly}
    >
      <div className="section-heading">
        <div>
          <div className="eyebrow">단계별로 함께 이해해요</div>
          <h1>{lesson.title}</h1>
          <p>{lesson.goal}</p>
          {replayOnly && <p role="status">저장된 수업 재생 · 기존 문제와 검증된 음성만 재생합니다. 새 답변·음성 생성은 하지 않습니다.</p>}
        </div>
        <span className="badge muted-badge">
          {lesson.provenance === "demo_fixture"
            ? "설명용 예시"
            : lesson.provenance === "tool_derived"
              ? "계산 근거 연결 · 설명 검토 범위 확인"
              : "생성 강의 · 정확성 미검증"}{" "}
          · {lesson.steps.length}단계
        </span>
      </div>
      <div className="lecture-layout">
        <div className="lecture-main">
          <div className="board-toolbar">
            <span>
              <span className="live-dot" />
              오늘의 칠판
            </span>
            <span>
              {playback.step + 1} / {lesson.steps.length} 단계
            </span>
          </div>
          <div className="chalk-stage" ref={stageRef}>
            <div className="chalk-board" aria-label="강의 판서">
              <div className="board-step-heading">
                <span>0{playback.step + 1}</span>
                {step?.title}
              </div>
              {scene?.elements.map((element) => {
                const highlight = scene.highlights.find(
                  (h) => h.target_element_id === element.element_id,
                );
                return (
                  <Element
                    key={element.element_id}
                    element={element}
                    highlightedRows={highlight?.row_indices}
                    highlightedColumns={highlight?.column_indices}
                    highlightStyle={highlight?.style}
                    highlightedCells={highlight?.cell_ids}
                    selectedCell={selectedCell}
                    onSelectCell={setSelectedCell}
                  />
                );
              })}
              <BoardShapes
                shapes={scene?.shapes || []}
                writing={
                  step?.gesture.kind === "write" &&
                  playback.playing &&
                  !playback.interrupted
                }
                onPen={setPen}
              />
            </div>
            <div className="teacher-area">
              <div className="teacher-label">
                {customAvatar ? "사용자 PNG" : "기본 아바타"}
              </div>
              <div className="teacher-figure" ref={figureRef}>
                <Avatar
                  custom={customAvatar}
                  speaking={mouthOpen && playback.playing}
                  armAngle={playback.interrupted ? 0 : armAngle}
                  gesture={playback.interrupted ? "idle" : step?.gesture.kind}
                />
                <div className="hand-anchor" ref={handRef} />
              </div>
              <span>
                {playback.interrupted
                  ? "질문을 듣고 있어요"
                  : step?.gesture.kind === "point" ||
                      step?.gesture.kind === "write"
                    ? "여기를 함께 보세요"
                    : "천천히 살펴보세요"}
              </span>
            </div>
            <svg className="pointer-layer" aria-hidden="true">
              <defs>
                <marker
                  id="board-arrow"
                  markerWidth="7"
                  markerHeight="7"
                  refX="5"
                  refY="3"
                  orient="auto"
                >
                  <path d="M0 0 6 3 0 6" fill="#dfc780" />
                </marker>
              </defs>
              {pointer && !playback.interrupted && (
                <>
                  <line
                    data-testid="avatar-pointer"
                    x1={pointer.x1}
                    y1={pointer.y1}
                    x2={pointer.x2}
                    y2={pointer.y2}
                    stroke="#d6e9b0"
                    strokeWidth="2"
                    strokeDasharray="4 5"
                  />
                  <circle
                    cx={pointer.x2}
                    cy={pointer.y2}
                    r="5"
                    fill="#e6edaa"
                  />
                </>
              )}
              {arrows.map((a) => (
                <line
                  key={a.id}
                  data-board-arrow={a.id}
                  {...a}
                  stroke="#dfc780"
                  strokeWidth="2"
                  markerEnd="url(#board-arrow)"
                />
              ))}
            </svg>
          </div>
          <div className="caption-box">
            <span className="caption-label">강의 자막</span>
            <p aria-live="polite">{step?.speech}</p>
          </div>
          <div className="playback-controls">
            <button
              className="icon-button"
              aria-label="이전 단계"
              disabled={playback.step === 0}
              onClick={() => navigate("previous")}
            >
              <ArrowLeft size={19} />
            </button>
            <button
              className="button primary"
              onClick={
                playback.playing
                  ? pause
                  : audioUrl
                    ? play
                    : () => navigate("next")
              }
              disabled={!audioUrl && playback.step === lesson.steps.length - 1}
            >
              {playback.playing ? (
                <Pause size={17} />
              ) : audioUrl ? (
                <Play size={17} />
              ) : (
                <ArrowRight size={17} />
              )}{" "}
              {playback.playing
                ? "일시정지"
                : audioUrl
                  ? "음성 재생"
                  : "다음 단계"}
            </button>
            <button
              className="icon-button"
              aria-label="다음 단계"
              disabled={playback.step === lesson.steps.length - 1}
              onClick={() => navigate("next")}
            >
              <ArrowRight size={19} />
            </button>
            <span className="controls-divider" />
            <button
              className="icon-button"
              disabled={!audioUrl}
              onClick={() => setMuted(!muted)}
              aria-label={muted ? "소리 켜기" : "소리 끄기"}
            >
              {muted ? <VolumeX size={18} /> : <Volume2 size={18} />}
            </button>
            <select
              aria-label="음성 재생 속도"
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value))}
              disabled={!audioUrl}
            >
              <option value="0.75">0.75×</option>
              <option value="1">1.0×</option>
              <option value="1.25">1.25×</option>
              <option value="1.5">1.5×</option>
            </select>
            <span className="manual-label">
              {audioUrl
                ? "실제 오디오 시간 기준"
                : speechAvailable
                  ? "자막 · 수동 단계"
                  : "음성 사용 불가 · 수동 단계"}
            </span>
          </div>
          {replayOnly && speechAvailable && !continuous && (
            <button className="button secondary" disabled={audioLoading || interrupting} onClick={() => {
              if (playbackStatus.current === "completed") { audioPosition.current = 0; playbackStatus.current = "paused"; }
              dispatch({ type: "return" });
              continuousRef.current = true;
              setContinuous(true);
              autoAttempt.current = "";
              setAudioError("");
            }}>저장된 수업 이어 재생</button>
          )}
          {replayOnly && onSavedSupplement && (
            <button className="button secondary" disabled={interrupting} onClick={() => void openSavedSupplement()}>
              저장된 보충 설명 듣기
            </button>
          )}
          {speechAvailable && !audioUrl && (
            <button
              className="button secondary"
              disabled={audioLoading}
              onClick={() => void prepareAudio()}
            >
              <Volume2 size={16} />
              {audioLoading ? "음성 준비 중…" : "현재 단계 음성 준비"}
            </button>
          )}
          {audioLoading && (
            <button
              className="button secondary"
              onClick={() => {
                pause();
                void cancelAudio().catch((e) => setAudioError(errorText(e)));
              }}
            >
              음성 준비 중지
            </button>
          )}
          {audioError && (
            <div role="alert" className="notice error">
              {audioError}
            </div>
          )}
          {audioUrl && (
            <audio
              key={`${audioUrl}:${audioEpoch}`}
              ref={(node) => { audioRef.current = node; if (node) lastAudio.current = node; }}
              src={audioUrl}
              data-lesson-record-id={lessonRecordId}
              data-step-id={step?.id}
              data-playback-epoch={audioEpoch}
              onLoadedMetadata={(event) => {
                if (!mounted.current || event.currentTarget !== audioRef.current || audioEpoch !== epochRef.current) return;
                event.currentTarget.currentTime = Math.min(
                  audioPosition.current,
                  event.currentTarget.duration || 0,
                );
                if (
                  autoPlayEpoch.current === audioEpoch
                ) {
                  autoPlayEpoch.current = undefined;
                  void play();
                }
              }}
              onPlaying={(mediaEvent) => {
                if (!mounted.current || mediaEvent.currentTarget !== audioRef.current || audioEpoch !== epochRef.current || playbackStatus.current !== "playing") {
                  mediaEvent.currentTarget.pause();
                  return;
                }
                event("audio_playing", {
                  audio_position: mediaEvent.currentTarget.currentTime,
                  replay_only: replayOnly,
                });
                prefetchNext();
                if (lastEnded.current !== undefined) {
                  event("stage_gap", {
                    gap_ms: performance.now() - lastEnded.current,
                  });
                  lastEnded.current = undefined;
                }
              }}
              onPause={(mediaEvent) => {
                if (!mounted.current || mediaEvent.currentTarget !== audioRef.current) return;
                event("audio_pause", {
                  audio_position: mediaEvent.currentTarget.currentTime,
                  audio_epoch: audioEpoch,
                });
              }}
              onTimeUpdate={(event) => {
                if (!mounted.current || event.currentTarget !== audioRef.current || audioEpoch !== epochRef.current) return;
                const audio = event.currentTarget;
                audioPosition.current = audio.currentTime;
                setMouthOpen(
                  playback.playing &&
                    (waveform[Math.floor(audio.currentTime * 20)] || 0) > 0.015,
                );
                dispatch({
                  type: "tick",
                  epoch: audioEpoch,
                  progress: audio.duration
                    ? audio.currentTime / audio.duration
                    : 0,
                });
              }}
              onEnded={(mediaEvent) => {
                if (!mounted.current || mediaEvent.currentTarget !== audioRef.current || audioEpoch !== epochRef.current) return;
                audioPosition.current = mediaEvent.currentTarget.currentTime;
                playbackStatus.current = playback.step + 1 >= lesson.steps.length ? "completed" : "paused";
                setMouthOpen(false);
                event("audio_ended");
                dispatch({ type: "ended", epoch: audioEpoch });
                if (playback.step + 1 >= lesson.steps.length)
                  void cancelAudio().catch(error => setAudioError(errorText(error)));
                if (continuousRef.current && !playback.interrupted) {
                  if (playback.step + 1 < lesson.steps.length) {
                    lastEnded.current = performance.now();
                    audioPosition.current = 0;
                    setSelectedCell(null);
                    epochRef.current++;
                    dispatch({
                      type: "seek",
                      step: playback.step + 1,
                      progress: 0,
                    });
                  } else {
                    continuousRef.current = false;
                    setContinuous(false);
                    onComplete?.();
                  }
                }
              }}
            />
          )}
          {playback.interrupted && (
            <div className="notice">
              <span>강의를 멈추고 현재 칠판을 보존했습니다.</span>
              <button
                className="text-button"
                onClick={() => {
                  dispatch({ type: "return" });
                  setAudioEpoch(epochRef.current + 1);
                  onResume?.();
                }}
              >
                <CornerUpLeft size={15} />
                {isSupplement
                  ? "현재 보충 설명 계속 보기"
                  : "원래 강의로 돌아가기"}
              </button>
            </div>
          )}
          <form
            className="interrupt-form"
            onSubmit={(e) => {
              e.preventDefault();
              interrupt();
            }}
          >
            <BookOpen size={19} />
            <input
              aria-label="강의 중 질문"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onCompositionStart={() => (composing.current = true)}
              onCompositionEnd={() => (composing.current = false)}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !shouldSubmit(e.nativeEvent, composing.current)
                )
                  e.preventDefault();
              }}
              placeholder="잠깐, 이 부분이 궁금해요…"
            />
            <button
              className="icon-button accent"
              aria-label="강의 멈추고 질문"
              disabled={!question.trim() || interrupting}
              type="submit"
            >
              <Send size={17} />
            </button>
          </form>
          {selectedCell && (
            <div className="selected-cell-context">
              <span>
                선택한 셀: {selectedCell.row_index + 1}행 ·{" "}
                {selectedCell.value === null
                  ? "NULL"
                  : String(selectedCell.value)}
              </span>
              <button
                className="text-button"
                onClick={() => setSelectedCell(null)}
              >
                선택 해제
              </button>
              <label>
                <input
                  type="checkbox"
                  checked={hypothesis}
                  onChange={(event) => setHypothesis(event.target.checked)}
                />{" "}
                별도 가정: 이 열의 값을 모두 NULL로 보기
              </label>
              <small>원래 표의 값은 변경하지 않습니다.</small>
            </div>
          )}
        </div>
        <aside className="lesson-outline">
          <div className="panel-label">강의 순서</div>
          {lesson.steps.map((s, i) => (
            <button
              className={`step-link ${i === playback.step ? "current" : ""}`}
              key={s.id}
              onClick={() => {
                pause();
                playbackStatus.current = "paused";
                setSelectedCell(null);
                audioPosition.current = 0;
                dispatch({ type: "seek", step: i });
              }}
            >
              <span className="step-number">
                {i < playback.step ? (
                  <Check size={13} />
                ) : (
                  String(i + 1).padStart(2, "0")
                )}
              </span>
              <span>{s.title}</span>
              {i === playback.step && <ChevronRight size={15} />}
            </button>
          ))}
          <div className="lesson-note">
            <span className="panel-label">확인된 범위</span>
            <p>{lesson.verification.scope}</p>
            {lesson.verification.limitations.map((limit, i) => (
              <p className="fine-print" key={i}>
                {limit}
              </p>
            ))}
          </div>
          <button
            className="text-button"
            onClick={() => {
              pause();
              playbackStatus.current = "paused";
              setSelectedCell(null);
              audioPosition.current = 0;
              dispatch({ type: "seek", step: 0 });
            }}
          >
            <RefreshCw size={14} />
            처음부터 보기
          </button>
        </aside>
      </div>
    </div>
  );
}
