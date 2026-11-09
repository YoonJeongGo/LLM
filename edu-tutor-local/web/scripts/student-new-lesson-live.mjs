// One authorized new question through the ordinary student UI. No retries or fixtures.
import { chromium } from '@playwright/test';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
const root=resolve('..'), out=resolve(root,'runs/student-latency/20261027/new-lesson');
if(!process.argv.includes('--run'))throw Error('Explicit --run required');
if(existsSync(resolve(out,'actual.json')))throw Error('Existing actual run; never repeat automatically');
const input=JSON.parse(readFileSync(resolve(out,'input.json'),'utf8'));
const oracle=JSON.parse(readFileSync(resolve(out,'private-expected.json'),'utf8'));
const token=readFileSync(resolve(root,'.local/auth-token'),'utf8').trim();
const result={started_at:new Date().toISOString(),scope:'One new synthetic development question, actual local models, normal student UI; no human review',input,requests:[],responses:[],events:[],screenshots:[],errors:[],quality_checks:[],blocked_requests:[]};
const save=()=>writeFileSync(resolve(out,'actual.json'),JSON.stringify(result,null,2));
const api=async path=>{const r=await fetch('http://127.0.0.1:8000/api'+path,{headers:{Authorization:`Bearer ${token}`}});if(!r.ok)throw Error(`GET ${path}: ${r.status}`);return r.json();};
result.budget_before=await api('/resources/budget');
const grant=result.budget_before.active_execution_allowance;
if(!grant||grant.text_remaining!==1||grant.audio_remaining!==2||grant.vision_remaining!==0)throw Error('Grant no longer matches one unspent experiment');
const js=[...readFileSync(resolve(root,'web/dist/index.html'),'utf8').matchAll(/src="([^"]+\.js)"/g)].map(m=>m[1]);
result.bundle=js.map(p=>({path:p,sha256:createHash('sha256').update(readFileSync(resolve(root,'web/dist',p.replace(/^\//,'')))).digest('hex')}));
save();
const browser=await chromium.launch({channel:'chrome',headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1100}});
const page=await context.newPage();
const speechSteps=new Set();let textPosts=0,sessionPosts=0,lessonPosts=0,planPosts=0;
await context.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url());
  try{
    if(url.origin!=='http://127.0.0.1:8000')throw Error('External request prohibited');
    if(req.method()==='POST'){
      const p=url.pathname;
      if(p==='/api/sessions'){if(++sessionPosts>1)throw Error('Second session blocked');}
      else if(/^\/api\/sessions\/[^/]+\/messages$/.test(p)){if(++textPosts>1)throw Error('Second text submission blocked');}
      else if(p==='/api/lessons'){if(++lessonPosts>1)throw Error('Second lesson blocked');}
      else if(/^\/api\/lessons\/[^/]+\/generate$/.test(p)){if(++planPosts>1)throw Error('Second plan blocked');}
      else if(/^\/api\/lessons\/[^/]+\/speech$/.test(p)){
        const body=req.postDataJSON(),id=p.split('/')[3];
        const lesson=await api('/lessons/'+id), messages=await api('/sessions/'+lesson.source_session_id+'/messages');
        const message=messages.find(m=>m.id===lesson.source_message_id);
        result.actual_lesson=lesson;result.actual_message=message;save();
        const checks={verified:message?.evidence?.status==='verified',one_model_attempt:message?.model_attempts?.length===1,
          sqlite_write_sql:message?.problem?.dialect==='sqlite'&&message?.problem?.task_kind==='write_sql'&&!message.problem.query,
          original_table_unchanged:JSON.stringify(message?.problem?.tables)===JSON.stringify(input.tables),
          expected_result:JSON.stringify(message?.evidence?.result?.rows)===JSON.stringify(oracle.rows),
          two_complete_steps:lesson.plan?.steps?.length===2&&lesson.speech_allowed===true,
          requested_step_valid:!!body.step_id&&lesson.plan?.steps?.some(s=>s.id===body.step_id),
          safe_spoken_core:lesson.plan?.steps?.every((s,i)=>s.speech?.includes(String(oracle.rows[0][i]))&&s.speech.length<120)&&/NULL|널/.test(lesson.plan?.steps?.[1]?.speech??'')};
        result.quality_checks.push({at:new Date().toISOString(),checks,raw_explanation_notice:'Model prose is preserved separately; speech is the independently calculated and checked aggregate explanation.'});save();
        if(Object.values(checks).some(v=>!v))throw Error('Quality gate failed before speech');
        if(speechSteps.has(body.step_id)||speechSteps.size>=2)throw Error('Repeated/third speech request blocked');
        speechSteps.add(body.step_id);
      }else if(!/^\/api\/jobs\/[^/]+\/cancel$/.test(p))throw Error('Unapproved POST');
    }else if(req.method()!=='GET')throw Error('Unapproved method');
    result.requests.push({at:new Date().toISOString(),method:req.method(),path:url.pathname});
    await route.continue();
  }catch(e){result.blocked_requests.push({path:url.pathname,method:req.method(),reason:String(e)});save();await route.abort();}
});
page.on('pageerror',e=>{result.errors.push(e.message);save();});
page.on('response',async r=>{try{const path=new URL(r.url()).pathname;if(!path.startsWith('/api/')||!r.headers()['content-type']?.includes('application/json'))return;
  if(r.request().method()!=='GET'||/\/lessons\/|\/messages$/.test(path)){result.responses.push({at:new Date().toISOString(),method:r.request().method(),path,status:r.status(),value:await r.json()});save();}}catch{}});
await page.addInitScript(()=>{
  window.__lessonEvents=[];
  window.addEventListener('edu:lesson',e=>{
    const audio=document.querySelector('audio');
    window.__lessonEvents.push({...e.detail,board_text:document.querySelector('.chalk-board')?.innerText??null,
      audio:{paused:audio?.paused,currentTime:audio?.currentTime,playbackRate:audio?.playbackRate,step:audio?.dataset.stepId}});
  });
});
async function shot(name){const path=resolve(out,name+'.png');await page.screenshot({path,fullPage:true});result.screenshots.push(path);save();}
try{
  await page.goto('http://127.0.0.1:8000');
  await page.getByRole('button',{name:'서버 연결 필요'}).click();
  await page.getByLabel('로컬 토큰 파일',{exact:true}).setInputFiles(resolve(root,'.local/auth-token'));
  await page.getByRole('button',{name:'로컬 연결됨'}).waitFor({timeout:30000});
  const menu=page.getByRole('button',{name:'메뉴 열기'});if(await menu.isVisible())await menu.click();
  await page.getByRole('navigation').getByRole('button',{name:'대화',exact:true}).click();
  await page.locator('.problem-editor summary').click();
  await page.getByLabel('이 질문에 원본 표·SQL을 함께 보냅니다').check();
  await page.getByLabel('문제 종류').selectOption('write_sql');
  await page.getByLabel('DBMS').selectOption('sqlite');
  await page.getByLabel('문제의 원본 표 JSON',{exact:true}).fill(JSON.stringify(input.tables));
  await page.getByLabel('원문과 비교해 표·값·SQL을 확인했습니다').check();
  await page.getByLabel('질문 입력',{exact:true}).fill(input.question);
  await shot('input-before-submit');
  await page.getByRole('button',{name:'수업 시작',exact:true}).click();
  for(const step of ['s1','s2']){
    await page.waitForFunction(s=>window.__lessonEvents.some(e=>e.type==='audio_playing'&&e.step_id===s)||window.__lessonEvents.some(e=>e.type==='lesson_blocked')||document.querySelector('[role="alert"]'),step,{timeout:330000});
    result.events=await page.evaluate(()=>window.__lessonEvents);save();
    if(!result.events.some(e=>e.type==='audio_playing'&&e.step_id===step))throw Error('Lesson blocked before '+step);
    await shot(step+'-playing');
  }
  await page.waitForFunction(()=>window.__lessonEvents.some(e=>e.type==='audio_ended'&&e.step_id==='s2'),null,{timeout:60000});
  await shot('completed');result.status='PASS_LIMITED_NEW_LESSON_NOT_GENERAL_READINESS';
}catch(e){result.status='FAILED_LIMITED_NEW_LESSON_NO_RETRY';result.failure=String(e);await shot('failure').catch(()=>{});}
finally{
  result.events=await page.evaluate(()=>window.__lessonEvents).catch(()=>[]);
  result.final_text=await page.locator('body').innerText().catch(()=>'');
  result.budget_after=await api('/resources/budget');result.completed_at=new Date().toISOString();save();
  await context.close();await browser.close();
  console.log(JSON.stringify({status:result.status,failure:result.failure,budget:result.budget_after,blocked_requests:result.blocked_requests},null,2));
  if(result.status.startsWith('FAILED'))process.exitCode=1;
}
