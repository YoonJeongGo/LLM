import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  BookOpen,
  BrainCircuit,
  Check,
  ChevronRight,
  Copy,
  Cpu,
  FileText,
  GraduationCap,
  ImagePlus,
  KeyRound,
  Menu,
  MessageCircle,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Send,
  Settings,
  ShieldCheck,
  Square,
  Trash2,
  VolumeX,
  X,
} from "lucide-react";
import {
  activeJob,
  ApiError,
  api,
  download,
  errorText,
  list,
  post,
  setToken,
  setExecutionAllowance,
  setStudentSession,
  statusLabel,
  waitForJob,
} from "./api";
import type { Job, Message, Session } from "./api";
import { parseLesson, shouldSubmit } from "./lesson";
import type { Lesson, CellSelection } from "./lesson";
import ProblemEditor, {
  emptyProblemDraft,
  typedProblem,
} from "./ProblemEditor";
import type { ProblemDraft } from "./ProblemEditor";
import Classroom from "./Classroom";
import PhotoDialog from "./PhotoDialog";
import { Materials, Models } from "./Admin";
import Training from "./Training";
import Neural from "./Neural";
import { readAvatar, saveAvatar } from "./localAssets";
import { lessonEvent } from "./student";
import { savedSupplementMatches } from "./speechCache";
const navigation = [
  { id: "chat", label: "대화", icon: MessageCircle },
  { id: "classroom", label: "강의실", icon: GraduationCap },
  { id: "materials", label: "교육자료", icon: BookOpen },
  { id: "training", label: "학습·평가", icon: Activity },
  { id: "models", label: "모델 분석", icon: Cpu },
  { id: "neural", label: "신경망 보기", icon: BrainCircuit },
  { id: "settings", label: "설정", icon: Settings },
] as const;
type Tab = (typeof navigation)[number]["id"];
type StudentFollowup = {
  sourceLessonId: string;
  sourcePlan: Lesson;
  question: string;
  context: Record<string, any>;
};
function saved(key: string, fallback = "") {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}
function safeSave(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* Browser may disallow optional view state persistence. */
  }
}
function PlainMessage({ text }: { text: string }) {
  const blocks = text.split(/(```[\s\S]*?```)/g);
  const cells = (line: string) =>
    line
      .trim()
      .replace(/^\|/, "")
      .replace(/\|$/, "")
      .split(/(?<!\\)\|/)
      .map((cell) => cell.trim().replace(/\\\|/g, "|"));
  function prose(part: string, key: number) {
    const lines = part.split("\n"),
      elements = [];
    let paragraph: string[] = [];
    const flush = () => {
      if (paragraph.length) {
        elements.push(
          <p key={`p${elements.length}`}>{paragraph.join("\n")}</p>,
        );
        paragraph = [];
      }
    };
    for (let i = 0; i < lines.length; i++) {
      if (
        lines[i].includes("|") &&
        i + 1 < lines.length &&
        /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[i + 1])
      ) {
        flush();
        const columns = cells(lines[i]),
          rows: string[][] = [];
        i += 2;
        while (i < lines.length && lines[i].includes("|")) {
          rows.push(cells(lines[i]));
          i++;
        }
        i--;
        elements.push(
          <div className="table-scroll" key={`t${elements.length}`}>
            <table>
              <thead>
                <tr>
                  {columns.map((value, index) => (
                    <th key={index}>{value}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={index}>
                    {row.map((value, col) => (
                      <td key={col}>{value}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>,
        );
      } else paragraph.push(lines[i]);
    }
    flush();
    return <div key={key}>{elements}</div>;
  }
  return (
    <div className="message-content">
      {blocks.map((part, i) =>
        part.startsWith("```") ? (
          <pre key={i}>
            <code>{part.replace(/^```[^\n]*\n?/, "").replace(/```$/, "")}</code>
          </pre>
        ) : (
          prose(part, i)
        ),
      )}
    </div>
  );
}
export default function App() {
  const [tab, setTab] = useState<Tab>(
    (window.location.hash === "#neural"
      ? "neural"
      : navigation.some((x) => x.id === saved("edu-tab"))
        ? saved("edu-tab")
        : "chat") as Tab,
  );
  const [textScale, setTextScale] = useState(
    Math.min(2, Math.max(1, Number(saved("edu-text-scale", "1")) || 1)),
  );
  useEffect(() => {
    document.documentElement.style.fontSize = `${14 * textScale}px`;
    safeSave("edu-text-scale", String(textScale));
  }, [textScale]);
  const [sidebarOpen, setSidebarOpen] = useState(false),
    [authenticated, setAuthenticated] = useState(false),
    [connecting, setConnecting] = useState(false),
    [tokenInput, setTokenInput] = useState("");
  const [capabilities, setCapabilities] = useState<any>(),
    [model, setModel] = useState<any>(),
    [doctor, setDoctor] = useState<any>(),
    [error, setError] = useState(""),
    [info, setInfo] = useState("");
  const [sessions, setSessions] = useState<Session[]>([]),
    [sessionId, setSessionId] = useState(saved("edu-session")),
    [messages, setMessages] = useState<Message[]>([]),
    [draft, setDraft] = useState(
      saved(`edu-draft:${saved("edu-session") || "new"}`),
    );
  const [sending, setSending] = useState(false),
    [job, setJob] = useState<Job | null>(null),
    [rag, setRag] = useState(true),
    [photoOpen, setPhotoOpen] = useState(false),
    [rightPanel, setRightPanel] = useState(true),
    [lesson, setLesson] = useState<Lesson | null>(null),
    [fallback, setFallback] = useState(""),
    [customAvatar, setCustomAvatar] = useState<string>();
  const [problemDraft, setProblemDraft] = useState<ProblemDraft>(() => {
    try {
      return JSON.parse(saved("edu-problem-draft")) || emptyProblemDraft;
    } catch {
      return emptyProblemDraft;
    }
  });
  const [lessonRecord, setLessonRecord] = useState<any>(null);
  const [studentLessonId, setStudentLessonId] = useState("");
  const [replayLessonId, setReplayLessonId] = useState("");
  const [replayAutoplayId, setReplayAutoplayId] = useState("");
  const [replayResumeId, setReplayResumeId] = useState("");
  const classroomStop = useRef<(() => Promise<void>) | null>(null);
  const registerClassroomStop = useCallback((stop: (() => Promise<void>) | null) => { classroomStop.current = stop; }, []);
  const [replayBaseId, setReplayBaseId] = useState("");
  const requestedReplay = new URLSearchParams(window.location.search).get("lesson") || "";
  const requestedSupplement = new URLSearchParams(window.location.search).get("supplement") || "";
  const [photoLesson, setPhotoLesson] = useState(false);
  const [resourceBudget, setResourceBudget] = useState<any>(null);
  const [executionScope, setExecutionScope] = useState("");
  const [studentBudget, setStudentBudget] = useState<any>(null);
  const [budgetLoading, setBudgetLoading] = useState(false);
  const [budgetBusy, setBudgetBusy] = useState(false);
  const [budgetError, setBudgetError] = useState("");
  const [budgetRefresh, setBudgetRefresh] = useState(0);
  const [budgetCaps, setBudgetCaps] = useState({seconds: 300, text_requests: 2, new_audio_clips: 4, vision_requests: 0});
  const budgetStart = useRef<{ session: string; caps: string; request_id: string } | null>(null);
  const currentStudentBudget = studentBudget?.session_id === sessionId ? studentBudget : null;
  const studentBudgetReady = !!sessionId && !!currentStudentBudget && !budgetLoading && !budgetBusy;
  const studentGenerationAllowed = studentBudgetReady && currentStudentBudget.exists &&
    currentStudentBudget.state === "active" && currentStudentBudget.effective_remaining.seconds > 0;
  const developerGenerationAllowed = !!executionScope && !budgetLoading && !budgetBusy &&
    (!sessionId || (studentBudgetReady && !currentStudentBudget.exists));
  const generationAllowed = !!(studentGenerationAllowed || developerGenerationAllowed);
  const textGenerationAllowed = generationAllowed && (developerGenerationAllowed || currentStudentBudget.effective_remaining.text_requests > 0);
  const visionGenerationAllowed = generationAllowed && (developerGenerationAllowed || currentStudentBudget.effective_remaining.vision_requests > 0);
  const [editingPhotoId, setEditingPhotoId] = useState<string>();
  const [retryQuestion, setRetryQuestion] = useState<{
    content: string;
    context?: any;
  } | null>(null);
  const lessonEpoch = useRef(0);
  const [originalLecture, setOriginalLecture] = useState<{
    id: string;
    plan: Lesson;
    step: number;
    progress: number;
    selected_cell?: CellSelection | null;
    audio_position?: number;
    record: any;
    student_mode?: boolean;
    replay_only?: boolean;
    replay_playing?: boolean;
    replay_continuous?: boolean;
  } | null>(null);
  const [lessonRecordId, setLessonRecordId] = useState(""),
    [lessonGenerating, setLessonGenerating] = useState(false);
  const displayedLesson = useRef({ id: lessonRecordId, plan: lesson });
  displayedLesson.current = { id: lessonRecordId, plan: lesson };
  const lessonRequest = useRef<
    { controller: AbortController; id?: string } | undefined
  >(undefined);
  const reprocessRequestIds = useRef(new Map<string, string>());
  const activeTab = useRef(tab);
  activeTab.current = tab;
  const pendingChatJob = useRef<string | undefined>(undefined);
  const generation = useRef(0),
    composing = useRef(false),
    chatEnd = useRef<HTMLDivElement>(null),
    sessionRef = useRef(sessionId);
  sessionRef.current = sessionId;
  const busy = sending || activeJob(job);
  const demo =
    capabilities?.fixture === true ||
    (tab === "classroom" && lesson?.provenance === "demo_fixture");
  const refreshState = useCallback(async () => {
    const results = await Promise.allSettled([
      api("/capabilities"),
      api("/models"),
      api("/doctor"),
      api("/sessions"),
      api("/resources/budget"),
    ]);
    if (results[0].status === "fulfilled") setCapabilities(results[0].value);
    else throw results[0].reason;
    if (results[1].status === "fulfilled") setModel(results[1].value);
    if (results[2].status === "fulfilled") setDoctor(results[2].value);
    if (results[3].status === "fulfilled") setSessions(list(results[3].value));
    if (results[4].status === "fulfilled") setResourceBudget(results[4].value);
  }, []);
  useEffect(() => {
    safeSave("edu-tab", tab);
    setSidebarOpen(false);
    if (tab === "neural" && window.location.hash !== "#neural")
      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}${window.location.search}#neural`,
      );
    else if (tab !== "neural" && window.location.hash === "#neural")
      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}${window.location.search}`,
      );
  }, [tab]);
  useEffect(() => {
    const followHash = () => {
      if (window.location.hash === "#neural") setTab("neural");
    };
    window.addEventListener("hashchange", followHash);
    return () => window.removeEventListener("hashchange", followHash);
  }, []);
  useEffect(() => {
    if (authenticated && (tab === "models" || tab === "settings")) {
      void refreshState().catch((error) => setError(errorText(error)));
    }
  }, [tab, authenticated, refreshState]);
  useEffect(() => {
    safeSave(`edu-draft:${sessionId || "new"}`, draft);
  }, [draft, sessionId]);
  useEffect(
    () => safeSave("edu-problem-draft", JSON.stringify(problemDraft)),
    [problemDraft],
  );
  useEffect(() => {
    setStudentSession("");
    setStudentBudget(null);
    setBudgetError("");
    if (!authenticated || !sessionId) { setBudgetLoading(false); return; }
    const controller = new AbortController();
    setBudgetLoading(true);
    let timer: ReturnType<typeof setTimeout>;
    const refreshBudget = async () => {
      try {
        const value = await api(`/sessions/${sessionId}/budget`, { signal: controller.signal, studentSession: null });
        if (controller.signal.aborted || sessionRef.current !== sessionId) return;
        if (value.session_id !== sessionId) throw new Error("수업 한도 응답의 대화가 일치하지 않습니다.");
        setStudentBudget(value);
        setStudentSession(value.exists ? sessionId : "");
        if (value.exists) { setExecutionAllowance(""); setExecutionScope(""); }
        setBudgetError("");
        setBudgetLoading(false);
        if (value.exists && value.state === "active") timer = setTimeout(refreshBudget, 5000);
      } catch (error) {
        if (!controller.signal.aborted && sessionRef.current === sessionId) {
          setStudentSession(""); setStudentBudget(null); setBudgetLoading(false);
          setBudgetError(errorText(error));
        }
      }
    };
    void refreshBudget();
    return () => { controller.abort(); clearTimeout(timer); setStudentSession(""); };
  }, [authenticated, sessionId, budgetRefresh]);
  async function createStudentConversation() {
    if (!authenticated || sessionId || budgetBusy || busy || lessonGenerating) return;
    setBudgetBusy(true); setBudgetError("");
    setExecutionAllowance(""); setExecutionScope(""); setStudentSession("");
    try {
      const value = await post<Session>("/sessions", { title: "새 수업" });
      setSessions((previous) => [value, ...previous]);
      setSessionId(value.id); sessionRef.current = value.id;
    } catch (error) { setBudgetError(errorText(error)); }
    finally { setBudgetBusy(false); }
  }
  async function startStudentBudget() {
    if (!sessionId || !studentBudgetReady || currentStudentBudget.exists || busy || lessonGenerating) return;
    const selectedSession = sessionId;
    const caps = JSON.stringify(budgetCaps);
    if (!budgetStart.current || budgetStart.current.session !== selectedSession || budgetStart.current.caps !== caps)
      budgetStart.current = { session: selectedSession, caps, request_id: crypto.randomUUID() };
    setBudgetBusy(true); setBudgetError("");
    setExecutionAllowance(""); setExecutionScope(""); setStudentSession("");
    try {
      const value = await api(`/sessions/${selectedSession}/budget`, {
        method: "POST", studentSession: null,
        body: JSON.stringify({ ...budgetCaps, request_id: budgetStart.current.request_id }),
      });
      if (sessionRef.current !== selectedSession) return;
      if (value.session_id !== selectedSession || !value.exists) throw new Error("수업 한도 생성 응답을 확인할 수 없습니다.");
      setStudentBudget(value); setStudentSession(selectedSession);
      setBudgetRefresh((value) => value + 1);
    } catch (error) {
      if (sessionRef.current === selectedSession) setBudgetError(errorText(error));
    } finally { setBudgetBusy(false); }
  }
  async function closeStudentBudget() {
    if (!studentBudgetReady || !currentStudentBudget.exists || currentStudentBudget.state !== "active" || busy || lessonGenerating) return;
    const selectedSession = sessionId;
    setBudgetBusy(true); setBudgetError("");
    try {
      const value = await api(`/sessions/${selectedSession}/budget/close`, {
        method: "POST", body: "{}", studentSession: selectedSession,
      });
      if (sessionRef.current === selectedSession) { setStudentBudget(value); setBudgetRefresh((value) => value + 1); }
    } catch (error) { if (sessionRef.current === selectedSession) setBudgetError(errorText(error)); }
    finally { setBudgetBusy(false); }
  }
  useEffect(() => {
    safeSave("edu-session", sessionId);
    if (!authenticated || !sessionId) {
      setMessages([]);
      return;
    }
    let current = true;
    api(`/sessions/${sessionId}/messages`)
      .then((v) => {
        if (current) setMessages(list(v));
      })
      .catch((e) => {
        if (current) setError(errorText(e));
      });
    return () => {
      current = false;
    };
  }, [sessionId, authenticated]);
  useEffect(() => {
    chatEnd.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages]);
  useEffect(
    () => () => {
      if (customAvatar) URL.revokeObjectURL(customAvatar);
    },
    [customAvatar],
  );
  useEffect(() => {
    let alive = true;
    readAvatar()
      .then((blob) => {
        if (alive && blob?.type === "image/png" && blob.size <= 5 * 1024 * 1024)
          setCustomAvatar(URL.createObjectURL(blob));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);
  useEffect(() => {
    if (!job || !activeJob(job) || !sessionId) return;
    let alive = true,
      timer: ReturnType<typeof setTimeout>;
    // Stopping invalidates answer/lesson delivery, but this exact owned job
    // must still be observed until the server confirms a terminal state.
    const current = () => alive && pendingChatJob.current === job.id && sessionRef.current === sessionId;
    const poll = async () => {
      try {
        const [next, newMessages] = await Promise.all([
          api<Job>(`/jobs/${job.id}`),
          api(`/sessions/${sessionId}/messages`),
        ]);
        if (!current()) return;
        setJob(next);
        setMessages(list(newMessages));
        if (!activeJob(next)) pendingChatJob.current = undefined;
        if (!activeJob(next) && next.error)
          setError(
            typeof next.error === "string"
              ? next.error
              : JSON.stringify(next.error),
          );
        if (activeJob(next)) timer = setTimeout(poll, 1000);
      } catch (e) {
        if (current()) {
          setError(errorText(e));
          timer = setTimeout(poll, 3000);
        }
      }
    };
    timer = setTimeout(poll, 500);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [job?.id, job?.state, job?.status, sessionId]);
  async function connect(token = tokenInput) {
    setConnecting(true);
    setError("");
    setToken(token);
    try {
      await refreshState();
      setAuthenticated(true);
      const previousLesson = /^[a-zA-Z0-9_-]{1,128}$/.test(requestedReplay) ? requestedReplay : saved("edu-lesson");
      if (previousLesson) {
        const connectionEpoch = ++lessonEpoch.current;
        try {
          const existing = await api(`/lessons/${previousLesson}`);
          if (connectionEpoch !== lessonEpoch.current) return;
          setLessonRecord(existing);
          setLessonRecordId(existing.id);
          setReplayLessonId(requestedReplay ? existing.id : "");
          setReplayBaseId(requestedReplay ? existing.id : "");
          setReplayAutoplayId("");
          setReplayResumeId("");
          setStudentLessonId("");
          if (requestedReplay) { setTab("classroom"); safeSave("edu-lesson", existing.id); }
          if (existing.valid === false) {
            setLesson(null);
            setFallback(
              existing.invalidated_reason ||
                "원문이 수정되어 이전 강의가 무효화되었습니다.",
            );
          } else if (existing.plan) {
            setLesson(parseLesson(existing.plan));
            setFallback("");
          } else {
            setLesson(null);
            setFallback(existing.fallback_text || "");
          }
        } catch {
          /* Last lesson can have been deleted; leave the current view usable. */
        }
      }
      setTokenInput("");
      setInfo("이 PC의 로컬 서버에 연결했습니다.");
    } catch (e) {
      setToken("");
      setAuthenticated(false);
      setError(errorText(e));
    } finally {
      setConnecting(false);
    }
  }
  async function tokenFile(file?: File) {
    if (file) await connect(await file.text());
  }
  function selectSession(id: string) {
    if (busy || budgetBusy || lessonGenerating) {
      setInfo("현재 응답을 중지한 후 다른 대화를 열어 주세요.");
      return;
    }
    generation.current++;
    setJob(null);
    setStudentSession(""); setStudentBudget(null);
    sessionRef.current = id;
    setSessionId(id);
    setDraft(saved(`edu-draft:${id || "new"}`));
    setTab("chat");
    setError("");
  }
  async function send(content = draft, context?: unknown, asLesson = false) {
    if (!content.trim() || busy || !authenticated) return;
    if (!textGenerationAllowed) { setError("선택한 대화에서 수업 한도를 확인하고 시작해 주세요. 종료되거나 소진된 한도에서는 새 설명을 만들 수 없습니다."); return; }
    // Capture the interrupted source before awaiting or scheduling React state.
    // originalLecture is set by interrupt() in the same event and may be stale here.
    const followup: StudentFollowup | undefined = asLesson && context && lesson
      ? { sourceLessonId: lessonRecordId, sourcePlan: lesson, question: content,
          context: structuredClone(context as Record<string, any>) }
      : undefined;
    if (asLesson && context && (!followup || followup.context.lesson_id !== followup.sourceLessonId ||
        followup.context.problem_revision !== followup.sourcePlan.problem_revision)) {
      setError("질문할 원래 수업과 현재 칠판이 일치하지 않습니다. 현재 단계에서 다시 질문해 주세요.");
      return;
    }
    const expected = ++generation.current;
    lessonEvent("question_submitted", {
      input_kind: context ? "followup" : "text",
      student_mode: asLesson,
    });
    setSending(true);
    setError("");
    setInfo("");
    try {
      const problem = context
        ? undefined
        : typedProblem(problemDraft, content.trim());
      let id = sessionId;
      let current = sessions.find((s) => s.id === id);
      if (!id) {
        current = await post<Session>("/sessions", {
          title: content.slice(0, 38),
        });
        id = current.id;
        setSessions((prev) => [current!, ...prev]);
        setSessionId(id);
        sessionRef.current = id;
      }
      if (expected !== generation.current) return;
      const response = await post(`/sessions/${id}/messages`, {
        content: content.trim(),
        request_id: crypto.randomUUID(),
        generation_epoch: current?.generation_epoch ?? 0,
        use_rag: rag,
        lesson_context: context,
        problem,
        hypothesis: (context as any)?.hypothesis,
      });
      if (expected !== generation.current) {
        void post(`/jobs/${response.job_id}/cancel`).catch(() => {});
        return;
      }
      pendingChatJob.current = response.job_id;
      setDraft("");
      if (!context) setOriginalLecture(null);
      setRetryQuestion(null);
      safeSave(`edu-draft:${id}`, "");
      safeSave("edu-draft:new", "");
      const newMessages = await api(`/sessions/${id}/messages`);
      if (expected !== generation.current) return;
      setMessages(list(newMessages));
      const next = await api<Job>(`/jobs/${response.job_id}`);
      if (expected !== generation.current) return;
      setJob(next);
      if (!activeJob(next)) {
        // Completion may occur after the first messages snapshot. A terminal
        // job never enters the polling effect, so read its final messages now.
        pendingChatJob.current = undefined;
        const finalMessages = await api(`/sessions/${id}/messages`);
        if (expected !== generation.current) return;
        setMessages(list(finalMessages));
      }
      setSessions(list(await api("/sessions")));
      if (asLesson && expected === generation.current)
        await prepareStudentLesson(response.job_id, id, expected, followup);
    } catch (e) {
      if (expected === generation.current) {
        setError(errorText(e));
        if (e instanceof ApiError && e.status === 409) {
          setDraft(content);
          setRetryQuestion({ content, context });
        }
      }
    } finally {
      if (expected === generation.current) setSending(false);
    }
  }
  async function stop() {
    const expected = ++generation.current;
    const stoppedSession = sessionRef.current;
    const id = pendingChatJob.current || (job && activeJob(job) ? job.id : undefined);
    const current = () => expected === generation.current && sessionRef.current === stoppedSession;
    // Seed observation even if stop races the initial job GET. A failed or
    // same-state cancel response must not leave the UI waiting forever.
    if (id) setJob(previous => previous?.id === id
      ? {...previous, cancel_requested: true}
      : {id, state: "queued", cancel_requested: true});
    await cancelLesson();
    if (!current()) return;
    setSending(false);
    setInfo(
      "화면 생성을 중지했습니다. 서버 작업의 실제 중지 상태를 확인합니다.",
    );
    if (id) {
      try {
        const result = await post(`/jobs/${id}/cancel`);
        if (!current()) return;
        setJob(previous => previous?.id === id && activeJob(previous)
          ? {...previous, ...result, id, cancel_requested: true} : previous);
        if (!activeJob(result) && pendingChatJob.current === id) pendingChatJob.current = undefined;
        const refreshed = await api("/sessions");
        if (current()) setSessions(list(refreshed));
      } catch (e) {
        if (current()) setError(errorText(e));
      }
    }
  }
  async function removeSession() {
    if (
      !sessionId ||
      !window.confirm(
        "이 대화와 메시지를 로컬 저장소에서 삭제합니다. 계속할까요?",
      )
    )
      return;
    try {
      await api(`/sessions/${sessionId}`, { method: "DELETE" });
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      selectSession("");
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function exportSession() {
    try {
      download(
        await api(`/sessions/${sessionId}/export`),
        `AI-강의실-${sessionId}.json`,
      );
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function loadDemo() {
    setStudentLessonId("");
    await cancelLesson();
    const epoch = ++lessonEpoch.current;
    setError("");
    try {
      const result = await api("/lessons/demo");
      if (epoch !== lessonEpoch.current) return;
      setLessonRecord(result);
      setOriginalLecture(null);
      setLesson(parseLesson(result.plan));
      setLessonRecordId(result.id);
      safeSave("edu-lesson", result.id);
      setFallback("");
      setTab("classroom");
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function makeLesson(message: Message) {
    setStudentLessonId("");
    await cancelLesson();
    const epoch = ++lessonEpoch.current;
    setError("");
    try {
      const result = await post("/lessons", {
        session_id: sessionId,
        message_id: message.id,
      });
      if (epoch !== lessonEpoch.current) return;
      setLessonRecord(result);
      if (result.valid === false)
        throw new Error(
          result.invalidated_reason || "원문 수정으로 무효화된 답변입니다.",
        );
      setLessonRecordId(result.id);
      safeSave("edu-lesson", result.id);
      if (result.plan) {
        setLesson(parseLesson(result.plan));
        setFallback("");
      } else {
        setLesson(null);
        setFallback(result.fallback_text || message.content);
      }
      setTab("classroom");
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function generateLesson() {
    if (!textGenerationAllowed) { setError("새 판서 생성에는 활성 수업 한도가 필요합니다."); return; }
    if (!lessonRecordId || lessonRecord?.status === "verification_stopped")
      return;
    setLessonGenerating(true);
    setError("");
    const epoch = ++lessonEpoch.current;
    const request = {
      controller: new AbortController(),
      id: undefined as string | undefined,
    };
    lessonRequest.current = request;
    try {
      const start = await post(`/lessons/${lessonRecordId}/generate`);
      request.id = start.job_id;
      if (request.controller.signal.aborted || epoch !== lessonEpoch.current) {
        await post(`/jobs/${start.job_id}/cancel`).catch(() => {});
        return;
      }
      await waitForJob(start.job_id, request.controller.signal);
      const result = await api(`/lessons/${lessonRecordId}`, {
        signal: request.controller.signal,
      });
      if (request.controller.signal.aborted || epoch !== lessonEpoch.current)
        return;
      setLessonRecord(result);
      if (result.valid === false)
        throw new Error(
          result.invalidated_reason || "원문 수정으로 강의가 무효화되었습니다.",
        );
      if (result.plan) {
        setLesson(parseLesson(result.plan));
        setFallback("");
      } else
        setError(
          result.reason ||
            "판서 계획 생성에 실패했습니다. 원래 답변을 보존합니다.",
        );
    } catch (e) {
      if (!request.controller.signal.aborted) setError(errorText(e));
    } finally {
      if (lessonRequest.current === request) {
        setLessonGenerating(false);
        lessonRequest.current = undefined;
      }
    }
  }
  async function reprocessLesson() {
    if (!lessonRecordId || requestedReplay || lessonGenerating || lessonRequest.current ||
        lessonRecord?.valid === false || lessonRecord?.status !== "verification_stopped") return;
    const sourceId = lessonRecordId;
    const epoch = ++lessonEpoch.current, expectedGeneration = generation.current;
    const request = { controller: new AbortController(), id: undefined as string | undefined };
    lessonRequest.current = request;
    setLessonGenerating(true);
    setError("");
    const current = () => !request.controller.signal.aborted && epoch === lessonEpoch.current &&
      expectedGeneration === generation.current && activeTab.current === "classroom";
    try {
      const requestId = reprocessRequestIds.current.get(sourceId) || crypto.randomUUID();
      reprocessRequestIds.current.set(sourceId, requestId);
      lessonEvent("saved_response_reprocess_submitted", { source_lesson_record_id: sourceId, request_id: requestId,
        new_text_inference: false });
      // CPU-only saved-response verification; no /generate or new chat request.
      const result = await api(`/lessons/${encodeURIComponent(sourceId)}/reprocess`, {
        method: "POST", body: JSON.stringify({ request_id: requestId }), signal: request.controller.signal,
      });
      if (!current()) return;
      if (!result.id || result.id === sourceId || result.valid !== true || !result.plan ||
          result.reprocessing?.source_lesson_id !== sourceId ||
          result.speech_allowed !== true || result.status === "verification_stopped")
        throw new Error(result.reason || "저장 답변의 설명 검증을 통과하지 못했습니다. 이전 실패 기록을 보존합니다.");
      const nextPlan = parseLesson(result.plan);
      // Commit the new linked record and automatic student playback together.
      setLessonRecord(result);
      setLessonRecordId(result.id);
      setLesson(nextPlan);
      setFallback("");
      setOriginalLecture(null);
      setReplayLessonId("");
      setReplayBaseId("");
      setReplayAutoplayId("");
      setReplayResumeId("");
      setStudentLessonId(result.id);
      safeSave("edu-lesson", result.id);
      setInfo("저장 답변을 다시 검증한 수업입니다. 이전 실패 기록과 모델 원문은 보존했습니다.");
      lessonEvent("saved_response_reprocessed", { source_lesson_record_id: sourceId, lesson_record_id: result.id,
        lesson_id: nextPlan.lesson_id, new_text_inference: false });
      lessonEvent("plan_ready", { lesson_record_id: result.id, lesson_id: nextPlan.lesson_id, saved_response: true });
    } catch (error) {
      if (current()) {
        setError(errorText(error));
        lessonEvent("saved_response_reprocess_blocked", { source_lesson_record_id: sourceId, reason: errorText(error) });
      }
    } finally {
      if (lessonRequest.current === request) {
        setLessonGenerating(false);
        lessonRequest.current = undefined;
      }
    }
  }
  async function cancelLesson() {
    lessonEpoch.current++;
    const request = lessonRequest.current;
    request?.controller.abort();
    setLessonGenerating(false);
    if (request?.id)
      await post(`/jobs/${request.id}/cancel`).catch((e) =>
        setError(errorText(e)),
      );
  }
  async function prepareStudentLesson(
    chatJobId: string,
    sourceSession: string,
    expected: number,
    followup?: StudentFollowup,
  ) {
    await cancelLesson();
    const epoch = ++lessonEpoch.current;
    const request = {
      controller: new AbortController(),
      id: chatJobId as string | undefined,
    };
    lessonRequest.current = request;
    setLessonGenerating(true);
    const current = () =>
      !request.controller.signal.aborted &&
      expected === generation.current &&
      epoch === lessonEpoch.current &&
      (!followup || (sessionRef.current === sourceSession && displayedLesson.current.id === followup.sourceLessonId &&
        displayedLesson.current.plan === followup.sourcePlan));
    let failedRecordId: string | undefined;
    let preserveFollowup = !!followup;
    const sourceInvalid = (record: any) => record.valid === false || (followup &&
      record.current_problem_revision != null && record.current_problem_revision !== followup.sourcePlan.problem_revision);
    try {
      const completed = await waitForJob(
        chatJobId,
        request.controller.signal,
        (value) => {
          if (current()) setJob(value);
        },
      );
      const answerList = list(
        await api(`/sessions/${sourceSession}/messages`, {
          signal: request.controller.signal,
        }),
      ) as Message[];
      if (!current()) return;
      setMessages(answerList);
      const answer = answerList.find(
        (message) => message.id === completed.result?.message_id,
      );
      if (!answer || answer.role !== "assistant")
        throw new Error("완료된 질문의 답변을 확인하지 못했습니다.");
      const boundAnswer = answer as Message & { session_id?: string; lesson_context?: Record<string, any> };
      if (followup && (boundAnswer.session_id !== sourceSession ||
          boundAnswer.lesson_context?.lesson_id !== followup.sourceLessonId ||
          boundAnswer.lesson_context?.problem_revision !== followup.context.problem_revision ||
          boundAnswer.lesson_context?.step !== followup.context.step ||
          boundAnswer.lesson_context?.selected_cell?.cell_id !== followup.context.selected_cell?.cell_id))
        throw new Error("보충 답변의 원래 수업·원문 연결이 일치하지 않아 현재 칠판을 보존했습니다.");
      let record = await post("/lessons", {
        session_id: sourceSession,
        message_id: answer.id,
      });
      if (!current()) return;
      if (followup && record.source_message_id !== answer.id)
        throw new Error("보충 판서의 답변 출처가 일치하지 않아 현재 칠판을 보존했습니다.");
      failedRecordId = record.id;
      if (sourceInvalid(record)) preserveFollowup = false;
      if (sourceInvalid(record) || record.status === "verification_stopped") {
        if (!preserveFollowup) {
          if (followup) setOriginalLecture(null);
          setLessonRecord(record);
          setLessonRecordId(record.id);
          safeSave("edu-lesson", record.id);
          setStudentLessonId("");
          setLesson(null);
          setFallback(record.fallback_text || answer.content);
          setTab("classroom");
        }
        throw new Error(
          record.reason ||
            record.invalidated_reason ||
            "검증되지 않은 답변이므로 수업 음성을 시작하지 않습니다.",
        );
      }
      if (!record.plan) {
        const started = await post(`/lessons/${record.id}/generate`);
        request.id = started.job_id;
        if (!current()) {
          await post(`/jobs/${started.job_id}/cancel`).catch(() => {});
          return;
        }
        await waitForJob(started.job_id, request.controller.signal);
        record = await api(`/lessons/${record.id}`, {
          signal: request.controller.signal,
        });
      }
      if (!current()) return;
      if (followup && record.source_message_id !== answer.id)
        throw new Error("보충 판서의 답변 출처가 일치하지 않아 현재 칠판을 보존했습니다.");
      if (sourceInvalid(record)) preserveFollowup = false;
      if (
        sourceInvalid(record) ||
        !record.plan ||
        record.speech_allowed !== true
      ) {
        if (!preserveFollowup) {
          if (followup) setOriginalLecture(null);
          setLessonRecord(record);
          setLessonRecordId(record.id);
          safeSave("edu-lesson", record.id);
          setLesson(
            !sourceInvalid(record) && record.plan
              ? parseLesson(record.plan)
              : null,
          );
          setFallback(record.plan ? "" : record.fallback_text || answer.content);
          setStudentLessonId("");
          setTab("classroom");
        }
        throw new Error(
          record.reason ||
            "설명과 판서의 검증을 통과하지 못해 자동 음성을 멈췄습니다.",
        );
      }
      // Keep the existing Classroom instance on a failed supplement. A valid
      // new plan, record id and automatic mode are committed together below.
      const nextPlan = parseLesson(record.plan);
      setLessonRecord(record);
      setLessonRecordId(record.id);
      safeSave("edu-lesson", record.id);
      setLesson(nextPlan);
      setFallback("");
      setStudentLessonId(record.id);
      setTab("classroom");
      lessonEvent("plan_ready", {
        lesson_record_id: record.id,
        lesson_id: record.plan.lesson_id,
      });
    } catch (error) {
      if (current()) {
        if (followup && preserveFollowup) {
          // A failed POST can mean that the original photo was invalidated,
          // even before a failed lesson record exists. Recheck the source on
          // every preservation path. A transient read failure preserves only
          // the previously verified paused snapshot, not a new validity claim.
          let sourceCurrent = false;
          let sourceInvalidated = false;
          try {
            const source = await api(`/lessons/${followup.sourceLessonId}`, {
              signal: AbortSignal.any([request.controller.signal, AbortSignal.timeout(10000)]),
            });
            sourceInvalidated = source.id !== followup.sourceLessonId || sourceInvalid(source) ||
              source.source_message_id !== followup.sourcePlan.source_message_id || !source.plan;
            if (!sourceInvalidated) {
              try { sourceInvalidated = JSON.stringify(parseLesson(source.plan)) !== JSON.stringify(followup.sourcePlan); }
              catch { sourceInvalidated = true; }
            }
            sourceCurrent = !sourceInvalidated && source.valid === true && source.speech_allowed === true;
          } catch (sourceError) {
            sourceInvalidated = sourceError instanceof ApiError && sourceError.status === 404;
          }
          if (!current()) return;
          if (sourceInvalidated) {
            setOriginalLecture(null);
            setStudentLessonId("");
            setLesson(null);
            setLessonRecord({ valid: false, invalidated_reason: "보충 설명 중 원래 수업이 변경되거나 무효화되었습니다." });
            setFallback("원래 수업의 원문·판서가 변경되거나 삭제되어 이전 수업을 멈췄습니다. 최신 원문을 확인해 주세요.");
            setError(errorText(error));
            lessonEvent("supplement_source_invalidated", { source_lesson_record_id: followup.sourceLessonId,
              failed_lesson_record_id: failedRecordId, reason: errorText(error) });
            return;
          }
          setDraft((value) => value || followup.question);
          setInfo(sourceCurrent
            ? "보충 설명을 시작하지 못했습니다. 원래 칠판과 선택한 셀, 멈춘 음성 위치와 질문을 보존했습니다."
            : "원래 수업의 최신 상태를 다시 확인하지 못했습니다. 이전에 확인한 칠판과 질문을 유지하고 음성은 멈췄습니다. 연결과 원문을 확인해 주세요.");
          lessonEvent("supplement_blocked_preserved", { source_lesson_record_id: followup.sourceLessonId,
            failed_lesson_record_id: failedRecordId, source_reverified: sourceCurrent, reason: errorText(error) });
        }
        setError(errorText(error));
        lessonEvent("lesson_blocked", { reason: errorText(error) });
      }
    } finally {
      if (lessonRequest.current === request) {
        setLessonGenerating(false);
        lessonRequest.current = undefined;
      }
    }
  }
  function interrupt(question: string, context: unknown) {
    if (lesson)
      setOriginalLecture(
        (previous) =>
          previous || {
            id: lessonRecordId,
            plan: lesson,
            step: (context as any)?.step ?? 0,
            progress: (context as any)?.progress ?? 1,
            selected_cell: (context as any)?.selected_cell,
            audio_position: (context as any)?.audio_position ?? 0,
            record: lessonRecord,
            student_mode: (context as any)?.student_lesson === true,
          },
      );
    setDraft(question);
    if (busy) {
      void stop();
      setInfo(
        "강의를 멈추고 질문을 임시 저장했습니다. 기존 작업의 실제 중지 후 대화에서 전송하세요.",
      );
      return;
    }
    void send(question, context, (context as any)?.student_lesson === true);
    setInfo(
      "현재 칠판을 보존했습니다. 질문의 답변과 처리 상태는 대화에서 확인하세요.",
    );
  }
  async function openSavedSupplement(context: any, signal: AbortSignal) {
    if (!lesson || replayLessonId !== lessonRecordId || lessonRecordId !== replayBaseId ||
        !/^[a-zA-Z0-9_-]{1,128}$/.test(requestedSupplement))
      throw new Error("연결된 저장 보충 설명이 없습니다.");
    const epoch = ++lessonEpoch.current;
    const [original, supplement] = await Promise.all([
      api<any>(`/lessons/${lessonRecordId}`, { signal }), api<any>(`/lessons/${requestedSupplement}`, { signal }),
    ]);
    signal.throwIfAborted();
    if (epoch !== lessonEpoch.current) return;
    if (JSON.stringify(original.plan) !== JSON.stringify(lesson) || !savedSupplementMatches(original, supplement))
      throw new Error("저장된 보충 설명의 원본 수업·문제·검증 조건이 일치하지 않아 재생을 멈췄습니다.");
    setOriginalLecture({ id: lessonRecordId, plan: lesson, record: original,
      step: context.step, progress: context.progress, selected_cell: context.selected_cell,
      audio_position: context.audio_position, replay_only: true, replay_playing: context.replay_playing, replay_continuous: context.replay_continuous });
    // A stored supplement starts at its own beginning; B's position stays separate.
    safeSave(`lecture:${supplement.plan.lesson_id}`, JSON.stringify({ step: 0, progress: 0, audio_position: 0, playback_status: "resume_requested", problem_revision: supplement.plan.problem_revision }));
    setLessonRecordId(supplement.id);
    setLessonRecord(supplement);
    setLesson(parseLesson(supplement.plan));
    setReplayLessonId(supplement.id);
    setReplayAutoplayId(supplement.id);
    setReplayResumeId("");
    setStudentLessonId("");
    setFallback("");
    lessonEvent("saved_supplement_loaded", { lesson_record_id: supplement.id, original_lesson_record_id: original.id, replay_only: true });
  }
  async function returnOriginal() {
    if (!originalLecture) return;
    try { await classroomStop.current?.(); }
    catch (error) { setError(errorText(error)); return; }
    await cancelLesson();
    const epoch = ++lessonEpoch.current;
    try {
      const current = await api(`/lessons/${originalLecture.id}`);
      if (epoch !== lessonEpoch.current) return;
      if (
        current.valid === false ||
        (current.current_problem_revision &&
          current.current_problem_revision !==
            originalLecture.plan.problem_revision)
      )
        throw new Error(
          current.invalidated_reason ||
            "원문이 변경되어 이전 강의로 돌아갈 수 없습니다. 수정한 원문으로 다시 풀이하세요.",
        );
      if (originalLecture.replay_only && JSON.stringify(current.plan) !== JSON.stringify(originalLecture.plan))
        throw new Error("원래 수업의 판서·대사가 변경되어 저장 위치에서 이어 재생할 수 없습니다.");
      safeSave(
        `lecture:${originalLecture.plan.lesson_id}`,
        JSON.stringify({
          step: originalLecture.step,
          progress: originalLecture.progress,
          selected_cell: originalLecture.selected_cell,
          audio_position: originalLecture.audio_position ?? 0,
          playback_status: originalLecture.student_mode || originalLecture.replay_playing || originalLecture.replay_continuous ? "resume_requested" : "paused",
          problem_revision: originalLecture.plan.problem_revision,
        }),
      );
      safeSave("edu-lesson", originalLecture.id);
      setLesson(originalLecture.plan);
      setLessonRecordId(originalLecture.id);
      setLessonRecord(current);
      setReplayLessonId(originalLecture.replay_only ? originalLecture.id : "");
      setReplayAutoplayId(originalLecture.replay_only && originalLecture.replay_continuous ? originalLecture.id : "");
      setReplayResumeId(originalLecture.replay_only && originalLecture.replay_playing ? originalLecture.id : "");
      setStudentLessonId(
        originalLecture.student_mode ? originalLecture.id : "",
      );
      lessonEvent("lesson_resumed", {
        lesson_record_id: originalLecture.id,
        step: originalLecture.step,
        selected_cell_id: originalLecture.selected_cell?.cell_id,
        audio_position: originalLecture.audio_position,
      });
      setFallback("");
      setOriginalLecture(null);
      setTab("classroom");
      setInfo(
        (originalLecture.student_mode || originalLecture.replay_playing)
          ? "원래 수업의 칠판과 음성 위치에서 이어갑니다."
          : "원래 강의의 단계와 칠판 상태로 돌아왔습니다. 음성은 재생 버튼으로 시작하세요.",
      );
    } catch (error) {
      setError(errorText(error));
      setOriginalLecture(null);
    }
  }
  function photoRevisionChanged(photo: any) {
    const affected = photo.invalidated_lesson_ids || [];
    const currentAffected =
      affected.includes(lessonRecordId) ||
      lesson?.source_photo_id === photo.id ||
      lessonRecord?.original_problem?.source?.photo_id === photo.id;
    const originalAffected =
      originalLecture &&
      (affected.includes(originalLecture.id) ||
        originalLecture.plan.source_photo_id === photo.id ||
        originalLecture.record?.original_problem?.source?.photo_id ===
          photo.id);
    if (currentAffected || originalAffected) {
      void cancelLesson();
      if (busy) void stop();
      setOriginalLecture(null);
      setLesson(null);
      setLessonRecord({
        valid: false,
        invalidated_reason: "사진 원문이 수정되었습니다.",
      });
      setFallback(
        "사진 원문이 수정되어 이전 풀이·판서·음성이 무효화되었습니다. 새 revision을 확인하고 다시 풀이하세요.",
      );
    }
    if (sessionId)
      api(`/sessions/${sessionId}/messages`)
        .then((value) => setMessages(list(value)))
        .catch((error) => setError(errorText(error)));
  }
  function editProblem(next: ProblemDraft) {
    const changed =
      next.tables !== problemDraft.tables ||
      next.query !== problemDraft.query ||
      next.dialect !== problemDraft.dialect;
    const typedLesson =
      lessonRecord?.original_problem?.source?.kind === "typed";
    if (changed && (originalLecture || typedLesson)) {
      void cancelLesson();
      if (busy) void stop();
      setOriginalLecture(null);
      setLesson(null);
      setLessonRecord({
        valid: false,
        invalidated_reason: "원본 입력이 수정되었습니다.",
      });
      setFallback(
        "원본 입력이 수정되어 이전 풀이·판서·음성이 무효화되었습니다. 수정한 표·SQL을 확인하고 다시 질문하세요.",
      );
      safeSave("edu-lesson", "");
      setInfo(
        "원본 입력이 바뀌어 이전 중단 지점의 복귀 기록을 해제했습니다. 수정한 원문으로 다시 질문하세요.",
      );
    }
    setProblemDraft(next);
  }
  function disconnect() {
    generation.current++;
    setAuthenticated(false);
    setToken("");
    setCapabilities(undefined);
    setModel(undefined);
    setDoctor(undefined);
    setSessions([]);
    setMessages([]);
    setJob(null);
    setInfo("로컬 연결을 해제했습니다. 대화 기록은 서버에 보존됩니다.");
  }
  async function avatarFile(file?: File) {
    if (!file) return;
    if (file.type !== "image/png" || file.size > 5 * 1024 * 1024) {
      setError("아바타는 5MiB 이하의 PNG 파일을 사용해 주세요.");
      return;
    }
    try {
      const bitmap = await createImageBitmap(file);
      if (bitmap.width * bitmap.height > 16_000_000) {
        bitmap.close();
        throw new Error(
          "아바타 이미지가 너무 큽니다. 16MP 이하를 사용해 주세요.",
        );
      }
      bitmap.close();
      await saveAvatar(file);
      setCustomAvatar(URL.createObjectURL(file));
    } catch (e) {
      setError(errorText(e));
    }
  }
  const currentLabel = navigation.find((n) => n.id === tab)!.label;
  const latestAssistant = [...messages]
    .reverse()
    .find((m) => m.role === "assistant");
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        본문으로 이동
      </a>
      {sidebarOpen && (
        <button
          className="sidebar-scrim"
          aria-label="메뉴 닫기"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
        <a
          href="#"
          className="brand"
          onClick={(e) => {
            e.preventDefault();
            setTab("chat");
          }}
        >
          <span className="brand-mark">
            <GraduationCap size={22} />
          </span>
          <span>
            AI 강의실<small>나의 로컬 튜터</small>
          </span>
        </a>
        <button
          className="new-chat"
          onClick={() => selectSession("")}
          disabled={busy}
        >
          <Plus size={18} />
          새로운 대화
        </button>
        <div className="nav-label">나의 학습 공간</div>
        <nav aria-label="주 메뉴">
          {navigation.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              aria-current={tab === id ? "page" : undefined}
              className={`nav-item ${tab === id ? "active" : ""}`}
              onClick={() => { setTab(id); setSidebarOpen(false); }}
            >
              <Icon size={18} />
              <span>{label}</span>
              {id === tab && <span className="nav-active-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-history">
          <div className="nav-label">
            최근 대화 <span>{sessions.length}</span>
          </div>
          {sessions.length ? (
            sessions.slice(0, 12).map((session) => (
              <button
                key={session.id}
                className={`history-item ${sessionId === session.id && tab === "chat" ? "selected" : ""}`}
                onClick={() => selectSession(session.id)}
                disabled={busy}
              >
                <MessageCircle size={13} />
                <span>{session.title || "제목 없는 대화"}</span>
              </button>
            ))
          ) : (
            <p>
              배운 내용을 차곡차곡
              <br />
              이곳에 모아둘게요.
            </p>
          )}
        </div>
        <div className="sidebar-bottom">
          <ShieldCheck size={17} />
          <div>
            <strong>내 PC 안에서 안전하게</strong>
            <span>대화와 자료는 로컬에 보관</span>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label="메뉴 열기"
              onClick={() => setSidebarOpen(true)}
            >
              <Menu size={20} />
            </button>
            <span>나의 학습 공간</span>
            <ChevronRight size={14} />
            <strong>{currentLabel}</strong>
          </div>
          <div className="topbar-right">
            {demo && (
              <span className="badge amber demo-badge">데모 데이터 재생</span>
            )}
            <button
              className={`connection-pill ${authenticated ? "connected" : ""}`}
              onClick={() => setTab("settings")}
            >
              <span />
              {authenticated ? "로컬 연결됨" : "서버 연결 필요"}
            </button>
            <span className="user-avatar" aria-label="개인 학습 공간">
              나
            </span>
          </div>
        </header>
        <main id="main" className={`main main-${tab}`} tabIndex={-1}>
          {authenticated && (tab === "chat" || tab === "classroom") && (
            <section className="notice" aria-label="이 수업 실행 한도" style={{display: "block"}}>
              <strong>이 수업 실행 한도</strong>
              <p className="fine-print">전체 승인 잔여 안에서 사용하는 이 대화의 한도입니다. 추가 이용권이나 확정 예약이 아니며, 실패·취소·모델 준비 시간도 사용량에 포함됩니다.</p>
              {!sessionId ? <button className="button secondary" disabled={budgetBusy || busy || lessonGenerating}
                onClick={() => void createStudentConversation()}>수업 대화 만들기</button> :
                budgetLoading ? <p role="status">수업 한도 확인 중</p> : currentStudentBudget?.exists ? <>
                  <p>{currentStudentBudget.state === "closed" ? "종료된 수업 한도 · 저장 수업은 다시 볼 수 있습니다." : "활성 수업 한도"}</p>
                  <p aria-label="수업 실제 잔여">사용 가능: 질문 {currentStudentBudget.effective_remaining.text_requests}회 · 새 음성 {currentStudentBudget.effective_remaining.new_audio_clips}개 · 사진 인식 {currentStudentBudget.effective_remaining.vision_requests}회 · 처리 시간 {Math.floor(currentStudentBudget.effective_remaining.seconds)}초</p>
                  <p className="fine-print">수업 사용량: 질문 {currentStudentBudget.used.text_requests}회 · 새 음성 {currentStudentBudget.used.new_audio_clips}개 · 사진 인식 {currentStudentBudget.used.vision_requests}회 · {Math.ceil(currentStudentBudget.used.seconds)}초</p>
                  {currentStudentBudget.state === "active" && <button className="button secondary" disabled={budgetBusy || busy || lessonGenerating} onClick={() => void closeStudentBudget()}>이 수업 한도 종료</button>}
                </> : currentStudentBudget ? <>
                  <p>전체 잔여: 질문 {currentStudentBudget.parent_remaining.text_requests}회 · 새 음성 {currentStudentBudget.parent_remaining.new_audio_clips}개 · 사진 인식 {currentStudentBudget.parent_remaining.vision_requests}회 · {Math.floor(currentStudentBudget.parent_remaining.seconds)}초</p>
                  <div className="button-row" style={{display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: "0.75rem", marginBlock: "0.75rem"}}>
                    {([['text_requests', '질문 횟수'], ['new_audio_clips', '새 음성 개수'], ['vision_requests', '사진 인식 횟수'], ['seconds', '처리 시간(초)']] as const).map(([key, label]) => <label key={key}>{label}<input type="number" aria-label={label} min={key === 'seconds' ? 1 : 0} max={Math.floor(currentStudentBudget.parent_remaining[key])} step="1" style={{width: "7rem"}} value={budgetCaps[key]} disabled={budgetBusy} onChange={(event) => setBudgetCaps((previous) => ({...previous, [key]: Number(event.target.value)}))}/></label>)}
                  </div>
                  <button className="button primary" disabled={budgetBusy || busy || lessonGenerating || Object.entries(budgetCaps).some(([key, value]) => !Number.isInteger(value) || value < (key === 'seconds' ? 1 : 0) || value > currentStudentBudget.parent_remaining[key])}
                    onClick={() => void startStudentBudget()}>입력한 한도로 수업 시작</button>
                </> : <p>수업 한도를 확인할 수 없어 새 생성을 멈췄습니다.</p>}
              {budgetError && <p role="alert">{budgetError}</p>}
              {sessionId && <button className="text-button" disabled={budgetBusy} onClick={() => setBudgetRefresh((value) => value + 1)}>수업 한도 다시 확인</button>}
            </section>
          )}
          {error && (
            <div className="global-notice notice error" role="alert">
              <div>
                <strong>요청을 완료하지 못했습니다</strong>
                <p>{error}</p>
              </div>
              <button
                className="icon-button"
                aria-label="오류 알림 닫기"
                onClick={() => setError("")}
              >
                <X size={17} />
              </button>
            </div>
          )}
          {info && (
            <div className="global-notice notice" role="status">
              <span>{info}</span>
              <button
                className="icon-button"
                aria-label="안내 닫기"
                onClick={() => setInfo("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {retryQuestion && (
            <div className="global-notice notice">
              <div>
                <strong>질문을 보관했습니다 · 자동 전송하지 않습니다</strong>
                <p>{retryQuestion.content}</p>
              </div>
              <button
                className="button secondary"
                disabled={busy || !authenticated}
                onClick={() =>
                  send(retryQuestion.content, retryQuestion.context)
                }
              >
                보관한 질문 다시 전송
              </button>
            </div>
          )}
          {tab === "chat" && (
            <div
              className={`chat-layout ${rightPanel ? "" : "panel-collapsed"}`}
            >
              <section className="chat-panel">
                <div className="chat-toolbar">
                  <span>
                    {sessionId
                      ? sessions.find((s) => s.id === sessionId)?.title ||
                        "나의 대화"
                      : "오늘의 궁금증을 시작하세요"}
                  </span>
                  <div className="button-row">
                    {sessionId && (
                      <>
                        <button
                          className="icon-button"
                          aria-label="대화 내보내기"
                          onClick={exportSession}
                          disabled={busy}
                        >
                          <ArrowDownToLine size={17} />
                        </button>
                        <button
                          className="icon-button"
                          aria-label="대화 삭제"
                          onClick={removeSession}
                          disabled={busy}
                        >
                          <Trash2 size={16} />
                        </button>
                      </>
                    )}
                    <button
                      className="icon-button"
                      aria-label={
                        rightPanel ? "상태 패널 접기" : "상태 패널 열기"
                      }
                      onClick={() => setRightPanel(!rightPanel)}
                    >
                      <MoreHorizontal size={20} />
                    </button>
                  </div>
                </div>
                <div className="chat-scroll">
                  {messages.length === 0 ? (
                    <div className="welcome">
                      <div className="welcome-symbol">
                        <GraduationCap size={34} />
                        <span className="spark spark-one">✦</span>
                        <span className="spark spark-two">✧</span>
                      </div>
                      <div className="eyebrow">
                        모르는 것이, 알게 되는 순간으로
                      </div>
                      <h1>
                        오늘은 무엇을
                        <br />
                        <span>함께 배워볼까요?</span>
                      </h1>
                      <p>
                        작은 질문도 괜찮아요. 개념부터 풀이까지,
                        <br />
                        이해할 수 있도록 한 단계씩 함께합니다.
                      </p>
                      <div className="suggestion-grid">
                        <button
                          onClick={() =>
                            setDraft(
                              "COUNT(*)와 COUNT(salary)는 NULL을 어떻게 다르게 처리하나요?",
                            )
                          }
                        >
                          <span className="suggestion-icon purple">
                            <FileText size={19} />
                          </span>
                          <strong>헷갈리는 개념 이해하기</strong>
                          <span>
                            COUNT와 NULL의 차이가 궁금해요
                            <ArrowRight size={14} />
                          </span>
                        </button>
                        <button
                          onClick={() =>
                            authenticated
                              ? setPhotoOpen(true)
                              : setTab("settings")
                          }
                        >
                          <span className="suggestion-icon orange">
                            <ImagePlus size={19} />
                          </span>
                          <strong>문제 사진으로 질문하기</strong>
                          <span>
                            원문을 확인하고 함께 풀어봐요
                            <ArrowRight size={14} />
                          </span>
                        </button>
                        <button
                          onClick={() =>
                            authenticated ? loadDemo() : setTab("settings")
                          }
                        >
                          <span className="suggestion-icon green-icon">
                            <GraduationCap size={19} />
                          </span>
                          <strong>칠판으로 차근차근 보기</strong>
                          <span>
                            설명용 강의 예시를 살펴봐요
                            <ArrowRight size={14} />
                          </span>
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="messages">
                      {messages.map((message) => (
                        <article
                          className={`message message-${message.role}`}
                          key={message.id}
                        >
                          <div className="message-avatar">
                            {message.role === "user" ? (
                              "나"
                            ) : (
                              <GraduationCap size={19} />
                            )}
                          </div>
                          <div className="message-body">
                            <div className="message-author">
                              {message.role === "user" ? "나" : "로컬 튜터"}
                              {message.role === "assistant" && (
                                <span>
                                  {message.valid === false
                                    ? "원문 수정으로 무효화된 답변"
                                    : message.evidence
                                      ? "도구 검증 범위 있음 · 설명 검토 별도"
                                      : "모델 답변 · 정확성 미검증"}
                                </span>
                              )}
                            </div>
                            <PlainMessage text={message.content} />
                            {message.role === "assistant" && (
                              <>
                                <div className="message-actions">
                                  <button
                                    onClick={() => {
                                      navigator.clipboard
                                        .writeText(message.content)
                                        .then(() =>
                                          setInfo("답변을 복사했습니다."),
                                        )
                                        .catch(() =>
                                          setError(
                                            "복사 권한이 없습니다. 텍스트를 직접 선택해 주세요.",
                                          ),
                                        );
                                    }}
                                  >
                                    <Copy size={13} />
                                    복사
                                  </button>
                                  <button
                                    onClick={() => makeLesson(message)}
                                    disabled={busy || message.valid === false}
                                  >
                                    <GraduationCap size={14} />
                                    강의 보기
                                  </button>
                                  {message.id === latestAssistant?.id && (
                                    <button
                                      onClick={() => {
                                        const previous = [...messages]
                                          .reverse()
                                          .find((m) => m.role === "user");
                                        if (previous)
                                          void send(previous.content);
                                      }}
                                      disabled={busy}
                                    >
                                      <RefreshCw size={13} />
                                      다시 생성
                                    </button>
                                  )}
                                </div>
                                {message.original_problem?.source?.kind ===
                                  "photo" && (
                                  <button
                                    className="text-button"
                                    onClick={() => {
                                      setEditingPhotoId(
                                        message.original_problem.source
                                          .photo_id,
                                      );
                                      setPhotoOpen(true);
                                    }}
                                  >
                                    사진 원문 수정
                                  </button>
                                )}
                                {message.evidence && (
                                  <details className="message-evidence">
                                    <summary>
                                      입력·계산·의도·설명별 확인 범위
                                    </summary>
                                    <p className="fine-print">
                                      SQL 실행 성공과 질문 의도 충족, 설명의
                                      정확성은 각각 확인합니다. 사람 검토를
                                      대신하지 않습니다.
                                    </p>
                                    <pre className="json-view">
                                      {JSON.stringify(
                                        message.evidence,
                                        null,
                                        2,
                                      )}
                                    </pre>
                                  </details>
                                )}
                                {message.raw_model_response && (
                                  <details>
                                    <summary>
                                      실제 모델 원시 응답 · 앱 표시와 구분
                                    </summary>
                                    <PlainMessage
                                      text={message.raw_model_response}
                                    />
                                  </details>
                                )}
                                {message.original_problem && (
                                  <details>
                                    <summary>
                                      보존된 원본 문제 · revision{" "}
                                      {message.original_problem.revision}
                                    </summary>
                                    <pre className="json-view">
                                      {JSON.stringify(
                                        message.original_problem,
                                        null,
                                        2,
                                      )}
                                    </pre>
                                  </details>
                                )}
                                {message.sources?.length ? (
                                  <details className="message-sources">
                                    <summary>
                                      참고한 출처 {message.sources.length}개
                                    </summary>
                                    {message.sources.map(
                                      (s: any, i: number) => (
                                        <p key={i}>
                                          {s.source_title ||
                                            s.label ||
                                            s.document_id}{" "}
                                          ·{" "}
                                          {s.page
                                            ? `${s.page}쪽`
                                            : `청크 ${s.chunk_id}`}
                                          <br />
                                          {s.text}
                                        </p>
                                      ),
                                    )}
                                  </details>
                                ) : (
                                  <p className="fine-print">참고 청크 없음</p>
                                )}
                                <p className="fine-print">
                                  {message.generation_snapshot?.source ===
                                    "worker_metadata" &&
                                  message.generation_snapshot.model_id
                                    ? `생성 모델 ${message.generation_snapshot.model_id} · 어댑터 ${message.generation_snapshot.adapter_id === "base" ? "기반 모델" : message.generation_snapshot.adapter_id || "미기록"} · revision ${message.generation_snapshot.revision || "미기록"}`
                                    : "생성 시 모델 정보 기록 없음"}
                                </p>
                              </>
                            )}
                          </div>
                        </article>
                      ))}
                    </div>
                  )}
                  {busy && job?.partial_text && !job.cancel_requested && (
                    <article className="streaming-text" aria-live="polite">
                      <PlainMessage text={job.partial_text} />
                    </article>
                  )}
                  {busy && (
                    <div className="generation-state" role="status">
                      <span className="thinking-dots">
                        <i />
                        <i />
                        <i />
                      </span>
                      <span>
                        {job?.cancel_requested
                          ? "취소 요청됨 · 실제 중지를 기다리는 중"
                          : job?.state === "queued"
                            ? "GPU 작업 대기 중"
                            : "로컬 모델이 답변을 준비하고 있어요"}
                      </span>
                    </div>
                  )}
                  <div ref={chatEnd} />
                </div>
                <div className="composer-wrap">
                  <ProblemEditor value={problemDraft} onChange={editProblem} />
                  {!authenticated && (
                    <div className="connect-hint">
                      <KeyRound size={14} />
                      <span>처음이라면 로컬 서버를 연결해 주세요.</span>
                      <button
                        className="text-button"
                        onClick={() => setTab("settings")}
                      >
                        연결하기
                        <ArrowRight size={14} />
                      </button>
                    </div>
                  )}
                  <form
                    className="composer"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void send();
                    }}
                  >
                    <textarea
                      aria-label="질문 입력"
                      placeholder={
                        authenticated
                          ? "궁금한 내용을 자유롭게 물어보세요."
                          : "연결 전에도 질문을 작성해 둘 수 있어요."
                      }
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onCompositionStart={() => (composing.current = true)}
                      onCompositionEnd={() => (composing.current = false)}
                      onKeyDown={(e) => {
                        if (shouldSubmit(e.nativeEvent, composing.current)) {
                          e.preventDefault();
                          void send();
                        }
                      }}
                      rows={2}
                    />
                    <div className="composer-bottom">
                      <div className="button-row">
                        <button
                          type="button"
                          className="icon-button"
                          aria-label="문제 사진 첨부"
                          onClick={() => {
                            setEditingPhotoId(undefined);
                            setPhotoOpen(true);
                          }}
                          disabled={!authenticated || busy}
                        >
                          <ImagePlus size={19} />
                        </button>
                        <label className="rag-toggle">
                          <input
                            type="checkbox"
                            checked={rag}
                            onChange={(e) => setRag(e.target.checked)}
                          />
                          <BookOpen size={14} />내 자료 참고
                        </label>
                      </div>
                      {!busy && (
                        <button
                          type="button"
                          className="button primary"
                          aria-label="수업 시작"
                          disabled={
                            !draft.trim() ||
                            !authenticated ||
                            !capabilities?.speech?.available || !textGenerationAllowed
                          }
                          onClick={() => void send(draft, undefined, true)}
                        >
                          <GraduationCap size={17} />
                          수업 시작
                        </button>
                      )}
                      {busy ? (
                        <button
                          type="button"
                          className="send-button stop"
                          aria-label="생성 중지"
                          onClick={event => {
                            // This DOM button can become the submit button as
                            // stop clears sending before the click completes.
                            event.preventDefault();
                            void stop();
                          }}
                        >
                          <Square size={16} />
                        </button>
                      ) : (
                        <button
                          className="send-button"
                          aria-label="질문 전송"
                          disabled={!draft.trim() || !authenticated || !textGenerationAllowed}
                        >
                          <ArrowRight size={20} />
                        </button>
                      )}
                    </div>
                  </form>
                  <div className="composer-help">
                    <label>
                      <input
                        type="checkbox"
                        checked={photoLesson}
                        onChange={(event) =>
                          setPhotoLesson(event.target.checked)
                        }
                      />{" "}
                      사진 답변도 수업으로 듣기
                    </label>
                    <span>Enter 전송 · Shift+Enter 줄바꿈</span>
                    <span>
                      답변은 틀릴 수 있어요. 중요한 내용은 출처를 확인하세요.
                    </span>
                  </div>
                </div>
              </section>
              {rightPanel && (
                <aside className="context-panel">
                  <div className="panel-label">학습 준비 상태</div>
                  <div className="model-status-card">
                    <div className="model-icon">
                      <Cpu size={20} />
                    </div>
                    <strong>
                      {model?.model_id?.split("/").pop() || "로컬 모델"}
                    </strong>
                    <span
                      className={`badge ${capabilities?.text?.available ? "green" : "amber"}`}
                    >
                      {capabilities?.text?.available
                        ? "응답 준비됨"
                        : authenticated
                          ? "모델 준비 필요"
                          : "연결 대기"}
                    </span>
                    <p>
                      {capabilities?.text?.reason ||
                        "서버에 연결하면 실제 모델 상태를 확인할 수 있습니다."}
                    </p>
                    <button
                      className="text-button"
                      onClick={() => setTab("models")}
                    >
                      모델 정보 보기
                      <ArrowRight size={14} />
                    </button>
                  </div>
                  <div className="context-section">
                    <div className="panel-label">함께 보는 출처</div>
                    {latestAssistant?.sources?.length ? (
                      latestAssistant.sources.map((source: any, i: number) => (
                        <div className="source-mini" key={i}>
                          <FileText size={17} />
                          <span>
                            {source.source_title ||
                              source.label ||
                              source.chunk_id}
                          </span>
                        </div>
                      ))
                    ) : (
                      <>
                        <div className="source-placeholder">
                          <BookOpen size={25} />
                        </div>
                        <p>
                          자료를 참고한 답변이 오면
                          <br />
                          출처를 여기에 모아드려요.
                        </p>
                        <button
                          className="text-button"
                          onClick={() => setTab("materials")}
                        >
                          교육자료 등록하기
                          <ArrowRight size={14} />
                        </button>
                      </>
                    )}
                  </div>
                  <div className="gentle-note">
                    <span>나의 속도로 배우세요</span>
                    <p>잘 모르겠다면 “더 쉽게 설명해 줘”라고 말해 보세요.</p>
                  </div>
                  <div className="voice-status">
                    <VolumeX size={15} />
                    <span>
                      {capabilities?.speech?.available
                        ? "로컬 음성 사용 가능"
                        : "음성 미준비 · 자막 사용 가능"}
                    </span>
                  </div>
                </aside>
              )}
            </div>
          )}
          {tab === "classroom" &&
            originalLecture &&
            (fallback || lessonRecordId !== originalLecture.id) && (
              <div className="global-notice notice">
                <span>중간 질문의 재설명을 살펴보고 있습니다.</span>
                <button className="text-button" onClick={returnOriginal}>
                  원래 강의로 돌아가기
                </button>
              </div>
            )}
          {tab === "classroom" && lessonRecord?.reprocessing?.source_lesson_id && (
            <div className="global-notice notice" role="status">
              <span>저장된 모델 원문을 보존하고, 다시 검증한 근거로 설명과 판서를 구성한 수업입니다.</span>
              <a className="text-button" href={`/?lesson=${encodeURIComponent(lessonRecord.reprocessing.source_lesson_id)}`}
                target="_blank" rel="noreferrer">이전 검증 기록</a>
            </div>
          )}
          {tab === "classroom" &&
            (fallback ? (
              <div className="page-content">
                <div className="section-heading">
                  <div>
                    <div className="eyebrow">
                      {lessonRecord?.status === "verification_stopped"
                        ? "검증되지 않은 모델 원문 · 보존 기록"
                        : "실제 생성된 답변"}
                    </div>
                    <h1>
                      {lessonRecord?.status === "verification_stopped"
                        ? "검증 중단"
                        : "설명 텍스트"}
                    </h1>
                  </div>
                  <span className="badge amber">
                    {lessonRecord?.status === "verification_stopped"
                      ? "검증 실패 · 판서·음성 차단"
                      : "구조화 강의 미생성"}
                  </span>
                </div>
                {lessonRecord?.status === "verification_stopped" ? (
                  <div className="notice error" role="alert">
                    <div>
                      <p>
                        {lessonRecord.reason ||
                          "검증을 통과하지 못해 판서와 음성을 중단했습니다."}
                      </p>
                      <p>
                        {requestedReplay
                          ? "저장된 검증 중단 기록입니다. 이 조회에서는 새 답변이나 음성을 생성하지 않습니다."
                          : "이 원문은 검증된 답변이 아닙니다. 저장된 문제와 SQL을 다시 검증해 설명을 확인할 수 있습니다. 이전 기록은 보존됩니다."}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="notice">
                    판서 계획이 생성되지 않아 원래 답변을 그대로 표시합니다.
                    구조화 강의 성공으로 기록하지 않습니다.
                  </div>
                )}
                <section className="card">
                  {lessonRecord?.status === "verification_stopped" && (
                    <h2>검증되지 않은 모델 원문</h2>
                  )}
                  <PlainMessage text={fallback} />
                </section>
                <div className="button-row">
                  {!requestedReplay && lessonRecord?.status === "verification_stopped" && (
                    <button className="button primary"
                      disabled={lessonGenerating || lessonRecord?.valid === false}
                      onClick={reprocessLesson}>
                      {lessonGenerating ? "저장 답변 검증 중…" : "저장 답변으로 다시 검증"}
                    </button>
                  )}
                  <button
                    className="button primary"
                    disabled={
                      lessonGenerating ||
                      !capabilities?.text?.available ||
                      lessonRecord?.valid === false ||
                      lessonRecord?.status === "verification_stopped"
                    }
                    onClick={generateLesson}
                  >
                    {lessonGenerating
                      ? "판서 계획 생성 중…"
                      : "이 답변으로 판서 강의 생성"}
                  </button>
                  {lessonGenerating && (
                    <button className="button secondary" onClick={cancelLesson}>
                      생성 중지
                    </button>
                  )}
                  <button
                    className="button secondary"
                    disabled={lessonGenerating}
                    onClick={() => setFallback("")}
                  >
                    강의실로 돌아가기
                  </button>
                </div>
              </div>
            ) : (
              <Classroom
                key={lessonRecordId}
                lessonRecordId={lessonRecordId}
                lesson={lesson}
                onDemo={loadDemo}
                onInterrupt={interrupt}
                speechAvailable={replayLessonId === lessonRecordId || !!capabilities?.speech?.available}
                customAvatar={customAvatar}
                studentMode={studentLessonId === lessonRecordId}
                replayOnly={replayLessonId === lessonRecordId}
                replayAutoplay={replayAutoplayId === lessonRecordId}
                replayResumePlaying={replayResumeId === lessonRecordId}
                onRegisterStop={registerClassroomStop}
                onSavedSupplement={replayLessonId === lessonRecordId && replayBaseId === lessonRecordId && requestedSupplement ? openSavedSupplement : undefined}
                onComplete={() => {
                  if (originalLecture && (studentLessonId === lessonRecordId || replayLessonId === lessonRecordId))
                    void returnOriginal();
                }}
                isSupplement={
                  !!originalLecture && lessonRecordId !== originalLecture.id
                }
                onResume={() => {
                  if (originalLecture?.id === lessonRecordId)
                    setOriginalLecture(null);
                }}
              />
            ))}
          {tab === "materials" && <Materials authenticated={authenticated} />}
          {tab === "training" && (
            <Training
              authenticated={authenticated}
              capabilities={capabilities}
            />
          )}
          {tab === "models" && (
            <Models
              authenticated={authenticated}
              model={model}
              doctor={doctor}
              onRefresh={() =>
                refreshState().catch((e) => setError(errorText(e)))
              }
            />
          )}
          {tab === "neural" && <Neural authenticated={authenticated} />}
          {tab === "settings" && (
            <div className="page-content settings-page">
              <div className="section-heading">
                <div>
                  <div className="eyebrow">나에게 맞는 학습 환경</div>
                  <h1>설정</h1>
                  <p>이 PC의 서버 연결과 표시 설정을 관리하세요.</p>
                </div>
                <span className="badge muted-badge">개인용 · 로컬 전용</span>
              </div>
              <section className="card">
                <div className="card-heading">
                  <h2>로컬 서버 연결</h2>
                  <KeyRound size={19} />
                </div>
                <p className="muted">
                  서버가 생성한 <code>.local/auth-token</code> 파일을 선택하거나
                  토큰을 입력하세요. 토큰은 현재 브라우저 메모리에만 보관합니다.
                </p>
                {authenticated ? (
                  <div className="connection-success">
                    <Check size={19} />
                    <span>인증된 로컬 서버에 연결되어 있습니다.</span>
                    <button
                      className="button secondary"
                      onClick={disconnect}
                      disabled={busy}
                    >
                      연결 해제
                    </button>
                  </div>
                ) : (
                  <>
                    <label className="token-file button secondary">
                      로컬 토큰 파일 선택
                      <input
                        aria-label="로컬 토큰 파일"
                        type="file"
                        onChange={(e) => tokenFile(e.target.files?.[0])}
                        disabled={connecting}
                      />
                    </label>
                    <form
                      className="connection-form"
                      onSubmit={(e) => {
                        e.preventDefault();
                        void connect();
                      }}
                    >
                      <label>
                        관리 토큰
                        <input
                          aria-label="관리 토큰"
                          type="password"
                          autoComplete="off"
                          value={tokenInput}
                          onChange={(e) => setTokenInput(e.target.value)}
                          placeholder="토큰을 붙여 넣으세요"
                        />
                      </label>
                      <button
                        className="button primary"
                        disabled={!tokenInput.trim() || connecting}
                      >
                        {connecting ? "확인 중…" : "연결"}
                      </button>
                    </form>
                  </>
                )}
                <p className="fine-print">
                  개발 서버 127.0.0.1:5173 → API 127.0.0.1:8000. 새로고침 후에는
                  다시 연결합니다.
                </p>
              </section>
              <section className="card">
                <div className="card-heading">
                  <h2>글자 크기</h2>
                </div>
                <label>
                  화면 글자 크기
                  <select
                    aria-label="화면 글자 크기"
                    value={textScale}
                    onChange={(e) => setTextScale(Number(e.target.value))}
                  >
                    <option value="1">100%</option>
                    <option value="1.25">125%</option>
                    <option value="1.5">150%</option>
                    <option value="2">200%</option>
                  </select>
                </label>
              </section>
              <div className="materials-grid">
                <section className="card">
                  <div className="card-heading">
                    <h2>강의 아바타</h2>
                    <GraduationCap size={19} />
                  </div>
                  <p className="muted">
                    자체 제작한 기본 벡터 아바타 또는 개인 PNG 이미지를
                    사용합니다.
                  </p>
                  <label className="button secondary token-file">
                    PNG 아바타 선택
                    <input
                      aria-label="PNG 아바타 선택"
                      type="file"
                      accept="image/png"
                      onChange={(e) => avatarFile(e.target.files?.[0])}
                    />
                  </label>
                  {customAvatar && (
                    <button
                      className="text-button"
                      onClick={() =>
                        saveAvatar(null)
                          .then(() => setCustomAvatar(undefined))
                          .catch((e) => setError(errorText(e)))
                      }
                    >
                      기본 아바타로 복원
                    </button>
                  )}
                  <p className="fine-print">
                    PNG는 정적 이미지입니다. 완전 리깅이나 음소 립싱크를
                    제공하지 않습니다. 사용할 권리가 있는 이미지로 교체하세요.
                    이 브라우저의 로컬 저장소에 보관합니다.
                  </p>
                </section>
                <section className="card">
                  <div className="card-heading">
                    <h2>음성 · 언어</h2>
                    <VolumeX size={18} />
                  </div>
                  <div className="key-values">
                    <div>
                      <span>화면 언어</span>
                      <b>한국어</b>
                    </div>
                    <div>
                      <span>음성 엔진</span>
                      <b>
                        {capabilities?.speech?.engine || "로컬 TTS 확인 전"}
                      </b>
                    </div>
                    <div>
                      <span>실제 음성</span>
                      <b>
                        {capabilities?.speech?.available
                          ? "준비됨"
                          : "사용 불가"}
                      </b>
                    </div>
                  </div>
                  <p className="fine-print">
                    {capabilities?.speech?.reason ||
                      "음성을 준비하지 않아도 자막과 수동 단계로 공부할 수 있습니다."}
                  </p>
                </section>
              </div>
              <section className="card">
                <div className="card-heading">
                  <h2>저장 · 자원 · 검증</h2>
                  <ShieldCheck size={18} />
                </div>
                {doctor?.cached && (
                  <p className="notice">
                    {doctor.cache_notice ||
                      "저장된 환경 진단 기록입니다. 현재 자원 상태와 다를 수 있습니다."}{" "}
                    기록 시각: {doctor.recorded_at || "미기록"}
                  </p>
                )}
                {resourceBudget?.enabled && (
                  <div className="notice">
                    <strong>이번 검증 회차의 남은 한도</strong>
                    <p>
                      모델 작업{" "}
                      {Math.floor(resourceBudget.gpu_seconds_remaining / 60)}분
                      · 새 음성 {resourceBudget.new_audio_remaining}개 · 사진
                      인식 {resourceBudget.vision_remaining}회
                    </p>
                    <p className="fine-print">
                      실패한 시도와 모델 로딩 시간도 포함합니다. 이 한도는
                      현재 개발 검증 승인에 해당하며, 무제한 수업 이용권이 아닙니다.
                    </p>
                    {resourceBudget.active_execution_allowance?.text_remaining > 0 && (
                      <button className="button secondary" disabled={budgetBusy || budgetLoading || !!currentStudentBudget?.exists} onClick={() => {
                        const id = executionScope ? "" : resourceBudget.active_execution_allowance.id;
                        setExecutionAllowance(id); setExecutionScope(id);
                      }}>
                        {executionScope ? "검증 예산 사용 종료" : "이번 브라우저에서 검증 예산 사용"}
                      </button>
                    )}
                    {executionScope && <p className="fine-print">선택된 실행 범위: {executionScope}</p>}
                    <button
                      className="text-button"
                      onClick={() =>
                        refreshState().catch((error) =>
                          setError(errorText(error)),
                        )
                      }
                    >
                      현재 한도 확인
                    </button>
                  </div>
                )}
                <div className="key-values">
                  <div>
                    <span>모델 캐시</span>
                    <b className="path-value">
                      {model?.path || "서버 연결 후 확인"}
                    </b>
                  </div>
                  <div>
                    <span>외부 분석·텔레메트리</span>
                    <b>사용하지 않음</b>
                  </div>
                  <div>
                    <span>로컬 생성 동시 실행</span>
                    <b>공통 GPU 작업 잠금</b>
                  </div>
                </div>
                <details>
                  <summary>서버가 보고한 검증 상태</summary>
                  <pre className="json-view">
                    {JSON.stringify(
                      capabilities?.validation || {
                        status: "아직 확인되지 않았습니다.",
                      },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              </section>
            </div>
          )}
        </main>
      </div>
      {photoOpen && (
        <PhotoDialog
          photoId={editingPhotoId}
          onRevisionChange={photoRevisionChanged}
          visionAvailable={!!capabilities?.vision?.available}
          onClose={() => {
            setPhotoOpen(false);
            setEditingPhotoId(undefined);
          }}
          sessionId={sessionId || undefined}
          textGenerationAllowed={textGenerationAllowed}
          visionGenerationAllowed={visionGenerationAllowed}
          onSolved={(result) => {
            const expected = ++generation.current;
            setOriginalLecture(null);
            if (result.session_id) setSessionId(result.session_id);
            if (result.job_id) {
              pendingChatJob.current = result.job_id;
              api<Job>(`/jobs/${result.job_id}`)
                .then((value) => {
                  if (expected === generation.current) setJob(value);
                })
                .catch((e) => {
                  if (expected === generation.current) setError(errorText(e));
                });
            }
            setTab("chat");
            setInfo("확정한 원문으로 풀이를 요청했습니다.");
            if (photoLesson && result.job_id && result.session_id)
              void prepareStudentLesson(
                result.job_id,
                result.session_id,
                expected,
              );
          }}
        />
      )}
    </div>
  );
}
