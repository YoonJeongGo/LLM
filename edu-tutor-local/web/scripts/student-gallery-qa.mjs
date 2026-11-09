// Offline evidence-page render check. Does not contact the app or run models.
import { chromium } from '@playwright/test';
import { writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const root = resolve('..');
const folder = resolve(root, 'runs/student-experience/20261027');
const out = resolve(folder, 'gallery-render');
mkdirSync(out, { recursive: true });
const report = { started_at: new Date().toISOString(), scope: 'Static offline gallery layout; no audio listening judgment or model calls', external_requests: [], errors: [], views: [] };
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
page.on('pageerror', e => report.errors.push(e.message));
await page.route(/^https?:/, r => { report.external_requests.push(r.request().url()); return r.abort(); });
try {
  await page.goto(pathToFileURL(resolve(folder, 'index.html')).href);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1100 });
    for (const id of ['overview', 'A-final', 'BC-voicefix', 'D-normal-lesson', 'D-cut-review']) {
      if (id === 'overview') await page.evaluate(() => scrollTo(0, 0));
      else await page.locator('#' + id).evaluate(el => el.scrollIntoView());
      await page.screenshot({ path: resolve(out, `${id}-${width}.png`) });
      report.views.push(await page.evaluate(({ id, width }) => ({ id, width, scroll_width: document.documentElement.scrollWidth, viewport_width: innerWidth, horizontal_page_overflow: document.documentElement.scrollWidth > innerWidth + 1, heading: id === 'overview' ? document.querySelector('h1')?.textContent : document.getElementById(id)?.querySelector('h2')?.textContent }), { id, width }));
    }
  }
  report.local_media = await page.evaluate(() => ({ audio: document.querySelectorAll('audio').length, screenshots: document.querySelectorAll('img').length, scripts: document.querySelectorAll('script').length }));
  report.audio_metadata = await page.evaluate(async () => Promise.all([...document.querySelectorAll('audio')].map((element, index) => new Promise(resolve => {
    let done = false;
    const finish = error => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      resolve({ index, duration_seconds: Number.isFinite(element.duration) ? element.duration : null, error, ready_state: element.readyState });
    };
    const timer = setTimeout(() => finish('metadata_timeout'), 5000);
    element.addEventListener('loadedmetadata', () => finish(null), { once: true });
    element.addEventListener('error', () => finish(`media_error_${element.error?.code}`), { once: true });
    element.preload = 'metadata';
    element.load();
  }))));
  report.status = report.errors.length || report.external_requests.length || report.views.some(v => v.horizontal_page_overflow) || report.audio_metadata.some(v => v.error || !v.duration_seconds) ? 'REVIEW_REQUIRED' : 'PASS_AUTOMATED_LAYOUT';
} catch (error) { report.errors.push(String(error)); report.status = 'FAILED'; }
finally {
  report.finished_at = new Date().toISOString();
  writeFileSync(resolve(out, 'report.json'), JSON.stringify(report, null, 2));
  await browser.close();
}
console.log(JSON.stringify(report));
