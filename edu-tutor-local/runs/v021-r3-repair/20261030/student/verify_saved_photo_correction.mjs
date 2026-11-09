// Real saved-photo UI correction only. All model/speech/OCR endpoints blocked.
import {createRequire} from 'node:module';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname,resolve} from 'node:path';
import assert from 'node:assert/strict';
const base=dirname(fileURLToPath(import.meta.url)),root=resolve(base,'../../../..');
const require=createRequire(new URL('../../../../web/package.json',import.meta.url));
const {chromium}=require('@playwright/test');
const previous=JSON.parse(readFileSync(resolve(base,'final-v021-r3-student-v4/J06/actual.json'),'utf8'));
const source=JSON.parse(readFileSync(resolve(base,'correction-visible-source.json'),'utf8'));
const photoId=previous.photo.id,sessionId=previous.owned_session_id,out=resolve(base,'saved-J06-correction-ui');
if(existsSync(resolve(out,'result.json')))throw Error('Do not overwrite saved correction attempt');
mkdirSync(out,{recursive:true});
const fields=[['문제 본문','question',/^\s*문제 본문/],['SQL / 코드','sql',/^\s*SQL \/ 코드/],['보기','choices',/^\s*보기/],['읽지 못한 부분','unreadable_regions',/^\s*읽지 못한 부분/],['누락 조건','missing_conditions',/^\s*누락 조건/]];
const result={status:'RUNNING',photo_id:photoId,session_id:sessionId,previous_attempt:resolve(base,'final-v021-r3-student-v4/J06/actual.json'),model_calls:0,tts_calls:0,ocr_calls:0,requests:[],blocked:[],fields:[]};
const save=()=>writeFileSync(resolve(out,'result.json'),JSON.stringify(result,null,2));save();
const browser=await chromium.launch({channel:'chrome',headless:true});
const context=await browser.newContext({viewport:{width:1280,height:1000}});
await context.addInitScript(id=>localStorage.setItem('edu-session',id),sessionId);
let patches=0,confirms=0;
await context.route('**/*',async route=>{
 const req=route.request(),url=new URL(req.url()),method=req.method();
 try{
  assert.equal(url.origin,'http://127.0.0.1:8000');
  if(method==='PATCH'){
   assert.equal(url.pathname,'/api/photos/'+photoId);assert.equal(++patches,1);
   assert.deepEqual(req.postDataJSON(),Object.fromEntries(['question','sql','tables','choices','unreadable_regions','missing_conditions'].map(k=>[k,source[k]])));
  }else if(method==='POST'){assert.equal(url.pathname,'/api/photos/'+photoId+'/confirm');assert.equal(++confirms,1);}
  else assert.equal(method,'GET');
  result.requests.push({method,path:url.pathname});await route.continue();
 }catch(e){result.blocked.push({method,path:url.pathname,error:String(e)});save();await route.abort();}
});
const page=await context.newPage();page.setDefaultTimeout(15000);
try{
 await page.goto('http://127.0.0.1:8000');
 await page.getByRole('button',{name:'서버 연결 필요',exact:true}).click();
 await page.getByLabel('로컬 토큰 파일',{exact:true}).setInputFiles(resolve(root,'.local/auth-token'));
 await page.getByRole('button',{name:'로컬 연결됨',exact:true}).waitFor();
 await page.locator('nav').getByRole('button',{name:'대화',exact:true}).click();
 await page.getByRole('button',{name:'문제 사진 첨부',exact:true}).click();
 await page.getByLabel('저장한 사진',{exact:true}).selectOption(photoId);
 const dialog=page.getByRole('dialog');
 await dialog.locator('fieldset.photo-fields').waitFor();
 await dialog.getByText('표 · 읽지 못한 부분 · 누락 조건 편집',{exact:true}).click();
 const html=await dialog.locator('fieldset.photo-fields').evaluate(e=>e.outerHTML);
 writeFileSync(resolve(out,'actual-fieldset-before.html'),html);
 await page.screenshot({path:resolve(out,'before.png'),fullPage:true});
 for(const [label,key,regex] of fields){
  const labels=dialog.locator('fieldset.photo-fields label').filter({hasText:regex});
  assert.equal(await labels.count(),1);
  const actualLabel=await labels.evaluate(e=>e.textContent);
  assert(actualLabel.trimStart().startsWith(label));
  const input=labels.locator('textarea');assert.equal(await input.count(),1);
  const value=Array.isArray(source[key])?source[key].join('\n'):source[key];
  await input.fill(value);assert.equal(await input.inputValue(),value);
  result.fields.push({label,actual_label_text:actualLabel,unique:true,input_matches:true});
 }
 await dialog.getByLabel('사진 표 JSON',{exact:true}).fill(JSON.stringify(source.tables));
 const changed=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/photos/'+photoId&&r.request().method()==='PATCH');
 await dialog.getByRole('button',{name:'교정 저장',exact:true}).click();
 const changedResponse=await changed;assert(changedResponse.ok());result.corrected=await changedResponse.json();
 assert(result.corrected.revision>previous.photo.revision&&!result.corrected.confirmed);
 for(const key of ['question','sql','tables','choices','unreadable_regions','missing_conditions'])assert.deepEqual(result.corrected[key],source[key]);
 await page.screenshot({path:resolve(out,'corrected-unconfirmed.png'),fullPage:true});
 const confirmed=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/photos/'+photoId+'/confirm'&&r.request().method()==='POST');
 await dialog.getByRole('button',{name:'이 원문으로 확정',exact:true}).click();
 const response=await confirmed;assert(response.ok());result.confirmed=await response.json();
 assert(result.confirmed.confirmed&&result.confirmed.revision===result.corrected.revision&&result.confirmed.id===photoId);
 await page.screenshot({path:resolve(out,'confirmed.png'),fullPage:true});
 // Exact saved live DOM, not a manually spaced synthetic approximation.
 const mock=await context.newPage();await mock.setContent('<div role="dialog">'+html+'</div>');
 for(const [label,key,regex] of fields){const input=mock.getByRole('dialog').locator('fieldset.photo-fields label').filter({hasText:regex}).locator('textarea');assert.equal(await input.count(),1);const value=Array.isArray(source[key])?source[key].join('\n'):source[key];await input.fill(value);assert.equal(await input.inputValue(),value);}
 await mock.close();result.actual_DOM_CPU_fixture='PASS_5_OF_5';
 assert.equal(result.blocked.length,0);result.status='SAVED_OCR_CORRECTION_AND_CONFIRMATION_PASS_NO_GENERATION';
 result.scope='Same original OCR photo revised and confirmed through existing UI. Closed student budget remains closed; no solve requested.';
}catch(e){result.status='FAILED_NO_MODEL_CALL';result.failure=String(e);await page.screenshot({path:resolve(out,'failure.png'),fullPage:true}).catch(()=>{});}
finally{save();await context.close();await browser.close();console.log(JSON.stringify({status:result.status,failure:result.failure,fields:result.fields.length,model_TTS_OCR:0}));if(result.status.startsWith('FAILED'))process.exitCode=1;}
