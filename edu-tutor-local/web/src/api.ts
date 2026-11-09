let bearer = "";
let executionAllowance = "";
let studentSession = "";
export const setStudentSession = (id: string) => { studentSession = id; };
export const setExecutionAllowance = (id: string) => { executionAllowance = id; };
export const setToken = (token: string) => {
  bearer = token.trim();
  if (!bearer) { executionAllowance = ""; studentSession = ""; }
};
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function api<T = any>(
  path: string,
  init: RequestInit & { studentSession?: string | null } = {},
): Promise<T> {
  const { studentSession: selectedStudentSession, ...request } = init;
  const headers = new Headers(request.headers);
  const studentId = selectedStudentSession === undefined ? studentSession : selectedStudentSession;
  if (studentId) headers.set("X-Student-Session", studentId);
  else headers.delete("X-Student-Session");
  if (bearer) headers.set("Authorization", `Bearer ${bearer}`);
  if (executionAllowance) headers.set("X-Execution-Allowance", executionAllowance);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...request,
      headers,
      credentials: "omit",
    });
  } catch {
    throw new Error(
      "서버에 연결하지 못했습니다. 로컬 서버 실행 상태를 확인해 주세요.",
    );
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const detail =
      error.detail ?? error.error ?? `요청 실패 (${response.status})`;
    throw new ApiError(
      response.status,
      typeof detail === "string" ? detail : JSON.stringify(detail),
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}
export async function protectedBlob(
  path: string,
  signal?: AbortSignal,
): Promise<Blob> {
  const response = await fetch(`/api${path}`, {
    headers: { Authorization: `Bearer ${bearer}` },
    signal,
    credentials: "omit",
  });
  if (!response.ok)
    throw new ApiError(response.status, "파일을 불러오지 못했습니다.");
  return response.blob();
}
export const post = <T = any>(path: string, body: unknown = {}) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });

/** Authenticated SSE: credentials stay in the header, never in the URL. */
export async function streamEvents<T>(
  path: string,
  onEvent: (value: T) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(`/api${path}`, {
    headers: { Authorization: `Bearer ${bearer}`, Accept: "text/event-stream" },
    credentials: "omit",
    cache: "no-store",
    signal,
  });
  if (!response.ok)
    throw new ApiError(response.status, `관측 연결 실패 (${response.status})`);
  if (
    !response.body ||
    !response.headers.get("content-type")?.includes("text/event-stream")
  )
    throw new Error("서버가 관측 이벤트 스트림을 반환하지 않았습니다.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  try {
    while (true) {
      signal.throwIfAborted();
      const { done, value } = await reader.read();
      if (done) break;
      pending = (pending + decoder.decode(value, { stream: true })).replace(
        /\r\n/g,
        "\n",
      );
      if (pending.length > 2 * 1024 * 1024)
        throw new Error("관측 프레임 한도를 초과해 연결을 종료했습니다.");
      let end: number;
      while ((end = pending.indexOf("\n\n")) >= 0) {
        const frame = pending.slice(0, end);
        pending = pending.slice(end + 2);
        const data = frame
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        if (data) onEvent(JSON.parse(data) as T);
      }
    }
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
export const list = (value: any): any[] =>
  Array.isArray(value)
    ? value
    : (value?.items ??
      value?.sessions ??
      value?.jobs ??
      value?.documents ??
      value?.messages ??
      value?.results ??
      []);
export const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error);
export function download(data: unknown, filename: string) {
  const url = URL.createObjectURL(
    new Blob(
      [typeof data === "string" ? data : JSON.stringify(data, null, 2)],
      { type: "application/json;charset=utf-8" },
    ),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
export type Session = {
  id: string;
  title: string;
  generation_epoch: number;
  created_at?: string;
};
export type Message = {
  id: string;
  role: string;
  content: string;
  generation_epoch?: number;
  sources?: any[];
  metadata?: Record<string, any>;
  generation_snapshot?: {
    source?: string;
    model_id?: string;
    revision?: string;
    adapter_id?: string | null;
  };
  original_problem?: any;
  evidence?: any;
  raw_model_response?: string;
  valid?: boolean;
  created_at?: string;
};
export type Job = {
  id: string;
  kind?: string;
  type?: string;
  state?: string;
  status?: string;
  partial_text?: string;
  metrics?: Record<string, any>[];
  progress?: any;
  error?: any;
  result?: any;
  created_at?: string;
  cancel_requested?: boolean;
  worker_phase?: string;
  worker_reason?: string;
};
export const activeJob = (job?: Job | null) =>
  !!job &&
  [
    "queued",
    "running",
    "pending",
    "cancel_requested",
    "cancelling",
    "loading",
    "saving",
    "checkpointing",
  ].includes(job.state ?? job.status ?? "");
export const statusLabel = (status?: string) =>
  ({
    queued: "대기",
    pending: "대기",
    running: "실행 중",
    loading: "모델 로딩 중",
    saving: "결과 저장 중",
    checkpointing: "체크포인트 저장 중",
    completed: "완료",
    succeeded: "완료",
    failed: "실패",
    cancel_requested: "취소 요청됨",
    cancelling: "중지 처리 중",
    cancelled: "중지됨",
    canceled: "중지됨",
    interrupted: "실행 중단",
    blocked: "실행 차단",
    ready: "준비됨",
    unavailable: "사용 불가",
    not_installed: "미설치",
    not_loaded: "미로딩",
    unverified: "미검증",
    approved: "검토 승인",
    pending_review: "검토 대기",
  })[status ?? ""] ??
  status ??
  "확인 필요";
export async function waitForJob(
  id: string,
  signal: AbortSignal,
  update?: (job: Job) => void,
): Promise<Job> {
  for (let attempt = 0; attempt < 600; attempt++) {
    signal.throwIfAborted();
    const job = await api<Job>(`/jobs/${id}`, { signal });
    update?.(job);
    if (!activeJob(job)) {
      if (
        ["failed", "cancelled", "canceled", "interrupted", "blocked"].includes(
          job.state ?? job.status ?? "",
        )
      )
        throw new Error(
          typeof job.error === "string"
            ? job.error
            : job.error
              ? JSON.stringify(job.error)
              : `작업 ${statusLabel(job.state ?? job.status)}`,
        );
      return job;
    }
    await new Promise<void>((resolve, reject) => {
      const abort = () => {
        clearTimeout(timer);
        reject(new DOMException("작업 대기 취소", "AbortError"));
      };
      const timer = setTimeout(() => {
        signal.removeEventListener("abort", abort);
        resolve();
      }, 1000);
      signal.addEventListener("abort", abort, { once: true });
    });
  }
  throw new Error(
    "작업 상태 확인 시간이 초과되었습니다. 학습·평가에서 실제 작업 상태를 확인하세요.",
  );
}
