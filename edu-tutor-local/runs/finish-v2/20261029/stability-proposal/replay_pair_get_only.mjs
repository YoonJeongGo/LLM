// Two stored first clips + one transition each, one Chrome context, GET only.
// Full URL reload between lessons. Not two fresh questions in one React tree.
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, existsSync, mkdirSync, realpathSync } from 'node:fs';
import { dirname, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import assert from 'node:assert/strict';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../../..');
const require=createRequire(resolve(root,'web/package.json'));
const {chromium}=require('@playwright/test');
const args=process.argv.slice(2),arg=k=>args[args.indexOf(k)+1];
assert(args.includes('--run'),'Explicit coordinator GO and --run required');
const version=arg('--version'), expectedPid=Number(arg('--api-pid'));
assert(/^[A-Za-z0-9_-]{1,60}$/.test(version)&&Number.isInteger(expectedPid)&&expectedPid>0);
const out=resolve(root,arg('--output'));
assert(out.startsWith(resolve(root,'runs')+sep)&&!existsSync(out));
assert(realpathSync(dirname(out)).startsWith(realpathSync(root)+sep));
const read=p=>JSON.parse(readFileSync(p,'utf8'));
const hash=b=>createHash('sha256').update(b).digest('hex');
const sha=p=>hash(readFileSync(p));
const base=resolve(root,'runs/finish-v2/20261029/student',version);
const frozen=read(resolve(base,'execution-version.json'));
for(const [name,digest] of Object.entries(frozen.source_hashes))assert.equal(existsSync(resolve(root,name))?sha(resolve(root,name)):null,digest,name);
const lease=read(resolve(root,'.local/api-lease.json'));assert.equal(lease.pid,expectedPid);assert.equal(lease.state,'held');
const token=readFileSync(resolve(root,'.local/auth-token'),'utf8').trim();
const origin='http://127.0.0.1:8000';
const terminal=new Set(['succeeded','failed','cancelled','interrupted','blocked']);
const get=async p=>{const r=await fetch(origin+'/api'+p,{headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(10000)});assert(r.ok,p+':'+r.status);return r.json();};
assert((await get('/jobs')).every(j=>terminal.has(j.state)),'A model job is active; preserve the ledger comparison');
mkdirSync(out);
const ledger=resolve(root,'runs/phase2/current/resource-budget.json');
const report={status:'RUNNING',started_at:new Date().toISOString(),version,api_before:lease,
  scope:'Two stored first clips and next-stage onset, one Chrome context, URL reload/re-auth between lessons. No fresh questions or same-React-instance claim.',
  human_review:'H_PENDING',new_model_calls:0,new_TTS:0,new_OCR:0,requests:[],blocked:[],errors:[],cases:[],
  budget_before_sha256:sha(ledger),file_cache_notice:'Preflight WAV hashes can warm the OS cache; not cold disk or synthesis timing.'};
const save=()=>writeFileSync(resolve(out,'result.json'),JSON.stringify(report,null,2));save();
let browser,context;
const started=Date.now();
try{
  browser=await chromium.launch({channel:'chrome',headless:true,ignoreDefaultArgs:['--mute-audio']});
  const cdp=await browser.newBrowserCDPSession();
  const processes=await cdp.send('SystemInfo.getProcessInfo');
  const pid=processes.processInfo.find(p=>p.type==='browser').id;
  const owned=JSON.parse(execFileSync(resolve(root,'.venv/Scripts/python.exe'),['-c',
    'import psutil,sys,json;p=psutil.Process(int(sys.argv[1]));print(json.dumps({"pid":p.pid,"birth":p.create_time(),"argv":p.cmdline(),"ancestors":[x.pid for x in p.parents()]}))',String(pid)],{encoding:'utf8',windowsHide:true}));
  assert(owned.ancestors.includes(process.pid)&&!owned.argv.includes('--mute-audio'));
  report.browser={...owned,actual_arguments:owned.argv,contexts_created:1,headless:true};
  await cdp.detach();
  context=await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block'});
  await context.route('**/*',async route=>{
    const q=route.request(),u=new URL(q.url());
    const row={method:q.method(),path:u.pathname,at:new Date().toISOString()};
    if(u.origin!==origin||q.method()!=='GET') {report.blocked.push(row);save();await route.abort('blockedbyclient');}
    else {report.requests.push(row);await route.continue();}
  });
  await context.addInitScript(()=>{
    window.__replayNative=[];window.__replayEvents=[];window.__replayBlobs={};window.__replayTasks=[];
    const original=URL.createObjectURL.bind(URL);
    URL.createObjectURL=blob=>{const url=original(blob);if(blob instanceof Blob)window.__replayTasks.push(blob.arrayBuffer().then(async bytes=>{
      const digest=await crypto.subtle.digest('SHA-256',bytes);window.__replayBlobs[url]=[...new Uint8Array(digest)].map(v=>v.toString(16).padStart(2,'0')).join('');
    }));return url;};
    window.addEventListener('edu:lesson',e=>window.__replayEvents.push(e.detail));
    for(const type of ['playing','pause','ended','seeking','seeked','ratechange','error'])document.addEventListener(type,event=>{
      const a=event.target;if(!(a instanceof HTMLAudioElement))return;
      window.__replayNative.push({type,at_ms:performance.now(),lesson_id:a.dataset.lessonRecordId,step_id:a.dataset.stepId,
        epoch:a.dataset.playbackEpoch,src:a.currentSrc||a.src,currentTime:a.currentTime,duration:a.duration,
        muted:a.muted,volume:a.volume,playbackRate:a.playbackRate,error:a.error?.code||null});
    },true);
  });
  const page=await context.newPage();page.on('pageerror',e=>report.errors.push(String(e)));
  for(const id of ['J01','J03']){
    assert(Date.now()-started<100000,'Two-minute bounded replay limit');
    const actual=read(resolve(base,id,'actual.json'));
    assert(actual.completed_at&&actual.source_unchanged_at_end===true&&actual.status==='COMPLETED_ACTUAL_JOURNEY_H_PENDING');
    const lessonId=actual.first_playing.lesson_record_id;
    const lesson=await get('/lessons/'+lessonId),manifest=await get('/lessons/'+lessonId+'/speech?voice=default');
    const clips={};
    for(const step of lesson.plan.steps){
      const clip=manifest.steps.find(a=>a.step_id===step.id);
      assert(clip?.provider==='windows_sapi_local'&&clip.voice.includes('HEAMI')&&/^[a-f0-9]{64}$/.test(clip.audio_id));
      assert.equal(sha(resolve(root,'.local/audio',clip.audio_id+'.wav')),clip.checksum);clips[step.id]=clip;
    }
    const entry={id,lesson_id:lessonId,question:lesson.plan.question_text,plan:lesson.plan,cached_clips:clips,
      source_actual_sha256:sha(resolve(base,id,'actual.json')),url:origin+'/?lesson='+lessonId};report.cases.push(entry);save();
    await page.goto(entry.url,{timeout:15000});
    await page.getByRole('button',{name:'서버 연결 필요',exact:true}).click();
    await page.getByLabel('로컬 토큰 파일',{exact:true}).setInputFiles(resolve(root,'.local/auth-token'));
    await page.getByRole('button',{name:'로컬 연결됨',exact:true}).waitFor({timeout:10000});
    await page.locator(`.classroom[data-lesson-record-id="${lessonId}"][data-replay-only="true"]`).waitFor();
    entry.click_at_ms=await page.evaluate(()=>performance.now());
    await page.getByRole('button',{name:'저장된 수업 이어 재생',exact:true}).click();
    const first=lesson.plan.steps[0].id,second=lesson.plan.steps[1]?.id;
    await page.waitForFunction(step=>window.__replayNative.some(e=>e.type==='playing'&&e.step_id===step),first,{timeout:10000});
    await page.waitForFunction(()=>document.querySelector('.classroom audio')?.currentTime>=.4,null,{timeout:5000});
    entry.dom=await page.evaluate(()=>({lesson_id:document.querySelector('.classroom')?.dataset.lessonRecordId,
      step_id:document.querySelector('.classroom')?.dataset.stepId,caption:document.querySelector('.caption-box p')?.textContent,
      board:document.querySelector('.chalk-board')?.innerText,gesture:document.querySelector('[data-gesture]')?.getAttribute('data-gesture')}));
    entry.screenshot=resolve(out,id+'-playing.png');await page.screenshot({path:entry.screenshot});
    await page.waitForFunction(step=>window.__replayNative.some(e=>e.type==='ended'&&e.step_id===step),first,{timeout:40000});
    if(second)await page.waitForFunction(step=>window.__replayNative.some(e=>e.type==='playing'&&e.step_id===step),second,{timeout:5000});
    const pause=page.getByRole('button',{name:'일시정지',exact:true});if(await pause.isVisible())await pause.click();
    const data=await page.evaluate(async()=>{await Promise.allSettled(window.__replayTasks);return {native:window.__replayNative,events:window.__replayEvents,blobs:window.__replayBlobs};});
    Object.assign(entry,data);
    const played=data.native.filter(e=>e.type==='playing');
    entry.validated_media=played.map(e=>({step_id:e.step_id,epoch:e.epoch,sha256:data.blobs[e.src],
      matches_actual_WAV:data.blobs[e.src]===clips[e.step_id]?.checksum,rate:e.playbackRate,muted:e.muted,volume:e.volume}));
    assert(entry.validated_media.length&&entry.validated_media.every(e=>e.matches_actual_WAV&&e.rate===1&&!e.muted&&e.volume>0));
    assert(!data.native.some(e=>e.type==='error'||e.type==='seeking'||e.type==='seeked'||e.playbackRate!==1));
    const firstPlaying=played.find(e=>e.step_id===first),ended=data.native.find(e=>e.type==='ended'&&e.step_id===first);
    const next=played.find(e=>e.step_id===second&&e.at_ms>=ended.at_ms);
    entry.cached_click_to_playing_ms=firstPlaying.at_ms-entry.click_at_ms;
    entry.cached_stage_gap_ms=next?next.at_ms-ended.at_ms:null;
    entry.status='PASS_FIRST_CLIP_AND_NEXT_ONSET_GET_ONLY';save();
  }
  report.status='PASS_TWO_STORED_CLIPS_SAME_BROWSER_CONTEXT';
}catch(error){report.status='FAILED_NO_RETRY';report.error=String(error);}
finally{
  if(context)await context.close();if(browser)await browser.close();
  report.budget_after_sha256=sha(ledger);report.budget_unchanged=report.budget_before_sha256===report.budget_after_sha256;
  report.api_after=read(resolve(root,'.local/api-lease.json'));report.same_API_pid=report.api_after.pid===expectedPid;
  report.network_mutation_attempts=report.requests.filter(r=>r.method!=='GET').length+report.blocked.filter(r=>r.method!=='GET').length;
  report.elapsed_wall_seconds=(Date.now()-started)/1000;report.completed_at=new Date().toISOString();
  if(report.blocked.length||report.errors.length||!report.budget_unchanged||!report.same_API_pid||report.elapsed_wall_seconds>120)report.status='FAILED_EVIDENCE_OR_BOUND';
  save();
}
console.log(JSON.stringify({status:report.status,output:out,budget_unchanged:report.budget_unchanged,network_mutation_attempts:report.network_mutation_attempts,seconds:report.elapsed_wall_seconds,error:report.error}));
if(!report.status.startsWith('PASS'))process.exitCode=1;
