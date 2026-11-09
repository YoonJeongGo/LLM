import { describe, expect, it, vi } from "vitest";
import { api, setToken, streamEvents } from "./api";
import {
  activeNeuralRun,
  belongsToRun,
  boundedEvents,
  displayMode,
  eventCursor,
  sampleTone,
} from "./neuralEvents";
import type { NeuralEvent, NeuralRun, NeuralStructure } from "./neuralEvents";

const run: NeuralRun = {
  run_id: "run-a",
  job_id: "job-a",
  request_id: "request-a",
  generation_epoch: 4,
  state: "running",
  observer_enabled: true,
  observation_mode: "light",
};
const event: NeuralEvent = {
  ...run,
  event_type: "token",
  sequence_no: 2,
  payload: { token_ids: [42], cumulative_text: "한글" },
  source: "cpu_fixture",
};
const structure: NeuralStructure = {
  nodes: [{ path: "model.layers.0", type: "TestBlock", role: "block" }],
};

describe("CPU fixture: neural event safety and bounded display", () => {
  it("rejects other requests, generations and duplicate/out-of-order events", () => {
    expect(belongsToRun(event, run)).toBe(true);
    for (const changed of [
      { run_id: "other" },
      { request_id: "other" },
      { generation_epoch: 3 },
    ])
      expect(eventCursor({ ...event, ...changed }, 0, run).accepted).toBe(
        false,
      );
    expect(eventCursor(event, 2, run).accepted).toBe(false);
    expect(eventCursor(event, 3, run).accepted).toBe(false);
    expect(eventCursor(event, 0, run)).toEqual({
      accepted: true,
      sequence: 2,
      gaps: 1,
    });
  });
  it("treats snapshot as out-of-band so initial retained events are not suppressed", () => {
    expect(
      eventCursor({ ...event, event_type: "snapshot", sequence_no: 99 }, 0, run)
        .sequence,
    ).toBe(0);
    expect(eventCursor(event, 0, run).accepted).toBe(true);
  });
  it("ends LIVE on completion, disconnect, disabled observation, view pause or stale reception", () => {
    const context = {
      replay: false,
      run,
      connected: true,
      structure,
      recent: true,
    };
    expect(displayMode(context)).toBe("LIVE");
    for (const changed of [
      { connected: false },
      { recent: false },
      { paused: true },
      { run: { ...run, observer_enabled: false } },
      { run: { ...run, observation_mode: "off" as const } },
    ])
      expect(displayMode({ ...context, ...changed })).toBe("STALE");
    expect(
      displayMode({ ...context, run: { ...run, state: "completed" } }),
    ).toBe("STATIC");
    expect(displayMode({ ...context, run: null, structure: null })).toBe(
      "UNAVAILABLE",
    );
    expect(displayMode({ ...context, replay: true })).toBe("REPLAY");
  });
  it("bounds UI history without manufacturing lost events", () => {
    const first = Array.from({ length: 600 }, (_, i) => ({
      ...event,
      sequence_no: i,
    }));
    const value = boundedEvents(first, [{ ...event, sequence_no: 600 }]);
    expect(value).toHaveLength(600);
    expect(value[0].sequence_no).toBe(1);
    expect(value.at(-1)?.sequence_no).toBe(600);
  });
  it("uses fixed heatmap endpoints and distinguishes loading from terminal", () => {
    expect(sampleTone(4)).toBe(sampleTone(40));
    expect(sampleTone(-4)).toBe(sampleTone(-40));
    expect(sampleTone(4)).not.toBe(sampleTone(-4));
    expect(activeNeuralRun({ ...run, state: "loading" })).toBe(true);
    expect(activeNeuralRun({ ...run, state: "cancelled" })).toBe(false);
  });
});

describe("CPU fixture: authenticated Fetch SSE", () => {
  it("sends bearer only as header and decodes split Korean UTF8 + split CRLF", async () => {
    const raw = `: heartbeat\r\n\r\nevent: observation\r\ndata: ${JSON.stringify(event)}\r\n\r\n`;
    const bytes = new TextEncoder().encode(raw);
    const chunks = Array.from(bytes, (byte) => new Uint8Array([byte]));
    const body = new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(chunk);
        controller.close();
      },
    });
    const fetcher = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(body, {
        headers: { "content-type": "text/event-stream; charset=utf-8" },
      }),
    );
    setToken("CPU_FIXTURE_TOKEN_ONLY");
    const received: NeuralEvent[] = [];
    await streamEvents<NeuralEvent>(
      "/neural/runs/run-a/events?after=1",
      (value) => received.push(value),
      new AbortController().signal,
    );
    expect(received).toEqual([event]);
    expect(fetcher.mock.calls[0][0]).not.toContain("TOKEN");
    expect(fetcher.mock.calls[0][1]?.headers).toMatchObject({
      Authorization: "Bearer CPU_FIXTURE_TOKEN_ONLY",
    });
    fetcher.mockRestore();
  });
  it("rejects unauthorized and non-SSE responses without disclosing credentials", async () => {
    const fetcher = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response("{}", { status: 401 }))
      .mockResolvedValueOnce(
        new Response("{}", { headers: { "content-type": "application/json" } }),
      );
    await expect(
      streamEvents(
        "/neural/runs/a/events",
        () => undefined,
        new AbortController().signal,
      ),
    ).rejects.toThrow("401");
    await expect(
      streamEvents(
        "/neural/runs/a/events",
        () => undefined,
        new AbortController().signal,
      ),
    ).rejects.toThrow("스트림");
    fetcher.mockRestore();
  });
  it("caps a malformed stream frame and closes its reader", async () => {
    const fetcher = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("data: " + "x".repeat(2 * 1024 * 1024), {
        headers: { "content-type": "text/event-stream" },
      }),
    );
    await expect(
      streamEvents(
        "/neural/runs/a/events",
        () => undefined,
        new AbortController().signal,
      ),
    ).rejects.toThrow("한도");
    fetcher.mockRestore();
  });
});
