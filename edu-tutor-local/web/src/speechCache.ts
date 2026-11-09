import { activeJob, api, protectedBlob } from "./api";
import { parseLesson } from "./lesson";
import type { Lesson } from "./lesson";
import { cancelSpeechRequest } from "./student";
import type { SpeechRequest } from "./student";

export type CachedSpeech = {
  step_id: string; audio_id: string; audio_url: string;
  binding_fingerprint: string; cache_hit: boolean;
  provider?: string; voice?: string;
};
export type Trace = (type: string, detail?: Record<string, unknown>) => void;
const hash = /^[a-f0-9]{64}$/;
/** Only an explicit, current-plan cache miss may reach normal generation. */
export class CacheMissError extends Error {
  readonly name = "CacheMissError";
  constructor(message: string, readonly generationAllowed = false) { super(message); }
}
export async function cachedStep(lesson: string, step: string, expectedPlan: Lesson, signal: AbortSignal, trace: Trace): Promise<CachedSpeech> {
  const started = performance.now();
  trace("cache_manifest_start");
  const [current, manifest] = await Promise.all([
    api<any>(`/lessons/${encodeURIComponent(lesson)}`, { signal }),
    api<any>(`/lessons/${encodeURIComponent(lesson)}/speech?step_id=${encodeURIComponent(step)}&voice=default`, { signal }),
  ]);
  signal.throwIfAborted();
  const audio = manifest.steps?.find((item: CachedSpeech) => item.step_id === step);
  trace("cache_manifest_end", { elapsed_ms: performance.now() - started, hit: !!audio });
  if (current.id !== lesson || current.valid === false || !current.plan ||
      !hash.test(current.speech_binding_fingerprint || ""))
    throw new Error("현재 수업의 판서·음성 연결을 확인할 수 없어 재생을 멈췄습니다.");
  const currentPlan = parseLesson(current.plan);
  if (JSON.stringify(currentPlan) !== JSON.stringify(expectedPlan))
    throw new Error("화면의 판서·대사와 현재 저장 수업이 달라 재생을 멈췄습니다. 수업을 다시 열어 주세요.");
  if (!manifest.replay_only || !hash.test(manifest.binding_fingerprint || ""))
    throw new Error("저장 음성의 검증 정보를 확인할 수 없어 재생을 멈췄습니다. 새 음성은 생성하지 않았습니다.");
  if (current.speech_binding_fingerprint !== manifest.binding_fingerprint)
    throw new Error("조회 중 문제·판서·음성이 바뀌어 재생을 멈췄습니다. 새 음성은 생성하지 않았습니다.");
  if (!audio) {
    const miss = manifest.cache_misses?.find((item: any) => item.step_id === step);
    const message = `저장된 수업의 현재 단계 음성을 사용할 수 없습니다. 새 음성은 생성하지 않았습니다.${miss?.reason ? ` (${miss.reason})` : ""}`;
    if (miss?.code === "cache_missing")
      throw new CacheMissError(message, current.speech_allowed === true && manifest.generation_available === true);
    throw new Error(message);
  }
  if (!hash.test(audio.audio_id) || !hash.test(audio.binding_fingerprint))
    throw new Error("저장 음성의 검증 정보를 확인할 수 없어 재생을 멈췄습니다. 새 음성은 생성하지 않았습니다.");
  if (manifest.binding_fingerprint !== audio.binding_fingerprint)
    throw new Error("조회 중 문제·판서·음성이 바뀌어 재생을 멈췄습니다. 새 음성은 생성하지 않았습니다.");
  return audio;
}
/** Recheck a foreground clip too: its valid server binding must match the visible board. */
export async function validateVisibleSpeech(audio: CachedSpeech, lesson: string, step: string, expectedPlan: Lesson, signal: AbortSignal, trace: Trace): Promise<CachedSpeech> {
  const current = await cachedStep(lesson, step, expectedPlan, signal, trace);
  if (!sameCachedSpeech(audio, current))
    throw new Error("준비 중 문제·판서·음성이 바뀌어 이전 음성을 폐기했습니다. 새 음성은 생성하지 않았습니다.");
  return current;
}
export function scopedAudioPath(audio: CachedSpeech, lesson: string, step: string) {
  const url = new URL(audio.audio_url, "http://local.invalid");
  const expected = `/api/lessons/${encodeURIComponent(lesson)}/speech/${encodeURIComponent(step)}/audio`;
  const voice = audio.provider === "windows_sapi_local" ? `windows_sapi:${audio.voice}` : (audio.voice || "Sohee");
  if (url.origin !== "http://local.invalid" || url.hash || url.pathname !== expected || url.searchParams.get("voice") !== voice ||
      url.searchParams.get("binding") !== audio.binding_fingerprint || !hash.test(audio.binding_fingerprint) ||
      [...url.searchParams.keys()].some((key) => key !== "voice" && key !== "binding") ||
      url.searchParams.getAll("voice").length !== 1 || url.searchParams.getAll("binding").length !== 1)
    throw new Error("저장 음성의 검증 주소가 일치하지 않습니다.");
  return url.pathname.slice(4) + url.search;
}
export type PreparedSpeech = { audio: CachedSpeech; blob: Blob; waveform: Promise<number[]>; generationRequested?: boolean; generated?: boolean };
export async function decodeWaveform(blob: Blob, trace: Trace): Promise<number[]> {
  const started = performance.now();
  trace("audio_decode_start");
  let context: AudioContext | undefined;
  try {
    context = new AudioContext();
    const buffer = await context.decodeAudioData(await blob.arrayBuffer());
    const samples = buffer.getChannelData(0), size = Math.max(1, Math.floor(buffer.sampleRate / 20)), peaks: number[] = [];
    for (let i = 0; i < samples.length; i += size) {
      let sum = 0;
      for (let j = i; j < Math.min(i + size, samples.length); j++) sum += samples[j] * samples[j];
      peaks.push(Math.sqrt(sum / Math.min(size, samples.length - i)));
    }
    return peaks;
  } catch { return []; }
  finally {
    if (context) await context.close().catch(() => {});
    trace("audio_decode_end", { elapsed_ms: performance.now() - started });
  }
}
export async function prepareCachedSpeech(lesson: string, step: string, expectedPlan: Lesson, signal: AbortSignal, trace: Trace): Promise<PreparedSpeech> {
  const audio = await cachedStep(lesson, step, expectedPlan, signal, trace);
  const started = performance.now();
  trace("audio_fetch_start", { audio_id: audio.audio_id });
  const blob = await protectedBlob(scopedAudioPath(audio, lesson, step), signal);
  signal.throwIfAborted();
  trace("audio_fetch_end", { audio_id: audio.audio_id, elapsed_ms: performance.now() - started, bytes: blob.size });
  // Optional mouth animation decoding never gates valid WAV playback.
  return { audio, blob, waveform: decodeWaveform(blob, trace) };
}
/** Prepare at most the requested step; server jobs retain GPU serialization and accounting. */
export async function prepareNextSpeech(lesson: string, step: string, expectedPlan: Lesson, request: SpeechRequest,
  trace: Trace, reserveGeneration?: () => void): Promise<PreparedSpeech> {
  const signal = request.controller.signal;
  try {
    try { return await prepareCachedSpeech(lesson, step, expectedPlan, signal, trace); }
    catch (error) {
      if (!(error instanceof CacheMissError) || !reserveGeneration) throw error;
      trace("next_cache_prefetch_miss", { generation_started: false });
      if (!error.generationAllowed) throw new Error("다음 설명의 음성 생성이 허용되지 않아 준비를 멈췄습니다.");
    }
    const budget = await api<any>("/resources/budget", { signal });
    signal.throwIfAborted();
    if (budget.enabled && budget.new_audio_remaining < 1)
      throw new Error("새 음성 생성 한도를 모두 사용했습니다. 현재 칠판과 자막을 보존합니다.");
    // A changed plan is blocked and a cache that arrived during this read is reused.
    try { return await prepareCachedSpeech(lesson, step, expectedPlan, signal, trace); }
    catch (error) {
      if (!(error instanceof CacheMissError) || !error.generationAllowed) throw error;
    }
    signal.throwIfAborted();
    reserveGeneration();
    const startedAt = performance.now();
    trace("next_speech_generation_start", { generation_requested: true });
    // Keep a late POST response observable so its job can still be cancelled.
    request.creation = api(`/lessons/${encodeURIComponent(lesson)}/speech`, {
      method: "POST", body: JSON.stringify({ voice: "default", step_id: step, request_id: crypto.randomUUID() }),
    });
    const created = await request.creation;
    request.id = created.job_id;
    if (!request.id) throw new Error("다음 음성 작업 식별자를 확인하지 못했습니다.");
    trace("next_speech_job_created", { job_id: request.id });
    signal.throwIfAborted();
    let generated: boolean | undefined;
    for (;;) {
      const job = await api<any>(`/jobs/${request.id}`, { signal });
      signal.throwIfAborted();
      if (!activeJob(job)) {
        // A completed synthesis can retain a resident TTS worker. Keep its
        // owner ID so the existing cancellation path can release that worker.
        if (!["succeeded", "completed"].includes(job.state ?? job.status))
          throw new Error(typeof job.error === "string" ? job.error : "다음 설명의 음성 준비에 실패했습니다. 자동으로 다시 생성하지 않습니다.");
        request.completed = true;
        const produced = job.result?.steps?.find((item: any) => item.step_id === step);
        if (typeof produced?.cache_hit === "boolean") generated = !produced.cache_hit;
        break;
      }
      await new Promise<void>((resolve, reject) => {
        const abort = () => { clearTimeout(timer); reject(new DOMException("다음 음성 준비 취소", "AbortError")); };
        const timer = setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, 350);
        signal.addEventListener("abort", abort, { once: true });
      });
    }
    const unit = await prepareCachedSpeech(lesson, step, expectedPlan, signal, trace);
    trace("next_speech_generation_ready", { job_elapsed_ms: performance.now() - startedAt, audio_id: unit.audio.audio_id,
      generated: generated ?? null, cached: generated === undefined ? null : !generated });
    return { ...unit, generationRequested: true, generated };
  } catch (error) {
    if (request.id || request.creation) await cancelSpeechRequest(request);
    // Failed synthesis cannot fall through to a second automatic foreground POST.
    if (reserveGeneration && error instanceof CacheMissError) throw new Error(error.message);
    throw error;
  }
}
/** One future unit only. This slot itself has no generation callback or POST dependency. */
export class OneAhead<T> {
  private entry?: { key: string; controller: AbortController; promise: Promise<T> };
  prepare(key: string, load: (signal: AbortSignal) => Promise<T>) {
    if (this.entry?.key === key) return;
    this.clear();
    const controller = new AbortController();
    const promise = load(controller.signal).then((value) => { controller.signal.throwIfAborted(); return value; });
    void promise.catch(() => {});
    this.entry = { key, controller, promise };
  }
  async take(key: string, signal: AbortSignal): Promise<T | undefined> {
    const entry = this.entry;
    if (!entry || entry.key !== key) return;
    this.entry = undefined;
    const abort = () => entry.controller.abort();
    signal.addEventListener("abort", abort, { once: true });
    try { if (signal.aborted) abort(); signal.throwIfAborted(); const value = await entry.promise; signal.throwIfAborted(); return value; }
    finally { signal.removeEventListener("abort", abort); }
  }
  clear() { this.entry?.controller.abort(); this.entry = undefined; }
}
export function sameCachedSpeech(before: CachedSpeech, after: CachedSpeech) {
  return before.step_id === after.step_id && before.audio_id === after.audio_id && before.binding_fingerprint === after.binding_fingerprint;
}
export function savedSupplementMatches(original: any, supplement: any): boolean {
  const context = supplement.source_lesson_context;
  const a = original.original_problem || original.problem, b = supplement.original_problem || supplement.problem;
  return original.valid !== false && supplement.valid !== false && !!original.plan && !!supplement.plan &&
    (!original.source_session_id || !supplement.source_session_id || original.source_session_id === supplement.source_session_id) &&
    supplement.speech_allowed === true && context?.lesson_id === original.plan.lesson_id &&
    context.problem_revision === original.plan.problem_revision && !!a?.id && a.id === b?.id && a.revision === b.revision &&
    original.plan.problem_revision === a.revision && supplement.plan.problem_revision === a.revision &&
    original.evidence?.problem_id === a.id && supplement.evidence?.problem_id === a.id &&
    original.evidence?.problem_revision === a.revision && supplement.evidence?.problem_revision === a.revision;
}
