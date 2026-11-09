import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import { cancelSpeechRequest } from "./student";
import type { SpeechRequest } from "./student";

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  api: vi.fn(),
}));
const mockedApi = vi.mocked(api);
function pendingCreation() {
  let resolve!: (value: { job_id: string }) => void;
  const creation = new Promise<{ job_id: string }>((done) => {
    resolve = done;
  });
  const request: SpeechRequest = {
    controller: new AbortController(),
    creation,
  };
  return { request, resolve };
}
beforeEach(() => {
  vi.useFakeTimers();
  mockedApi.mockReset();
});
afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe("bounded speech cancellation", () => {
  it("rejects within 15 seconds when POST creation never resolves", async () => {
    const { request } = pendingCreation();
    const cancellation = cancelSpeechRequest(request);
    const rejection = expect(cancellation).rejects.toThrow("15초");
    expect(request.controller.signal.aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(15000);
    await rejection;
    expect(mockedApi).not.toHaveBeenCalled();
  });

  it("cancels a late-created job independently of the already rejected UI wait", async () => {
    const { request, resolve } = pendingCreation();
    const cancellation = cancelSpeechRequest(request);
    const rejection =
      expect(cancellation).rejects.toThrow("질문은 전송하지 않았습니다");
    await vi.advanceTimersByTimeAsync(15000);
    await rejection;
    expect(cancelSpeechRequest(request)).toBe(cancellation);
    mockedApi
      .mockResolvedValueOnce({ state: "cancelling" })
      .mockResolvedValueOnce({ state: "cancelled" });
    resolve({ job_id: "late-job" });
    await request.serverCancellation;
    expect(mockedApi).toHaveBeenNthCalledWith(
      1,
      "/jobs/late-job/cancel",
      expect.objectContaining({
        method: "POST",
        signal: expect.any(AbortSignal),
      }),
    );
    expect(mockedApi).toHaveBeenNthCalledWith(
      2,
      "/jobs/late-job",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(mockedApi).toHaveBeenCalledTimes(2);
    await expect(cancelSpeechRequest(request)).rejects.toThrow("15초");
    expect(vi.getTimerCount()).toBe(0);
  });

  it("resolves only after an on-time creation reaches a terminal server state", async () => {
    const { request, resolve } = pendingCreation();
    mockedApi
      .mockResolvedValueOnce({ state: "cancelling" })
      .mockResolvedValueOnce({ state: "cancelling" })
      .mockResolvedValueOnce({ state: "cancelled" });
    const cancellation = cancelSpeechRequest(request);
    let complete = false;
    void cancellation.then(() => {
      complete = true;
    });
    await vi.advanceTimersByTimeAsync(1000);
    resolve({ job_id: "on-time-job" });
    await vi.advanceTimersByTimeAsync(0);
    expect(complete).toBe(false);
    await vi.advanceTimersByTimeAsync(200);
    await cancellation;
    expect(complete).toBe(true);
    expect(mockedApi).toHaveBeenCalledTimes(3);
    expect(cancelSpeechRequest(request)).toBe(cancellation);
    expect(vi.getTimerCount()).toBe(0);
  });
});
