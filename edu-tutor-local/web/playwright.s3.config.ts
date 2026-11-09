import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  testMatch: "actual-training.spec.ts",
  timeout: 300000,
  workers: 1,
  outputDir: "test-results-s3",
  reporter: [
    ["list"],
    ["json", { outputFile: "test-results-s3/actual-training-report.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:8000",
    channel: "chrome",
    headless: true,
    trace: "off",
    screenshot: "only-on-failure",
  },
});
