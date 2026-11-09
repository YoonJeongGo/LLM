import { test, expect } from "@playwright/test";
import type { Page, APIRequestContext } from "@playwright/test";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
const out = "test-results-phase2-live";
async function nav(page: Page, name: string) {
  const menu = page.getByRole("button", { name: "메뉴 열기" });
  if (await menu.isVisible()) await menu.click();
  await page
    .getByRole("navigation")
    .getByRole("button", { name, exact: true })
    .click();
}
async function board(page: Page) {
  return page.locator(".chalk-board").evaluate((element) => {
    const root = element.getBoundingClientRect(),
      round = (v: number) => Math.round(v * 10) / 10;
    return {
      elements: Array.from(
        element.querySelectorAll("[data-board-element]"),
      ).map((e) => {
        const b = e.getBoundingClientRect();
        return {
          id: (e as HTMLElement).dataset.boardElement,
          text: e.textContent,
          x: round(b.left - root.left),
          y: round(b.top - root.top),
          width: round(b.width),
          height: round(b.height),
        };
      }),
      cells: Array.from(element.querySelectorAll("[data-cell-id]")).map(
        (e) => ({
          id: (e as HTMLElement).dataset.cellId,
          text: e.textContent,
          class: e.className,
        }),
      ),
      rows: Array.from(element.querySelectorAll("[data-row-id]")).map((e) => ({
        id: (e as HTMLElement).dataset.rowId,
        class: e.className,
      })),
    };
  });
}
async function waitJob(api: APIRequestContext, id: string) {
  let job: any;
  await expect
    .poll(
      async () => {
        const response = await api.get(`/api/jobs/${id}`);
        expect(response.ok()).toBeTruthy();
        job = await response.json();
        return [
          "succeeded",
          "failed",
          "cancelled",
          "blocked",
          "interrupted",
        ].includes(job.state);
      },
      { timeout: 330000, intervals: [500, 1000] },
    )
    .toBe(true);
  expect(job.state, job.error).toBe("succeeded");
  return job;
}

test("T3 actual v0.2: populated COUNT board, two model/TTS supplements and exact original return", async ({
  page,
  playwright,
}) => {
  mkdirSync(out, { recursive: true });
  const checkpoint = JSON.parse(
    readFileSync(resolve("../runs/phase2/current/live/T02-count.json"), "utf8"),
  );
  const originalId = checkpoint.lesson.id,
    originalPlan = checkpoint.lesson.plan;
  expect(originalPlan.provenance).toBe("tool_derived");
  const token = readFileSync(resolve("../.local/auth-token"), "utf8").trim();
  const api = await playwright.request.newContext({
    baseURL: "http://127.0.0.1:8000",
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });
  const evidence: any = {
    tier: "T3",
    source: "actual_local_model_TTS_UI",
    started_at: new Date().toISOString(),
    checkpoint: { session_id: checkpoint.session_id, lesson_id: originalId },
    requests: [],
    audio_responses: [],
    page_errors: [],
    human_review: "not_reviewed",
    status: "running",
  };
  const save = () =>
    writeFileSync(`${out}/evidence.json`, JSON.stringify(evidence, null, 2));
  save();
  page.on("pageerror", (error) => evidence.page_errors.push(error.message));
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      /\/api\/sessions\/[^/]+\/messages$/.test(request.url())
    )
      evidence.requests.push({
        submitted_at: new Date().toISOString(),
        body: request.postDataJSON(),
      });
  });
  page.on("response", (response) => {
    if (/\/api\/audio\//.test(response.url()))
      evidence.audio_responses.push({
        url: new URL(response.url()).pathname,
        status: response.status(),
        at: new Date().toISOString(),
      });
  });
  try {
    await page.addInitScript(
      ({ session, id, planId }) => {
        localStorage.clear();
        localStorage.setItem("edu-session", session);
        localStorage.setItem("edu-lesson", id);
        localStorage.setItem("edu-tab", "classroom");
        localStorage.setItem(
          `lecture:${planId}`,
          JSON.stringify({ step: 0, progress: 1 }),
        );
      },
      {
        session: checkpoint.session_id,
        id: originalId,
        planId: originalPlan.lesson_id,
      },
    );
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/");
    await page.getByRole("button", { name: "서버 연결 필요" }).click();
    await page
      .getByLabel("로컬 토큰 파일", { exact: true })
      .setInputFiles(resolve("../.local/auth-token"));
    await expect(page.getByRole("button", { name: "로컬 연결됨" })).toBeVisible(
      { timeout: 60000 },
    );
    await nav(page, "강의실");
    await expect(page.locator(".chalk-board table")).toHaveCount(1);
    await page
      .getByRole("button", { name: "score, 2행: NULL", exact: true })
      .click();
    await page.getByRole("button", { name: "현재 단계 음성 준비" }).click();
    await expect(page.locator("audio")).toHaveCount(1);
    await page.getByRole("button", { name: "음성 재생", exact: true }).click();
    await expect
      .poll(() =>
        page.locator("audio").evaluate((a: HTMLAudioElement) => a.currentTime),
      )
      .toBeGreaterThan(0.15);
    await page
      .getByLabel("강의 중 질문")
      .fill("점수가 없는데 왜 사람 수에는 들어가?");
    await page.evaluate(() => {
      const audio = document.querySelector("audio")!,
        button = document.querySelector('[aria-label="강의 멈추고 질문"]')!;
      (window as any).__stopTimes = {};
      button.addEventListener(
        "click",
        () => {
          (window as any).__stopTimes.click = performance.now();
        },
        { once: true, capture: true },
      );
      audio.addEventListener(
        "pause",
        () => {
          (window as any).__stopTimes.pause = performance.now();
        },
        { once: true },
      );
    });
    let submitted = page.waitForResponse(
      (r) =>
        r.request().method() === "POST" &&
        /\/api\/sessions\/[^/]+\/messages$/.test(r.url()),
    );
    const firstStart = Date.now();
    await page.getByRole("button", { name: "강의 멈추고 질문" }).click();
    const firstResponse = await submitted;
    expect(firstResponse.status()).toBe(202);
    let request = await firstResponse.json();
    evidence.original_board = await board(page);
    evidence.original_snapshot = evidence.requests[0].body.lesson_context;
    expect(
      evidence.original_board.rows.some((r: any) =>
        r.class.includes("highlight-row"),
      ),
    ).toBe(true);
    expect(
      evidence.original_board.cells.some((c: any) => c.text === "80"),
    ).toBe(true);
    evidence.stop_times = await page.evaluate(
      () => (window as any).__stopTimes,
    );
    evidence.local_stop_seconds =
      (evidence.stop_times.pause - evidence.stop_times.click) / 1000;
    evidence.local_stop_goal_seconds = 0.3;
    evidence.local_stop_goal_met = evidence.local_stop_seconds <= 0.3;
    expect(Number.isFinite(evidence.local_stop_seconds)).toBe(true);
    expect(
      await page.locator("audio").evaluate((a: HTMLAudioElement) => a.paused),
    ).toBe(true);
    await page.screenshot({
      path: `${out}/01-populated-interruption.png`,
      fullPage: true,
    });
    save();
    for (let index = 0; index < 2; index++) {
      const started = index === 0 ? firstStart : Date.now();
      if (index === 1) {
        await page
          .getByRole("button", { name: "score, 2행: NULL", exact: true })
          .click();
        await page.getByLabel("강의 중 질문").fill("그럼 셋 다 점수가 없으면?");
        submitted = page.waitForResponse(
          (r) =>
            r.request().method() === "POST" &&
            /\/api\/sessions\/[^/]+\/messages$/.test(r.url()),
        );
        await page.getByRole("button", { name: "강의 멈추고 질문" }).click();
        const response = await submitted;
        expect(response.status()).toBe(202);
        request = await response.json();
      }
      const job = await waitJob(api, request.job_id);
      const messages = await (
        await api.get(`/api/sessions/${checkpoint.session_id}/messages`)
      ).json();
      const answer = messages.find((m: any) => m.id === job.result.message_id);
      const item: any = {
        question_index: index + 1,
        job_id: job.id,
        answer,
        request_to_answer_seconds: (Date.now() - started) / 1000,
      };
      evidence[`supplement_${index + 1}`] = item;
      save();
      expect(answer.evidence.status).toBe("verified");
      expect(answer.evidence.result.rows).toEqual(
        index === 0 ? [[3, 2]] : [[3, 0]],
      );
      if (index === 1) {
        expect(answer.evidence.scenario).toBe("hypothesis");
        expect(evidence.requests[1].body.hypothesis).toBeUndefined();
      }
      await nav(page, "대화");
      await expect(
        page.getByRole("button", { name: "강의 보기", exact: true }),
      ).toHaveCount(messages.filter((m: any) => m.role === "assistant").length);
      const createdResponse = page.waitForResponse(
        (response) =>
          response.request().method() === "POST" &&
          new URL(response.url()).pathname === "/api/lessons",
      );
      await page
        .getByRole("button", { name: "강의 보기", exact: true })
        .last()
        .click();
      const created = await (await createdResponse).json();
      const generate = page.getByRole("button", {
        name: "이 답변으로 판서 강의 생성",
        exact: true,
      });
      if (!created.plan) {
        await generate.click();
      }
      await expect(page.locator(".chalk-board")).toBeVisible({
        timeout: 330000,
      });
      item.first_valid_board_seconds = (Date.now() - started) / 1000;
      const id = await page.evaluate(() => localStorage.getItem("edu-lesson"));
      item.lesson = await (await api.get(`/api/lessons/${id}`)).json();
      expect(item.lesson.plan.provenance).toBe("tool_derived");
      const voiceStart = Date.now();
      await page.getByRole("button", { name: "현재 단계 음성 준비" }).click();
      await expect(
        page.getByRole("button", { name: "음성 재생", exact: true }),
      ).toBeVisible({ timeout: 330000 });
      item.voice_prepare_seconds = (Date.now() - voiceStart) / 1000;
      await page
        .getByRole("button", { name: "음성 재생", exact: true })
        .click();
      await expect
        .poll(() =>
          page
            .locator("audio")
            .evaluate((a: HTMLAudioElement) => a.currentTime),
        )
        .toBeGreaterThan(0.15);
      item.first_valid_audio_seconds = (Date.now() - started) / 1000;
      item.first_valid_audio_goal_seconds = 10;
      item.first_valid_audio_goal_met = item.first_valid_audio_seconds <= 10;
      item.audio_duration = await page
        .locator("audio")
        .evaluate((a: HTMLAudioElement) => a.duration);
      item.lesson = await (await api.get(`/api/lessons/${id}`)).json();
      await page.getByRole("button", { name: "일시정지", exact: true }).click();
      await page.screenshot({
        path: `${out}/0${index + 2}-supplement.png`,
        fullPage: true,
      });
      save();
    }
    const returnedAt = Date.now();
    await page
      .getByRole("button", { name: "원래 강의로 돌아가기", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: originalPlan.title, exact: true }),
    ).toBeVisible();
    evidence.return_seconds = (Date.now() - returnedAt) / 1000;
    evidence.returned_board = await board(page);
    expect(evidence.returned_board).toEqual(evidence.original_board);
    const saved = await page.evaluate(
      (id) => JSON.parse(localStorage.getItem(`lecture:${id}`) || "null"),
      originalPlan.lesson_id,
    );
    evidence.returned_snapshot = saved;
    expect(saved.step).toBe(evidence.original_snapshot.step);
    expect(saved.progress).toBeCloseTo(evidence.original_snapshot.progress, 2);
    await page.getByRole("button", { name: "현재 단계 음성 준비" }).click();
    await expect(page.locator("audio")).toHaveCount(1);
    await expect
      .poll(() =>
        page.locator("audio").evaluate((a: HTMLAudioElement) => a.currentTime),
      )
      .toBeCloseTo(evidence.original_snapshot.audio_position, 1);
    expect(
      await page.locator("audio").evaluate((a: HTMLAudioElement) => a.paused),
    ).toBe(true);
    await page.screenshot({
      path: `${out}/04-original-restored.png`,
      fullPage: true,
    });
    for (const width of [1280, 390]) {
      await page.setViewportSize({ width, height: 900 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth + 1,
        ),
      ).toBe(true);
      await page.screenshot({
        path: `${out}/05-restored-${width}.png`,
        fullPage: true,
      });
    }
    expect(evidence.page_errors).toEqual([]);
    evidence.status = "passed";
    evidence.finished_at = new Date().toISOString();
    save();
  } catch (error) {
    evidence.status = "failed";
    evidence.error = String(error);
    evidence.finished_at = new Date().toISOString();
    save();
    throw error;
  } finally {
    await api.dispose();
  }
});
