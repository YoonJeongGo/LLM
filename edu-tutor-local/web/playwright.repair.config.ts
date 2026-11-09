import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests', testMatch: 'student-fixture.spec.ts', workers: 1,
  timeout: 45000, fullyParallel: false,
  outputDir: process.env.REPAIR_WEB_OUTPUT || '../runs/v021-r3-repair/20261030/playback/browser-final-output',
  reporter: [['list'], ['json', {outputFile: process.env.REPAIR_WEB_REPORT || '../runs/v021-r3-repair/20261030/playback/browser-report.json'}]],
  use: {baseURL:'http://127.0.0.1:5175',channel:'chrome',headless:true,trace:'off',screenshot:'only-on-failure'},
  webServer:{command:'npm run dev -- --port 5175 --strictPort',url:'http://127.0.0.1:5175',reuseExistingServer:false,timeout:30000},
});
