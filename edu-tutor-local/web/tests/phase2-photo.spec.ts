import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
const out = "test-results-phase2-photo";
const source = JSON.parse(
  readFileSync(resolve("../runs/phase2/current/live/T05-edit.json"), "utf8"),
);
async function nav(page: Page, name: string) {
  const menu = page.getByRole("button", { name: "메뉴 열기" });
  if (await menu.isVisible()) await menu.click();
  await page
    .getByRole("navigation")
    .getByRole("button", { name, exact: true })
    .click();
  if (await menu.isVisible())
    await expect
      .poll(() =>
        page
          .locator(".sidebar")
          .evaluate((e) => e.getBoundingClientRect().right),
      )
      .toBeLessThanOrEqual(0);
}
async function connect(page: Page, record: any) {
  const errors: string[] = [],
    forbidden: string[] = [];
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
    { session: record.session_id, lesson: record.lesson.id },
  );
  await page.setViewportSize({ width: 1440, height: 1050 });
  const response = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === `/api/lessons/${record.lesson.id}` &&
      r.request().method() === "GET",
  );
  await page.goto("/");
  await page.getByRole("button", { name: "서버 연결 필요" }).click();
  await page
    .getByLabel("로컬 토큰 파일", { exact: true })
    .setInputFiles(resolve("../.local/auth-token"));
  await expect(page.getByRole("button", { name: "로컬 연결됨" })).toBeVisible({
    timeout: 60000,
  });
  await nav(page, "강의실");
  return { errors, forbidden, lesson: await (await response).json() };
}
async function size(page: Page, width: number, scale: number) {
  await page.setViewportSize({ width, height: 1050 });
  if (scale > 1) {
    await nav(page, "설정");
    await page.getByLabel("화면 글자 크기").selectOption(String(scale));
    await nav(page, "강의실");
  }
}
async function shot(page: Page, name: string) {
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    )
    .toBe(true);
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: true });
}
function save(name: string, value: any) {
  expect(value.errors).toEqual([]);
  expect(value.forbidden).toEqual([]);
  writeFileSync(
    `${out}/${name}.json`,
    JSON.stringify(
      {
        ...value,
        new_model_requests: 0,
        new_TTS_requests: 0,
        human_review: "not_reviewed",
      },
      null,
      2,
    ),
  );
}

test("T05 saved invalidated revision 3: old board and audio stay unavailable", async ({
  page,
}) => {
  mkdirSync(out, { recursive: true });
  const old = source.revisions[0],
    actual = await connect(page, old);
  expect(actual.lesson.valid).toBe(false);
  expect(actual.lesson.current_problem_revision).toBe(4);
  expect(actual.lesson.audio_steps).toEqual([]);
  for (const [width, scale] of [
    [1440, 1],
    [390, 1],
    [390, 2],
  ]) {
    await size(page, width, scale);
    await expect(
      page.getByText(actual.lesson.invalidated_reason, { exact: false }),
    ).toBeVisible();
    expect(await page.locator(".chalk-board").count()).toBe(0);
    expect(await page.locator("audio").count()).toBe(0);
    expect(
      await page
        .getByRole("button", { name: "현재 단계 음성 준비", exact: true })
        .count(),
    ).toBe(0);
    await expect(
      page.getByRole("button", {
        name: "이 답변으로 판서 강의 생성",
        exact: true,
      }),
    ).toBeDisabled();
    await shot(page, `T05-old-${width}-text${scale * 100}`);
  }
  await nav(page, "대화");
  await expect(
    page.getByText("원문 수정으로 무효화된 답변", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "강의 보기", exact: true }),
  ).toBeDisabled();
  save("T05-old-evidence", {
    scope:
      "GET-only invalidated photo lesson UI; stale generation/audio absent and invalidated assistant message disabled",
    lesson_id: old.lesson.id,
    invalidated_reason: actual.lesson.invalidated_reason,
    current_problem_revision: actual.lesson.current_problem_revision,
    widths: [1440, 390],
    text200: true,
    errors: actual.errors,
    forbidden: actual.forbidden,
  });
});

test("T05 saved revision 4: edited 20/NULL/100 average60, cached voice and persisted photo editor", async ({
  page,
}) => {
  mkdirSync(out, { recursive: true });
  const current = source.revisions[1],
    actual = await connect(page, current),
    lesson = actual.lesson;
  expect(lesson.valid).toBe(true);
  expect(lesson.original_problem.revision).toBe(4);
  expect(lesson.evidence.result.rows).toEqual([[60]]);
  const aggregate = lesson.evidence.logical_steps.aggregates[0];
  expect(aggregate).toMatchObject({
    included_values: [20, 100],
    count: 2,
    sum: 120,
    result: 60,
  });
  await page
    .getByRole("button", { name: "현재 단계 음성 준비", exact: true })
    .click();
  await page.getByRole("button", { name: "음성 재생", exact: true }).click();
  await expect
    .poll(() =>
      page.locator("audio").evaluate((e: HTMLAudioElement) => e.currentTime),
    )
    .toBeGreaterThan(0.1);
  await page.getByRole("button", { name: "일시정지", exact: true }).click();
  const audio = await page.locator("audio").evaluate((e: HTMLAudioElement) => ({
    duration: e.duration,
    position: e.currentTime,
    paused: e.paused,
    url: new URL(e.src).pathname,
  }));
  expect(audio.duration).toBeCloseTo(8.32, 2);
  const checks: any[] = [];
  for (const [width, scale] of [
    [1440, 1],
    [390, 1],
    [390, 2],
  ]) {
    await size(page, width, scale);
    await page.locator(".lesson-outline .step-link").first().click();
    const rows = await page
      .locator(".chalk-board tbody tr")
      .evaluateAll((elements) =>
        elements.map((row) =>
          Array.from(row.querySelectorAll("td"), (cell) =>
            cell.textContent?.trim(),
          ),
        ),
      );
    expect(rows).toEqual([
      ["박강열", "20"],
      ["유성재", "NULL"],
      ["김현수", "100"],
      ["60"],
    ]);
    const highlighted = await page
      .locator(".chalk-board td.highlight-cell")
      .allTextContents();
    expect(highlighted).toEqual(["20", "100"]);
    await expect(page.locator(".caption-box p")).toContainText(
      "120을 값 2개로 나누면 평균 60.0",
    );
    await shot(page, `T05-current-${width}-text${scale * 100}`);
    checks.push({ width, scale, rows, highlighted });
  }
  await nav(page, "대화");
  await page.locator(".message-evidence summary").click();
  const renderedEvidence = JSON.parse(
    await page.locator(".message-evidence pre").innerText(),
  );
  expect(renderedEvidence.logical_steps.aggregates[0]).toMatchObject({
    included_values: [20, 100],
    count: 2,
    sum: 120,
    result: 60,
  });
  const photoResponse = page.waitForResponse(
    (r) =>
      new URL(r.url()).pathname === `/api/photos/${source.photo_id}` &&
      r.request().method() === "GET",
  );
  await page
    .getByRole("button", { name: "사진 원문 수정", exact: true })
    .click();
  const photo = await (await photoResponse).json();
  expect(photo.revision).toBe(4);
  expect(photo.confirmed).toBe(true);
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("revision 4", { exact: true })).toBeVisible();
  await expect(dialog.getByText("원문 확정", { exact: true })).toBeVisible();
  await expect(dialog.getByLabel("SQL / 코드")).toHaveValue(
    "SELECT AVG(score) AS average_score FROM exam_result;",
  );
  await expect(dialog.getByLabel("SQL / 코드")).toBeEditable();
  await dialog
    .getByText("표 · 읽지 못한 부분 · 누락 조건 편집", { exact: true })
    .click();
  const input = dialog.getByLabel("사진 표 JSON");
  await expect(input).toBeEditable();
  const tables = JSON.parse(await input.inputValue());
  expect(tables[0].rows).toEqual([
    ["박강열", 20],
    ["유성재", null],
    ["김현수", 100],
  ]);
  await expect(
    dialog.getByRole("button", { name: "교정 저장", exact: true }),
  ).toBeDisabled();
  await expect(
    dialog.getByRole("button", { name: "이 원문으로 확정", exact: true }),
  ).toBeDisabled();
  await expect(
    dialog.getByRole("button", { name: "확정한 문제 풀이", exact: true }),
  ).toBeEnabled();
  await input.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `${out}/T05-photo-editor-fields.png`,
    fullPage: true,
  });
  await dialog.locator(".photo-status").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `${out}/T05-photo-editor-revision4.png`,
    fullPage: true,
  });
  await dialog.getByRole("button", { name: "닫기", exact: true }).click();
  save("T05-current-evidence", {
    scope:
      "GET-only saved manual-edit revision4 board/audio/evidence and editable persisted source; no new correction, confirmation or solve was submitted",
    lesson_id: lesson.id,
    photo_id: photo.id,
    photo_revision: photo.revision,
    photo_confirmed: photo.confirmed,
    tables,
    audio,
    checks,
    aggregate,
    persisted_editor_read_only_check: true,
    errors: actual.errors,
    forbidden: actual.forbidden,
  });
});
