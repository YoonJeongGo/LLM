import { defineConfig } from "@playwright/test";
const output =
  process.env.EDU_STUDENT_UI_OUTPUT ||
  "../runs/student-experience/20261027/frontend-fixture";
process.env.EDU_UI_ARTIFACT_DIR = `${output}/artifacts`;
export default defineConfig({
  testDir: "./tests",
  testMatch: [
    "student-fixture.spec.ts",
    "phase2-fixture.spec.ts",
    "ui-fixture.spec.ts",
  ],
  timeout: 45000,
  fullyParallel: false,
  workers: 1,
  outputDir: `${output}/runs`,
  reporter: [["list"], ["json", { outputFile: `${output}/report.json` }]],
  use: {
    baseURL: "http://127.0.0.1:5186",
    channel: "chrome",
    headless: true,
    trace: "off",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "npm run dev -- --port 5186 --strictPort",
    url: "http://127.0.0.1:5186",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
