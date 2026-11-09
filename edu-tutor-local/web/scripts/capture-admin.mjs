import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
const output = "test-results-admin";
mkdirSync(output, { recursive: true });
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const evidence = { source: "actual_read_only_admin", errors: [], blocked: [] };
let models;
page.on("pageerror", (error) => evidence.errors.push(error.message));
await page.route("**/api/**", async (route) => {
  if (route.request().method() !== "GET") {
    evidence.blocked.push(new URL(route.request().url()).pathname);
    await route.abort();
    return;
  }
  await route.continue();
});
page.on("response", async (response) => {
  if (response.url().endsWith("/api/models")) models = await response.json();
});
try {
  await page.goto("http://127.0.0.1:8000");
  await page.getByRole("button", { name: "서버 연결 필요" }).click();
  await page
    .getByLabel("로컬 토큰 파일", { exact: true })
    .setInputFiles(resolve("../.local/auth-token"));
  await page.getByRole("button", { name: "로컬 연결됨" }).waitFor();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "학습·평가", exact: true })
    .click();
  const comparison = page.locator(".evaluation-comparison");
  await comparison.locator(".comparison-answer").first().waitFor();
  evidence.comparison_question = await comparison
    .locator(".comparison-question")
    .innerText();
  evidence.comparison_answers = await comparison
    .locator(".evaluation-answer")
    .allTextContents();
  for (const detail of await comparison
    .locator(".comparison-answer details")
    .all())
    await detail.locator("summary").click();
  evidence.default_scores = await comparison
    .locator(".comparison-answer select")
    .evaluateAll((selects) => selects.map((select) => select.value));
  if (evidence.default_scores.some(Boolean))
    throw new Error("Actual rubric scores must never be prefilled");
  await comparison.screenshot({ path: `${output}/actual-comparison-1440.png` });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => {
    document.documentElement.style.fontSize = "28px";
  });
  evidence.narrow_large_text_overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > innerWidth + 1,
  );
  if (evidence.narrow_large_text_overflow) {
    evidence.overflow_elements = await page.evaluate(() =>
      Array.from(document.querySelectorAll("main *"))
        .map((element) => ({
          tag: element.tagName,
          class: element.className,
          width: element.getBoundingClientRect().width,
          right: element.getBoundingClientRect().right,
          text: element.textContent?.slice(0, 140),
        }))
        .filter((element) => element.right > innerWidth + 1)
        .slice(0, 30),
    );
    await page.screenshot({ path: `${output}/overflow.png`, fullPage: true });
    throw new Error("Comparison page horizontal overflow");
  }
  await comparison.screenshot({
    path: `${output}/actual-comparison-390-text200.png`,
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.evaluate(() => {
    document.documentElement.style.fontSize = "14px";
  });
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "모델 분석", exact: true })
    .click();
  const module = models.modules.find(
    (module) => module.name.includes("layers.0.") && module.tensors?.length,
  );
  if (!module) throw new Error("Actual tensor metadata unavailable");
  const layer = page
    .locator(".module-layer")
    .filter({
      has: page
        .locator(".module-children summary .mono")
        .filter({ hasText: module.name }),
    })
    .first();
  await layer.locator(":scope > summary").click();
  await layer.getByText(module.name, { exact: true }).click();
  evidence.tensor_module = module;
  evidence.current_selection = models.active_adapter;
  evidence.last_loaded_adapter = models.last_loaded_adapter;
  evidence.resident = models.resident;
  await page.screenshot({
    path: `${output}/actual-model-modules.png`,
    fullPage: true,
  });
  if (evidence.blocked.length || evidence.errors.length)
    throw new Error("Read-only admin page reported errors");
  evidence.status = "passed";
} catch (error) {
  evidence.status = "failed";
  evidence.error = String(error);
  throw error;
} finally {
  writeFileSync(`${output}/evidence.json`, JSON.stringify(evidence, null, 2));
  await browser.close();
}
