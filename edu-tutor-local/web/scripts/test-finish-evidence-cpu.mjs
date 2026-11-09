// Synthetic DOM + generated PCM fixture only. No tutor API, model, TTS, OCR,
// downloads, saved lesson, or human listening judgement is exercised.
import { chromium } from '@playwright/test';
import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync, mkdtempSync } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';
import katex from 'katex';

const root = resolve('..');
const source = readFileSync(resolve('scripts/finish-student-journeys.mjs'), 'utf8');
const body = source.split('await page.addInitScript(() => {')[1]?.split('\n});\nasync function events()')[0];
assert.ok(body, 'Exact live instrumentation must be extracted');
const sourceFunction = source.slice(source.indexOf('function sources() {'), source.indexOf('\nconst terminal ='));
const sourceCheck = new Function('root', 'input', 'readFileSync', 'readdirSync', 'existsSync', 'resolve', 'sha', sourceFunction + '\nreturn sources();');
const fixtureRoot = mkdtempSync(resolve(root, 'runs/finish-v2/20261029/student-audit/source-drift-fixture-'));
mkdirSync(resolve(fixtureRoot, 'src/edu_tutor/models'), { recursive: true });
mkdirSync(resolve(fixtureRoot, 'web/dist'), { recursive: true });
writeFileSync(resolve(fixtureRoot, 'web/dist/index.html'), '<script src="/app.js"></script>');
writeFileSync(resolve(fixtureRoot, 'web/dist/app.js'), '/* fixed browser bundle */');
const fixedModule = resolve(fixtureRoot, 'src/edu_tutor/models/text_session.py');
writeFileSync(fixedModule, '# fixed worker');
const readSources = () => sourceCheck(fixtureRoot, { journeys: [] }, readFileSync, readdirSync, existsSync, resolve,
  file => createHash('sha256').update(readFileSync(file)).digest('hex'));
const frozenSources = readSources();
writeFileSync(fixedModule, '# changed after freeze');
assert.notDeepEqual(readSources(), frozenSources, 'Changing a resident-worker module must invalidate the frozen version');
const equation = katex.renderToString('2+3=5', { throwOnError: false, trust: false, strict: 'error', maxExpand: 100, maxSize: 10, output: 'html' });
const frames = 4410, wav = Buffer.alloc(44 + frames * 2);
wav.write('RIFF'); wav.writeUInt32LE(wav.length - 8, 4); wav.write('WAVEfmt ', 8); wav.writeUInt32LE(16, 16);
wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22); wav.writeUInt32LE(22050, 24); wav.writeUInt32LE(44100, 28);
wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34); wav.write('data', 36); wav.writeUInt32LE(frames * 2, 40);
for (let i = 0; i < frames; i++) wav.writeInt16LE(i % 2 ? 16 : -16, 44 + i * 2);
const browser = await chromium.launch({ channel: 'chrome', headless: true });
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.addInitScript({ content: body });
  await page.route('**/*', route => route.fulfill({ contentType: 'text/html', body: `<!doctype html><meta charset="utf-8"><div class="classroom" data-lesson-record-id="fixture"><div class="chalk-board"><section data-board-element="table"><table><thead><tr><th>x</th></tr></thead><tbody><tr><td data-cell-id="cell"><button aria-pressed="true">2</button></td></tr></tbody></table></section><section data-board-element="equation"><div class="equation">${equation}</div></section></div><div class="caption-box"><p>검증 대사</p></div><audio data-lesson-record-id="fixture" data-step-id="s1" data-playback-epoch="7"></audio></div>` }));
  await page.goto('http://127.0.0.1:8765/offline-evidence-fixture');
  const result = await page.evaluate(async bytes => {
    const audio = document.querySelector('audio');
    audio.addEventListener('playing', () => window.dispatchEvent(new CustomEvent('edu:lesson', { detail: { type: 'audio_playing', at_ms: performance.now(), lesson_record_id: 'fixture', step_id: 's1', epoch: 7 } })));
    const ended = new Promise(resolve => audio.addEventListener('ended', resolve, { once: true }));
    audio.src = URL.createObjectURL(new Blob([new Uint8Array(bytes)], { type: 'audio/wav' }));
    await audio.play(); await ended; await Promise.allSettled(window.__finishBlobTasks);
    return { events: window.__finishEvents, native: window.__finishMedia, blobs: window.__finishBlobs, snapshot: window.__finishSnapshot() };
  }, [...wav]);
  const played = result.events.find(e => e.type === 'audio_playing');
  const native = result.native.find(e => e.type === 'playing');
  assert.equal(played.media.media_id, native.media_id);
  assert.equal(native.epoch, 7);
  assert.equal(result.blobs[native.current_src].sha256, createHash('sha256').update(wav).digest('hex'));
  assert.equal(played.board_content[0].rows[0][0].text, '2');
  assert.equal(played.board_content[1].equation_html, equation);
  assert.equal(played.caption, '검증 대사');
  assert.ok(result.native.some(e => e.type === 'ended' && e.media_id === native.media_id));
  const report = { provenance: 'Synthetic CPU/browser DOM + short PCM fixture, not a model/TTS/student lesson or listening judgement', status: 'PASS', source_drift_rejected: true, model_calls: 0, tts_calls: 0, ocr_calls: 0, ...result };
  writeFileSync(resolve(root, 'runs/finish-v2/20261029/student-audit/browser-instrumentation-cpu.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ status: report.status, same_native_blob_and_epoch: true, exact_equation_dom: true, real_tts_calls: 0 }));
} finally { await browser.close(); }
