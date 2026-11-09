import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  testMatch: "phase2-content.spec.ts",
  timeout: 90000,
  workers: 1,
  outputDir: "test-results-phase2-content",
  reporter: [
    ["list"],
    ["json", { outputFile: "test-results-phase2-content/report.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:8000",
    channel: "chrome",
    headless: true,
    trace: "off",
    screenshot: "only-on-failure",
  },
});
