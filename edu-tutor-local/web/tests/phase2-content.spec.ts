import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const out = "test-results-phase2-content";
const load = (name: string) =>
  JSON.parse(
    readFileSync(resolve(`../runs/phase2/current/live/${name}.json`), "utf8"),
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

async function size(page: Page, width: number, scale: number) {
  await page.setViewportSize({ width, height: 1050 });
  if (scale > 1) {
    await nav(page, "설정");
    await page.getByLabel("화면 글자 크기").selectOption(String(scale));
    await nav(page, "강의실");
  }
}

async function connect(page: Page, artifact: any) {
  const forbidden: string[] = [],
    errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
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
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.goto("/");
  await page.getByRole("button", { name: "서버 연결 필요" }).click();
  await page
    .getByLabel("로컬 토큰 파일", { exact: true })
    .setInputFiles(resolve("../.local/auth-token"));
  await expect(page.getByRole("button", { name: "로컬 연결됨" })).toBeVisible({
    timeout: 60000,
  });
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "강의실", exact: true })
    .click();
  await expect(page.locator(".board-step-heading")).toBeVisible();
  return { forbidden, errors };
}

async function cachedAudio(page: Page, artifact: any) {
  expect(artifact.lesson.audio_steps.length).toBeGreaterThan(0);
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
  const result = await page
    .locator("audio")
    .evaluate((e: HTMLAudioElement) => ({
      duration: e.duration,
      position: e.currentTime,
      paused: e.paused,
      url: new URL(e.src).pathname,
    }));
  expect(result.duration).toBeCloseTo(
    artifact.lesson.audio_steps[0].duration,
    1,
  );
  return result;
}

async function tables(page: Page) {
  return page.locator("[data-board-element]").evaluateAll((elements) =>
    elements
      .filter((e) => e.querySelector("table"))
      .map((e) => ({
        id: (e as HTMLElement).dataset.boardElement,
        columns: Array.from(e.querySelectorAll("thead th"), (c) =>
          c.textContent?.trim(),
        ),
        rows: Array.from(e.querySelectorAll("tbody tr"), (row) =>
          Array.from(row.querySelectorAll("td"), (c) => c.textContent?.trim()),
        ),
      })),
  );
}
function display(rows: any[][]) {
  return rows.map((row) =>
    row.map((value) => (value === null ? "NULL" : String(value))),
  );
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
  writeFileSync(`${out}/${name}.json`, JSON.stringify(value, null, 2));
}

test("saved actual T04: all four computed GROUP BY stages and first cached voice", async ({
  page,
}) => {
  mkdirSync(out, { recursive: true });
  const artifact = load("T04-group"),
    lesson = artifact.lesson,
    plan = lesson.plan;
  expect(lesson.valid).toBe(true);
  expect(plan.steps).toHaveLength(4);
  expect(lesson.evidence.result.rows).toEqual([
    ["A", 2, 10, 10],
    ["C", 2, 80, 40],
  ]);
  const guards = await connect(page, artifact);
  const audio = await cachedAudio(page, artifact);
  const original = plan.steps[0].board_actions.find(
    (a: any) => a.type === "table",
  );
  const findTable = (suffix: string) =>
    plan.steps
      .flatMap((s: any) => s.board_actions)
      .find((a: any) => a.type === "table" && a.element_id.endsWith(suffix));
  const where = findTable("-where"),
    groups = findTable("-groups"),
    aggregate = findTable("-aggregate"),
    result = findTable("-result");
  const originals = [
    ["A", 10, 1],
    ["A", null, 1],
    ["A", 30, 0],
    ["B", 40, 1],
    ["C", 20, 1],
    ["C", 60, 1],
  ];
  const expected = {
    [original.element_id]: {
      columns: ["dept", "score", "active"],
      rows: display(originals),
    },
    [where.element_id]: {
      columns: ["dept", "score", "active"],
      rows: display(originals.filter((row) => row[2] === 1)),
    },
    [groups.element_id]: {
      columns: ["dept", "포함 행"],
      rows: display([
        ["A", "1, 2"],
        ["B", "4"],
        ["C", "5, 6"],
      ]),
    },
    [aggregate.element_id]: {
      columns: ["dept", "people", "total", "average"],
      rows: display([
        ["A", 2, 10, 10],
        ["B", 1, 40, 40],
        ["C", 2, 80, 40],
      ]),
    },
    [result.element_id]: {
      columns: ["dept", "people", "total", "average"],
      rows: display([
        ["A", 2, 10, 10],
        ["C", 2, 80, 40],
      ]),
    },
  };
  const stageIds = [
    [original.element_id],
    [original.element_id, where.element_id, groups.element_id],
    [original.element_id, groups.element_id, aggregate.element_id],
    [original.element_id, aggregate.element_id, result.element_id],
  ];
  const checks: any[] = [];
  for (const [width, scale] of [
    [1440, 1],
    [390, 1],
    [390, 2],
  ]) {
    await size(page, width, scale);
    for (let step = 0; step < 4; step++) {
      await page.locator(".lesson-outline .step-link").nth(step).click();
      await expect(page.locator(".board-step-heading")).toContainText(
        plan.steps[step].title,
      );
      const actual = await tables(page);
      expect(actual.map((t) => t.id)).toEqual(stageIds[step]);
      for (const table of actual)
        expect({ columns: table.columns, rows: table.rows }).toEqual(
          expected[table.id!],
        );
      const rowIds = await page
        .locator(`[data-board-element="${original.element_id}"] [data-row-id]`)
        .evaluateAll((rows) =>
          rows.map((r) => (r as HTMLElement).dataset.rowId),
        );
      expect(rowIds).toEqual(original.row_ids);
      const highlightedRows = await page
        .locator(
          `[data-board-element="${original.element_id}"] tr.highlight-row`,
        )
        .count();
      expect(highlightedRows).toBe(5);
      const name = `T04-${width}${scale > 1 ? "-text200" : ""}-step${step + 1}`;
      await page.locator(".table-scroll").evaluateAll((elements) =>
        elements.forEach((element) => {
          element.scrollLeft = 0;
        }),
      );
      await shot(page, name);
      const horizontalScroll = await page
        .locator(".table-scroll")
        .evaluateAll((elements) =>
          elements.map((element) => {
            const scrollable = element.scrollWidth > element.clientWidth + 1;
            if (scrollable) element.scrollLeft = element.scrollWidth;
            return {
              scrollable,
              reached_right:
                !scrollable ||
                element.scrollLeft + element.clientWidth >=
                  element.scrollWidth - 1,
            };
          }),
        );
      expect(horizontalScroll.every((item) => item.reached_right)).toBe(true);
      if (horizontalScroll.some((item) => item.scrollable))
        await shot(page, `${name}-rightmost`);
      checks.push({
        width,
        scale,
        step: step + 1,
        tables: actual,
        stable_original_row_ids: rowIds,
        highlighted_rows: highlightedRows,
        horizontalScroll,
      });
    }
    await page.locator(".lesson-outline .step-link").first().click();
    expect((await tables(page))[0].rows).toEqual(display(originals));
  }
  expect(guards.forbidden).toEqual([]);
  expect(guards.errors).toEqual([]);
  save("T04-evidence", {
    scope:
      "GET-only rendering of actual T04 computed plan and cached first voice; no new generation",
    lesson_id: lesson.id,
    audio,
    checks,
    manual_return_to_step1: true,
    ...guards,
    new_model_requests: 0,
    new_TTS_requests: 0,
    human_review: "not_reviewed",
  });
});

test("saved actual T01 repair: model-authored CREATE example before/after evidence and cached voice", async ({
  page,
}) => {
  mkdirSync(out, { recursive: true });
  const artifact = load("T01-concept-1-repair1"),
    lesson = artifact.lesson,
    evidence = lesson.example_evidence;
  expect(lesson.status).toBe("verified_example_plan");
  expect(evidence.source).toBe("model_authored_sql");
  expect(evidence.steps).toHaveLength(1);
  const executed = evidence.steps[0];
  expect(executed.operation).toBe("create_table");
  expect(executed.before).toEqual([]);
  expect(executed.after).toHaveLength(1);
  expect(executed.after[0].columns).toEqual(["name", "score"]);
  expect(executed.after[0].rows).toEqual([]);
  expect(executed.effects).toMatchObject({
    table_count_before: 0,
    table_count_after: 1,
    rows_before: 0,
    rows_after: 0,
    columns_after: 2,
  });
  const guards = await connect(page, artifact);
  const audio = await cachedAudio(page, artifact);
  const checks: any[] = [];
  for (const [width, scale] of [
    [1440, 1],
    [390, 1],
    [390, 2],
  ]) {
    await size(page, width, scale);
    await page.locator(".lesson-outline .step-link").first().click();
    await expect(page.locator(".chalk-board")).toContainText(
      "실행 전: 이 예시 표가 없습니다.",
    );
    await expect(page.locator(".chalk-board")).toContainText(
      "설명용 새 예시 · 실행 후",
    );
    const displayedSql = await page
      .locator(".chalk-board pre")
      .evaluate((element) => {
        const copy = element.cloneNode(true) as HTMLElement;
        copy
          .querySelectorAll(".line-number")
          .forEach((number) => number.remove());
        return copy.textContent?.trim();
      });
    expect(displayedSql).toBe(executed.sql);
    const sqlFontPx = await page
      .locator(".chalk-board pre")
      .evaluate((element) => parseFloat(getComputedStyle(element).fontSize));
    expect(sqlFontPx).toBeGreaterThanOrEqual(
      (width === 1440 ? 13 : 12) * scale,
    );
    const actual = await tables(page);
    expect(actual).toEqual([
      { id: executed.after[0].id, columns: ["name", "score"], rows: [] },
    ]);
    await shot(
      page,
      `T01-${width}${scale > 1 ? "-text200" : ""}-create-before-after`,
    );
    checks.push({
      width,
      scale,
      sql_font_px: sqlFontPx,
      tables: actual,
      before_table_count: 0,
      after_table_count: 1,
      source_sql: executed.sql,
    });
  }
  expect(guards.forbidden).toEqual([]);
  expect(guards.errors).toEqual([]);
  save("T01-evidence", {
    scope:
      "GET-only actual repaired model CREATE example. Only CREATE/no-table to empty two-column table is demonstrated; ALTER/DROP and row insertion are not demonstrated here.",
    lesson_id: lesson.id,
    audio,
    checks,
    ...guards,
    new_model_requests: 0,
    new_TTS_requests: 0,
    human_review: "not_reviewed",
  });
});
