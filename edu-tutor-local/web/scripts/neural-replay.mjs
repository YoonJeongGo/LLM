// Save one requested synthetic QA trace, then replay it through the real API/UI.
// No model inference or training is submitted.
import { chromium } from '@playwright/test';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
const base = 'http://127.0.0.1:8000';
const output = resolve('../runs/neural/current/replay-browser');
mkdirSync(output, { recursive: true });
const token = readFileSync(resolve('../.local/auth-token'), 'utf8').trim();
const trace = JSON.parse(readFileSync(resolve('../runs/neural/current/gpu/detail-a.json'), 'utf8'));
const evidence = { source: 'saved_actual_gpu_events_replay', run_id: trace.run_id, errors: [], modelRequests: [] };
const api = async (path, method = 'GET', body) => {
  const response = await fetch(base + '/api' + path, { method, headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}) });
  if (!response.ok) throw new Error(`Replay API ${response.status} ${path}`);
  return await response.json();
};
const records = (await api('/neural/records')).records;
const record = records.find(x => x.run_id === trace.run_id && x.include_sensitive) ??
  await api(`/neural/runs/${trace.run_id}/save`, 'POST', { include_sensitive: true });
evidence.record_id = record.id;
const redacted = records.find(x => x.run_id === trace.run_id && !x.include_sensitive) ??
  await api(`/neural/runs/${trace.run_id}/save`, 'POST', { include_sensitive: false });
evidence.redacted_record_id = redacted.id;
evidence.retention = 'Explicit synthetic acceptance trace for requested real event/screenshot evidence; product default remains off';
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
page.on('pageerror', e => evidence.errors.push(e.message));
page.on('request', r => { if (r.method() === 'POST' && /\/api\/neural\/runs$/.test(new URL(r.url()).pathname)) evidence.modelRequests.push('unexpected'); });
try {
  await page.goto(base + '/#neural');
  await page.getByRole('button', { name: '서버 연결 필요' }).click();
  await page.getByLabel('로컬 토큰 파일', { exact: true }).setInputFiles(resolve('../.local/auth-token'));
  await page.getByRole('button', { name: '로컬 연결됨' }).waitFor();
  await page.getByRole('navigation').getByRole('button', { name: '신경망 보기', exact: true }).click();
  await page.getByLabel('저장 기록 선택', { exact: true }).selectOption(record.id);
  await page.getByTestId('neural-mode').filter({ hasText: /^REPLAY$/ }).waitFor();
  // Preserve the recorded model-loading interval; first reach prefill at 1x.
  // Slowing the whole cold-load interval to 0.25x can correctly take >20 s.
  await page.getByLabel('재생 속도', { exact: true }).selectOption('1');
  await page.getByRole('button', { name: '기록 재생', exact: true }).click();
  await page.locator('.neural-samples strong').first().waitFor({ timeout: 40000 });
  evidence.actualSampleValues = await page.locator('.neural-samples strong').allTextContents();
  await page.locator('.neural-workspace').screenshot({ path: `${output}/actual-record-structure-and-values.png` });
  await page.getByRole('button', { name: '기록 일시정지', exact: true }).click();
  evidence.pausedMode = await page.getByTestId('neural-mode').innerText();
  await page.getByLabel('재생 속도', { exact: true }).selectOption('0.25');
  await page.getByRole('button', { name: '기록 재생', exact: true }).click();
  await page.waitForTimeout(1200);
  evidence.modeAtQuarterX = await page.getByTestId('neural-mode').innerText();
  await page.getByRole('button', { name: '기록 일시정지', exact: true }).click();
  await page.getByLabel('재생 속도', { exact: true }).selectOption('1');
  await page.getByRole('button', { name: '기록 재생', exact: true }).click();
  await page.waitForTimeout(1200);
  await page.getByRole('button', { name: '기록 일시정지', exact: true }).click();
  evidence.modeAtOneX = await page.getByTestId('neural-mode').innerText();
  await page.screenshot({ path: `${output}/actual-record-replay-1440.png`, fullPage: true });
  await page.getByLabel('저장 기록 선택', { exact: true }).selectOption(redacted.id);
  await page.getByRole('button', { name: '기록 재생', exact: true }).click();
  await page.waitForTimeout(1200);
  evidence.redactedSampleCount = await page.locator('.neural-samples strong').count();
  evidence.redactedOutput = await page.getByTestId('neural-output').innerText();
  evidence.redactedTokenCount = await page.locator('.neural-token-strip span').count();
  if (evidence.redactedSampleCount || evidence.redactedTokenCount) throw new Error('Redacted replay invented/restored sensitive values');
  await page.screenshot({ path: `${output}/actual-redacted-replay.png`, fullPage: true });
  if (evidence.errors.length || evidence.modelRequests.length) throw new Error('Replay produced runtime errors or extra model request');
  evidence.status = 'passed';
} catch (error) {
  evidence.status = 'failed'; evidence.failure = error.message; process.exitCode = 1;
  await page.screenshot({ path: `${output}/failure.png`, fullPage: true }).catch(() => undefined);
} finally {
  await browser.close();
  writeFileSync(`${output}/evidence.json`, JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify({ status: evidence.status, run_id: evidence.run_id, record_id: evidence.record_id, failure: evidence.failure }));
}
