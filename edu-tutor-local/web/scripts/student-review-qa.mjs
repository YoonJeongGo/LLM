// Isolated browser UI checks. Synthetic reviewer, never human quality evidence.
import { chromium } from '@playwright/test';
import { readFileSync, writeFileSync, mkdirSync, readdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';

const root = resolve('..');
const folder = resolve(root, 'runs/student-experience/20261027');
const out = resolve(root, 'runs/student-latency/20261027');
mkdirSync(out, { recursive: true });
const url = pathToFileURL(resolve(folder, 'index.html')).href;
const key = 'edu-tutor.local-evidence-review.v1';
const digest = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const protectedFiles = [resolve(root, 'runs/phase2/current/resource-budget.json'), resolve(root, '.local/phase2-policy.json'),
  ...['cases', 'audio'].flatMap(dir => readdirSync(resolve(folder, dir)).map(name => resolve(folder, dir, name)))];
const before = Object.fromEntries(protectedFiles.map(path => [path, digest(path)]));
const report = { started_at: new Date().toISOString(), scope: 'Isolated local-file UI control tests with original WAV metadata/playback; synthetic reviewer; not human education/listening review',
  new_model_calls: 0, new_tts: 0, new_ocr: 0, production_db_writes: 0, human_review: 'H_PENDING', checks: [], external_requests: [], errors: [], screenshots: [] };
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const check = (name, value = true) => { assert(value, name); report.checks.push(name); };
const envelope = records => ({ schema_version: 1, scope: 'local_self_records_not_global_approval', exported_at: new Date().toISOString(), records });

async function contextPage(options = {}) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, acceptDownloads: true });
  if (options.init) await context.addInitScript(options.init, { key });
  await context.route(/^https?:/, route => { report.external_requests.push(route.request().url()); return route.abort(); });
  const page = await context.newPage();
  page.on('console', message => { if(message.type()==='error') (report.console_errors ??= []).push(message.text()); });
  page.on('pageerror', e => report.errors.push(e.message));
  await page.goto(url);
  await page.locator('#review-notice').filter({ hasText: /검토|저장소/ }).waitFor();
  return { context, page };
}

async function importText(page, text, name = 'review-fixture.json') {
  await page.locator('#review-import').setInputFiles({ name, mimeType: 'application/json', buffer: Buffer.from(text) });
  await page.waitForFunction(() => document.querySelector('#review-import').value === '');
}

async function fillMinimal(page) {
  const form = page.locator('#A-final .review-form').first();
  await form.locator('..').locator('summary').click();
  await form.locator('[name=reviewer]').fill('자동 UI 검사, 인간 검토 아님');
  return form;
}

try {
  const { context, page } = await contextPage();
  check('default zero records', await page.locator('#review-count').textContent() === '0');
  check('all review states default unreviewed', await page.locator('.review-form [name=review_status]').evaluateAll(nodes => nodes.every(n => n.value === '미검토')));
  check('heard utterances are never prefilled from planned speech', await page.locator('[name=heard_utterance]').evaluateAll(nodes => nodes.every(n => n.value === '')));
  check('H_PENDING stays visible', await page.locator('#human-review').innerText().then(t => t.includes('H_PENDING')));
  const replay = await page.locator('#BC-voicefix .app-replay-link').getAttribute('href');
  check('B replay links exact stored C supplement', replay === 'http://127.0.0.1:8000/?lesson=7d1851b54e8e4eb3b4838ae8ddfe3dbf&supplement=7ef3d4a25fee409e8310bde69995f48c');
  check('app links only explicit localhost navigation', await page.locator('.app-replay-link').evaluateAll(nodes => nodes.every(n => n.href.startsWith('http://127.0.0.1:8000/?lesson='))));
  check('B s2 static completed board keeps previous original table', await page.locator('#BC-voicefix .subcard').evaluateAll(nodes => {
    const target = nodes.find(n => { const f=n.querySelector('form.review-form'); if(!f)return false; const c=JSON.parse(f.dataset.reviewTarget); return c.lesson_id==='7d1851b54e8e4eb3b4838ae8ddfe3dbf' && c.step_id==='s2'; });
    return target?.querySelectorAll('.board-preview table').length === 3;
  }));
  check('cropped picture permits non-audio record without invented clip', await page.locator('#D-cut-review .review-form').evaluate(form => { const c=JSON.parse(form.dataset.reviewTarget); return c.audio_id===null && c.step_id===null && !form.querySelector('[data-read-offset]'); }));
  const form = await fillMinimal(page);
  await form.locator('[name=review_status]').selectOption({ label: '수정 필요' });
  await form.locator('[name=issue_kind]').selectOption({ label: '판서 불일치' });
  await form.locator('[name=heard_utterance]').fill('자동 UI 검사 문자열: <img src=x onerror="window.__reviewXSS=1">');
  await form.locator('[name=comment]').fill('이 기록은 제어 테스트이며 실제 교육·청취 판단이 아닙니다.');
  await form.locator('button[type=submit]').click();
  check('reviewed audio requires explicit current offset', await page.locator('#review-count').textContent() === '0');
  check('missing offset explains action', await form.locator('.review-feedback').textContent().then(t => t.includes('현재 음성 위치')));
  const media = await page.locator('#A-final audio').first().evaluate(async audio => {
    if(audio.readyState < 1) await new Promise((resolve,reject) => { audio.addEventListener('loadedmetadata',resolve,{once:true}); audio.addEventListener('error',reject,{once:true}); audio.load(); });
    await audio.play(); await new Promise(resolve=>setTimeout(resolve,350)); audio.pause();
    return { duration: audio.duration, currentTime: audio.currentTime, readyState: audio.readyState };
  });
  report.original_wav_sample = media;
  check('original WAV native metadata and sample playback', media.duration === 12.96 && media.currentTime > 0 && media.readyState >= 1);
  await form.locator('[data-read-offset]').click();
  const offset = Number(await form.locator('[name=audio_offset_seconds]').inputValue());
  check('offset button reads original audio currentTime', Math.abs(offset-media.currentTime)<0.002);
  await form.locator('button[type=submit]').click();
  check('explicit save appends one self-record', await page.locator('#review-count').textContent() === '1');
  const downloaded = page.waitForEvent('download');
  await page.locator('#review-export').click();
  const file = await downloaded;
  report.download_failure = await file.failure();
  const downloadPath = resolve(out, 'review-qa-synthetic-records.json');
  await file.saveAs(downloadPath);
  const saved = JSON.parse(readFileSync(downloadPath, 'utf8'));
  check('download identifies synthetic reviewer and original SHA', saved.records.length===1 && saved.records[0].reviewer==='자동 UI 검사, 인간 검토 아님' && saved.records[0].audio_sha256==='87e2f118475504aeffd61bbf79a6e3a4273529869a1ff7193f3f4c4085b08d6c');
  check('no H_PASS emitted by self-record', !JSON.stringify(saved).includes('H_PASS'));
  await page.reload();
  check('browser-local record survives reload in isolated profile', await page.locator('#review-count').textContent() === '1');
  check('XSS-shaped heard text remains text', await page.evaluate(() => window.__reviewXSS===undefined && document.querySelectorAll('#review-records img').length===0));
  await importText(page, JSON.stringify(saved));
  check('duplicate review ID appended rather than overwriting', await page.locator('#review-count').textContent()==='2');
  check('duplicate ID preservation notice', (await page.locator('#review-records').textContent()).includes('덮어쓰지 않고'));
  const incorrectSha = structuredClone(saved.records[0]); incorrectSha.audio_sha256='0'.repeat(64);
  await importText(page, JSON.stringify(envelope([incorrectSha])));
  check('wrong source SHA rejected atomically', await page.locator('#review-count').textContent()==='2' && (await page.locator('#review-notice').textContent()).includes('SHA'));
  const badStatus=structuredClone(saved.records[0]); badStatus.review_status='H_PASS';
  await importText(page, JSON.stringify(envelope([badStatus])));
  check('global approval status rejected', await page.locator('#review-count').textContent()==='2');
  const badOffset=structuredClone(saved.records[0]); badOffset.audio_offset_seconds=100000;
  await importText(page, JSON.stringify(envelope([badOffset])));
  check('offset outside original WAV rejected', await page.locator('#review-count').textContent()==='2' && (await page.locator('#review-notice').textContent()).includes('WAV'));
  await importText(page, JSON.stringify(envelope(Array(501).fill(saved.records[0]))));
  check('record-count limit enforced without mutation', await page.locator('#review-count').textContent()==='2');
  await importText(page, ' '.repeat(2*1024*1024+1));
  check('2MB import size limit enforced before parse', (await page.locator('#review-notice').textContent()).includes('2MB') && await page.locator('#review-count').textContent()==='2');
  await importText(page, '{not json}');
  check('invalid JSON preserves existing records', await page.locator('#review-count').textContent()==='2');
  for (const [width,scale] of [[1440,1],[390,1],[390,2]]) {
    await page.setViewportSize({width,height:1100});
    await page.evaluate(scale=>document.body.style.fontSize=(16*scale)+'px',scale);
    for (const id of ['human-review','A-final']) {
      await page.locator('#'+id).evaluate(el=>el.scrollIntoView());
      const path=resolve(out,`review-${id}-${width}-${scale}x.png`);
      await page.screenshot({path}); report.screenshots.push(path);
      check(`no page overflow ${id} ${width} ${scale}x`, await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    }
    const unit=page.locator('#A-final .subcard').first();
    await unit.locator('details.review-entry').evaluate(el=>el.open=true);
    const unitPath=resolve(out,`review-audio-board-form-${width}-${scale}x.png`);
    await unit.screenshot({path:unitPath}); report.screenshots.push(unitPath);
  }
  await context.close();

  const unavailable=await contextPage({init:()=>{ Storage.prototype.setItem=function(){throw new DOMException('Test storage unavailable','SecurityError');}; }});
  const fallbackForm=await fillMinimal(unavailable.page);
  await fallbackForm.locator('button[type=submit]').click();
  check('storage unavailable keeps memory record and explicit export notice', await unavailable.page.locator('#review-count').textContent()==='1' && (await fallbackForm.locator('.review-feedback').textContent()).includes('반드시 JSON'));
  await unavailable.context.close();

  const corrupt=await contextPage({init:({key})=>localStorage.setItem(key,'{"old-unreadable":"keep"}')});
  const corruptForm=await fillMinimal(corrupt.page);
  await corruptForm.locator('button[type=submit]').click();
  check('unreadable prior storage never overwritten', await corrupt.page.evaluate(key=>localStorage.getItem(key),key)==='{"old-unreadable":"keep"}');
  await corrupt.context.close();
  check('no HTTP/API/external request attempted', report.external_requests.length===0);
  check('no page execution errors', report.errors.length===0);
  check('source cases WAV metadata budget and policy unchanged', protectedFiles.every(path=>digest(path)===before[path]));
  report.status='PASS_AUTOMATED_REVIEW_CONTROLS_NOT_HUMAN_REVIEW';
} catch(error) { report.errors.push(error.stack||String(error)); report.status='FAILED'; }
finally {
  await browser.close();
  report.completed_at=new Date().toISOString();
  writeFileSync(resolve(out,'review-ui-qa.json'),JSON.stringify(report,null,2));
}
console.log(JSON.stringify({status:report.status,checks:report.checks.length,errors:report.errors,external_requests:report.external_requests}));
if(report.status==='FAILED')process.exitCode=1;
