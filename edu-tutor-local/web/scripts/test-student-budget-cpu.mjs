import {createRequire} from 'node:module';
import {readFileSync,writeFileSync,existsSync,mkdirSync} from 'node:fs';
import {resolve,dirname,extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createServer} from 'node:http';
import assert from 'node:assert/strict';
const web=resolve(dirname(fileURLToPath(import.meta.url)), '..'),root=resolve(web,'..');
const args=process.argv.slice(2), option=(name,fallback)=>args.includes(name)?args[args.indexOf(name)+1]:fallback;
const require=createRequire(resolve(root,'web/package.json')), {chromium,expect}=require('@playwright/test'),ts=require('typescript');
const out=resolve(option('--output',resolve(web,'test-results/student-budget')));mkdirSync(out,{recursive:true});
const checks=[],requests=[],serverHits=[];
const record=(name)=>checks.push({name,status:'PASS'});
// Exercise the actual API module without a network connection.
const moduleText=ts.transpileModule(readFileSync(resolve(web,'src/api.ts'),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const client=await import(`data:text/javascript;base64,${Buffer.from(moduleText).toString('base64')}`);
const nativeFetch=globalThis.fetch;let received;
globalThis.fetch=async(_,init)=>{received=Object.fromEntries(init.headers);return new Response('{}',{status:200,headers:{'content-type':'application/json'}})};
client.setToken('MOCK');client.setExecutionAllowance('dev');client.setStudentSession('s1');
await client.api('/probe',{method:'POST',body:'{}'});assert.equal(received['x-student-session'],'s1');record('API attaches selected student identity');
await client.api('/probe',{method:'POST',body:'{}',studentSession:null});assert.equal(received['x-student-session'],undefined);record('Budget creation can omit student header explicitly');
client.setToken('');await client.api('/probe');assert.equal(received['x-student-session'],undefined);assert.equal(received['x-execution-allowance'],undefined);record('Logout clears both execution identities');
client.setToken('MOCK');client.setStudentSession('closed-session');await client.api('/lessons/cached');assert.equal(received['x-student-session'],'closed-session');record('Closed selected identity does not block cached GET in client');
globalThis.fetch=nativeFetch;
const dist=resolve(option('--dist',resolve(web,'dist'))),types={'.js':'text/javascript','.css':'text/css','.html':'text/html','.woff2':'font/woff2'};
const server=createServer((req,res)=>{serverHits.push(req.url);const p=resolve(dist,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));if(!p.startsWith(dist)||req.url.startsWith('/api/')){res.writeHead(403).end();return;}const target=existsSync(p)&&extname(p)?p:resolve(dist,'index.html');res.setHeader('Content-Type',types[extname(target)]||'application/octet-stream');res.end(readFileSync(target));});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin=`http://127.0.0.1:${server.address().port}`;
let browser;
const result={status:'RUNNING',kind:'MOCK_API_ONLY_NO_MODEL_OR_LIVE_LEDGER',checks,requests};
try {
 browser=await chromium.launch({channel:'chrome',headless:true});const context=await browser.newContext({viewport:{width:1360,height:1000}});
 const page=await context.newPage();const pageErrors=[];page.on('pageerror',e=>pageErrors.push(e.message));
 await page.addInitScript(()=>{localStorage.setItem('edu-session','s1');localStorage.setItem('edu-tab','chat');localStorage.setItem('edu-lesson','mock-lesson');});
 const lessonFixture=JSON.parse(readFileSync(resolve(root,'web/src/lesson.fixture.json'),'utf8'));
 const parent={text_requests:10,new_audio_clips:10,vision_requests:2,seconds:1000};const budgets={};
 const sessions=[{id:'s1',title:'첫 번째 모의 수업',generation_epoch:0},{id:'s2',title:'두 번째 모의 수업',generation_epoch:0}];
 let messages=[],firstStartFail=true,photo=null,delaySecond=false,rejectMessage=false;
 const budget=(id)=>budgets[id]||{exists:false,session_id:id,parent_remaining:parent};
 await context.route('**/*',async route=>{
   const req=route.request(),u=new URL(req.url());if(u.origin!==origin){await route.abort();return;}
   if(!u.pathname.startsWith('/api/')){await route.continue();return;}
   const path=u.pathname.slice(4),method=req.method();let body={};try{body=req.postDataJSON()||{}}catch{}
   const item={path,method,headers:{student:req.headers()['x-student-session']||null,development:req.headers()['x-execution-allowance']||null},body};requests.push(item);
   let value={},status=200;
   if(path==='/capabilities')value={text:{available:true},speech:{available:true},vision:{available:true}};
   else if(path==='/models')value={installed:true,ready:true,model_id:'MOCK_ONLY'};
   else if(path==='/doctor')value={};
   else if(path==='/lessons/mock-lesson')value={id:'mock-lesson',valid:true,plan:lessonFixture,source_message:{session_id:'s1'}};
   else if(path.startsWith('/lessons/mock-lesson/')&&method==='GET')value={steps:[],state:null};
   else if(path==='/resources/budget')value={enabled:true,gpu_seconds_remaining:1000,new_audio_remaining:10,vision_remaining:2,active_execution_allowance:{id:'mock-development',text_remaining:10}};
   else if(path==='/sessions'&&method==='GET')value=sessions;
   else if(path==='/sessions'&&method==='POST'){value={id:'s3',title:body.title,generation_epoch:0};sessions.unshift(value);}
   else if(/^\/sessions\/[^/]+\/budget$/.test(path)){
     const id=path.split('/')[2];
     if(method==='POST'){
       assert.equal(item.headers.student,null);assert.equal(item.headers.development,null);
       if(!budgets[id])budgets[id]={exists:true,session_id:id,state:'active',limits:{...body},used:{seconds:0,text_requests:0,new_audio_clips:0,vision_requests:0},remaining:{...body},parent_remaining:parent,effective_remaining:{...body},parent_scope_id:'MOCK'};
       if(firstStartFail){firstStartFail=false;status=503;value={detail:'모의 응답 유실: 자동 재시도 금지'};}else value=budget(id);
     }else {if(id==='s2'&&delaySecond)await new Promise(r=>setTimeout(r,400));value=budget(id);}
   }else if(path.endsWith('/budget/close')){const id=path.split('/')[2];assert.equal(item.headers.student,id);budgets[id].state='closed';value=budget(id);}
   else if(path.endsWith('/messages')){if(method==='GET')value=messages;else {assert.equal(item.headers.student,path.split('/')[2]);if(rejectMessage){status=409;value={detail:'모의 수업 한도 소진'};}else{messages.push({id:'u1',role:'user',content:body.content});value={job_id:'mockj1'};}}}
   else if(path==='/jobs/mockj1')value={id:'mockj1',state:'completed',result:{}};
   else if(path==='/photos'&&method==='GET')value=[];
   else if(path==='/photos'&&method==='POST'){
     const raw=req.postDataBuffer().toString();assert(raw.includes('name="session_id"\r\n\r\ns1'));assert.equal(item.headers.student,'s1');
     photo={id:'mock-photo',session_id:'s1',question:'모의 사진',sql:'',tables:[],choices:[],unreadable_regions:[],missing_conditions:[],confirmed:false,revision:1,recognition_status:'not_run'};value=photo;
   }else {status=404;value={detail:`Unexpected mock route ${method} ${path}`};}
   await route.fulfill({status,json:value});
 });
 await page.goto(origin);await page.getByRole('button',{name:'서버 연결 필요'}).click();
 await page.getByLabel('관리 토큰',{exact:true}).fill('MOCK_TOKEN');await page.getByRole('button',{name:'연결',exact:true}).click();
 await expect(page.getByRole('button',{name:'로컬 연결됨'})).toBeVisible();
 await page.getByRole('button',{name:'대화',exact:true}).click();
 await expect(page.getByRole('button',{name:'입력한 한도로 수업 시작'})).toBeVisible();
 assert.equal(requests.filter(r=>r.method!=='GET').length,0);record('Connection performs no implicit conversation or budget creation');
 await page.getByLabel('질문 입력').fill('예산 전 질문');await expect(page.getByRole('button',{name:'질문 전송',exact:true})).toBeDisabled();
 await page.getByLabel('질문 입력').press('Enter');assert.equal(requests.filter(r=>r.method!=='GET').length,0);record('Question and Enter are blocked before explicit budget start');
 await page.getByLabel('질문 횟수',{exact:true}).fill('11');await expect(page.getByRole('button',{name:'입력한 한도로 수업 시작'})).toBeDisabled();
 await page.getByLabel('질문 횟수',{exact:true}).fill('2');record('Caps above parent remaining cannot be submitted');
 await page.getByRole('button',{name:'설정',exact:true}).click();await page.getByRole('button',{name:'이번 브라우저에서 검증 예산 사용'}).click();
 await page.getByRole('button',{name:'대화',exact:true}).click();
 await page.getByRole('button',{name:'입력한 한도로 수업 시작'}).click();await expect(page.getByText('모의 응답 유실: 자동 재시도 금지')).toBeVisible();
 assert.equal(requests.filter(r=>r.method==='POST'&&r.path==='/sessions/s1/budget').length,1);record('Failed start receipt is displayed without automatic retry');
 await page.getByRole('button',{name:'입력한 한도로 수업 시작'}).click();await expect(page.getByText('활성 수업 한도',{exact:true})).toBeVisible();
 const starts=requests.filter(r=>r.method==='POST'&&r.path==='/sessions/s1/budget');assert.equal(starts.length,2);assert.equal(starts[0].body.request_id,starts[1].body.request_id);record('Manual same-cap retry preserves request ID and removes development/student start headers');
 await page.getByRole('button',{name:'강의실',exact:true}).click();
 await expect(page.getByLabel('강의 판서',{exact:true})).toBeVisible();
 await expect(page.getByLabel('강의 판서',{exact:true}).locator('table')).toHaveCount(1);
 const boardBefore=await page.getByLabel('강의 판서',{exact:true}).innerText();
 rejectMessage=true;await page.getByLabel('강의 중 질문',{exact:true}).fill('현재 표를 다시 설명해 주세요');
 await page.getByLabel('강의 멈추고 질문',{exact:true}).click();
 await expect(page.getByText('모의 수업 한도 소진',{exact:true})).toBeVisible();
 assert.equal(await page.getByLabel('강의 판서',{exact:true}).innerText(),boardBefore);record('Budget 409 on interruption preserves existing populated board');
 rejectMessage=false;await page.getByRole('button',{name:'대화',exact:true}).click();
 await page.getByLabel('질문 입력').fill('모의 학생 질문');await page.getByRole('button',{name:'질문 전송',exact:true}).click();
 await expect.poll(()=>requests.filter(r=>r.method==='POST'&&r.path.endsWith('/messages')).length).toBe(2);
 await expect(page.getByRole('button',{name:'질문 전송',exact:true})).toBeVisible();record('Student question carries matching selected session header');
 rejectMessage=true;await page.getByLabel('질문 입력').fill('한도 거절 후 보존할 질문');await page.getByRole('button',{name:'질문 전송',exact:true}).click();
 await expect(page.getByText('모의 수업 한도 소진',{exact:true})).toBeVisible();await expect(page.getByLabel('질문 입력')).toHaveValue('한도 거절 후 보존할 질문');
 assert(messages.some(m=>m.content==='모의 학생 질문'));record('Budget 409 preserves draft and prior messages without automatic retry');rejectMessage=false;
 delaySecond=true;await page.getByRole('button',{name:'두 번째 모의 수업',exact:true}).click();await page.getByLabel('질문 입력').fill('전환 중 질문');
 await expect(page.getByRole('button',{name:'질문 전송',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'첫 번째 모의 수업',exact:true}).click();await expect(page.getByText('활성 수업 한도',{exact:true})).toBeVisible();
 await page.getByLabel('문제 사진 첨부').click();await page.getByLabel('문제 사진 업로드').setInputFiles({name:'fixture.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64')});
 await expect(page.getByAltText('업로드한 문제 원본')).toBeVisible();record('Session switch blocks pending generation and stale budget cannot change photo ownership');
 const ocr=page.getByRole('button',{name:/사진.*인식|자동.*인식|글자.*인식/});
 // Zero vision allowance must not invoke recognition regardless of hardware availability.
 const disabledRecognition=await page.getByRole('dialog').getByRole('button').filter({hasText:'인식'}).all();
 assert(disabledRecognition.length>0);assert(await disabledRecognition[0].isDisabled());record('Photo upload carries session ID and zero photo cap disables OCR');
 await page.getByLabel('사진 창 닫기').click();
 await page.screenshot({path:resolve(out,'active-budget.png'),fullPage:true});
 await page.getByRole('button',{name:'이 수업 한도 종료'}).click();await expect(page.getByText('종료된 수업 한도 · 저장 수업은 다시 볼 수 있습니다.')).toBeVisible();
 await page.getByLabel('질문 입력').fill('종료 후 질문');await expect(page.getByRole('button',{name:'질문 전송',exact:true})).toBeDisabled();record('Explicit close preserves history and prevents fresh question generation');
 await page.getByRole('button',{name:'새로운 대화',exact:true}).click();await expect(page.getByRole('button',{name:'수업 대화 만들기'})).toBeVisible();
 assert.equal(requests.filter(r=>r.path==='/sessions'&&r.method==='POST').length,0);
 await page.getByRole('button',{name:'수업 대화 만들기'}).click();await expect(page.getByRole('button',{name:'입력한 한도로 수업 시작'})).toBeVisible();
 assert.equal(requests.filter(r=>r.path==='/sessions'&&r.method==='POST').length,1);assert.equal(requests.filter(r=>r.path==='/sessions/s3/budget'&&r.method==='POST').length,0);record('New conversation requires separate explicit click and creates no budget');
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:resolve(out,'new-budget-mobile.png'),fullPage:true});
 assert.equal(pageErrors.length,0);assert.equal(serverHits.filter(p=>p.startsWith('/api/')).length,0);record('All API calls mocked; no live server or model requests; no page errors');
 result.status='PASS_MOCK_UI';result.page_errors=pageErrors;result.live_api_requests=0;
}catch(error){result.status='FAIL_MOCK_UI';result.error=String(error.stack||error);process.exitCode=1;}
finally{await browser?.close();await new Promise(r=>server.close(r));writeFileSync(resolve(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({status:result.status,checks:checks.length,error:result.error}));}
