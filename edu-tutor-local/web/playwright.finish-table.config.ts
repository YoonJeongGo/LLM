import { defineConfig } from "@playwright/test";
const output = process.env.EDU_FINISH_TABLE_OUTPUT || "../runs/finish-v2/20261029/table-editor-fixture";
export default defineConfig({
  testDir: "./tests", testMatch: "finish-table-editor.spec.ts", timeout: 60000,
  fullyParallel: false, workers: 1,
  outputDir: `${output}/runs`,
  reporter: [["list"], ["json", { outputFile: `${output}/report.json` }]],
  use: { baseURL: "http://127.0.0.1:5197", channel: "chrome", headless: true, trace: "off", screenshot: "only-on-failure" },
  webServer: { command: "npm run dev -- --port 5197 --strictPort", url: "http://127.0.0.1:5197", reuseExistingServer: false, timeout: 30000 },
});
