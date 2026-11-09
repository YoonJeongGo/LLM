import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  testMatch: "live-api.spec.ts",
  timeout: 45000,
  workers: 1,
  fullyParallel: false,
  outputDir: "test-results-live",
  reporter: [
    ["list"],
    ["json", { outputFile: "test-results-live/live-report.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:8000",
    channel: "chrome",
    headless: true,
    trace: "off",
    screenshot: "only-on-failure",
  },
});
