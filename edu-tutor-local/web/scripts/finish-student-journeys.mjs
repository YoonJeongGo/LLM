// Fresh real student journeys. Preparing this file performs no model calls.
// Run one case only after the coordinator has frozen a tested version:
//   node scripts/finish-student-journeys.mjs --freeze final01
//   node scripts/finish-student-journeys.mjs --run J01 --version final01
// No automatic repeat, OCR correction, fixed lesson, audio seek or rate change.
import { chromium } from '@playwright/test';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { resolve, relative } from 'node:path';
import { execFileSync } from 'node:child_process';
import katex from 'katex';

const root = resolve('..');
const base = resolve(root, 'runs/finish-v2/20261029/student');
const scope = 'finish-local-tutor-20261028-v1';
const origin = 'http://127.0.0.1:8000';
const args = process.argv.slice(2);
const parameter = name => args.includes(name) ? args[args.indexOf(name) + 1] : undefined;
const sha = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const input = JSON.parse(readFileSync(resolve(base, 'journeys.json'), 'utf8'));
const version = parameter('--version') || parameter('--freeze');
if (!version || !/^[a-zA-Z0-9_-]{1,60}$/.test(version)) throw Error('An explicit version is required');
const versionDir = resolve(base, version);
mkdirSync(versionDir, { recursive: true });
const token = readFileSync(resolve(root, '.local/auth-token'), 'utf8').trim();
const headers = { Authorization: `Bearer ${token}`, 'X-Execution-Allowance': scope };
async function get(path) {
  const response = await fetch(origin + '/api' + path, { headers });
  if (!response.ok) throw Error(`GET ${path}: ${response.status}`);
  return response.json();
}
function sources() {
  const paths = ['src/edu_tutor/api/app.py', 'src/edu_tutor/models/runtime.py', 'src/edu_tutor/models/worker.py',
    'src/edu_tutor/models/budget.py', 'src/edu_tutor/speech/provider.py', 'src/edu_tutor/speech/windows_sapi.py',
    'src/edu_tutor/speech/windows_sapi_worker.ps1', 'src/edu_tutor/lessons/verified.py',
    'src/edu_tutor/problems/evidence.py', 'src/edu_tutor/vision/structure.py', 'src/edu_tutor/models/vision_runtime.py',
    'web/src/ProblemEditor.tsx', 'web/src/problemTables.ts', 'web/src/PhotoDialog.tsx',
    'src/edu_tutor/models/text_session.py', 'src/edu_tutor/models/text_session_worker.py',
    'src/edu_tutor/speech/direct.py', 'src/edu_tutor/jobs/owned_process.py', 'src/edu_tutor/jobs/manager.py',
    'src/edu_tutor/lessons/concepts.py', 'scripts/finish_collect_journeys.py', 'scripts/student_experience_report.py',
    'web/scripts/finish-student-journeys.mjs', 'runs/finish-v2/20261029/student/private-oracle.json',
    '.local/speech-provider.json', '.local/model-selection.json', '.local/phase2-policy.json', '.local/text-session-policy.json',
    '.local/text-inference-policy.json', 'runs/finish-v2/20261029/student/journeys.json',
    '.local/models/text/model-manifest.json'];
  const visit = folder => { for (const item of readdirSync(resolve(root, folder), { withFileTypes: true })) {
    const name = folder + '/' + item.name;
    if (item.isDirectory() && item.name !== '__pycache__') visit(name);
    else if (item.isFile() && /\.(py|ps1)$/.test(item.name)) paths.push(name);
  } };
  visit('src/edu_tutor');
  paths.push('web/package-lock.json', '.local/models/text/config.json', '.local/models/text/generation_config.json');
  for (const journey of input.journeys) if (journey.photo?.path) paths.push(journey.photo.path);
  const html = readFileSync(resolve(root, 'web/dist/index.html'), 'utf8');
  paths.push('web/dist/index.html');
  for (const match of html.matchAll(/(?:src|href)="([^\"]+\.(?:js|css))"/g)) paths.push('web/dist/' + match[1].replace(/^\//, ''));
  return Object.fromEntries([...new Set(paths)].sort().map(path => [path, existsSync(resolve(root, path)) ? sha(resolve(root, path)) : null]));
}
const terminal = new Set(['succeeded', 'failed', 'cancelled', 'interrupted', 'blocked']);
async function preflight() {
  const [budget, jobs, session, health, model, capabilities] = await Promise.all([
    get('/resources/budget'), get('/jobs'), get('/tts/session'), get('/health'), get('/models'), get('/capabilities')]);
  if (budget.active_execution_allowance?.id !== scope || budget.accounting_scope !== scope)
    throw Error('Integrated explicit scope is not effective');
  if (jobs.some(j => !terminal.has(j.state))) throw Error('Another application job is active; no live journey started');
  if (session.resident) throw Error('Experimental resident TTS must be closed before selected-provider validation');
  return { budget, health, session, model: { model_id: model.model_id, revision: model.revision,
    active_adapter: model.active_adapter, ready: model.ready }, speech: capabilities.speech };
}
const versionPath = resolve(versionDir, 'execution-version.json');
if (args.includes('--freeze')) {
  if (existsSync(versionPath)) throw Error('Version is already frozen');
  const state = await preflight();
  // Preserve the authored inputs with each version, so a later development
  // question revision cannot prevent collecting the earlier failed attempt.
  writeFileSync(resolve(versionDir, 'journeys.json'), readFileSync(resolve(base, 'journeys.json')));
  writeFileSync(resolve(versionDir, 'private-oracle.json'), readFileSync(resolve(base, 'private-oracle.json')));
  writeFileSync(versionPath, JSON.stringify({ version, at: new Date().toISOString(), authorization_id: scope,
    source_hashes: sources(), input_sha256: sha(resolve(base, 'journeys.json')), state,
    scope: 'Frozen actual-journey configuration; not an acceptance result',
    deployment_proof: 'Disk hashes do not prove the running API loaded these files. Coordinator restart PID/start-time evidence is required separately.' }, null, 2));
  console.log(JSON.stringify({ status: 'FROZEN_NO_MODEL_CALLS', version }));
  process.exit(0);
}
const id = parameter('--run');
const spec = input.journeys.find(j => j.id === id);
if (!spec || !existsSync(versionPath)) throw Error('Select one known case and an existing frozen version');
const frozen = JSON.parse(readFileSync(versionPath, 'utf8'));
if (JSON.stringify(frozen.source_hashes) !== JSON.stringify(sources()) || frozen.input_sha256 !== sha(resolve(base, 'journeys.json')))
  throw Error('Code, settings or inputs changed after freeze; do not mix versions');
const out = resolve(versionDir, id);
mkdirSync(out, { recursive: true });
const actualPath = resolve(out, 'actual.json');
if (existsSync(actualPath)) throw Error('This case already has an attempt. No automatic retry or overwrite');
const before = await preflight();
if (JSON.stringify(before.model) !== JSON.stringify(frozen.state.model) || JSON.stringify(before.speech) !== JSON.stringify(frozen.state.speech))
  throw Error('Active model/provider differs from the frozen version');
const oracle = JSON.parse(readFileSync(resolve(base, 'private-oracle.json'), 'utf8'))[id];
const result = { id, version, started_at: new Date().toISOString(), status: 'RUNNING', spec,
  provenance: input.provenance, before, source_hashes: frozen.source_hashes,
  requests: [], responses: [], events: [], native_media: [], screenshots: [], samples: [], errors: [], blocked_requests: [], equation_renderings: {},
  harness: { human_review: 'H_PENDING', answer_injection: false, fixed_audio: false, playback_rate: 1,
    expected_values_only_in_test_harness: true, browser_submission_retry: false, actual_model_attempts: 'COLLECT_FROM_LEDGER', OCR_retry: false, manual_OCR_edit: false } };
const save = () => writeFileSync(actualPath, JSON.stringify(result, null, 2));
save();
// Playwright adds --mute-audio for headless Chromium by default. Remove that
// flag and inspect this owned browser's actual argv; this is still not a
// physical speaker/listener review.
const browser = await chromium.launch({ channel: 'chrome', headless: true, ignoreDefaultArgs: ['--mute-audio'] });
try {
  const cdp = await browser.newBrowserCDPSession();
  const info = await cdp.send('SystemInfo.getProcessInfo');
  const browserPid = info.processInfo.find(p => p.type === 'browser')?.id;
  if (!Number.isInteger(browserPid)) throw Error('Owned browser PID unavailable');
  const owned = JSON.parse(execFileSync(resolve(root, '.venv/Scripts/python.exe'), ['-c',
    'import psutil,sys,json; p=psutil.Process(int(sys.argv[1])); print(json.dumps({"pid":p.pid,"birth":p.create_time(),"exe":p.exe(),"argv":p.cmdline(),"ancestors":[x.pid for x in p.parents()]}))', String(browserPid)],
    { encoding: 'utf8', windowsHide: true }));
  if (!owned.ancestors.includes(process.pid) || owned.argv.includes('--mute-audio')) throw Error('Browser ownership/audio launch verification failed');
  result.browser_launch = { requested: { channel: 'chrome', headless: true, ignoreDefaultArgs: ['--mute-audio'] },
    actual: owned, no_browser_mute_flag: true, physical_listening_review: 'H_PENDING' };
  await cdp.detach(); save();
} catch (error) {
  result.status = 'FAILED_BROWSER_PREFLIGHT_NO_MODEL_CALL'; result.failure = String(error);
  result.completed_at = new Date().toISOString(); save(); await browser.close(); throw error;
}
const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
const page = await context.newPage();
page.on('pageerror', e => { result.errors.push(e.message); save(); });
const counts = { text: 0, speech: 0, vision: 0 };
const ownedJobIds = new Set();
const pendingResponses = new Set();
let finishing = false;
await context.route('**/*', async route => {
  const request = route.request(), url = new URL(request.url()), method = request.method(), path = url.pathname;
  try {
    if (url.origin !== origin) throw Error('External request prohibited');
    if (method === 'POST') {
      if (finishing && !/\/cancel$|\/speech\/session\/close$/.test(path)) throw Error('Late mutation after journey observation ended');
      if (request.headers()['x-execution-allowance'] !== scope) throw Error('Explicit execution scope header missing');
      if (/\/sessions\/[^/]+\/messages$/.test(path) || /\/photos\/[^/]+\/solve$/.test(path)) {
        if (++counts.text > (spec.followup ? 2 : 1)) throw Error('Unexpected additional student submission');
      } else if (/\/lessons\/[^/]+\/speech$/.test(path)) {
        if (++counts.speech > 12) throw Error('Journey audio-request bound reached');
      } else if (/\/photos\/[^/]+\/transcribe$/.test(path)) {
        if (++counts.vision > 1) throw Error('No automatic OCR retry');
      } else if (!(/^\/api\/(sessions|photos|lessons)$/.test(path) ||
        /^\/api\/lessons\/[^/]+\/generate$/.test(path) || /^\/api\/photos\/[^/]+\/(confirm|restructure)$/.test(path) ||
        /^\/api\/jobs\/[^/]+\/cancel$/.test(path) || /^\/api\/lessons\/[^/]+\/speech\/session\/close$/.test(path)))
        throw Error('Unexpected mutating endpoint');
    } else if (method !== 'GET') throw Error('No editing or deletion in the fresh journey harness');
    result.requests.push({ at: new Date().toISOString(), method, path });
    await route.continue();
  } catch (error) { result.blocked_requests.push({ path, method, reason: String(error) }); save(); await route.abort(); }
});
page.on('response', response => {
  const pending = (async () => {
  try {
    const path = new URL(response.url()).pathname, method = response.request().method();
    if (!path.startsWith('/api/') || !response.headers()['content-type']?.includes('application/json')) return;
    const value = await response.json();
    if (value?.plan?.steps) for (const step of value.plan.steps) for (const action of step.board_actions || [])
      if (action.type === 'equation') result.equation_renderings[action.latex] = katex.renderToString(action.latex,
        { throwOnError: false, trust: false, strict: 'error', maxExpand: 100, maxSize: 10, output: 'html' });
    if (method === 'POST' && value.job_id) ownedJobIds.add(value.job_id);
    if (method !== 'GET' || /\/lessons\/|\/photos\/|\/messages$/.test(path)) {
      let request;
      if (method !== 'GET' && response.request().headers()['content-type']?.includes('application/json'))
        request = response.request().postDataJSON();
      result.responses.push({ at: new Date().toISOString(), method, path, status: response.status(), request, value }); save();
    }
  } catch { /* A response can be cancelled while switching an interrupted lesson. */ }
  })();
  pendingResponses.add(pending);
  void pending.finally(() => pendingResponses.delete(pending));
});
await page.addInitScript(() => {
  localStorage.setItem('edu-tab', 'settings');
  window.__finishEvents = [];
  window.__finishMedia = [];
  window.__finishSceneSamples = [];
  window.__finishBlobs = {};
  window.__finishBlobTasks = [];
  const originalObjectURL = URL.createObjectURL.bind(URL);
  URL.createObjectURL = blob => {
    const url = originalObjectURL(blob);
    if (blob instanceof Blob) window.__finishBlobTasks.push(blob.arrayBuffer().then(async bytes => {
      const hash = await crypto.subtle.digest('SHA-256', bytes);
      window.__finishBlobs[url] = { sha256: [...new Uint8Array(hash)].map(x => x.toString(16).padStart(2, '0')).join(''), size: bytes.byteLength };
    }).catch(error => { window.__finishBlobs[url] = { error: String(error) }; }));
    return url;
  };
  const mediaIds = new WeakMap(); let nextMediaId = 0;
  const mediaId = element => { if (!element) return null; if (!mediaIds.has(element)) mediaIds.set(element, ++nextMediaId); return mediaIds.get(element); };
  const media = element => ({ paused: element?.paused, currentTime: element?.currentTime, duration: element?.duration,
    playbackRate: element?.playbackRate, lesson_id: element?.dataset.lessonRecordId, step_id: element?.dataset.stepId,
    epoch: Number(element?.dataset.playbackEpoch), media_id: mediaId(element), current_src: element?.currentSrc || element?.src,
    muted: element?.muted, volume: element?.volume });
  const equationGlyphRects = element => {
    const content = element.querySelector('.equation .katex-html');
    if (!content) return undefined;
    const rectangles = [], walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (!node.textContent?.trim() || !node.parentElement?.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) continue;
      const range = document.createRange(); range.selectNodeContents(node);
      rectangles.push(...[...range.getClientRects()].filter(rect => rect.width > 0 && rect.height > 0).map(rect => rect.toJSON()));
    }
    return rectangles;
  };
  window.__finishSnapshot = () => {
    const board = document.querySelector('.chalk-board');
    const elements = [...document.querySelectorAll('[data-board-element]')].map(e => ({ id: e.dataset.boardElement,
      text: e.querySelector(':scope > p')?.textContent,
      equation_html: e.querySelector('.equation')?.innerHTML,
      equation_glyph_rects: equationGlyphRects(e),
      code: [...e.querySelectorAll('.code-line')].map(line => [...line.childNodes].filter(n => !(n instanceof Element && n.classList.contains('line-number'))).map(n => n.textContent).join('')).join(''),
      columns: [...e.querySelectorAll('thead th')].map(c => c.textContent),
      rows: [...e.querySelectorAll('tbody tr')].map(row => [...row.querySelectorAll('[data-cell-id]')].map(c => ({ id: c.dataset.cellId, text: c.textContent }))),
      rect: e.getBoundingClientRect().toJSON() }));
    const content = elements.map(({ rect, equation_glyph_rects, ...rest }) => rest);
    const pointer = document.querySelector('[data-testid="avatar-pointer"]'), svg = pointer?.ownerSVGElement, point = svg?.createSVGPoint();
    if (point && pointer) { point.x = Number(pointer.getAttribute('x2')); point.y = Number(pointer.getAttribute('y2')); }
    const end = point && svg?.getScreenCTM() ? point.matrixTransform(svg.getScreenCTM()) : null;
    return { dom_lesson_record_id: document.querySelector('.classroom')?.dataset.lessonRecordId,
      dom_step_id: document.querySelector('.classroom')?.dataset.stepId,
      board_text: board?.innerText || '', board_content: content, board_content_serialized: JSON.stringify(content),
      stage_rect: document.querySelector('.chalk-stage')?.getBoundingClientRect().toJSON(),
      elements, cells: [...document.querySelectorAll('[data-cell-id]')].map(c => ({ id: c.dataset.cellId, text: c.textContent, selected: c.querySelector('button')?.getAttribute('aria-pressed') === 'true', rect: c.getBoundingClientRect().toJSON() })),
      caption: document.querySelector('.caption-box p')?.textContent,
      gesture: document.querySelector('[data-gesture]')?.getAttribute('data-gesture'), pointer_end: end ? { x: end.x, y: end.y } : null,
      arrows: [...document.querySelectorAll('.pointer-layer line[marker-end]')].map(e => ({ id: e.id,
        x1: Number(e.getAttribute('x1')), y1: Number(e.getAttribute('y1')), x2: Number(e.getAttribute('x2')), y2: Number(e.getAttribute('y2')) })),
      media: media(document.querySelector('audio')) };
  };
  const sampled = new Set();
  function sampleScene(kind, element = document.querySelector('audio')) {
    if (!(element instanceof HTMLAudioElement) || !Number.isFinite(element.duration) || element.duration <= 0) return;
    const progress = element.currentTime / element.duration;
    const key = `${mediaId(element)}:${element.dataset.playbackEpoch}:${Math.floor(progress * 10)}:${kind}`;
    if (kind !== 'native_ended' && (element.paused || progress < 0.05 || sampled.has(key))) return;
    sampled.add(key);
    window.__finishSceneSamples.push({ ...window.__finishSnapshot(), type: kind, at_ms: performance.now(),
      lesson_record_id: element.dataset.lessonRecordId, step_id: element.dataset.stepId,
      epoch: Number(element.dataset.playbackEpoch), media: media(element) });
  }
  setInterval(() => sampleScene('progress'), 100);
  window.addEventListener('edu:lesson', event => {
    const board = document.querySelector('.chalk-board');
    window.__finishEvents.push({ ...event.detail, ...window.__finishSnapshot(),
      board_html: ['audio_playing', 'interruption_submitted', 'interruption_stopped', 'lesson_resumed'].includes(event.detail.type) ? board?.outerHTML : undefined,
      media: media(document.querySelector('audio')) });
  });
  for (const type of ['play', 'playing', 'pause', 'ended', 'seeking', 'seeked'])
    document.addEventListener(type, event => { if (event.target instanceof HTMLAudioElement) {
      window.__finishMedia.push({ type, at_ms: performance.now(), ...media(event.target) });
      if (type === 'ended') sampleScene('native_ended', event.target);
    } }, true);
});
async function events() { return page.evaluate(() => window.__finishEvents); }
async function nav(name) {
  const menu = page.getByRole('button', { name: '메뉴 열기' }); if (await menu.isVisible()) await menu.click();
  await page.getByRole('navigation').getByRole('button', { name, exact: true }).click();
}
async function capture(name) {
  const path = resolve(out, name + '.png');
  await page.screenshot({ path, fullPage: true }); result.screenshots.push(relative(root, path));
  result.samples.push(await page.evaluate(label => {
    const pointer = document.querySelector('[data-testid="avatar-pointer"]');
    const svg = pointer?.ownerSVGElement, point = svg?.createSVGPoint();
    if (point && pointer) { point.x = Number(pointer.getAttribute('x2')); point.y = Number(pointer.getAttribute('y2')); }
    const position = point && svg?.getScreenCTM() ? point.matrixTransform(svg.getScreenCTM()) : null;
    const audio = document.querySelector('audio');
    return { ...window.__finishSnapshot(), label, at_ms: performance.now(), viewport: { width: innerWidth, height: innerHeight },
      lesson_record_id: document.querySelector('.classroom')?.dataset.lessonRecordId,
      step_id: audio?.dataset.stepId,
      board_text: document.querySelector('.chalk-board')?.innerText, board_html: document.querySelector('.chalk-board')?.outerHTML,
      caption: document.querySelector('.caption-box p')?.textContent,
      gesture: document.querySelector('[data-gesture]')?.getAttribute('data-gesture'),
      pointer_end: position ? { x: position.x, y: position.y } : null,
      elements: [...document.querySelectorAll('[data-board-element]')].map(e => ({ id: e.dataset.boardElement, text: e.innerText, rect: e.getBoundingClientRect().toJSON() })),
      cells: [...document.querySelectorAll('[data-cell-id]')].map(e => ({ id: e.dataset.cellId, text: e.textContent, rect: e.getBoundingClientRect().toJSON() })),
      arrows: document.querySelectorAll('.pointer-layer line[marker-end]').length,
      media: window.__finishSnapshot().media };
  }, name)); save();
}
async function firstPlaying(count = 0, supplement = null) {
  await page.waitForFunction(({ count, supplement }) => window.__finishEvents.filter(e => e.type === 'audio_playing').slice(count)
    .some(e => supplement === null || !!e.supplement === supplement) ||
    window.__finishEvents.some(e => e.type === 'lesson_blocked') || document.querySelector('.classroom [role="alert"]'), { count, supplement }, { timeout: 330000 });
  const history = await events();
  if (history.some(e => e.type === 'lesson_blocked')) throw Error(history.findLast(e => e.type === 'lesson_blocked').reason);
  const audio = history.filter(e => e.type === 'audio_playing').slice(count).find(e => supplement === null || !!e.supplement === supplement);
  if (!audio) throw Error(await page.locator('.classroom [role="alert"]').innerText());
  if (audio.media.playbackRate !== 1 || audio.media.muted || !(audio.media.volume > 0)) throw Error('Altered/muted playback');
  return audio;
}
async function waitJob(id) {
  const start = Date.now();
  while (Date.now() - start < 330000) {
    const job = await get('/jobs/' + id);
    if (terminal.has(job.state)) return job;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw Error('Job status did not finish within bounded observation window');
}
function comparableTable(t) { return { name: t.name.toLowerCase(), columns: t.columns.map(c => (typeof c === 'string' ? c : c.name).toLowerCase()), rows: t.rows }; }
function normalizedSQL(sql) { return String(sql || '').replace(/\s+/g, '').replace(/;$/, '').toLowerCase(); }
async function photoFlow() {
  await page.getByLabel('사진 답변도 수업으로 듣기').check();
  await page.getByRole('button', { name: '문제 사진 첨부', exact: true }).click();
  result.photo_upload_at_ms = await page.evaluate(() => performance.now());
  const uploaded = page.waitForResponse(r => new URL(r.url()).pathname === '/api/photos' && r.request().method() === 'POST');
  await page.getByLabel('문제 사진 업로드', { exact: true }).setInputFiles(resolve(root, spec.photo.path));
  const upload = await uploaded; const photoId = (await upload.json()).id;
  const started = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/transcribe') && r.request().method() === 'POST');
  result.ocr_submit_at_ms = await page.evaluate(() => performance.now());
  await page.getByRole('button', { name: '로컬 모델로 원문 인식', exact: true }).click();
  const transcribed = await started;
  if (!transcribed.ok()) throw Error('OCR request rejected: ' + transcribed.status());
  result.ocr_job = await waitJob((await transcribed.json()).job_id);
  result.ocr_candidate_at_ms = await page.evaluate(() => performance.now());
  result.photo = await get('/photos/' + photoId); save();
  await page.getByRole('button', { name: '로컬 모델로 원문 인식', exact: true }).waitFor();
  await capture('photo-candidate');
  if (result.ocr_job.state !== 'succeeded') throw Error('OCR failed: ' + result.ocr_job.error);
  if (spec.must_not_invent) {
    const candidate = result.photo;
    result.photo_check = { missing_condition_reported: !!candidate.missing_conditions?.length,
      numeric_threshold_invented: /qty\s*>=\s*[-+]?\d/i.test((candidate.sql || '') + '\n' + (candidate.original_text || '')),
      human_review: 'H_PENDING', no_manual_edit: true };
    if (result.photo_check.numeric_threshold_invented) throw Error('OCR invented an absent threshold; no confirmation/solve permitted');
    if (!result.photo_check.missing_condition_reported) throw Error('Missing condition not identified; cannot count safety as passed');
    const confirm = page.getByRole('button', { name: '이 원문으로 확정', exact: true });
    if (await confirm.isEnabled()) await confirm.click();
    const solve = page.getByRole('button', { name: '확정한 문제 풀이', exact: true });
    await solve.waitFor();
    if (await solve.isEnabled()) {
      const response = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/solve') && r.request().method() === 'POST');
      await solve.click(); const rejected = await response;
      result.safe_stop_response = { status: rejected.status(), value: await rejected.json() };
      if (rejected.status() !== 409) throw Error('Missing source was not rejected before inference');
    } else result.safe_stop_response = { status: 'UI_DISABLED', notice: 'No completed explanation or first-audio measurement' };
    await capture('missing-condition-safe-stop'); return false;
  }
  let candidate = result.photo;
  if (!candidate.tables?.length && candidate.original_text) {
    const restruct = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/restructure') && r.request().method() === 'POST');
    await page.getByRole('button', { name: '인식문에서 표 다시 정리', exact: true }).click();
    const response = await restruct; candidate = await response.json(); result.restructure = { status: response.status(), candidate };
  }
  result.photo_check = { table_exact: JSON.stringify(candidate.tables?.map(comparableTable)) === JSON.stringify(oracle.tables.map(comparableTable)),
    query_exact_ignoring_format: normalizedSQL(candidate.sql) === normalizedSQL(oracle.query),
    no_missing_conditions: !candidate.missing_conditions?.length, no_manual_edit: true, confirmation_kind: 'automated authored-source comparison, not human review' };
  save();
  if (!result.photo_check.table_exact || !result.photo_check.query_exact_ignoring_format || !result.photo_check.no_missing_conditions)
    throw Error('OCR differs from authored source; preserved without replacing it with the private oracle');
  result.source_review_started_at_ms = await page.evaluate(() => performance.now());
  const confirmed = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/confirm') && r.request().method() === 'POST');
  await page.getByRole('button', { name: '이 원문으로 확정', exact: true }).click(); await confirmed;
  result.source_confirmed_at_ms = await page.evaluate(() => performance.now());
  await page.getByRole('button', { name: '확정한 문제 풀이', exact: true }).click(); return true;
}
async function finishPlayback(originalId) {
  const lesson = await get('/lessons/' + originalId);
  result.actual_lesson = lesson;
  result.actual_messages = await get('/sessions/' + lesson.source_session_id + '/messages');
  const answer = result.actual_messages.find(m => m.id === lesson.source_message_id);
  result.quality = { app_result_matches_private_oracle: oracle?.result ? JSON.stringify(answer?.evidence?.result?.rows) === JSON.stringify(oracle.result.rows) : null,
    raw_model_response: answer?.raw_model_response, actual_app_response: answer?.content,
    generation_snapshot: answer?.generation_snapshot, evidence_status: answer?.evidence?.status,
    human_review: 'H_PENDING' };
  save();
  const captured = new Set();
  const lateCaptured = new Set();
  const started = Date.now();
  while (Date.now() - started < 420000) {
    const history = await events();
    if (history.some(e => e.type === 'lesson_blocked')) throw Error(history.findLast(e => e.type === 'lesson_blocked').reason);
    // Historical events retain their synchronous DOM snapshots. Never label a
    // current screenshot as an earlier supplement/step that has already ended.
    const current = await page.locator('audio').evaluate(a => ({ lesson: a.dataset.lessonRecordId, step: a.dataset.stepId, epoch: Number(a.dataset.playbackEpoch), playing: !a.paused })).catch(() => null);
    const currentKey = current && `${current.lesson}-${current.step}-${current.epoch}`;
    if (current?.playing && !captured.has(currentKey)) { captured.add(currentKey); await capture('current-playing-' + captured.size); }
    const later = await page.locator('audio').evaluate(a => ({ lesson: a.dataset.lessonRecordId, step: a.dataset.stepId,
      ready: !a.paused && a.duration > 0 && a.currentTime / a.duration >= 0.8 })).catch(() => null);
    if (later?.ready && !lateCaptured.has(later.lesson + '-' + later.step)) {
      lateCaptured.add(later.lesson + '-' + later.step); await capture('late-step-' + lateCaptured.size);
    }
    const last = lesson.plan.steps.at(-1).id;
    if (history.some(e => e.type === 'audio_ended' && e.lesson_record_id === originalId && e.step_id === last)) break;
    if (await page.locator('.classroom [role="alert"]').count()) throw Error(await page.locator('.classroom [role="alert"]').innerText());
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  result.events = await events();
  const last = lesson.plan.steps.at(-1).id;
  if (!result.events.some(e => e.type === 'audio_ended' && e.lesson_record_id === originalId && e.step_id === last)) throw Error('Natural final audio end not recorded');
  result.actual_lesson = await get('/lessons/' + originalId);
  const interruptEvent = result.events.find(e => e.type === 'interruption_submitted');
  const resumedEvent = result.events.find(e => e.type === 'lesson_resumed');
  const nativeMedia = await page.evaluate(() => window.__finishMedia);
  result.requirements = { final_audio_ended: true, numerical_result_matches: result.quality.app_result_matches_private_oracle,
    selected_row_interruption: !spec.followup || !!result.events.find(e => e.type === 'interruption_submitted' && e.selected_cell_id && e.board_text?.trim()),
    original_lesson_resumed: !spec.followup || result.events.some(e => e.type === 'lesson_resumed' && e.lesson_record_id === originalId),
    native_old_audio_pause: !spec.followup || nativeMedia.some(e => e.type === 'pause' && e.lesson_id === originalId && e.at_ms >= interruptEvent?.at_ms && e.at_ms < resumedEvent?.at_ms),
    no_cancelled_audio_before_resume: !spec.followup || !nativeMedia.some(e => e.type === 'playing' && e.lesson_id === originalId && e.at_ms > interruptEvent?.at_ms && e.at_ms < resumedEvent?.at_ms),
    diagram_present: !spec.requires_simple_diagram || result.samples.some(s => s.arrows > 0),
    diagram_in_plan: !spec.requires_simple_diagram || lesson.plan.steps.some(s => s.board_actions?.some(a => ['arrow', 'shape', 'diagram'].includes(a.type))) };
  await capture('completed');
  await page.setViewportSize({ width: 390, height: 844 });
  await capture('completed-390');
  await nav('설정'); await page.getByLabel('화면 글자 크기', { exact: true }).selectOption('2'); await nav('강의실');
  await capture('completed-390-text200');
}
try {
  await page.goto(origin);
  await page.getByRole('button', { name: '서버 연결 필요', exact: true }).click();
  await page.getByLabel('로컬 토큰 파일', { exact: true }).setInputFiles(resolve(root, '.local/auth-token'));
  await page.getByRole('button', { name: '로컬 연결됨', exact: true }).waitFor({ timeout: 30000 });
  await nav('설정');
  await page.getByRole('button', { name: '이번 브라우저에서 검증 예산 사용', exact: true }).click();
  await nav('대화');
  let startLesson = true;
  if (spec.kind === 'photo') startLesson = await photoFlow();
  else {
    if (spec.tables) {
      await page.locator('.problem-editor summary').click();
      await page.getByLabel('이 질문에 원본 표·SQL을 함께 보냅니다').check();
      await page.getByRole('combobox', { name: /^문제 종류/ }).selectOption(spec.task_kind);
      await page.getByRole('combobox', { name: /^DBMS/ }).selectOption('sqlite');
      await page.getByLabel('문제의 원본 SQL', { exact: true }).fill(spec.query);
      if (id === 'J03') {
        for (const [ti, table] of spec.tables.entries()) {
          await page.getByRole('button', { name: '표 추가', exact: true }).click();
          await page.getByLabel(`표 ${ti + 1} 이름`, { exact: true }).fill(table.name);
          for (const [ci, column] of table.columns.entries()) {
            await page.getByRole('button', { name: `표 ${ti + 1} 열 추가`, exact: true }).click();
            await page.getByLabel(`표 ${ti + 1} 열 ${ci + 1} 이름`, { exact: true }).fill(column.name);
            await page.getByLabel(`표 ${ti + 1} 열 ${ci + 1} 자료형`, { exact: true }).selectOption(column.type);
          }
          for (const [ri, row] of table.rows.entries()) {
            await page.getByRole('button', { name: `표 ${ti + 1} 행 추가`, exact: true }).click();
            for (const [ci, value] of row.entries()) {
              const label = `표 ${ti + 1} ${ri + 1}행 ${ci + 1}열`;
              if (value === null) await page.getByLabel(label + ' 상태', { exact: true }).selectOption('null');
              else { const cell = page.getByLabel(label + ' 값', { exact: true }); await cell.fill(String(value)); await cell.blur(); }
            }
          }
        }
        result.table_input_mode = 'student_grid';
      } else {
        await page.locator('.source-json-editor summary').click();
        await page.getByLabel('문제의 원본 표 JSON', { exact: true }).fill(JSON.stringify(spec.tables));
        result.table_input_mode = 'expert_JSON';
      }
      await page.getByLabel('원문과 비교해 표·값·SQL을 확인했습니다').check();
    }
    await page.getByLabel('질문 입력', { exact: true }).fill(spec.question);
    await capture('before-submit');
    await page.getByRole('button', { name: '수업 시작', exact: true }).click();
  }
  if (startLesson) {
    const first = await firstPlaying(); result.first_playing = first;
    const originalId = first.lesson_record_id;
    if (spec.followup) {
      const f = spec.followup;
      await page.getByRole('button', { name: `${f.column}, ${f.row_index + 1}행: ${f.value}`, exact: true }).click();
      await page.getByLabel('강의 중 질문', { exact: true }).fill(f.question);
      await capture('interruption-before');
      const wasPlaying = await page.locator('audio').evaluate(a => !a.paused && a.currentTime > 0 && a.playbackRate === 1);
      if (!wasPlaying) throw Error('Original audio ended before interruption; do not claim a stop measurement');
      await page.getByRole('button', { name: '강의 멈추고 질문', exact: true }).click();
      await page.waitForFunction(() => window.__finishEvents.some(e => e.type === 'interruption_stopped'));
      await capture('interruption-stopped');
      await firstPlaying(1, true); await capture('supplement-playing');
      await page.waitForFunction(() => window.__finishEvents.some(e => e.type === 'lesson_resumed'), null, { timeout: 330000 });
      await page.waitForFunction(id => document.querySelector('.classroom')?.dataset.lessonRecordId === id,
        originalId, { timeout: 30000 });
      await page.waitForFunction(id => {
        const resume = window.__finishEvents.findLast(e => e.type === 'lesson_resumed' && e.lesson_record_id === id);
        return resume && window.__finishEvents.some(e => e.type === 'audio_playing' && e.lesson_record_id === id && e.at_ms > resume.at_ms);
      }, originalId, { timeout: 30000 });
      await capture('original-resumed');
    }
    await finishPlayback(originalId);
    result.status = Object.values(result.requirements).some(value => value === false) ? 'COMPLETED_WITH_REQUIREMENT_FAILURES' : 'COMPLETED_ACTUAL_JOURNEY_H_PENDING';
  } else result.status = 'EXPECTED_MISSING_CONDITION_STOP_NO_EXPLANATION';
} catch (error) {
  result.status = 'FAILED_NO_RETRY'; result.failure = String(error);
  await capture('failure').catch(() => {});
} finally {
  finishing = true;
  await Promise.allSettled([...pendingResponses]);
  result.events = await events().catch(() => []);
  result.native_media = await page.evaluate(() => window.__finishMedia).catch(() => []);
  result.scene_samples = await page.evaluate(() => window.__finishSceneSamples).catch(() => []);
  result.blob_bytes = await page.evaluate(async () => { await Promise.allSettled(window.__finishBlobTasks); return window.__finishBlobs; }).catch(() => ({}));
  result.final_text = await page.locator('body').innerText().catch(() => '');
  // Only cancel jobs submitted by this exact browser attempt. Never touch another job.
  result.owned_jobs = [];
  for (const jobId of ownedJobIds) {
    const job = await get('/jobs/' + jobId).catch(() => null);
    if (job && !terminal.has(job.state)) {
      await fetch(origin + '/api/jobs/' + jobId + '/cancel', { method: 'POST', headers });
      try { result.owned_jobs.push(await waitJob(jobId)); }
      catch (error) { result.errors.push('Owned job cancellation did not settle: ' + jobId + ': ' + String(error)); }
    } else if (job) result.owned_jobs.push(job);
  }
  result.after = await get('/resources/budget').catch(() => null);
  await Promise.allSettled([...pendingResponses]);
  result.events = await events().catch(() => []);
  result.native_media = await page.evaluate(() => window.__finishMedia).catch(() => []);
  result.scene_samples = await page.evaluate(() => window.__finishSceneSamples).catch(() => []);
  result.source_unchanged_at_end = JSON.stringify(frozen.source_hashes) === JSON.stringify(sources());
  if (!result.source_unchanged_at_end || result.errors.length || result.blocked_requests.length) {
    result.status = 'FAILED_EVIDENCE_INTEGRITY';
    result.failure = result.failure || 'Source changed, browser error, blocked request or owned cancellation did not settle';
  }
  result.completed_at = new Date().toISOString(); save();
  await context.close(); await browser.close();
  console.log(JSON.stringify({ id, version, status: result.status, failure: result.failure, counters: counts,
    source_unchanged_at_end: result.source_unchanged_at_end, artifact: relative(root, actualPath) }, null, 2));
  if (result.status.startsWith('FAILED') || result.status === 'COMPLETED_WITH_REQUIREMENT_FAILURES') process.exitCode = 1;
}
