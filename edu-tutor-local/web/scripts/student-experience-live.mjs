// Actual local application/model run. No mocked answers or audio; no retries.
import { chromium } from '@playwright/test';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
const root=resolve('..'), out=resolve(root,'runs/student-experience/20261027/live');
mkdirSync(out,{recursive:true});
const token=readFileSync(resolve(root,'.local/auth-token'),'utf8').trim();
const mode=process.argv[2]??'BC';
const label=mode+(process.argv[3]?'-'+process.argv[3]:'');
const result={mode,started_at:new Date().toISOString(),scope:'actual local models and browser media; synthetic development inputs; no human review',errors:[],responses:[],screenshots:[]};
const save=()=>writeFileSync(resolve(out,label+'.json'),JSON.stringify(result,null,2));
const api=async(path,method='GET',body)=>{const r=await fetch('http://127.0.0.1:8000/api'+path,{method,headers:{Authorization:`Bearer ${token}`,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});const v=await r.json();if(!r.ok)throw Error(`${method} ${path}: ${r.status} ${JSON.stringify(v)}`);return v;};
const browser=await chromium.launch({channel:'chrome',headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1100}});
const page=await context.newPage();
page.on('pageerror',e=>{result.errors.push(e.message);save();});
page.on('response',async r=>{try {const path=new URL(r.url()).pathname; if(!path.startsWith('/api/')||path.includes('/events')||!r.headers()['content-type']?.includes('application/json'))return; const value=await r.json(); if(r.request().method()!=='GET'||/\/lessons\/|\/photos\/|\/messages$/.test(path)){let request;try{request=r.request().postDataJSON();}catch{}result.responses.push({at:new Date().toISOString(),method:r.request().method(),path,status:r.status(),request,value});save();}}catch{}});
await page.addInitScript(()=>{
  window.__lessonEvents=[];
  window.addEventListener('edu:lesson',e=>{
    const audio=document.querySelector('audio'),board=document.querySelector('.chalk-board'), avatar=document.querySelector('.avatar');
    const snap=e.detail.type==='audio_playing'||e.detail.type==='interruption_submitted'||e.detail.type==='interruption_stopped'||e.detail.type==='lesson_resumed';
    window.__lessonEvents.push({...e.detail,...(snap?{board:{text:board?.innerText??null,html:board?.outerHTML??null,elements:[...document.querySelectorAll('[data-board-element]')].map(n=>({id:n.dataset.boardElement,rect:n.getBoundingClientRect().toJSON()})),cells:[...document.querySelectorAll('[data-cell-id]')].map(n=>({id:n.dataset.cellId,text:n.textContent,class:n.className,rect:n.getBoundingClientRect().toJSON()}))},audio:{paused:audio?.paused,currentTime:audio?.currentTime,src:audio?.getAttribute('src'),step:audio?.dataset.stepId},character:avatar?.outerHTML??null}: {})});
  });
});
async function events(){return page.evaluate(()=>window.__lessonEvents);}
async function shot(name){const p=resolve(out,`${label}-${name}.png`);await page.screenshot({path:p,fullPage:true});result.screenshots.push(p);save();}
async function until(fn,arg,timeout=330000){await page.waitForFunction(fn,arg,{timeout});}
async function nav(name){const menu=page.getByRole('button',{name:'메뉴 열기'});if(await menu.isVisible())await menu.click();await page.getByRole('navigation').getByRole('button',{name,exact:true}).click();}
async function firstPlaying(after=0){await until(n=>window.__lessonEvents.filter(e=>e.type==='audio_playing').length>n||window.__lessonEvents.some(e=>e.type==='lesson_blocked')||document.querySelector('.classroom [role="alert"]'),after);const all=await events();if(all.some(e=>e.type==='lesson_blocked'))throw Error('Lesson blocked: '+all.findLast(e=>e.type==='lesson_blocked').reason);if(await page.locator('.classroom [role="alert"]').count())throw Error(await page.locator('.classroom [role="alert"]').innerText());return all.filter(e=>e.type==='audio_playing').at(-1);}
async function halt(){const button=page.getByRole('button',{name:'일시정지',exact:true});if(await button.isVisible())await button.click();}
async function snapshot(){result.events=await events();result.final_text=await page.locator('body').innerText();result.final_budget=await api('/resources/budget');save();}
try{
  result.budget_before=await api('/resources/budget');save();
  if(mode==='A-rechecked'){
    const original=JSON.parse(readFileSync(resolve(out,'A.json'),'utf8'));
    const session=original.responses.find(r=>r.path==='/api/sessions'&&r.method==='POST').value.id;
    result.input={question:original.input.question,session_id:session,source:'saved actual model answer from A.json; new supported DDL plan and voice; no new text inference; not original question-to-voice latency'};
    await page.addInitScript(id=>{localStorage.setItem('edu-session',id);localStorage.setItem('edu-tab','chat');},session);save();
  }
  await page.goto('http://127.0.0.1:8000');
  await page.getByRole('button',{name:'서버 연결 필요'}).click();
  await page.getByLabel('로컬 토큰 파일',{exact:true}).setInputFiles(resolve(root,'.local/auth-token'));
  await page.getByRole('button',{name:'로컬 연결됨'}).waitFor({timeout:30000});
  await nav('대화');
  if(mode==='BC'){
    const table={name:'study_results',columns:[{name:'student',type:'TEXT'},{name:'team',type:'TEXT'},{name:'score',type:'INTEGER'},{name:'attended',type:'INTEGER'}],rows:[['하린','청',35,1],['도윤','청',25,1],['서아','청',90,0],['지호','백',40,1],['유나','백',null,1],['민재','홍',70,1]]};
    const sql='SELECT team, COUNT(*) AS people, SUM(score) AS total FROM study_results WHERE attended = 1 GROUP BY team HAVING SUM(score) >= 50 ORDER BY team;';
    const question='개발 검증을 위해 직접 작성한 새 예시입니다. 이 SQL의 원본 표에서 WHERE, GROUP BY, HAVING을 거쳐 최종 결과가 나오는 과정을 설명해 줘.';
    result.input={question,table,sql,expected_rows:[['청',2,60],['홍',1,70]],provenance:'new independently authored development example, not a real student upload'};save();
    await page.locator('.problem-editor summary').click();
    await page.getByLabel('이 질문에 원본 표·SQL을 함께 보냅니다').check();
    await page.getByLabel('문제의 원본 SQL',{exact:true}).fill(sql);
    await page.getByLabel('문제의 원본 표 JSON',{exact:true}).fill(JSON.stringify([table]));
    await page.getByLabel('원문과 비교해 표·값·SQL을 확인했습니다').check();
    await page.getByLabel('질문 입력',{exact:true}).fill(question);
    await page.getByRole('button',{name:'수업 시작',exact:true}).click();
    result.B_first=await firstPlaying();
    await page.getByRole('button',{name:'attended, 1행: 1',exact:true}).click();
    await shot('C-before');
    await page.getByLabel('강의 중 질문',{exact:true}).fill('왜 이 행이 포함돼?');
    result.followup='왜 이 행이 포함돼?';save();
    await page.getByRole('button',{name:'강의 멈추고 질문',exact:true}).click();
    await until(()=>window.__lessonEvents.some(e=>e.type==='interruption_stopped'));
    await shot('C-stopped');
    result.C_first=await firstPlaying(1);
    await shot('C-explanation');
    await until(()=>window.__lessonEvents.some(e=>e.type==='lesson_resumed'));
    await shot('B-resumed');
    for(const step of ['s2','s3','s4']){
      await until(s=>window.__lessonEvents.some(e=>e.type==='audio_playing'&&e.step_id===s),step);
      await shot('B-'+step);
    }
    await until(()=>window.__lessonEvents.some(e=>e.type==='audio_ended'&&e.step_id==='s4'));
    await shot('B-completed');
  } else if(mode==='A'){
    result.input={question:'DDL이 뭐였지? 테이블 예시로 설명해 줘.'};save();
    await page.getByLabel('질문 입력',{exact:true}).fill(result.input.question);
    await page.getByRole('button',{name:'수업 시작',exact:true}).click();
    result.first_playing=await firstPlaying();
    await shot('first-explanation');
    if(['fixed','final'].includes(process.argv[3])){
      const id=await page.locator('.classroom').getAttribute('data-lesson-record-id');
      const record=await api('/lessons/'+id);result.verified_lesson=record;save();
      for(let i=1;i<record.plan.steps.length;i++){
        await firstPlaying(i);await shot('example-'+record.plan.steps[i].id+'-playing');
      }
      const last=record.plan.steps.at(-1).id;
      await until(s=>window.__lessonEvents.some(e=>e.type==='audio_ended'&&e.step_id===s)||window.__lessonEvents.some(e=>e.type==='lesson_blocked'),last);
      if((await events()).some(e=>e.type==='lesson_blocked'))throw Error('Lesson stopped before final audio ended');
      await shot('example-completed');
    }else await halt();
  } else if(mode==='A-rechecked'){
    await page.getByRole('button',{name:'강의 보기',exact:true}).last().click();
    const generated=page.waitForResponse(r=>/\/lessons\/[^/]+\/generate$/.test(new URL(r.url()).pathname)&&r.request().method()==='POST');
    result.plan_regeneration_at_ms=await page.evaluate(()=>performance.now());
    await page.getByRole('button',{name:'이 답변으로 판서 강의 생성',exact:true}).click();
    await generated;
    await page.locator('.chalk-board').waitFor({timeout:45000});
    await shot('definition-board');
    const speechStarted=page.waitForResponse(r=>/\/lessons\/[^/]+\/speech$/.test(new URL(r.url()).pathname)&&r.request().method()==='POST');
    await page.getByRole('button',{name:'현재 단계 음성 준비',exact:true}).click();
    const speech=await speechStarted; const jobId=(await speech.json()).job_id;
    // Wait for both complete clips in the same model batch before manual
    // navigation so the audit cannot cancel and waste its second clip.
    for(;;){const j=await api('/jobs/'+jobId);if(['succeeded','failed','cancelled','blocked','interrupted'].includes(j.state)){result.speech_job=j;if(j.state!=='succeeded')throw Error(j.error||j.state);break;}await new Promise(r=>setTimeout(r,500));}
    await page.getByRole('button',{name:'음성 재생',exact:true}).click();
    result.first_playing=await firstPlaying();await shot('definition-playing');
    await until(()=>window.__lessonEvents.some(e=>e.type==='audio_ended'&&e.step_id==='s1'));
    await page.getByRole('button',{name:'다음 단계',exact:true}).last().click();
    await page.getByRole('button',{name:'현재 단계 음성 준비',exact:true}).click();
    await page.getByRole('button',{name:'음성 재생',exact:true}).click();
    await firstPlaying(1);await shot('example-playing');
    await until(()=>window.__lessonEvents.some(e=>e.type==='audio_ended'&&e.step_id==='s2'));
    await shot('example-completed');
  } else if(mode==='D-normal-lesson'||mode==='D-cut-review'){
    const previous=JSON.parse(readFileSync(resolve(out,(mode==='D-normal-lesson'?'D-normal':'D-cut')+'.json'),'utf8'));
    const photoId=previous.photo.id;
    result.input={photo_id:photoId,prior_capture:mode==='D-normal-lesson'?'D-normal.json':'D-cut.json',provenance:'same saved synthetic test image/OCR; model-free structure repair; automated QA source comparison, not human review'};save();
    await page.getByLabel('사진 답변도 수업으로 듣기').check();
    await page.getByRole('button',{name:'문제 사진 첨부',exact:true}).click();
    await page.getByLabel('저장한 사진',{exact:true}).selectOption(photoId);
    await page.getByLabel('문제 본문',{exact:false}).waitFor();
    if(mode==='D-normal-lesson'){
      const response=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/restructure')&&r.request().method()==='POST');
      await page.getByRole('button',{name:'인식문에서 표 다시 정리',exact:true}).click();
      const parsed=await response; result.restructure={status:parsed.status(),photo:await parsed.json()};save();
      if(!parsed.ok())throw Error('CPU photo restructure failed');
      const photo=result.restructure.photo;
      if(JSON.stringify(photo.tables[0]?.rows)!==JSON.stringify([['박강열',80],['유성재',null],['김현수',100]]))throw Error('OCR candidate differs from synthetic source image; no automatic confirmation');
      await shot('unconfirmed-candidate');
    }
    const photo=await api('/photos/'+photoId);
    if(!photo.confirmed){
      const response=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/confirm')&&r.request().method()==='POST');
      await page.getByRole('button',{name:'이 원문으로 확정',exact:true}).click();await response;
    }
    await page.getByRole('button',{name:'확정한 문제 풀이',exact:true}).waitFor();
    await until(()=>![...document.querySelectorAll('button')].find(n=>n.textContent.trim()==='확정한 문제 풀이')?.disabled);
    const response=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/solve')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'확정한 문제 풀이',exact:true}).click();
    const solved=await response;result.solve_result={status:solved.status(),body:await solved.json()};save();
    if(mode==='D-cut-review'){
      if(solved.status()!==409)throw Error('Cut photo was not blocked by the server');
      await shot('missing-condition-blocked');
    } else {
      result.first_playing=await firstPlaying();await shot('first-explanation');await halt();
    }
  } else if(mode.startsWith('D')){
    result.input={file:resolve(root,`runs/phase2/current/live/photos/${mode==='D-normal'?'table':'cut'}.png`),provenance:'existing self-authored synthetic test image from phase2; reused with permission; not a real student upload'};save();
    await page.getByLabel('사진 답변도 수업으로 듣기').check();
    await page.getByRole('button',{name:'문제 사진 첨부',exact:true}).click();
    await page.getByLabel('문제 사진 업로드',{exact:true}).setInputFiles(result.input.file);
    const response=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/transcribe')&&r.request().method()==='POST');
    result.photo_submission_at=await page.evaluate(()=>performance.now());
    await page.getByRole('button',{name:'로컬 모델로 원문 인식',exact:true}).click();
    const jobId=(await (await response).json()).job_id;
    for(;;){const job=await api('/jobs/'+jobId);if(['succeeded','failed','cancelled','interrupted','blocked'].includes(job.state)){result.ocr_job=job;break;}await new Promise(r=>setTimeout(r,1000));}
    await page.getByRole('button',{name:'로컬 모델로 원문 인식',exact:true}).waitFor({timeout:15000});
    await shot('ocr');
    result.photo_fields=await page.locator('.photo-fields textarea').evaluateAll(ns=>ns.map(n=>({label:n.getAttribute('aria-label')||n.parentElement.innerText,value:n.value})));
    result.photo=await api('/photos/'+result.responses.findLast(r=>r.path.endsWith('/transcribe')).path.split('/')[3]);
    // Keep failed/missing OCR visible. Never repair or invent text automatically.
    if(mode==='D-cut'){
      const confirm=page.getByRole('button',{name:'이 원문으로 확정',exact:true});
      if(await confirm.isEnabled())await confirm.click();
      await shot('confirmation-check');
      result.solve_enabled=await page.getByRole('button',{name:'확정한 문제 풀이',exact:true}).isEnabled();
      if(result.solve_enabled){
        const rejected=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/solve')&&r.request().method()==='POST');
        await page.getByRole('button',{name:'확정한 문제 풀이',exact:true}).click();
        const denial=await rejected; result.solve_result={status:denial.status(),body:await denial.json()};
        await shot('solve-blocked');
      }
    } else {
      result.fresh_photo_lesson_status='awaiting_review_of_actual_ocr';
    }
  }
  await snapshot();
  result.status='completed_selected_scope';
}catch(e){result.status='failed';result.failure=String(e);await shot('failure').catch(()=>{});await snapshot().catch(()=>{});console.error(String(e));}
finally{result.completed_at=new Date().toISOString();await snapshot().catch(()=>{});save();await context.close();await browser.close();console.log(JSON.stringify({mode,status:result.status,failure:result.failure,budget:result.final_budget},null,2));}
