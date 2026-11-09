import { test, expect, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
const out = process.env.EDU_FINISH_TABLE_OUTPUT || "../runs/finish-v2/20261029/table-editor-fixture";
mkdirSync(out, { recursive: true });

async function fixture(page: Page) {
  const submitted: any[] = [];
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname.replace("/api", "");
    let value: any = {};
    if (path === "/capabilities") value = { text: { available: true }, speech: { available: false }, vision: { available: false }, training: { available: false } };
    else if (path === "/models") value = { ready: false, model_id: "CPU_UI_fixture_no_model", modules: [] };
    else if (path === "/sessions" && route.request().method() === "POST") value = { id: "fixture-session", generation_epoch: 0 };
    else if (path === "/sessions/fixture-session/messages" && route.request().method() === "POST") {
      submitted.push(route.request().postDataJSON()); value = { job_id: "fixture-job" };
    } else if (path === "/jobs/fixture-job") value = { id: "fixture-job", state: "succeeded", kind: "chat", result: {} };
    else if (["/sessions", "/jobs", "/documents", "/photos", "/sessions/fixture-session/messages"].includes(path)) value = [];
    else if (route.request().method() !== "GET") throw Error("Unexpected fixture mutation: " + path);
    await route.fulfill({ json: value });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "서버 연결 필요", exact: true }).click();
  await page.getByLabel("관리 토큰", { exact: true }).fill("CPU_UI_FIXTURE_NOT_REAL_TOKEN");
  await page.getByRole("button", { name: "연결", exact: true }).click();
  await expect(page.getByRole("button", { name: "로컬 연결됨", exact: true })).toBeVisible();
  await nav(page, "대화");
  return submitted;
}
async function nav(page: Page, name: string) {
  const mobile = page.getByRole("button", { name: "메뉴 열기" });
  if (await mobile.isVisible()) await mobile.click();
  await page.getByRole("navigation").getByRole("button", { name, exact: true }).click();
}
async function openEditor(page: Page) {
  await page.locator(".problem-editor > summary").click();
  await page.getByLabel("이 질문에 원본 표·SQL을 함께 보냅니다").check();
}
async function draft(page: Page) { return page.evaluate(() => JSON.parse(localStorage.getItem("edu-problem-draft") || "null")); }
async function captureGrid(page: Page, name: string) {
  await expect(page.getByRole("button", { name: "메뉴 닫기", exact: true })).toHaveCount(0);
  await expect.poll(() => page.locator(".sidebar").evaluate(e => e.getBoundingClientRect().right)).toBeLessThanOrEqual(1);
  await page.locator(".problem-editor").evaluate(editor => {
    const grid = editor.querySelector(".source-grid-scroll")!;
    editor.scrollTop += grid.getBoundingClientRect().top - editor.getBoundingClientRect().top - 12;
    grid.scrollLeft = 0;
  });
  await page.locator(".problem-editor").screenshot({ path: `${out}/${name}.png` });
}

test("CPU UI fixture: grid keeps values, confirmation, revision and a 390px scrolling draft", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const requests = await fixture(page);
  await openEditor(page);
  expect(JSON.parse((await draft(page)).tables)).toEqual([]);
  await page.getByRole("button", { name: "표 추가", exact: true }).click();
  await page.getByLabel("표 1 이름", { exact: true }).fill("ledger");
  for (const [i, name, type] of [[1, "label", "TEXT"], [2, "units", "REAL"]] as const) {
    await page.getByRole("button", { name: "표 1 열 추가", exact: true }).click();
    await page.getByLabel(`표 1 열 ${i} 이름`, { exact: true }).fill(name);
    await page.getByLabel(`표 1 열 ${i} 자료형`, { exact: true }).selectOption(type);
  }
  for (let i = 0; i < 3; i++) await page.getByRole("button", { name: "표 1 행 추가", exact: true }).click();
  const confirm = page.getByLabel("원문과 비교해 표·값·SQL을 확인했습니다");
  await expect(confirm).toBeDisabled();
  await page.getByLabel("표 1 1행 2열 값", { exact: true }).fill("0");
  await page.getByLabel("표 1 1행 2열 값", { exact: true }).blur();
  await page.getByLabel("표 1 2행 1열 값", { exact: true }).fill("NULL");
  await page.getByLabel("표 1 2행 2열 값", { exact: true }).fill("-2.5");
  await page.getByLabel("표 1 2행 2열 값", { exact: true }).blur();
  for (const col of [1, 2]) await page.getByLabel(`표 1 3행 ${col}열 상태`, { exact: true }).selectOption("null");
  await page.getByLabel("문제의 원본 SQL", { exact: true }).fill("SELECT COUNT(units) FROM ledger;");
  await expect(confirm).toBeEnabled(); await confirm.check();
  const preserved = await draft(page);
  expect(JSON.parse(preserved.tables)[0].rows).toEqual([["", 0], ["NULL", -2.5], [null, null]]);
  expect(await page.locator(".source-grid-scroll").evaluate(e => e.scrollWidth > e.clientWidth)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(true);
  await captureGrid(page, "grid-390");
  await nav(page, "설정");
  await page.getByLabel("화면 글자 크기", { exact: true }).selectOption("2");
  await nav(page, "대화");
  await page.locator(".problem-editor > summary").click();
  await captureGrid(page, "grid-390-text200");
  expect(await draft(page)).toEqual(preserved);
  await page.reload();
  await nav(page, "대화");
  await page.locator(".problem-editor > summary").click();
  expect(await draft(page)).toEqual(preserved);
  await page.getByLabel("표 1 2행 2열 값", { exact: true }).fill("-3.25");
  await page.getByLabel("표 1 2행 2열 값", { exact: true }).blur();
  const changed = await draft(page);
  expect(changed.confirmed).toBe(false); expect(changed.revision).toBeGreaterThan(preserved.revision);
  // Reconnect without touching the preserved local table draft.
  await page.getByRole("button", { name: "서버 연결 필요", exact: true }).click();
  await page.getByLabel("관리 토큰", { exact: true }).fill("CPU_UI_FIXTURE_NOT_REAL_TOKEN");
  await page.getByRole("button", { name: "연결", exact: true }).click(); await nav(page, "대화");
  await page.locator(".problem-editor > summary").click();
  await confirm.check();
  await page.getByLabel("질문 입력", { exact: true }).fill("직접 입력한 검증용 표의 결과는?");
  await page.getByRole("button", { name: "질문 전송", exact: true }).click();
  await expect.poll(() => requests.length).toBe(1);
  expect(requests[0].problem.tables[0].rows).toEqual([["", 0], ["NULL", -3.25], [null, null]]);
  expect(requests[0].problem.revision).toBe(changed.revision);
});

test("CPU UI fixture: malformed expert JSON is preserved and cannot be confirmed", async ({ page }) => {
  await fixture(page); await openEditor(page);
  await page.locator(".source-json-editor summary").click();
  await page.getByLabel("문제의 원본 표 JSON", { exact: true }).fill('[{"name":"unfinished"');
  await expect(page.getByLabel("원문과 비교해 표·값·SQL을 확인했습니다")).toBeDisabled();
  expect((await draft(page)).tables).toBe('[{"name":"unfinished"');
  await page.reload(); await nav(page, "대화");
  await page.locator(".problem-editor > summary").click();
  await page.locator(".source-json-editor summary").click();
  await expect(page.getByLabel("문제의 원본 표 JSON", { exact: true })).toHaveValue('[{"name":"unfinished"');
  const fixed = [{ name: "changed", columns: [{ name: "x", type: "TEXT", label: "보존 이름" }], rows: [[""]] }];
  await page.getByLabel("문제의 원본 표 JSON", { exact: true }).fill(JSON.stringify(fixed));
  await expect(page.getByLabel("표 1 이름", { exact: true })).toHaveValue("changed");
  await page.getByRole("button", { name: "표 1 행 추가", exact: true }).click();
  expect(JSON.parse((await draft(page)).tables)[0].columns[0].label).toBe("보존 이름");
});
