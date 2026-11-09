// GET-only existing lessons, source photos and WAVs. No generation or retry.
// The coordinator runs this only after the final API/build is frozen.
import {createRequire} from 'node:module';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {dirname,resolve,relative} from 'node:path';
import assert from 'node:assert/strict';
import {installProbe} from './browser_probe.mjs';
import {replaySources} from './saved_replay_sources.mjs';
const base=dirname(fileURLToPath(import.meta.url)),root=resolve(base,'../../../..');
const require=createRequire(new URL('../../../../web/package.json',import.meta.url));
const {chromium}=require('@playwright/test');
const args=process.argv.slice(2),arg=name=>args.includes(name)?args[args.indexOf(name)+1]:null;
if(!args.includes('--run')||!arg('--out')||!arg('--deployment'))throw Error('Explicit --run --out --deployment required');
const out=resolve(root,arg('--out')),sources=replaySources(root,{manifest:arg('--source-manifest'),cases:arg('--cases')});
if(existsSync(resolve(out,'report.json')))throw Error('Never overwrite an earlier replay');
mkdirSync(out,{recursive:true});
const origin='http://127.0.0.1:8000',read=p=>JSON.parse(readFileSync(p,'utf8'));
const sha=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
const ledger=resolve(root,'runs/phase2/current/resource-budget.json'),policy=resolve(root,'.local/phase2-policy.json');
const deployment=read(resolve(root,arg('--deployment'))),lease=read(resolve(root,'.local/api-lease.json'));
const birth=typeof deployment.process_start==='number'?deployment.process_start:Date.parse(deployment.process_start)/1000;
assert(lease.pid===deployment.pid&&Math.abs(lease.process_start-birth)<.01,'API lease differs from frozen deployment');
const token=readFileSync(resolve(root,'.local/auth-token'),'utf8').trim();
const report={status:'RUNNING',at:new Date().toISOString(),deployment,lease,
 scope:'GET-only final-build replay of previously generated lessons/WAVs and saved photos. Not new question latency, new OCR, or independent quality evaluation.',
 model_calls:0,new_audio:0,ocr_calls:0,human_review:'H_PENDING',audio_seek_by_harness:false,playback_rate:1,
 before:{ledger:sha(ledger),policy:sha(policy)},source_manifest:arg('--source-manifest'),
 source_manifest_sha256:arg('--source-manifest')?sha(resolve(root,arg('--source-manifest'))):null,
 harness_sources:Object.fromEntries(['saved_replay.mjs','saved_replay_sources.mjs','browser_probe.mjs'].map(name=>[name,sha(resolve(base,name))])),
 cases:[],blocked:[],errors:[]};
const save=()=>writeFileSync(resolve(out,'report.json'),JSON.stringify(report,null,2));save();
async function get(path){const r=await fetch(origin+'/api'+path,{headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(15000)});assert(r.ok,`GET ${path}: ${r.status}`);return r.json();}
const active=await get('/jobs');assert(active.every(j=>['succeeded','failed','cancelled','interrupted','blocked','completed'].includes(j.state)),'Another job is active');
const browser=await chromium.launch({channel:'chrome',headless:true,ignoreDefaultArgs:['--mute-audio']});
const cdp=await browser.newBrowserCDPSession(),info=await cdp.send('SystemInfo.getProcessInfo');
const pid=info.processInfo.find(p=>p.type==='browser').id;
const processProof=JSON.parse(execFileSync(resolve(root,'.venv/Scripts/python.exe'),['-c','import psutil,sys,json;p=psutil.Process(int(sys.argv[1]));print(json.dumps({"pid":p.pid,"birth":p.create_time(),"argv":p.cmdline(),"ancestors":[x.pid for x in p.parents()]}))',String(pid)],{encoding:'utf8',windowsHide:true}));
assert(processProof.ancestors.includes(process.pid)&&!processProof.argv.includes('--mute-audio'));
report.browser_launch=processProof;await cdp.detach();
try{
 for(const source of sources){
  const {id,old,lessonId}=source;
  const entry={id,source:source.path,source_sha256:source.source_sha256,replay_role:source.role,
   lesson_id:lessonId,events:[],snapshots:[],errors:[]};
  report.cases.push(entry);save();
  const context=await browser.newContext({viewport:{width:1440,height:1100},serviceWorkers:'block'});
  await context.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());
   if(url.origin!==origin||request.method()!=='GET'){
    report.blocked.push({id,method:request.method(),path:url.pathname});save();await route.abort();
   }else await route.continue();
  });
  await context.addInitScript(session=>localStorage.setItem('edu-session',session),old.owned_session_id);
  const page=await context.newPage();page.setDefaultTimeout(15000);
  page.on('pageerror',e=>entry.errors.push(e.message));
  await installProbe(page);
  await page.addInitScript(()=>{
   window.__repairFrames=[];
   const frame=()=>{const a=document.querySelector('audio');if(a&&!a.paused&&a.duration>0)window.__repairFrames.push({
    at_ms:performance.now(),time:a.currentTime,duration:a.duration,lesson:a.dataset.lessonRecordId,step:a.dataset.stepId,epoch:Number(a.dataset.playbackEpoch),
    elements:[...document.querySelectorAll('[data-board-element]')].map(e=>e.dataset.boardElement),arrows:[...document.querySelectorAll('[data-board-arrow]')].map(e=>e.dataset.boardArrow)});
    requestAnimationFrame(frame);};requestAnimationFrame(frame);
  });
  const nav=async name=>{const menu=page.getByRole('button',{name:'메뉴 열기'});if(await menu.isVisible())await menu.click();await page.getByRole('navigation').getByRole('button',{name,exact:true}).click();};
  const capture=async label=>{const name=id+'-'+label+'.png';await page.screenshot({path:resolve(out,name),fullPage:true});entry.snapshots.push({label,screenshot:name,state:await page.evaluate(()=>window.__finishSnapshot())});save();};
  try{
   const lesson=lessonId?await get('/lessons/'+lessonId):null;entry.lesson=lesson;
   await page.goto(origin+(lessonId?'/?lesson='+lessonId:''));
   await page.getByRole('button',{name:'서버 연결 필요',exact:true}).click();
   await page.getByLabel('로컬 토큰 파일',{exact:true}).setInputFiles(resolve(root,'.local/auth-token'));
   await page.getByRole('button',{name:'로컬 연결됨',exact:true}).waitFor();
   if(lesson?.plan){
    assert(lesson.valid!==false,'Stored lesson was invalidated; do not regenerate');
    await page.locator('.classroom[data-replay-only="true"]').waitFor();
    await capture('before');
    await page.getByRole('button',{name:'저장된 수업 이어 재생',exact:true}).click();
    for(const step of lesson.plan.steps){
     await page.waitForFunction(({id,step})=>window.__finishEvents.some(e=>e.type==='audio_playing'&&e.lesson_record_id===id&&e.step_id===step),{id:lessonId,step:step.id},{timeout:45000});
     await capture('playing-'+step.id);
     await page.waitForFunction(({id,step})=>window.__finishEvents.some(e=>e.type==='audio_ended'&&e.lesson_record_id===id&&e.step_id===step),{id:lessonId,step:step.id},{timeout:50000});
    }
    const beforeCount=await page.evaluate(()=>window.__finishEvents.filter(e=>e.type==='audio_playing').length);
    await capture('completed');await nav('설정');await page.getByLabel('화면 글자 크기',{exact:true}).selectOption('2');await nav('강의실');
    await page.waitForTimeout(600);await capture('completed-remount');
    entry.no_completed_autoplay=(await page.evaluate(()=>window.__finishEvents.filter(e=>e.type==='audio_playing').length))===beforeCount;
    assert(entry.no_completed_autoplay,'Completed remount emitted a new playing event');
   }
   if(old.photo?.id){
    const photo=await get('/photos/'+old.photo.id);entry.saved_photo=photo;
    await nav('대화');await page.getByRole('button',{name:'문제 사진 첨부',exact:true}).click();
    await page.getByLabel('저장한 사진',{exact:true}).selectOption(photo.id);
    const dialog=page.getByRole('dialog');await dialog.locator('fieldset.photo-fields').waitFor();
    await dialog.getByText('표 · 읽지 못한 부분 · 누락 조건 편집',{exact:true}).click();
    const fields=[['문제 본문','question'],['SQL / 코드','sql'],['보기','choices'],['읽지 못한 부분','unreadable_regions'],['누락 조건','missing_conditions']];
    entry.photo_fields=[];
    for(const[label,key]of fields){const field=dialog.locator('fieldset.photo-fields label').filter({hasText:new RegExp('^\\s*'+label.replaceAll('/','\\/'))}).locator('textarea');assert.equal(await field.count(),1);const actual=await field.inputValue(),expected=Array.isArray(photo[key])?photo[key].join('\n'):photo[key]||'';assert.equal(actual,expected);entry.photo_fields.push({label,actual});}
    if(id==='J07'){entry.missing_condition_preserved=photo.missing_conditions.length>0;assert(entry.missing_condition_preserved);assert(await dialog.getByRole('button',{name:'확정한 문제 풀이',exact:true}).isDisabled());}
    if(lesson){entry.photo_lesson_revision_matches=lesson.original_problem?.source?.photo_id===photo.id&&lesson.original_problem?.revision===photo.revision;}
    await capture('saved-photo-current-revision');
   }
   entry.status='SAVED_REPLAY_CHECKED_H_PENDING';
  }catch(error){entry.status='FAILED_NO_RETRY';entry.errors.push(String(error));await capture('failure').catch(()=>{});}
  finally{
   await nav('설정').catch(()=>{});
   const data=await page.evaluate(async()=>{await Promise.allSettled(window.__finishBlobTasks);return{events:window.__finishEvents,native_media:window.__finishMedia,scene_samples:window.__finishSceneSamples,blob_bytes:window.__finishBlobs,frames:window.__repairFrames,snapshot_at_ms:performance.now()};}).catch(()=>null);
   if(data)Object.assign(entry,data);
   entry.timing_bounds=[];
   for(const step of entry.lesson?.plan?.steps||[])for(const[actionIndex,action]of step.board_actions.entries()){
    if(!['text','arrow'].includes(action.type))continue;
    const fraction=action.timing?.start??actionIndex/step.board_actions.length;if(fraction<=0||fraction>=1)continue;
    const samples=(entry.frames||[]).filter(f=>f.lesson===lessonId&&f.step===step.id);if(!samples.length)continue;
    const due=samples[0].duration*fraction,key=action.type==='arrow'?'arrows':'elements';
    const first=samples.find(f=>f[key].includes(action.element_id)),last=samples.filter(f=>!f[key].includes(action.element_id)).at(-1);
    const bound={step:step.id,element_id:action.element_id,type:action.type,due,first_visible:first?.time,last_absent:last?.time,
     delay_lower_ms:Math.max(0,((last?.time??0)-due)*1000),delay_upper_ms:first?(first.time-due)*1000:null,threshold_ms:75};
    entry.timing_bounds.push(bound);
   }
   entry.all_timed_actions_within_75ms=entry.timing_bounds.every(b=>b.delay_upper_ms!==null&&b.delay_upper_ms<=75);
   if(!entry.all_timed_actions_within_75ms)entry.status='TIMING_BOUND_FAILED_NO_RETRY';
   entry.source_unchanged=sha(source.path)===entry.source_sha256;
   if(!entry.source_unchanged)entry.status='SOURCE_CHANGED';
   await context.close();save();
  }
  console.log(JSON.stringify({id,status:entry.status,timing_bounds:entry.timing_bounds,errors:entry.errors}));
 }
}finally{
 report.after={ledger:sha(ledger),policy:sha(policy)};report.records_unchanged=JSON.stringify(report.before)===JSON.stringify(report.after);
 report.harness_unchanged=Object.entries(report.harness_sources).every(([name,hash])=>sha(resolve(base,name))===hash);
 report.status=report.records_unchanged&&report.harness_unchanged&&!report.blocked.length&&report.cases.every(c=>c.status==='SAVED_REPLAY_CHECKED_H_PENDING'&&!c.errors.length)?'PASS_SAVED_REPLAY_ONLY_H_PENDING':'FAILED_OR_INCOMPLETE';
 report.finished_at=new Date().toISOString();save();await browser.close();
 console.log(JSON.stringify({status:report.status,report:relative(root,resolve(out,'report.json'))}));
 if(report.status!=='PASS_SAVED_REPLAY_ONLY_H_PENDING')process.exitCode=1;
}
