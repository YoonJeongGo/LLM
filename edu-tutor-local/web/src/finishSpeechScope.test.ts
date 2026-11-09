import { afterEach, describe, expect, it, vi } from "vitest";
import { api, setExecutionAllowance, setToken } from "./api";
import { scopedAudioPath } from "./speechCache";

afterEach(() => { setToken(""); vi.unstubAllGlobals(); });

describe("explicit execution scope transport", () => {
  it("sends a selected scope and clears it on logout", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response("{}", { status: 200 })));
    vi.stubGlobal("fetch", fetchMock);
    setToken("fixture-token-not-a-secret");
    await api("/fixture");
    expect(new Headers(fetchMock.mock.calls[0][1].headers).has("X-Execution-Allowance")).toBe(false);
    setExecutionAllowance("fixture-approved-scope");
    await api("/fixture", { method: "POST", body: "{}" });
    expect(new Headers(fetchMock.mock.calls[1][1].headers).get("X-Execution-Allowance")).toBe("fixture-approved-scope");
    setToken(""); setToken("fixture-new-session");
    await api("/fixture");
    expect(new Headers(fetchMock.mock.calls[2][1].headers).has("X-Execution-Allowance")).toBe(false);
  });
});

describe("system and historical voice cache boundaries", () => {
  const binding = "b".repeat(64);
  const base = { step_id: "s1", audio_id: "a".repeat(64), binding_fingerprint: binding, cache_hit: true };
  const token = "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\fixture-korean";
  const route = (voice: string) => `/api/lessons/lesson/speech/s1/audio?${new URLSearchParams({ voice, binding })}`;

  it("accepts the installed system voice only when URL and voice metadata agree", () => {
    const audio = { ...base, provider: "windows_sapi_local", voice: token, audio_url: route("windows_sapi:" + token) };
    expect(scopedAudioPath(audio, "lesson", "s1")).toContain("/lessons/lesson/speech/s1/audio?");
    expect(() => scopedAudioPath({ ...audio, voice: token + "changed" }, "lesson", "s1")).toThrow();
    expect(() => scopedAudioPath({ ...audio, audio_url: route("Sohee") }, "lesson", "s1")).toThrow();
    expect(() => scopedAudioPath({ ...audio, binding_fingerprint: "c".repeat(64) }, "lesson", "s1")).toThrow();
    expect(() => scopedAudioPath({ ...audio, audio_url: audio.audio_url + "&execution_allowance_id=other" }, "lesson", "s1")).toThrow();
  });

  it("retains the legacy Sohee route without weakening target or origin checks", () => {
    const audio = { ...base, provider: "qwen3_tts_local", voice: "Sohee", audio_url: route("Sohee") };
    expect(scopedAudioPath(audio, "lesson", "s1")).toContain("voice=Sohee");
    expect(() => scopedAudioPath(audio, "other-lesson", "s1")).toThrow();
    expect(() => scopedAudioPath({ ...audio, audio_url: "https://example.invalid" + audio.audio_url }, "lesson", "s1")).toThrow();
  });
});
