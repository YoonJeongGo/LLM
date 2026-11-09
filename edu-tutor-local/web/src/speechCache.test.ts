import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, protectedBlob } from "./api";
import { cancelSpeechRequest, type SpeechRequest } from "./student";
import raw from "./lesson.fixture.json";
import { parseLesson } from "./lesson";
import { CacheMissError, OneAhead, cachedStep, prepareNextSpeech, sameCachedSpeech, savedSupplementMatches, scopedAudioPath, validateVisibleSpeech } from "./speechCache";
vi.mock("./api", async (original) => ({ ...await original<typeof import("./api")>(), api: vi.fn(), protectedBlob: vi.fn() }));
const apiMock = vi.mocked(api);
const expectedPlan = parseLesson(raw);
const audio = { step_id: "s1", audio_id: "a".repeat(64), binding_fingerprint: "b".repeat(64), cache_hit: true,
  audio_url: `/api/lessons/lesson/speech/s1/audio?voice=Sohee&binding=${"b".repeat(64)}` };
function mockResponses(manifestOverrides: Record<string, unknown> = {}, lessonOverrides: Record<string, unknown> = {}) {
  const current = { id: "lesson", valid: true, speech_allowed: true, plan: expectedPlan,
    speech_binding_fingerprint: audio.binding_fingerprint, ...lessonOverrides };
  const manifest = { replay_only: true, binding_fingerprint: audio.binding_fingerprint, steps: [audio], ...manifestOverrides };
  apiMock.mockImplementation(async (path) => (String(path).includes("/speech?") ? manifest : current) as any);
}
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => resolve = done); return { promise, resolve }; }
beforeEach(() => apiMock.mockReset());
describe("GET-only cache replay", () => {
  it("reads a valid step even with no generation budget and never posts", async () => {
    mockResponses();
    await expect(cachedStep("lesson", "s1", expectedPlan, new AbortController().signal, () => {})).resolves.toEqual(audio);
    expect(apiMock).toHaveBeenCalledTimes(2);
    expect(apiMock).toHaveBeenCalledWith("/lessons/lesson", expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(apiMock).toHaveBeenCalledWith("/lessons/lesson/speech?step_id=s1&voice=default", expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(apiMock.mock.calls.every(([, options]) => !options?.method || options.method === "GET")).toBe(true);
  });
  it("reports a miss without any fallback API", async () => {
    mockResponses({ steps: [], cache_misses: [{ step_id: "s1", reason: "checksum mismatch" }] });
    await expect(cachedStep("lesson", "s1", expectedPlan, new AbortController().signal, () => {})).rejects.toThrow("새 음성은 생성하지 않았습니다");
    expect(apiMock).toHaveBeenCalledTimes(2);
  });
  it("classifies only an explicit missing clip under a valid current binding as a cache miss", async () => {
    mockResponses({ steps: [], cache_misses: [{ step_id: "s1", code: "cache_missing", reason: "No existing clip" }] });
    await expect(cachedStep("lesson", "s1", expectedPlan, new AbortController().signal, () => {})).rejects.toBeInstanceOf(CacheMissError);
    expect(apiMock).toHaveBeenCalledTimes(2);
    expect(apiMock.mock.calls.every(([, options]) => !options?.method || options.method === "GET")).toBe(true);
  });
  it("does not turn a changed plan or binding into a regeneratable cache miss", async () => {
    const missing = { steps: [], cache_misses: [{ step_id: "s1", code: "cache_missing" }] };
    mockResponses({ ...missing, binding_fingerprint: "c".repeat(64) });
    await expect(cachedStep("lesson", "s1", expectedPlan, new AbortController().signal, () => {})).rejects.not.toBeInstanceOf(CacheMissError);
    const changed = structuredClone(expectedPlan);
    changed.steps[0].speech += " 변경";
    mockResponses(missing, { plan: changed });
    await expect(cachedStep("lesson", "s1", expectedPlan, new AbortController().signal, () => {})).rejects.not.toBeInstanceOf(CacheMissError);
  });
  it("keeps corrupt and unclassified caches as hard failures", async () => {
    for (const code of ["cache_checksum_mismatch", undefined]) {
      mockResponses({ steps: [], cache_misses: [{ step_id: "s1", code }] });
      await expect(cachedStep("lesson", "s1", expectedPlan, new AbortController().signal, () => {})).rejects.not.toBeInstanceOf(CacheMissError);
    }
  });
  it("rejects an unbound legacy manifest and foreign or altered audio routes", async () => {
    mockResponses({ steps: [{ step_id: "s1", audio_url: "/api/audio/" + audio.audio_id }] });
    await expect(cachedStep("lesson", "s1", expectedPlan, new AbortController().signal, () => {})).rejects.toThrow();
    expect(scopedAudioPath(audio, "lesson", "s1")).toContain("/lessons/lesson/speech/s1/audio?");
    expect(() => scopedAudioPath({ ...audio, audio_url: "https://example.invalid" + audio.audio_url }, "lesson", "s1")).toThrow();
    expect(() => scopedAudioPath(audio, "other", "s1")).toThrow();
    expect(() => scopedAudioPath({ ...audio, audio_url: audio.audio_url + "#x" }, "lesson", "s1")).toThrow();
    expect(() => scopedAudioPath({ ...audio, audio_url: audio.audio_url + "&voice=Sohee" }, "lesson", "s1")).toThrow();
    expect(sameCachedSpeech(audio, { ...audio, binding_fingerprint: "c".repeat(64) })).toBe(false);
    expect(sameCachedSpeech(audio, { ...audio, audio_id: "c".repeat(64) })).toBe(false);
  });
  it("rejects a new server plan even when its cache binding is valid", async () => {
    const changed = structuredClone(expectedPlan);
    changed.steps[0].speech += " 변경된 문장";
    mockResponses({}, { plan: changed });
    await expect(cachedStep("lesson", "s1", expectedPlan, new AbortController().signal, () => {})).rejects.toThrow("화면의 판서·대사");
  });
  it("requires the read-only lesson binding projection", async () => {
    mockResponses({}, { speech_binding_fingerprint: undefined });
    await expect(cachedStep("lesson", "s1", expectedPlan, new AbortController().signal, () => {})).rejects.toThrow("연결을 확인");
  });
  it("rejects a revision changed between the parallel lesson and manifest reads", async () => {
    mockResponses({ binding_fingerprint: "c".repeat(64) });
    await expect(cachedStep("lesson", "s1", expectedPlan, new AbortController().signal, () => {})).rejects.toThrow("조회 중");
    mockResponses({}, { speech_binding_fingerprint: "c".repeat(64) });
    await expect(cachedStep("lesson", "s1", expectedPlan, new AbortController().signal, () => {})).rejects.toThrow("조회 중");
  });
  it("rechecks foreground clips before rendering their audio", async () => {
    mockResponses();
    await expect(validateVisibleSpeech(audio, "lesson", "s1", expectedPlan, new AbortController().signal, () => {})).resolves.toEqual(audio);
    mockResponses({ steps: [{ ...audio, audio_id: "c".repeat(64) }] });
    await expect(validateVisibleSpeech(audio, "lesson", "s1", expectedPlan, new AbortController().signal, () => {})).rejects.toThrow("이전 음성을 폐기");
  });
  it("blocks invalid or malformed current lessons despite valid cached metadata", async () => {
    mockResponses({}, { valid: false });
    await expect(cachedStep("lesson", "s1", expectedPlan, new AbortController().signal, () => {})).rejects.toThrow();
    mockResponses({}, { plan: { lesson_id: "broken" } });
    await expect(cachedStep("lesson", "s1", expectedPlan, new AbortController().signal, () => {})).rejects.toThrow("계획 형식");
  });
});
describe("verified future synthesis", () => {
  function fixture(options: { quota?: number; allowed?: boolean; available?: boolean; code?: string; failed?: boolean; cacheHit?: boolean; changedAfterBudget?: boolean } = {}) {
    let ready = false, changed = false;
    const posts: any[] = [];
    vi.mocked(protectedBlob).mockReset().mockResolvedValue(new Blob(["fixture only"]));
    apiMock.mockImplementation(async (path, init) => {
      if (String(path).endsWith("/cancel")) return { state: "cancelled" } as any;
      if (init?.method === "POST") { posts.push(JSON.parse(String(init.body))); return { job_id: "next-job" } as any; }
      if (path === "/resources/budget") { changed = !!options.changedAfterBudget; return { enabled: true, new_audio_remaining: options.quota ?? 1 } as any; }
      if (path === "/jobs/next-job") {
        ready = !options.failed;
        return { state: options.failed ? "failed" : "succeeded", result: { steps: [{ ...audio, cache_hit: options.cacheHit }] } } as any;
      }
      if (String(path).includes("/speech?")) return {
        replay_only: true, generation_available: options.available !== false, binding_fingerprint: audio.binding_fingerprint,
        steps: ready ? [audio] : [], cache_misses: [{ step_id: "s1", code: options.code ?? "cache_missing" }],
      } as any;
      return { id: "lesson", valid: true, speech_allowed: options.allowed !== false,
        plan: changed ? { ...expectedPlan, steps: expectedPlan.steps.map(s => ({ ...s, speech: "changed" })) } : expectedPlan,
        speech_binding_fingerprint: audio.binding_fingerprint } as any;
    });
    return posts;
  }
  it.each([false, true, undefined])("one step POST reports actual job cache_hit=%s without inferring from cache GET", async cacheHit => {
    const posts = fixture({ cacheHit });
    const reserve = vi.fn(), trace = vi.fn();
    const result = await prepareNextSpeech("lesson", "s1", expectedPlan, { controller: new AbortController() }, trace, reserve);
    expect(posts).toHaveLength(1);
    expect(posts[0]).toMatchObject({ voice: "default", step_id: "s1", request_id: expect.any(String) });
    expect(reserve).toHaveBeenCalledTimes(1);
    expect(vi.mocked(protectedBlob)).toHaveBeenCalledTimes(1);
    expect(result.generationRequested).toBe(true);
    expect(result.generated).toBe(cacheHit === undefined ? undefined : !cacheHit);
  });
  it.each([{ quota: 0 }, { allowed: false }, { available: false }, { code: "cache_checksum_mismatch" }, { changedAfterBudget: true }])("blocks unsafe or unavailable future synthesis: %j", async options => {
    const posts = fixture(options), reserve = vi.fn();
    await expect(prepareNextSpeech("lesson", "s1", expectedPlan, { controller: new AbortController() }, () => {}, reserve)).rejects.not.toBeInstanceOf(CacheMissError);
    expect(posts).toHaveLength(0);
    expect(reserve).not.toHaveBeenCalled();
    expect(vi.mocked(protectedBlob)).not.toHaveBeenCalled();
  });
  it("keeps saved review cache-only even with available generation and positive quota", async () => {
    const posts = fixture();
    await expect(prepareNextSpeech("lesson", "s1", expectedPlan, { controller: new AbortController() }, () => {})).rejects.toBeInstanceOf(CacheMissError);
    expect(posts).toHaveLength(0);
    expect(apiMock.mock.calls.some(([path]) => path === "/resources/budget")).toBe(false);
  });
  it("a failed future job is a hard error, not a miss eligible for foreground retry", async () => {
    const posts = fixture({ failed: true });
    await expect(prepareNextSpeech("lesson", "s1", expectedPlan, { controller: new AbortController() }, () => {}, () => {})).rejects.not.toBeInstanceOf(CacheMissError);
    expect(posts).toHaveLength(1);
    expect(vi.mocked(protectedBlob)).not.toHaveBeenCalled();
  });
  it("a completed future job keeps its owner identity for stop without another synthesis", async () => {
    const posts = fixture();
    const request: SpeechRequest = { controller: new AbortController() };
    await prepareNextSpeech("lesson", "s1", expectedPlan, request, () => {}, () => {});
    expect(request.id).toBe("next-job");
    await cancelSpeechRequest(request);
    expect(apiMock).toHaveBeenCalledWith("/jobs/next-job/cancel", expect.objectContaining({ method: "POST" }));
    expect(posts).toHaveLength(1);
  });
});
describe("one future cached unit", () => {
  it("starts during the current unit, deduplicates and consumes only the matching next key", async () => {
    const buffer = new OneAhead<number>(), next = deferred<number>(), load = vi.fn(() => next.promise);
    buffer.prepare("s2", load); buffer.prepare("s2", load);
    expect(load).toHaveBeenCalledTimes(1);
    next.resolve(2);
    expect(await buffer.take("s3", new AbortController().signal)).toBeUndefined();
    expect(await buffer.take("s2", new AbortController().signal)).toBe(2);
    expect(await buffer.take("s2", new AbortController().signal)).toBeUndefined();
  });
  it("replacing the one slot aborts the old future unit and ignores its late result", async () => {
    const buffer = new OneAhead<number>(), old = deferred<number>(); let oldSignal!: AbortSignal;
    buffer.prepare("s2", signal => { oldSignal = signal; return old.promise; });
    buffer.prepare("s3", async () => 3);
    expect(oldSignal.aborted).toBe(true); old.resolve(2);
    expect(await buffer.take("s2", new AbortController().signal)).toBeUndefined();
    expect(await buffer.take("s3", new AbortController().signal)).toBe(3);
  });
  it("interrupt/unmount clear aborts a pending load and no late unit is retained", async () => {
    const buffer = new OneAhead<number>(), late = deferred<number>(); let signal!: AbortSignal;
    buffer.prepare("s2", value => { signal = value; return late.promise; });
    buffer.clear(); expect(signal.aborted).toBe(true); late.resolve(2);
    expect(await buffer.take("s2", new AbortController().signal)).toBeUndefined();
  });
  it("a consumed pending unit remains cancellable by the current step request", async () => {
    const buffer = new OneAhead<number>(), late = deferred<number>(), controller = new AbortController(); let signal!: AbortSignal;
    buffer.prepare("s2", value => { signal = value; return late.promise; });
    const taken = buffer.take("s2", controller.signal);
    const rejected = expect(taken).rejects.toThrow();
    controller.abort(); expect(signal.aborted).toBe(true); late.resolve(2); await rejected;
  });
  it("an already cancelled consumer aborts the detached future controller", async () => {
    const buffer = new OneAhead<number>(), controller = new AbortController(); let signal!: AbortSignal;
    buffer.prepare("s2", value => { signal = value; return Promise.resolve(2); });
    controller.abort();
    await expect(buffer.take("s2", controller.signal)).rejects.toThrow();
    expect(signal.aborted).toBe(true);
  });
});
describe("saved supplement relationship", () => {
  const original = { valid: true, plan: { lesson_id: "b", problem_revision: 4 }, problem: { id: "p", revision: 4 }, evidence: { problem_id: "p", problem_revision: 4 } };
  const supplement = { ...original, speech_allowed: true, plan: { lesson_id: "c", problem_revision: 4 }, source_lesson_context: { lesson_id: "b", problem_revision: 4 } };
  it("requires the original plan and matching problem/evidence revisions", () => {
    expect(savedSupplementMatches(original, supplement)).toBe(true);
    expect(savedSupplementMatches(original, { ...supplement, source_lesson_context: { lesson_id: "other", problem_revision: 4 } })).toBe(false);
    expect(savedSupplementMatches(original, { ...supplement, evidence: { problem_id: "p", problem_revision: 5 } })).toBe(false);
    expect(savedSupplementMatches(original, { ...supplement, valid: false })).toBe(false);
    expect(savedSupplementMatches({ ...original, source_session_id: "a" }, { ...supplement, source_session_id: "b" })).toBe(false);
  });
});
