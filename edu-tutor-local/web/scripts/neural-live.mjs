// Read-only actual GPU browser witness. It never submits a model request.
import { chromium } from '@playwright/test';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const expectedEpoch = Number(process.argv[2] || 5);
const requireSamples = process.argv[3] !== 'light';
const output = resolve(`../runs/neural/current/${requireSamples ? 'browser' : 'browser-adapter'}`);
mkdirSync(output, { recursive: true });
const token = readFileSync(resolve('../.local/auth-token'), 'utf8').trim();
const base = 'http://127.0.0.1:8000';
const evidence = { source: 'actual_local_gpu_browser', expectedEpoch, errors: [], requests: [], samples: [], screenshots: [] };
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
const page = await context.newPage();
page.on('pageerror', e => evidence.errors.push(e.message));
page.on('request', request => {
  const url = new URL(request.url());
  if (url.pathname.startsWith('/api/')) evidence.requests.push({ method: request.method(), path: url.pathname });
});
try {
  let target;
  for (let attempt = 0; attempt < 600; attempt++) {
    const response = await fetch(base + '/api/neural/state', { headers: { Authorization: 'Bearer ' + token } });
    const state = await response.json();
    if (state.active_run?.generation_epoch === expectedEpoch) { target = state.active_run; break; }
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  if (!target) throw new Error('No matching already-running inference found; browser sent no model request');
  evidence.run_id = target.run_id;
  evidence.job_id = target.job_id;
  await page.goto(base + '/#neural');
  await page.getByRole('button', { name: '서버 연결 필요' }).click();
  await page.getByLabel('로컬 토큰 파일', { exact: true }).setInputFiles(resolve('../.local/auth-token'));
  await page.getByRole('button', { name: '로컬 연결됨' }).waitFor();
  await page.getByRole('navigation').getByRole('button', { name: '신경망 보기', exact: true }).click();
  await page.getByTestId('neural-mode').filter({ hasText: /^LIVE$/ }).waitFor({ timeout: 90000 });
  let captured = false;
  for (let index = 0; index < 600; index++) {
    const mode = await page.getByTestId('neural-mode').innerText();
    const count = await page.getByTestId('neural-event-count').innerText();
    const record = { at: new Date().toISOString(), mode, count,
      output: await page.getByTestId('neural-output').innerText(),
      sampleValues: await page.locator('.neural-samples strong').allTextContents() };
    evidence.samples.push(record);
    if (!captured && mode === 'LIVE' && (requireSamples ? record.sampleValues.length > 0 : record.output && !record.output.startsWith('아직 표시할'))) {
      await page.screenshot({ path: `${output}/actual-live-1440.png`, fullPage: true });
      evidence.screenshots.push('actual-live-1440.png');
      captured = true;
      console.log(JSON.stringify({ run_id: target.run_id, live: true, samples: record.sampleValues.length }));
    }
    if (mode !== 'LIVE' && evidence.samples.some(row => row.mode === 'LIVE')) {
      const response = await fetch(base + '/api/neural/runs/' + target.run_id, { headers: { Authorization: 'Bearer ' + token } });
      const run = await response.json();
      if (['succeeded', 'failed', 'cancelled', 'interrupted', 'blocked'].includes(run.state)) { evidence.finalRun = run; break; }
    }
    await page.waitForTimeout(150);
  }
  await page.getByTestId('neural-mode').filter({ hasText: /STATIC|UNAVAILABLE/ }).waitFor({ timeout: 10000 });
  evidence.finalMode = await page.getByTestId('neural-mode').innerText();
  evidence.layerDetail = await page.getByTestId('neural-layer-detail').innerText();
  evidence.actualGraphButtons = await page.locator('.neural-node button').count();
  evidence.actualGraphNodes = await page.locator('button.neural-node').count();
  await page.screenshot({ path: `${output}/actual-static-1440.png`, fullPage: true });
  evidence.screenshots.push('actual-static-1440.png');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => { document.documentElement.style.fontSize = '28px'; });
  evidence.narrowLargeTextOverflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
  await page.screenshot({ path: `${output}/actual-static-390-text200.png`, fullPage: true });
  evidence.screenshots.push('actual-static-390-text200.png');
  await page.getByRole('tab', { name: '학습 지표', exact: true }).click();
  evidence.trainingText = await page.locator('.neural-page').innerText();
  await page.screenshot({ path: `${output}/actual-training-history-390.png`, fullPage: true });
  evidence.screenshots.push('actual-training-history-390.png');
  if (!captured) throw new Error('No actual values/output were captured while LIVE');
  if (!requireSamples && evidence.samples.some(row => row.output.includes('\uFFFD'))) throw new Error('Incomplete token decoding leaked into the streamed output');
  if (evidence.narrowLargeTextOverflow) throw new Error('Narrow large-text page overflow');
  if (evidence.errors.length) throw new Error('Browser runtime errors');
  const counts = new Set(evidence.samples.filter(x => x.mode === 'LIVE').map(x => x.count));
  if (counts.size < 2) throw new Error('LIVE counter did not measurably update');
  if (evidence.requests.some(x => x.method !== 'GET')) throw new Error('Read-only witness made a mutation');
  evidence.status = 'passed';
} catch (error) {
  evidence.status = 'failed';
  evidence.failure = error.message;
  await page.screenshot({ path: `${output}/capture-failure.png`, fullPage: true }).catch(() => undefined);
  process.exitCode = 1;
} finally {
  await browser.close();
  writeFileSync(`${output}/evidence.json`, JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify({ status: evidence.status, failure: evidence.failure, run_id: evidence.run_id, screenshots: evidence.screenshots }));
}
