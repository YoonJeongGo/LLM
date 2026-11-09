import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  testMatch: "actual-model.spec.ts",
  timeout: 60000,
  workers: 1,
  outputDir: "test-results-t3",
  reporter: [
    ["list"],
    ["json", { outputFile: "test-results-t3/actual-report.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:8000",
    channel: "chrome",
    headless: true,
    trace: "off",
    screenshot: "only-on-failure",
  },
});
