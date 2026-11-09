// One saved lesson recovery, normal UI, existing scoped TTS only. No text calls.
import { chromium } from '@playwright/test';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
const root=resolve('..'), out=resolve(root,'runs/student-latency/20261027/condition-recovery');
if(!process.argv.includes('--run'))throw Error('Explicit --run required');
if(existsSync(resolve(out,'actual.json')))throw Error('Existing actual run: never repeat automatically');
const preview=JSON.parse(readFileSync(resolve(out,'cpu-saved-E-preview.json'),'utf8'));
if(preview.status!=='PASS')throw Error('CPU source replay has not passed');
const source=preview.source_lesson, original=preview.source_message;
const token=readFileSync(resolve(root,'.local/auth-token'),'utf8').trim();
const result={started_at:new Date().toISOString(),scope:'Saved failed E CPU recovery and same two-step speech; no new question or text inference; no human review',
  source_lesson_id:source.id,source_message_id:original.id,question:preview.source_question,requests:[],responses:[],events:[],screenshots:[],visual_samples:[],errors:[],quality_checks:[],blocked_requests:[]};
const save=()=>writeFileSync(resolve(out,'actual.json'),JSON.stringify(result,null,2));
const api=async path=>{const r=await fetch('http://127.0.0.1:8000/api'+path,{headers:{Authorization:`Bearer ${token}`}});if(!r.ok)throw Error(`GET ${path}: ${r.status}`);return r.json();};
result.budget_before=await api('/resources/budget');
const grant=result.budget_before.active_execution_allowance;
if(!grant||grant.text_remaining!==0||grant.audio_remaining<1||grant.audio_remaining>2||grant.vision_remaining!==0)throw Error('Unexpected remaining grant');
result.bundle=[...readFileSync(resolve(root,'web/dist/index.html'),'utf8').matchAll(/src="([^"]+\.js)"/g)].map(m=>({path:m[1],sha256:createHash('sha256').update(readFileSync(resolve(root,'web/dist',m[1].replace(/^\//,'')))).digest('hex')}));
const browser=await chromium.launch({channel:'chrome',headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1100}});
const page=await context.newPage();
let reprocessPosts=0;const speechSteps=new Set();
async function checkLesson(id){
  const lesson=await api('/lessons/'+id), messages=await api('/sessions/'+lesson.source_session_id+'/messages');
  const message=messages.find(m=>m.id===lesson.source_message_id);
  const indicator=message?.evidence?.logical_steps?.aggregates?.find(a=>a.input_transform==='is_not_null_indicator');
  const checks={distinct_linked_record:lesson.id!==source.id&&lesson.reprocessing?.source_lesson_id===source.id,
    derived_answer_link:message?.reprocessed_from_message_id===original.id,
    exact_raw_reused:message?.raw_model_response===original.raw_model_response,
    exact_problem_reused:JSON.stringify(message?.problem)===JSON.stringify(original.problem),
    exact_sql_reused:message?.evidence?.sql===JSON.parse(original.raw_model_response).sql,
    verified:message?.evidence?.status==='verified'&&message.evidence.calculation.status==='independent_aggregate_match',
    original_execution_match:JSON.stringify(message?.evidence?.result?.rows)===JSON.stringify(original.evidence.execution.rows),
    independent_bits_match:JSON.stringify(indicator?.input_rows?.map(x=>x.value))===JSON.stringify(original.problem.tables[0].rows.map(r=>Number(r[1]!==null))),
    two_complete_steps:lesson.plan?.steps?.length===2&&lesson.speech_allowed===true,
    original_question:lesson.plan?.question_text===preview.source_question,
    no_new_text:lesson.reprocessing?.new_model_calls===0,
    corrected_speech:lesson.plan?.steps?.every(s=>s.speech?.length<120&&!s.speech.includes('solved 컬럼이 NULL이 아닌 행을 세어줍니다'))};
  result.actual_lesson=lesson;result.actual_message=message;result.quality_checks.push({at:new Date().toISOString(),checks});save();
  if(Object.values(checks).some(v=>!v))throw Error('Saved-answer quality gate failed before speech');
  return lesson;
}
await context.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url());
  try{
    if(url.origin!=='http://127.0.0.1:8000')throw Error('External request prohibited');
    const p=url.pathname;
    if(req.method()==='POST'){
      if(p===`/api/lessons/${source.id}/reprocess`){if(++reprocessPosts>1)throw Error('Repeated reprocessing blocked');}
      else if(/^\/api\/lessons\/[^/]+\/speech$/.test(p)){
        const body=req.postDataJSON(),id=p.split('/')[3];
        const lesson=await checkLesson(id);
        if(!lesson.plan.steps.some(s=>s.id===body.step_id))throw Error('Requested speech step not in verified plan');
        if(speechSteps.has(body.step_id)||speechSteps.size>=2)throw Error('Repeated/third TTS blocked');
        speechSteps.add(body.step_id);
      }else if(!/^\/api\/jobs\/[^/]+\/cancel$/.test(p))throw Error('Unapproved POST (no chat/planner/OCR)');
    }else if(req.method()!=='GET')throw Error('Unapproved method');
    result.requests.push({at:new Date().toISOString(),method:req.method(),path:p,body:req.method()==='POST'?req.postDataJSON():undefined});
    await route.continue();
  }catch(e){result.blocked_requests.push({path:url.pathname,method:req.method(),reason:String(e)});save();await route.abort();}
});
page.on('pageerror',e=>{result.errors.push(e.message);save();});
page.on('response',async r=>{try{const path=new URL(r.url()).pathname;
  if(path.startsWith('/api/')&&r.headers()['content-type']?.includes('application/json')&&
    (r.request().method()!=='GET'||/\/lessons\/|\/messages$/.test(path))) {
    result.responses.push({at:new Date().toISOString(),method:r.request().method(),path,status:r.status(),value:await r.json()});save();}
}catch{}});
await page.addInitScript(({lessonId,sessionId})=>{
  localStorage.setItem('edu-lesson',lessonId);localStorage.setItem('edu-session',sessionId);localStorage.setItem('edu-tab','classroom');
  window.__lessonEvents=[];
  window.addEventListener('edu:lesson',e=>{
    const audio=document.querySelector('audio');
    window.__lessonEvents.push({...e.detail,board_text:document.querySelector('.chalk-board')?.innerText??null,
      audio:{paused:audio?.paused,currentTime:audio?.currentTime,duration:audio?.duration,playbackRate:audio?.playbackRate,step:audio?.dataset.stepId}});
  });
},{lessonId:source.id,sessionId:original.session_id});
async function capture(name){
  const path=resolve(out,name+'.png');await page.screenshot({path,fullPage:true});result.screenshots.push(path);
  result.visual_samples.push(await page.evaluate(name=>{
    const audio=document.querySelector('audio'), pointer=document.querySelector('[data-testid="avatar-pointer"]');
    const svg=pointer?.ownerSVGElement, p=svg?.createSVGPoint();
    if(p&&pointer){p.x=Number(pointer.getAttribute('x2'));p.y=Number(pointer.getAttribute('y2'));}
    const end=p&&svg?.getScreenCTM()?p.matrixTransform(svg.getScreenCTM()):null;
    return {name,at_ms:performance.now(),board_text:document.querySelector('.chalk-board')?.innerText,
      audio:{paused:audio?.paused,currentTime:audio?.currentTime,duration:audio?.duration,playbackRate:audio?.playbackRate,step:audio?.dataset.stepId},
      pointer_end:end?{x:end.x,y:end.y}:null,avatar_gesture:document.querySelector('[data-gesture]')?.getAttribute('data-gesture'),
      elements:[...document.querySelectorAll('[data-board-element]')].map(e=>{const r=e.getBoundingClientRect();return {id:e.getAttribute('data-board-element'),text:e.innerText,rect:{left:r.left,right:r.right,top:r.top,bottom:r.bottom}};})};
  },name));save();
}
try{
  save();await page.goto('http://127.0.0.1:8000');
  await page.getByRole('button',{name:'서버 연결 필요'}).click();
  await page.getByLabel('로컬 토큰 파일',{exact:true}).setInputFiles(resolve(root,'.local/auth-token'));
  await page.getByRole('button',{name:'로컬 연결됨'}).waitFor({timeout:30000});
  const menu=page.getByRole('button',{name:'메뉴 열기'});if(await menu.isVisible())await menu.click();
  await page.getByRole('navigation').getByRole('button',{name:'강의실',exact:true}).click();
  await page.getByRole('button',{name:'저장 답변으로 다시 검증',exact:true}).waitFor({timeout:15000});
  await capture('before-original-failure');
  await page.getByRole('button',{name:'저장 답변으로 다시 검증',exact:true}).click();
  await page.waitForFunction(()=>window.__lessonEvents.some(e=>e.type==='saved_response_reprocessed'||e.type==='saved_response_reprocess_blocked'),null,{timeout:30000});
  result.events=await page.evaluate(()=>window.__lessonEvents);save();
  const completed=result.events.find(e=>e.type==='saved_response_reprocessed');
  if(!completed)throw Error('CPU reprocessing blocked');
  await checkLesson(completed.lesson_record_id);
  await capture('reprocessed-plan');
  for(const step of ['s1','s2']){
    await page.waitForFunction(s=>window.__lessonEvents.some(e=>e.type==='audio_playing'&&e.step_id===s)||window.__lessonEvents.some(e=>e.type==='lesson_blocked'),step,{timeout:330000});
    result.events=await page.evaluate(()=>window.__lessonEvents);save();
    if(!result.events.some(e=>e.type==='audio_playing'&&e.step_id===step))throw Error('Speech blocked before '+step);
    await page.waitForFunction(s=>{const a=document.querySelector('audio');return a?.dataset.stepId===s&&a.currentTime>.3;},step,{timeout:10000});
    await capture(step+'-playing');
  }
  await page.waitForFunction(()=>window.__lessonEvents.some(e=>e.type==='audio_ended'&&e.step_id==='s2'),null,{timeout:60000});
  await capture('completed');result.status='PASS_SAVED_E_RECOVERY_TWO_STEPS_NOT_GENERAL_READINESS';
}catch(e){result.status='FAILED_SAVED_E_RECOVERY_NO_RETRY';result.failure=String(e);await capture('failure').catch(()=>{});}
finally{
  result.events=await page.evaluate(()=>window.__lessonEvents).catch(()=>[]);
  result.final_text=await page.locator('body').innerText().catch(()=>'');
  if(result.actual_lesson)result.final_lesson=await api('/lessons/'+result.actual_lesson.id);
  result.budget_after=await api('/resources/budget');result.completed_at=new Date().toISOString();save();
  await context.close();await browser.close();
  console.log(JSON.stringify({status:result.status,failure:result.failure,lesson_id:result.actual_lesson?.id,budget:result.budget_after,blocked_requests:result.blocked_requests},null,2));
  if(result.status.startsWith('FAILED'))process.exitCode=1;
}
