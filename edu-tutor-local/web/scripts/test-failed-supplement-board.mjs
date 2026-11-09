// Real React/Classroom regression with a local mock API and existing WAV files.
// No live project API, new model, speech synthesis, or budget storage is used.
import {createRequire} from 'node:module';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {resolve,dirname,extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
const web=resolve(dirname(fileURLToPath(import.meta.url)),'..'),root=resolve(web,'..');
const args=process.argv.slice(2),opt=(name,fallback)=>args.includes(name)?args[args.indexOf(name)+1]:fallback;
const fixturePath=resolve(opt('--fixture','')), actualPath=resolve(opt('--actual','')), audioDir=resolve(opt('--audio-dir',''));
if(!args.includes('--fixture')||!args.includes('--actual')||!args.includes('--audio-dir'))throw Error('Explicit recorded fixture, actual and audio-dir required');
const dist=resolve(opt('--dist',resolve(web,'dist'))),out=resolve(opt('--output',resolve(web,'test-results/failed-supplement')));
mkdirSync(out,{recursive:true});
const fixture=JSON.parse(readFileSync(fixturePath)),actual=JSON.parse(readFileSync(actualPath));
const require=createRequire(resolve(web,'package.json')),{chromium,expect}=require('@playwright/test');
const main=fixture.source_lesson,mainMessage=fixture.source_message,session=mainMessage.session_id;
const cached=actual.responses.find(r=>r.method==='GET'&&r.path.endsWith('/speech')&&r.value.replay_only&&r.value.steps?.length===2).value;
const question=fixture.submitted_followup_request.content,checks=[],runs=[];
const sha=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
const result={status:'RUNNING',boundary:'Real React + browser native cached WAV; mock API only. No live teaching completion or model quality claim.',
 source_sha256:sha(resolve(web,'src/App.tsx')),fixture_sha256:sha(fixturePath),actual_sha256:sha(actualPath),checks,runs};
const types={'.js':'text/javascript','.css':'text/css','.html':'text/html','.woff2':'font/woff2','.woff':'font/woff','.ttf':'font/ttf'};
const server=createServer((req,res)=>{const u=new URL(req.url,'http://local');if(u.pathname.startsWith('/api/')){res.writeHead(403).end();return;}
 const p=resolve(dist,'.'+decodeURIComponent(u.pathname));if(!p.startsWith(dist)){res.writeHead(403).end();return;}
 const file=existsSync(p)&&extname(p)?p:resolve(dist,'index.html');res.setHeader('Content-Type',types[extname(file)]||'application/octet-stream');res.end(readFileSync(file));});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin=`http://127.0.0.1:${server.address().port}`;
let browser;
function check(name,condition){assert(condition,name);checks.push({name,status:'PASS'});}
try{
 browser=await chromium.launch({channel:'chrome',headless:true});
 const cases=['immediate','generated-null','malformed-plan','foreign-answer','post409-valid','post409-invalid','post409-transient','post409-deleted','revision-invalid','late-new-source','initial-failure'];
 for(const kind of cases){
  const context=await browser.newContext({viewport:{width:1360,height:1000}}),page=await context.newPage();
  const requests=[],pageErrors=[],row={kind,requests,pageErrors};runs.push(row);page.on('pageerror',e=>pageErrors.push(e.message));
  let messages=[],followBody,followCreated=false,sourceInvalid=false,otherSource=false,release;
  const held=new Promise(r=>{release=r;});let heldRequest=false;
  await page.addInitScript(({session,lesson})=>{localStorage.setItem('edu-session',session);localStorage.setItem('edu-tab','chat');
    localStorage.setItem(`lecture:${lesson}`,JSON.stringify({step:1,progress:0.02,audio_position:1,problem_revision:28}));
    window.__plays=0;document.addEventListener('playing',()=>window.__plays++,true);}, {session,lesson:main.plan.lesson_id});
  const parent={text_requests:20,new_audio_clips:10,vision_requests:0,seconds:300};
  const failed=()=>({...fixture.failed_followup_lesson,valid:kind!=='revision-invalid',
    ...(kind==='revision-invalid'?{current_problem_revision:29}:{}),reason:`MOCK ${kind} failure`,source_message_id:fixture.followup_message.id});
  await context.route('**/*',async route=>{
   const req=route.request(),u=new URL(req.url());if(u.origin!==origin){await route.abort();return;}
   if(!u.pathname.startsWith('/api/')){await route.continue();return;}
   const path=u.pathname.slice(4),method=req.method();let body={};try{body=req.postDataJSON()||{}}catch{}
   requests.push({path,method,body,phase:followBody?'followup':'main'});let value={},status=200;
   if(path==='/capabilities')value={text:{available:true},speech:{available:true},vision:{available:false}};
   else if(path==='/models')value={installed:true,ready:true,model_id:'MOCK_ONLY'};
   else if(path==='/doctor')value={};
   else if(path==='/sessions')value=[{id:session,title:'보충 실패 화면 검사',generation_epoch:0}];
   else if(path==='/resources/budget')value={enabled:true,gpu_seconds_remaining:300,new_audio_remaining:0,vision_remaining:0};
   else if(path===`/sessions/${session}/budget`)value={exists:true,session_id:session,state:'active',limits:parent,used:{text_requests:0,new_audio_clips:0,vision_requests:0,seconds:0},remaining:parent,parent_remaining:parent,effective_remaining:parent};
   else if(path===`/sessions/${session}/messages`){
    if(method==='GET')value=messages;
    else if(!body.lesson_context){messages=[{id:'main-user',role:'user',content:body.content},mainMessage];value={job_id:'main-job'};}
    else{followBody=body;const answer=structuredClone(fixture.followup_message);answer.lesson_context=body.lesson_context;
     if(kind==='foreign-answer')answer.lesson_context={...answer.lesson_context,lesson_id:'foreign-source'};
     messages=[...messages,{id:'follow-user',role:'user',content:body.content},answer];value={job_id:'follow-job'};}
   }else if(path==='/jobs/main-job')value={id:'main-job',state:'succeeded',result:{message_id:mainMessage.id}};
   else if(path==='/jobs/follow-job')value={id:'follow-job',state:'succeeded',result:{message_id:fixture.followup_message.id}};
   else if(path==='/jobs/plan-job')value={id:'plan-job',state:'succeeded',result:{}};
   else if(path.endsWith('/cancel'))value={state:'cancelled'};
   else if(path==='/lessons'&&method==='POST'){
    if(body.message_id===mainMessage.id){
     if(kind==='initial-failure')value={...failed(),source_message_id:mainMessage.id};
     else if(otherSource){value=structuredClone(main);value.id='other-lesson';value.plan.lesson_id='other-lesson';value.plan.title='다른 원본 수업';}
     else value=main;
    }else{
     followCreated=true;
     if(kind==='late-new-source'){heldRequest=true;await held;}
     else await new Promise(r=>setTimeout(r,150));
     if(kind.startsWith('post409')){sourceInvalid=kind==='post409-invalid';status=409;value={detail:`MOCK ${kind} failure`};}
     else if(kind==='generated-null')value={...failed(),status:'pending',plan:null};
     else if(kind==='malformed-plan')value={...failed(),status:'verified_tool_plan',speech_allowed:true,plan:{invalid_schema:true}};
     else value=failed();
    }
   }else if(path===`/lessons/${fixture.failed_followup_lesson.id}/generate`)value={job_id:'plan-job'};
   else if(path===`/lessons/${fixture.failed_followup_lesson.id}`)value=failed();
   else if(path===`/lessons/${main.id}`){
    if(followCreated&&['post409-transient','post409-deleted'].includes(kind)){status=kind==='post409-deleted'?404:503;value={detail:'MOCK source read failed'};}
    else value=sourceInvalid?{...main,valid:false,current_problem_revision:29}:main;
   }
   else if(path===`/lessons/${main.id}/speech`)value={...cached,generation_available:false};
   else if(path.startsWith(`/lessons/${main.id}/speech/`)&&path.endsWith('/audio')){
    const step=path.split('/')[4],clip=cached.steps.find(x=>x.step_id===step);
    if(!clip){status=409;value={detail:'MOCK missing cache'};}else{await route.fulfill({status:200,contentType:'audio/wav',body:readFileSync(resolve(audioDir,`${clip.audio_id}.wav`))});return;}
   }else if(path.startsWith('/audio/')){const id=path.split('/')[2];await route.fulfill({status:200,contentType:'audio/wav',body:readFileSync(resolve(audioDir,`${id}.wav`))});return;}
   else{status=404;value={detail:`Unexpected MOCK ${method} ${path}`};}
   await route.fulfill({status,json:value}).catch(e=>{if(kind!=='late-new-source')throw e;});
  });
  await page.goto(origin);await page.getByRole('button',{name:'서버 연결 필요'}).click();
  await page.getByLabel('관리 토큰',{exact:true}).fill('MOCK_ONLY');await page.getByRole('button',{name:'연결',exact:true}).click();
  await expect(page.getByRole('button',{name:'로컬 연결됨'})).toBeVisible();await page.getByRole('button',{name:'대화',exact:true}).click();
  await page.getByLabel('질문 입력').fill('개발용 원본 수업을 설명해 줘');await expect(page.getByRole('button',{name:'수업 시작',exact:true})).toBeEnabled();
  await page.getByRole('button',{name:'수업 시작',exact:true}).click();
  if(kind==='initial-failure'){
   await expect(page.getByText('MOCK initial-failure failure',{exact:true}).first()).toBeVisible();
   check('Initial question failure still displays failed lesson fallback',await page.getByLabel('강의 판서',{exact:true}).count()===0);
   check('Initial failure record remains selected',await page.evaluate(()=>localStorage.getItem('edu-lesson'))===fixture.failed_followup_lesson.id);
   row.status='PASS';await context.close();continue;
  }
  await expect(page.locator('.classroom')).toHaveAttribute('data-student-mode','true');
  await expect(page.locator('.classroom')).toHaveAttribute('data-step-id','s2');
  await page.waitForFunction(()=>{const a=document.querySelector('audio');return a&&!a.paused&&a.currentTime>1;});
  await page.getByRole('button',{name:'minutes, 3행: 0',exact:true}).click();
  await page.getByLabel('강의 중 질문',{exact:true}).fill(question);
  await page.evaluate(()=>{document.querySelector('audio').__preserved='same-audio';document.querySelector('.classroom').__preserved='same-classroom';});
  await page.getByLabel('강의 멈추고 질문',{exact:true}).click();
  await expect.poll(()=>!!followBody).toBe(true);
  const stopped=await page.evaluate(()=>({board:document.querySelector('[aria-label="강의 판서"]').innerText,
   time:document.querySelector('audio').currentTime,paused:document.querySelector('audio').paused,plays:window.__plays,
   selected:document.querySelector('[data-cell-id]:has(button[aria-pressed="true"])')?.getAttribute('data-cell-id')}));row.stopped=stopped;
  if(kind==='late-new-source'){
   await expect.poll(()=>heldRequest).toBe(true);
   await page.getByRole('button',{name:'대화',exact:true}).click();await page.getByLabel('생성 중지',{exact:true}).click();
   otherSource=true;await page.getByRole('button',{name:'강의 보기',exact:true}).first().click();
   await expect(page.locator('.classroom')).toHaveAttribute('data-lesson-record-id','other-lesson');
   release();await page.waitForTimeout(300);
   check('Late failed supplement cannot replace a newly selected source',await page.locator('.classroom').getAttribute('data-lesson-record-id')==='other-lesson');
   check('Late failed supplement does not show old failure',await page.getByText('MOCK late-new-source failure',{exact:true}).count()===0);
  }else if(['post409-invalid','post409-deleted','revision-invalid'].includes(kind)){
   await expect(page.getByLabel('강의 판서',{exact:true})).toHaveCount(0);
   check(`${kind}: invalidated source is not preserved or restored`,await page.locator('.classroom').count()===0);
  }else{
   await expect.poll(()=>page.evaluate(()=>localStorage.getItem('edu-draft:'+localStorage.getItem('edu-session')))).toBe(question);
   const after=await page.evaluate(()=>{const c=document.querySelector('.classroom'),a=document.querySelector('audio');return {
    lesson:c?.getAttribute('data-lesson-record-id'),sameClassroom:c?.__preserved,sameAudio:a?.__preserved,
    board:document.querySelector('[aria-label="강의 판서"]')?.innerText,time:a?.currentTime,paused:a?.paused,plays:window.__plays,
    selected:document.querySelector('[data-cell-id]:has(button[aria-pressed="true"])')?.getAttribute('data-cell-id'),
    question:document.querySelector('[aria-label="강의 중 질문"]')?.value};});row.after=after;
   check(`${kind}: same original plan and Classroom instance preserved`,after.lesson===main.id&&after.sameClassroom==='same-classroom'&&after.board===stopped.board);
   check(`${kind}: same selected cell and local question preserved`,after.selected===stopped.selected&&after.selected===followBody.lesson_context.selected_cell.cell_id&&after.question===question);
   check(`${kind}: same paused audio position without replay`,after.sameAudio==='same-audio'&&after.paused&&Math.abs(after.time-stopped.time)<0.02&&after.plays===stopped.plays);
   check(`${kind}: failed lesson does not replace saved original`,await page.evaluate(()=>localStorage.getItem('edu-lesson'))===main.id);
   check(`${kind}: source was rechecked before preservation`,requests.some(r=>r.path===`/lessons/${main.id}`&&r.method==='GET'&&r.phase==='followup'));
   if(kind==='post409-transient')await expect(page.getByText(/원래 수업의 최신 상태를 다시 확인하지 못했습니다/)).toBeVisible();
   await page.screenshot({path:resolve(out,`${kind}.png`),fullPage:true});
  }
  check(`${kind}: no automatic new text or synthesis retry`,requests.filter(r=>r.method==='POST'&&r.path.endsWith('/messages')).length===2&&requests.filter(r=>r.method==='POST'&&r.path.endsWith('/speech')).length===0);
  check(`${kind}: no React exception`,pageErrors.length===0);
  row.status='PASS';release();await context.close();
 }
 result.status='PASS_REACT_MOCK_REGRESSION';
}catch(e){result.status='FAIL';result.error=String(e.stack||e);throw e;}
finally{writeFileSync(resolve(out,'result.json'),JSON.stringify(result,null,2));await browser?.close();await new Promise(r=>server.close(r));}
console.log(JSON.stringify({status:result.status,cases:runs.length,checks:checks.length,output:out}));
