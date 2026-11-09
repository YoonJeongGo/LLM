import { test, expect } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
test("actual training capability: ready runtime remains disabled by iteration policy", async ({ page }) => {
  const out = "test-results-phase2-training-policy";
  mkdirSync(out, { recursive: true });
  const forbidden: string[] = [], errors: string[] = [], requests: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/api/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    requests.push(`${request.method()} ${path}`);
    if (request.method() !== "GET") { forbidden.push(`${request.method()} ${path}`); await route.abort(); }
    else await route.continue();
  });
  await page.addInitScript(() => { localStorage.clear(); localStorage.setItem("edu-tab", "training"); });
  await page.setViewportSize({ width: 1440, height: 1050 });
  const capabilityResponse = page.waitForResponse(response => new URL(response.url()).pathname === "/api/capabilities");
  await page.goto("/");
  await page.getByRole("button", { name: "서버 연결 필요" }).click();
  await page.getByLabel("로컬 토큰 파일", { exact: true }).setInputFiles(resolve("../.local/auth-token"));
  await expect(page.getByRole("button", { name: "로컬 연결됨" })).toBeVisible({ timeout: 60000 });
  const capabilities = await (await capabilityResponse).json();
  expect(capabilities.training.runtime_ready).toBe(true);
  expect(capabilities.training.available).toBe(false);
  expect(capabilities.training.policy_blocked).toBe(true);
  expect(capabilities.training.reason).toBeTruthy();
  await page.getByRole("navigation").getByRole("button", { name: "학습·평가", exact: true }).click();
  const checks: any[] = [];
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1050 });
    const start = page.getByRole("button", { name: "예산 확인 후 학습", exact: true });
    await expect(start).toBeDisabled();
    await expect(page.getByText(capabilities.training.reason, { exact: true })).toBeVisible();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.screenshot({ path: `${out}/training-policy-${width}.png`, fullPage: true });
    await start.locator("xpath=ancestor::section[1]").screenshot({ path: `${out}/training-policy-card-${width}.png` });
    checks.push({ width, start_disabled: true, actual_policy_reason_visible: true, no_page_horizontal_overflow: true });
  }
  expect(forbidden).toEqual([]); expect(errors).toEqual([]);
  writeFileSync(`${out}/evidence.json`, JSON.stringify({ scope: "GET-only live capability and existing training UI check; no validation/training/model/doctor-refresh requests submitted", training: capabilities.training, checks, requests, forbidden, errors, new_model_requests: 0, new_training_requests: 0 }, null, 2));
});
