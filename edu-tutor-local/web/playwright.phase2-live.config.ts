import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  testMatch: "phase2-live.spec.ts",
  timeout: 1000000,
  workers: 1,
  outputDir: "test-results-phase2-live",
  reporter: [
    ["list"],
    ["json", { outputFile: "test-results-phase2-live/report.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:8000",
    channel: "chrome",
    headless: true,
    trace: "off",
    screenshot: "only-on-failure",
  },
});
