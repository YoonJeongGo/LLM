import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  testMatch: "phase2-fixture.spec.ts",
  timeout: 45000,
  workers: 1,
  outputDir: "test-results-phase2-fixture",
  reporter: [
    ["list"],
    ["json", { outputFile: "test-results-phase2-fixture/report.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:5173",
    channel: "chrome",
    headless: true,
    trace: "off",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: true,
    timeout: 30000,
  },
});
