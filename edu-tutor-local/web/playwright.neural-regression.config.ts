import { defineConfig } from "@playwright/test";
process.env.EDU_UI_ARTIFACT_DIR = "test-results-neural-regression/artifacts";
export default defineConfig({
  testDir: "./tests",
  testMatch: [
    "neural-fixture.spec.ts",
    "ui-fixture.spec.ts",
    "phase2-fixture.spec.ts",
  ],
  timeout: 45000,
  fullyParallel: false,
  workers: 1,
  outputDir: "test-results-neural-regression/runs",
  reporter: [
    ["list"],
    ["json", { outputFile: "test-results-neural-regression/report.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:5184",
    channel: "chrome",
    headless: true,
    trace: "off",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "npm run dev -- --port 5184 --strictPort",
    url: "http://127.0.0.1:5184",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
