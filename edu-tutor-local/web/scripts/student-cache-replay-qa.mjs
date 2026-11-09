// Actual existing WAVs at 1x; explicit replay controls only. Never synthesize.
// node scripts/student-cache-replay-qa.mjs --run [--roles A,BC,D-normal] [--base http://127.0.0.1:8000]
import { chromium } from '@playwright/test';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

const root=resolve(dirname(fileURLToPath(import.meta.url)), '../..');
let base='http://127.0.0.1:8000', roles=['A','BC','D-normal'], authorized=false;
for(let i=2;i<process.argv.length;i++) {
  if(process.argv[i]==='--run')authorized=true;
  else if(process.argv[i]==='--roles')roles=process.argv[++i].split(',');
  else if(process.argv[i]==='--base')base=process.argv[++i];
  else throw new Error('Unsupported argument');
}
if(!authorized)throw new Error('Explicit --run is required; syntax checking does not execute this harness.');
const origin=new URL(base);
if(origin.protocol!=='http:' || !['127.0.0.1','localhost','[::1]'].includes(origin.hostname))throw new Error('Local HTTP only');
base=origin.origin;
if(roles.some(x=>!['A','BC','D-normal'].includes(x)))throw new Error('Unsupported role');
const source=resolve(root,'runs/student-experience/20261027');
const output=resolve(root,'runs/student-latency/20261027/live-cache',new Date().toISOString().replace(/[:.]/g,'-'));
mkdirSync(output,{recursive:true});
const tokenFile=resolve(root,'.local/auth-token');
const token=readFileSync(tokenFile,'utf8').trim(); // Never logged or exported.
const read=path=>JSON.parse(readFileSync(path,'utf8'));
const sha=path=>createHash('sha256').update(readFileSync(path)).digest('hex');
const ledgerFile=resolve(root,'runs/phase2/current/resource-budget.json');
const policyFile=resolve(root,'.local/phase2-policy.json');
const report={started_at:new Date().toISOString(),scope:'GET-only actual stored lessons/WAVs, 1x natural ends; saved C replay, not a newly answered interruption',
  file_cache_condition:'Preflight SHA reads can warm the OS file cache; this is not a cold-disk or new-generation measurement.',
  human_listening_review:'NOT_RUN',human_education_review:'NOT_RUN',new_model_calls:0,new_tts:0,new_ocr:0,
  harness_audio_seek:false,harness_playback_acceleration:false,app_restore_seek:'Allowed only to resume the same saved B position; native seeking events retained',
  output,base,roles,api_reads:[],blocked_requests:[],page_errors:[],cases:[],errors:[]};
const save=()=>writeFileSync(resolve(output,'report.json'),JSON.stringify(report,null,2));
const dbSnapshot=()=>JSON.parse(execFileSync(resolve(root,'.venv/Scripts/python.exe'),['-c',
  'import sqlite3,json,hashlib,sys;from pathlib import Path;p=Path(sys.argv[1]);db=sqlite3.connect(p.as_uri()+"?mode=ro",uri=True);db.execute("PRAGMA query_only=ON");names=["sessions","messages","jobs","documents","chunks","photos","lessons","datasets","audit","evaluation_reviews"];out={};\nfor name in names:\n rows=db.execute("SELECT * FROM "+name+" ORDER BY id").fetchall();out[name]={"rows":len(rows),"sha256":hashlib.sha256(json.dumps(rows,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()}\nprint(json.dumps(out));db.close()',
  resolve(root,'.local/tutor.sqlite3')],{encoding:'utf8',env:{...process.env,PYTHONIOENCODING:'utf-8'}}));
const budgetSnapshot=()=>{const d=read(ledgerFile);return {sha256:sha(ledgerFile),requests:d.requests.length,seconds:d.requests.reduce((s,r)=>s+r.charged_seconds,0),audio:d.requests.reduce((s,r)=>s+r.new_audio_clips,0),vision:d.requests.reduce((s,r)=>s+r.vision_requests,0)};};
async function get(path) {
  if(!/^\/(?:lessons\/[a-f0-9]{32}|jobs|resources\/budget)$/.test(path))throw new Error('Disallowed read endpoint');
  const response=await fetch(base+'/api'+path,{headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(15000)});
  report.api_reads.push({method:'GET',path,status:response.status,at:new Date().toISOString(),via:'preflight'});
  if(!response.ok)throw new Error(`GET ${path} returned ${response.status}`);
  return response.json();
}
function discover(name) {
  const caseName={A:'A-final',BC:'BC-voicefix','D-normal':'D-normal-lesson'}[name];
  const path=resolve(source,'cases',caseName+'.json'),record=read(path);
  const first=record.playback.find(p=>!p.event?.supplement);
  const supplement=record.playback.find(p=>p.event?.supplement);
  assert(first && /^[a-f0-9]{32}$/.test(first.lesson_id));
  if(name==='BC')assert(supplement && /^[a-f0-9]{32}$/.test(supplement.lesson_id));
  return {role:name,caseName,path,source_sha256:sha(path),record,id:first.lesson_id,supplementId:supplement?.lesson_id};
}
async function pageState(page,label) {
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  return page.evaluate(label=>{
    const classroom=document.querySelector('.classroom'),board=document.querySelector('.chalk-board'),audio=document.querySelector('.classroom audio');
    const selected=document.querySelector('.board-cell-button[aria-pressed="true"]')?.closest('[data-cell-id]');
    const pointer=document.querySelector('[data-testid="avatar-pointer"]');
    const r=n=>n?.getBoundingClientRect().toJSON()||null;
    const cell=r(selected),matrix=pointer?.getScreenCTM();
    const point=pointer&&matrix?new DOMPoint(Number(pointer.getAttribute('x2')),Number(pointer.getAttribute('y2'))).matrixTransform(matrix):null;
    const viewport=selected?.closest('.table-scroll'),v=r(viewport);
    return {label,at_ms:performance.now(),lesson_id:classroom?.dataset.lessonRecordId,step_id:classroom?.dataset.stepId,
      replay_only:classroom?.dataset.replayOnly,board_text:board?.innerText,board_html:board?.outerHTML,
      speech_text:document.querySelector('.caption-box')?.textContent||null,selected_cell_id:selected?.dataset.cellId||null,
      selected_cell_text:selected?.textContent||null,cell_rect:cell,table_viewport_rect:v,
      selected_center_visible:cell&&v?cell.x+cell.width/2>=v.left&&cell.x+cell.width/2<=v.right&&cell.y+cell.height/2>=v.top&&cell.y+cell.height/2<=v.bottom:null,
      pointer_endpoint:point?{x:point.x,y:point.y}:null,pointer_cell_distance_px:point&&cell?Math.hypot(point.x-cell.x-cell.width/2,point.y-cell.y-cell.height/2):null,
      character:document.querySelector('.avatar')?.outerHTML||null,
      audio:audio?{currentTime:audio.currentTime,duration:audio.duration,paused:audio.paused,playbackRate:audio.playbackRate,step:audio.dataset.stepId}:null,
      document_width:document.documentElement.scrollWidth,viewport_width:innerWidth};
  },label);
}
async function capture(page,entry,label) {
  const state=await pageState(page,label),file=resolve(output,entry.role+'-'+label+'.png');
  await page.screenshot({path:file});entry.snapshots.push({...state,screenshot:file});save();return state;
}
async function events(page) {return page.evaluate(()=>({lesson:window.__savedLessonEvents,media:window.__savedMediaEvents,ui:window.__savedUiEvents}));}
async function waitEvent(page,type,lesson,step,after=0,timeout=45000) {
  await page.waitForFunction(({type,lesson,step,after})=>window.__savedLessonEvents.some(e=>e.type===type&&e.lesson_record_id===lesson&&(!step||e.step_id===step)&&e.at_ms>=after),{type,lesson,step,after},{timeout});
  return page.evaluate(({type,lesson,step,after})=>window.__savedLessonEvents.find(e=>e.type===type&&e.lesson_record_id===lesson&&(!step||e.step_id===step)&&e.at_ms>=after),{type,lesson,step,after});
}
function metrics(record) {
  const ev=record.events.lesson,ui=record.events.ui,media=record.events.media;
  const clicks=ui.filter(x=>x.type==='button_clicked');
  const first=clicks.map(click=>{const next=ev.find(e=>e.type==='audio_playing'&&e.at_ms>=click.at_ms);return {button:click.label,click_at_ms:click.at_ms,first_lesson_id:next?.lesson_record_id,first_step_id:next?.step_id,seconds:next?(next.at_ms-click.at_ms)/1000:null,clock:'same page performance.now'};});
  const ranges=ev.filter(e=>['cache_manifest_end','audio_fetch_end','audio_decode_end'].includes(e.type)).map(e=>({type:e.type,lesson_id:e.lesson_record_id,step_id:e.step_id,prefetch:!!e.prefetch,elapsed_ms:e.elapsed_ms,at_ms:e.at_ms,overlaps_other_spans:true}));
  const gaps=[];
  for(let i=0;i<ev.length;i++)if(ev[i].type==='audio_ended') {
    const a=ev[i],b=ev.slice(i+1).find(x=>x.type==='audio_playing');
    if(b)gaps.push({from_lesson_id:a.lesson_record_id,from_step_id:a.step_id,to_lesson_id:b.lesson_record_id,to_step_id:b.step_id,seconds:(b.at_ms-a.at_ms)/1000,clock:'same page performance.now'});
  }
  return {button_to_playing:first,manifest_fetch_decode:ranges,ended_to_next_playing:gaps,
    rates:media.filter(x=>x.type==='playing'||x.type==='ratechange').map(x=>x.playback_rate),
    boundary:'Stored replay only. Spans overlap during playback/prefetch/decode; never sum as new-question latency. No new synthesis performance measured.'};
}
let browser;
try {
  report.before={budget:budgetSnapshot(),policy_sha256:sha(policyFile),database:dbSnapshot()};save();
  const active=await get('/jobs');
  const jobs=Array.isArray(active)?active:active.jobs||[];
  if(jobs.some(j=>!['succeeded','failed','cancelled','interrupted','blocked'].includes(j.state)))throw new Error('Active app job found; read-only replay deferred');
  browser=await chromium.launch({channel:'chrome',headless:true});
  for(const role of roles) {
    const item=discover(role),lesson=await get('/lessons/'+item.id),supplement=item.supplementId?await get('/lessons/'+item.supplementId):null;
    const entry={role,source_case:item.caseName,source_path:item.path,source_sha256:item.source_sha256,lesson_id:item.id,supplement_id:item.supplementId||null,
      original_question:lesson.plan.question_text,original_problem:lesson.original_problem||lesson.problem,original_plan:lesson.plan,
      original_audio_steps:lesson.audio_steps,supplement_plan:supplement?.plan||null,supplement_audio_steps:supplement?.audio_steps||null,
      snapshots:[],expected_steps:lesson.plan.steps.map(s=>s.id),natural_end_events:[],status:'RUNNING'};
    report.cases.push(entry);save();
    for(const record of [lesson,...(supplement?[supplement]:[])]) for(const step of record.plan.steps) {
      const clip=record.audio_steps?.find(x=>x.step_id===step.id);assert(clip?.audio_id,'No cached clip; no synthesis fallback permitted');
      const wav=resolve(root,'.local/audio',clip.audio_id+'.wav');assert(sha(wav)===clip.checksum,'WAV hash differs from stored clip');
    }
    const context=await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block'});
    await context.route('**/*',async route=>{
      const request=route.request(),url=new URL(request.url());
      const external=url.protocol.startsWith('http')&&url.origin!==base;
      if(external||(url.pathname.startsWith('/api/')&&request.method()!=='GET')) {
        report.blocked_requests.push({role,method:request.method(),path:url.pathname,reason:external?'external':'non_GET_API'});save();await route.abort('blockedbyclient');
      } else await route.continue();
    });
    await context.addInitScript(()=>{
      window.__savedLessonEvents=[];window.__savedMediaEvents=[];window.__savedUiEvents=[];
      window.addEventListener('edu:lesson',e=>window.__savedLessonEvents.push(e.detail));
      document.addEventListener('click',e=>{const b=e.target.closest('button');if(b&&['저장된 수업 이어 재생','저장된 보충 설명 듣기'].includes(b.textContent.trim()))window.__savedUiEvents.push({type:'button_clicked',label:b.textContent.trim(),at_ms:performance.now()});},true);
      for(const kind of ['loadedmetadata','playing','pause','ended','seeking','seeked','ratechange','error'])document.addEventListener(kind,e=>{
        if(!(e.target instanceof HTMLAudioElement))return;const a=e.target;
        window.__savedMediaEvents.push({type:kind,at_ms:performance.now(),step_id:a.dataset.stepId,lesson_id:a.closest('.classroom')?.dataset.lessonRecordId,
          current_time:a.currentTime,duration:Number.isFinite(a.duration)?a.duration:null,playback_rate:a.playbackRate,paused:a.paused,error_code:a.error?.code||null});
      },true);
    });
    const page=await context.newPage();
    page.on('pageerror',e=>report.page_errors.push({role,message:e.message}));
    page.on('response',response=>{const u=new URL(response.url());if(u.pathname.startsWith('/api/'))report.api_reads.push({role,method:response.request().method(),path:u.pathname+u.search,status:response.status(),via:'browser'});});
    try {
      const query='?lesson='+item.id+(item.supplementId?'&supplement='+item.supplementId:'');
      entry.url=base+'/'+query;await page.goto(entry.url);
      await page.getByRole('button',{name:'서버 연결 필요',exact:true}).click();
      await page.getByLabel('로컬 토큰 파일',{exact:true}).setInputFiles(tokenFile);
      await page.getByRole('button',{name:'로컬 연결됨',exact:true}).waitFor({timeout:30000});
      await page.locator(`.classroom[data-lesson-record-id="${item.id}"][data-replay-only="true"]`).waitFor({timeout:15000});
      assert((await page.locator('.classroom').innerText()).includes('저장된 수업 재생'));
      await capture(page,entry,'before-play');
      await page.getByRole('button',{name:'저장된 수업 이어 재생',exact:true}).click();
      const first=await waitEvent(page,'audio_playing',item.id,entry.expected_steps[0]);
      await capture(page,entry,'first-playing');
      console.log(JSON.stringify({phase:'playing',role,step:entry.expected_steps[0]}));
      if(role==='BC') {
        const table=lesson.plan.steps[0].board_actions.find(a=>a.type==='table'&&a.columns.some(c=>(typeof c==='string'?c:c.name)==='attended'));
        assert(table,'Original attended table missing');const col=table.columns.findIndex(c=>(typeof c==='string'?c:c.name)==='attended');
        assert(table.rows[0][col]===1);const cellId=table.cell_ids[0][col];
        const cell=page.locator(`[data-cell-id="${cellId}"] .board-cell-button`);await cell.waitFor({state:'visible',timeout:5000});
        await page.waitForFunction(()=>document.querySelector('.classroom audio')?.currentTime>0.35,null,{timeout:5000});
        await cell.click();const before=await capture(page,entry,'B-selected-before-stored-C');
        assert(before.selected_cell_id===cellId && before.audio.currentTime>0 && before.audio.playbackRate===1);
        assert(before.pointer_cell_distance_px!==null && before.pointer_cell_distance_px<=2 && before.selected_center_visible);
        await page.getByRole('button',{name:'저장된 보충 설명 듣기',exact:true}).click();
        const requested=await waitEvent(page,'saved_supplement_requested',item.id,entry.expected_steps[0],first.at_ms);
        await waitEvent(page,'audio_playing',item.supplementId,supplement.plan.steps[0].id,requested.at_ms);
        await capture(page,entry,'stored-C-playing');
        const cEnd=await waitEvent(page,'audio_ended',item.supplementId,supplement.plan.steps[0].id,requested.at_ms,45000);
        entry.natural_end_events.push(cEnd);console.log(JSON.stringify({phase:'natural_ended',role:'stored-C',step:cEnd.step_id}));
        const resumed=await waitEvent(page,'lesson_resumed',item.id,null,cEnd.at_ms,15000);
        const again=await waitEvent(page,'audio_playing',item.id,entry.expected_steps[0],resumed.at_ms,15000);
        const after=await capture(page,entry,'B-restored-after-C');
        assert(resumed.selected_cell_id===cellId && after.selected_cell_id===cellId);
        assert(Math.abs(resumed.audio_position-requested.audio_position)<=0.05);
        assert(after.audio.currentTime>=requested.audio_position-0.05 && after.audio.currentTime<=requested.audio_position+1.5);
        assert(after.pointer_cell_distance_px!==null && after.pointer_cell_distance_px<=2 && after.selected_center_visible);
        entry.saved_supplement_restore={requested,resumed,playing:again,selected_cell_id:cellId,restored_position_matches:true,selected_cell_matches:true};
      }
      for(const step of lesson.plan.steps) {
        const ended=await waitEvent(page,'audio_ended',item.id,step.id,first.at_ms,50000);
        entry.natural_end_events.push(ended);entry.events=await events(page);save();
        console.log(JSON.stringify({phase:'natural_ended',role,step:step.id}));
      }
      await capture(page,entry,'natural-completion');entry.events=await events(page);entry.metrics=metrics(entry);
      assert(entry.metrics.rates.every(rate=>rate===1),'Playback rate changed');
      assert(!entry.events.media.some(e=>e.type==='error'),'Media error');
      entry.status='PASS_STORED_REPLAY_SCOPE';
    } catch(error) {
      entry.status='FAILED';entry.error=error.message;entry.events=await events(page).catch(()=>null);
      await capture(page,entry,'failure').catch(()=>{});throw error;
    } finally {await context.close();save();}
  }
  report.after={budget:budgetSnapshot(),policy_sha256:sha(policyFile),database:dbSnapshot()};
  report.preservation={budget_unchanged:JSON.stringify(report.before.budget)===JSON.stringify(report.after.budget),policy_unchanged:report.before.policy_sha256===report.after.policy_sha256,database_unchanged:JSON.stringify(report.before.database)===JSON.stringify(report.after.database),source_case_hashes_unchanged:report.cases.every(c=>sha(c.source_path)===c.source_sha256)};
  assert(Object.values(report.preservation).every(Boolean),'Production state changed');
  assert(report.blocked_requests.length===0,'Non-GET or external request attempted');
  assert(report.page_errors.length===0,'Page execution error');
  report.status='PASS_ACTUAL_STORED_WAV_REPLAY_NOT_NEW_GENERATION';
} catch(error) {report.errors.push(error.stack||String(error));report.status='FAILED';}
finally {
  if(browser)await browser.close();
  if(!report.after)report.after={budget:budgetSnapshot(),policy_sha256:sha(policyFile),database:dbSnapshot()};
  report.completed_at=new Date().toISOString();save();
}
console.log(JSON.stringify({status:report.status,output,cases:report.cases.map(c=>({role:c.role,status:c.status})),blocked_requests:report.blocked_requests.length,errors:report.errors}));
if(report.status==='FAILED')process.exitCode=1;
