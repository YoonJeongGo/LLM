import { test, expect } from "@playwright/test";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
test("T01 second actual example: bounded SQL failure visibly blocks board and audio", async ({
  page,
}) => {
  const out = "test-results-phase2-blocked";
  mkdirSync(out, { recursive: true });
  const artifact = JSON.parse(
    readFileSync(
      resolve(
        "../runs/phase2/current/live/T01-concept-2-example-repair-final.json",
      ),
      "utf8",
    ),
  );
  const forbidden: string[] = [],
    errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/api/**", async (route) => {
    if (route.request().method() !== "GET") {
      forbidden.push(
        `${route.request().method()} ${new URL(route.request().url()).pathname}`,
      );
      await route.abort();
    } else await route.continue();
  });
  await page.addInitScript(
    ({ session, lesson }) => {
      localStorage.clear();
      localStorage.setItem("edu-session", session);
      localStorage.setItem("edu-lesson", lesson);
      localStorage.setItem("edu-tab", "classroom");
    },
    { session: artifact.session_id, lesson: artifact.lesson.id },
  );
  const lessonResponse = page.waitForResponse(
    (r) => new URL(r.url()).pathname === `/api/lessons/${artifact.lesson.id}`,
  );
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await page.getByRole("button", { name: "서버 연결 필요" }).click();
  await page
    .getByLabel("로컬 토큰 파일", { exact: true })
    .setInputFiles(resolve("../.local/auth-token"));
  await expect(page.getByRole("button", { name: "로컬 연결됨" })).toBeVisible({
    timeout: 60000,
  });
  const lesson = await (await lessonResponse).json();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "강의실", exact: true })
    .click();
  expect(lesson.status).toBe("verification_stopped");
  expect(lesson.plan).toBeNull();
  expect(lesson.reason).toContain("duplicate column name: score");
  expect(lesson.speech_allowed).toBe(false);
  const checks: any[] = [];
  for (const [width, scale] of [
    [1440, 1],
    [390, 1],
    [390, 2],
  ]) {
    await page.setViewportSize({ width, height: 1000 });
    if (scale > 1) {
      const nav = async (name: string) => {
        await page.getByRole("button", { name: "메뉴 열기" }).click();
        await page
          .getByRole("navigation")
          .getByRole("button", { name, exact: true })
          .click();
        await expect
          .poll(() =>
            page
              .locator(".sidebar")
              .evaluate((e) => e.getBoundingClientRect().right),
          )
          .toBeLessThanOrEqual(0);
      };
      await nav("설정");
      await page.getByLabel("화면 글자 크기").selectOption("2");
      await nav("강의실");
    }
    await expect(
      page.getByRole("heading", { name: "검증 중단", exact: true }),
    ).toBeVisible();
    expect(await page.locator(".chalk-board").count()).toBe(0);
    expect(await page.locator("audio").count()).toBe(0);
    await expect(
      page.getByRole("heading", {
        name: "검증되지 않은 모델 원문",
        exact: true,
      }),
    ).toBeVisible();
    expect(
      await page
        .getByRole("button", { name: "현재 단계 음성 준비", exact: true })
        .count(),
    ).toBe(0);
    const reasonVisible = await page
      .getByText(lesson.reason, { exact: true })
      .isVisible();
    const generationDisabled = await page
      .getByRole("button", { name: "이 답변으로 판서 강의 생성", exact: true })
      .isDisabled();
    await page.screenshot({
      path: `${out}/T01-blocked-${width}${scale > 1 ? "-text200" : ""}.png`,
      fullPage: true,
    });
    checks.push({
      width,
      scale,
      reason_visible: reasonVisible,
      generation_disabled: generationDisabled,
      board_count: 0,
      audio_count: 0,
    });
  }
  writeFileSync(
    `${out}/evidence.json`,
    JSON.stringify(
      {
        scope:
          "GET-only actual failed second conceptual example; no substitute example or new generation",
        lesson_id: lesson.id,
        status: lesson.status,
        reason: lesson.reason,
        checks,
        forbidden,
        errors,
        new_model_requests: 0,
        new_TTS_requests: 0,
        human_review: "not_reviewed",
      },
      null,
      2,
    ),
  );
  expect(forbidden).toEqual([]);
  expect(errors).toEqual([]);
  expect(checks.every((check) => check.reason_visible)).toBe(true);
  expect(checks.every((check) => check.generation_disabled)).toBe(true);
});
