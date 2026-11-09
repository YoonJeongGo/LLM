import { test, expect } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
const checkpoint = JSON.parse(
  readFileSync(
    resolve(process.cwd(), "../runs/integration-live/latest-text.json"),
    "utf8",
  ),
);
const tokenPath = resolve(process.cwd(), "../.local/auth-token");
test("T3 actual saved model lesson and real cached TTS browser playback", async ({
  page,
}) => {
  const pageErrors: string[] = [],
    forbidden: string[] = [],
    audioResponses: any[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.route("**/api/**", async (route) => {
    if (route.request().method() !== "GET") {
      forbidden.push(
        `${route.request().method()} ${new URL(route.request().url()).pathname}`,
      );
      await route.abort();
      return;
    }
    await route.continue();
  });
  page.on("response", (response) => {
    if (/\/api\/audio\//.test(response.url()))
      audioResponses.push({ status: response.status(), url: response.url() });
  });
  await page.addInitScript(
    ({ session, lesson }) => {
      localStorage.setItem("edu-session", session);
      localStorage.setItem("edu-lesson", lesson);
      localStorage.setItem("edu-tab", "chat");
    },
    { session: checkpoint.session_id, lesson: checkpoint.lesson_id },
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.getByRole("button", { name: "서버 연결 필요" }).click();
  await page
    .getByLabel("로컬 토큰 파일", { exact: true })
    .setInputFiles(tokenPath);
  await expect(page.getByRole("button", { name: "로컬 연결됨" })).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "대화", exact: true })
    .click();
  await expect(
    page.getByText("모델 답변 · 정확성 미검증", { exact: true }).first(),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results-t3/actual-chat-1440.png",
    fullPage: true,
  });
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "강의실", exact: true })
    .click();
  await expect(page.locator(".chalk-stage")).toBeVisible();
  await expect(page.getByText("데모 데이터 재생", { exact: true })).toHaveCount(
    0,
  );
  await page.getByRole("button", { name: "현재 단계 음성 준비" }).click();
  await expect(page.locator("audio")).toHaveCount(1);
  await page.getByRole("button", { name: "음성 재생", exact: true }).click();
  await expect
    .poll(() =>
      page
        .locator("audio")
        .evaluate((audio: HTMLAudioElement) => audio.currentTime),
    )
    .toBeGreaterThan(0.5);
  const duration = await page
    .locator("audio")
    .evaluate((audio: HTMLAudioElement) => audio.duration);
  expect(duration).toBeGreaterThan(7);
  await page.getByRole("button", { name: "일시정지", exact: true }).click();
  expect(
    await page
      .locator("audio")
      .evaluate((audio: HTMLAudioElement) => audio.paused),
  ).toBe(true);
  const pausedAt = await page
    .locator("audio")
    .evaluate((audio: HTMLAudioElement) => audio.currentTime);
  await page.getByLabel("음성 재생 속도").selectOption("1.25");
  await page.getByRole("button", { name: "음성 재생", exact: true }).click();
  await expect
    .poll(() =>
      page
        .locator("audio")
        .evaluate((audio: HTMLAudioElement) => audio.currentTime),
    )
    .toBeGreaterThan(pausedAt + 0.2);
  expect(
    await page
      .locator("audio")
      .evaluate((audio: HTMLAudioElement) => audio.playbackRate),
  ).toBe(1.25);
  await page.getByRole("button", { name: "일시정지", exact: true }).click();
  await page.getByRole("button", { name: "음성 재생", exact: true }).click();
  await expect
    .poll(
      () =>
        page
          .locator("audio")
          .evaluate((audio: HTMLAudioElement) => audio.ended),
      { timeout: 15000 },
    )
    .toBe(true);
  expect(await page.locator("[data-board-element]").count()).toBeGreaterThan(0);
  for (const [width, height] of [
    [1440, 900],
    [1280, 720],
    [390, 844],
  ]) {
    await page.setViewportSize({ width, height });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results-t3/actual-lecture-${width}.png`,
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.locator('button[aria-label="다음 단계"]').click();
  await page.getByRole("button", { name: "현재 단계 음성 준비" }).click();
  await page.getByRole("button", { name: "음성 재생", exact: true }).click();
  await expect
    .poll(() =>
      page
        .locator("audio")
        .evaluate((audio: HTMLAudioElement) => audio.currentTime),
    )
    .toBeGreaterThan(0.3);
  const secondDuration = await page
    .locator("audio")
    .evaluate((audio: HTMLAudioElement) => audio.duration);
  await page.getByRole("button", { name: "일시정지", exact: true }).click();
  expect(secondDuration).toBeGreaterThan(8);
  expect(forbidden).toEqual([]);
  expect(pageErrors).toEqual([]);
  expect(audioResponses).toHaveLength(2);
  expect(audioResponses.every((response) => response.status === 200)).toBe(
    true,
  );
  writeFileSync(
    "test-results-t3/actual-evidence.json",
    JSON.stringify(
      {
        source: "actual_local_model_and_cached_qwen_tts",
        checkpoint,
        firstDuration: duration,
        secondDuration,
        pausedAt,
        audioResponses,
        gpuPostRequests: forbidden,
        pageErrors,
        verified: [
          "authenticated actual answer",
          "unverified label",
          "actual structured lesson",
          "actual cached WAV browser clock",
          "pause/resume",
          "speed",
          "responsive 1440/1280/390",
          "two step audio",
        ],
        notVerified: [
          "educational correctness",
          "human voice quality",
          "phoneme lip sync",
          "live interruption reexplanation",
        ],
      },
      null,
      2,
    ),
  );
});

test("T3 actual S2 one interruption explanation audio and original return", async ({
  page,
}) => {
  test.skip(
    process.env.EDU_RUN_ACTUAL_S2 !== "1",
    "Explicit GPU authorization required; default read-only T3 never starts this test.",
  );
  test.setTimeout(600000);
  const evidence: any = {
    source: "actual_local_model_s2",
    checkpoint,
    started_at: new Date().toISOString(),
    requests: [],
    jobs: {},
    human_review: "not_reviewed",
    education_correctness: "unverified",
  };
  const limits: Record<string, number> = {
    question: 1,
    lesson: 1,
    plan: 1,
    speech: 1,
  };
  await page.route("**/api/**", async (route) => {
    const req = route.request(),
      path = new URL(req.url()).pathname;
    if (req.method() === "GET") {
      await route.continue();
      return;
    }
    const kind = /\/sessions\/[^/]+\/messages$/.test(path)
      ? "question"
      : path === "/api/lessons"
        ? "lesson"
        : /\/lessons\/[^/]+\/generate$/.test(path)
          ? "plan"
          : /\/lessons\/[^/]+\/speech$/.test(path)
            ? "speech"
            : "unexpected";
    evidence.requests.push({ method: req.method(), path, kind });
    if (!limits[kind]) {
      evidence.budget_blocked = kind;
      await route.abort();
      return;
    }
    limits[kind]--;
    await route.continue();
  });
  page.on("response", async (response) => {
    const path = new URL(response.url()).pathname;
    if (/\/api\/jobs\/[^/]+$/.test(path))
      try {
        const job = await response.json();
        evidence.jobs[job.id] = {
          kind: job.kind,
          state: job.state,
          error: job.error,
          result: job.result,
        };
      } catch {}
    if (response.request().method() === "POST" && path.endsWith("/messages"))
      evidence.question_request = response.request().postDataJSON();
  });
  await page.addInitScript(
    ({ session, lesson }) => {
      localStorage.setItem("edu-session", session);
      localStorage.setItem("edu-lesson", lesson);
      localStorage.setItem("edu-tab", "chat");
    },
    { session: checkpoint.session_id, lesson: checkpoint.lesson_id },
  );
  try {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    await page.getByRole("button", { name: "서버 연결 필요" }).click();
    await page
      .getByLabel("로컬 토큰 파일", { exact: true })
      .setInputFiles(tokenPath);
    await expect(
      page.getByRole("button", { name: "로컬 연결됨" }),
    ).toBeVisible();
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "대화", exact: true })
      .click();
    await expect(page.locator(".message-assistant").first()).toBeVisible();
    const originalMessageCount = await page
      .locator(".message-assistant")
      .count();
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "강의실", exact: true })
      .click();
    await expect(page.locator(".chalk-stage")).toBeVisible();
    const originalTitle = await page.locator("main h1").textContent();
    await page.locator('button[aria-label="다음 단계"]').click();
    await page.getByRole("button", { name: "현재 단계 음성 준비" }).click();
    await page.getByRole("button", { name: "음성 재생", exact: true }).click();
    await expect
      .poll(() =>
        page
          .locator("audio")
          .evaluate((audio: HTMLAudioElement) => audio.currentTime),
      )
      .toBeGreaterThan(2);
    await page
      .getByLabel("강의 중 질문")
      .fill(
        "지금 설명에서 COUNT(*)와 COUNT(v)가 헷갈립니다. sample(v)에 1, NULL, 3 세 행이 있을 때 두 값이 왜 다른지 두 문장으로 쉽게 다시 설명해 주세요.",
      );
    await page.getByRole("button", { name: "강의 멈추고 질문" }).click();
    await expect(
      page.getByText("강의를 멈추고 현재 칠판을 보존했습니다.", {
        exact: true,
      }),
    ).toBeVisible();
    expect(
      await page
        .locator("audio")
        .evaluate((audio: HTMLAudioElement) => audio.paused),
    ).toBe(true);
    const originalBoard = await page.locator(".chalk-board").innerText();
    evidence.original = { title: originalTitle, board: originalBoard };
    await page.screenshot({
      path: "test-results-t3/s2-original-interrupted.png",
      fullPage: true,
    });
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "대화", exact: true })
      .click();
    await expect(page.locator(".message-assistant")).toHaveCount(
      originalMessageCount + 1,
      { timeout: 180000 },
    );
    evidence.answer = await page
      .locator(".message-assistant")
      .last()
      .innerText();
    await page.screenshot({
      path: "test-results-t3/s2-actual-answer.png",
      fullPage: true,
    });
    await page
      .locator(".message-assistant")
      .last()
      .getByRole("button", { name: "강의 보기", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "설명 텍스트" }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "이 답변으로 판서 강의 생성", exact: true })
      .click();
    await expect(page.locator(".chalk-stage")).toBeVisible({ timeout: 240000 });
    evidence.new_lesson_id = await page.evaluate(() =>
      localStorage.getItem("edu-lesson"),
    );
    expect(evidence.new_lesson_id).not.toBe(checkpoint.lesson_id);
    await page.getByRole("button", { name: "현재 단계 음성 준비" }).click();
    await expect(
      page.getByRole("button", { name: "음성 재생", exact: true }),
    ).toBeVisible({ timeout: 300000 });
    await page.getByRole("button", { name: "음성 재생", exact: true }).click();
    await expect
      .poll(() =>
        page
          .locator("audio")
          .evaluate((audio: HTMLAudioElement) => audio.currentTime),
      )
      .toBeGreaterThan(0.5);
    evidence.new_audio_duration = await page
      .locator("audio")
      .evaluate((audio: HTMLAudioElement) => audio.duration);
    await page.getByRole("button", { name: "일시정지", exact: true }).click();
    await page.screenshot({
      path: "test-results-t3/s2-reexplanation-audio.png",
      fullPage: true,
    });
    await page
      .getByRole("button", { name: "원래 강의로 돌아가기", exact: true })
      .click();
    await expect(page.locator("main h1")).toHaveText(originalTitle!);
    await expect(page.locator(".chalk-board")).toHaveText(
      originalBoard.replace(/\n/g, " "),
      { useInnerText: true },
    );
    expect(await page.evaluate(() => localStorage.getItem("edu-lesson"))).toBe(
      checkpoint.lesson_id,
    );
    expect(await page.locator("audio").count()).toBe(0);
    await page.screenshot({
      path: "test-results-t3/s2-original-returned.png",
      fullPage: true,
    });
    evidence.status = "passed";
    evidence.returned_board = await page.locator(".chalk-board").innerText();
    evidence.audio_post_count = evidence.requests.filter(
      (request: any) => request.kind === "speech",
    ).length;
    expect(evidence.audio_post_count).toBe(1);
    expect(evidence.budget_blocked).toBeUndefined();
  } catch (error) {
    evidence.status = "failed";
    evidence.error = String(error);
    await page
      .screenshot({ path: "test-results-t3/s2-failure.png", fullPage: true })
      .catch(() => {});
    throw error;
  } finally {
    evidence.completed_at = new Date().toISOString();
    writeFileSync(
      "test-results-t3/s2-evidence.json",
      JSON.stringify(evidence, null, 2),
    );
  }
});
