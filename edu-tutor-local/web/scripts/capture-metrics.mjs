import { chromium } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const output = resolve("test-results-live");
mkdirSync(output, { recursive: true });
const browser = await chromium.launch({ channel: "chrome" });
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
  });
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
  await page.locator(".job-item").first().waitFor();
  await page.screenshot({
    path: resolve(output, "training-live.png"),
    fullPage: true,
  });
  await page
    .locator(".job-item")
    .filter({ has: page.locator(".metric-plot") })
    .first()
    .screenshot({ path: resolve(output, "training-chart.png") });
  const response = await page.request.get("http://127.0.0.1:8000/api/jobs", {
    headers: {
      Authorization: `Bearer ${readFileSync(resolve("../.local/auth-token"), "utf8").trim()}`,
    },
  });
  const jobs = await response.json();
  const evidence = {
    captured_at: new Date().toISOString(),
    browser: "Chrome",
    scope:
      "실제 API 작업 지표 읽기와 UI 표시만 검사. 새 GPU 작업을 시작하지 않음.",
    charts: await page.locator(".metric-plot figcaption").allTextContents(),
    training_jobs: jobs
      .filter((job) => job.kind === "training")
      .map((job) => ({
        id: job.id,
        state: job.state,
        metrics: job.metrics ?? [],
        latest_metrics: job.latest_metrics,
      })),
    educational_quality: "not_reviewed",
  };
  writeFileSync(
    resolve(output, "training-live-evidence.json"),
    JSON.stringify(evidence, null, 2),
  );
  console.log(
    JSON.stringify({
      charts: evidence.charts.length,
      training_jobs: evidence.training_jobs.length,
    }),
  );
} finally {
  await browser.close();
}
