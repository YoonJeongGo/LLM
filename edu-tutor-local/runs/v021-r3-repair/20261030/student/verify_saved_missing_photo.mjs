// Saved J07 hydrated-screen proof only; every mutation/generation is blocked.
import {createRequire} from 'node:module';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname,resolve} from 'node:path';
import assert from 'node:assert/strict';
const base=dirname(fileURLToPath(import.meta.url)),root=resolve(base,'../../../..');
const require=createRequire(new URL('../../../../web/package.json',import.meta.url));
const {chromium}=require('@playwright/test');
const raw=JSON.parse(readFileSync(resolve(base,'final-v021-r3-student-v3/J07/actual.json'),'utf8'));
const photoId=raw.photo.id,sessionId=raw.owned_session_id,out=resolve(base,'saved-J07-hydrated-screen');
if(existsSync(resolve(out,'result.json')))throw Error('Do not overwrite');mkdirSync(out,{recursive:true});
const result={status:'RUNNING',source_attempt:resolve(base,'final-v021-r3-student-v3/J07/actual.json'),photo_id:photoId,session_id:sessionId,model_TTS_OCR_calls:0,mutations:0,requests:[],blocked:[],original_screenshot_limitation:'Original safe-stop screenshot was taken before UI hydration and does not prove the returned missing-condition screen.'};
const save=()=>writeFileSync(resolve(out,'result.json'),JSON.stringify(result,null,2));save();
const browser=await chromium.launch({channel:'chrome',headless:true});
const context=await browser.newContext({viewport:{width:1280,height:1000}});
await context.addInitScript(id=>localStorage.setItem('edu-session',id),sessionId);
await context.route('**/*',async route=>{const r=route.request(),u=new URL(r.url());try{assert.equal(u.origin,'http://127.0.0.1:8000');assert.equal(r.method(),'GET');result.requests.push({method:r.method(),path:u.pathname});await route.continue();}catch(e){result.blocked.push({method:r.method(),path:u.pathname,error:String(e)});await route.abort();}});
const page=await context.newPage();page.setDefaultTimeout(15000);
try{
 await page.goto('http://127.0.0.1:8000');await page.getByRole('button',{name:'서버 연결 필요',exact:true}).click();
 await page.getByLabel('로컬 토큰 파일',{exact:true}).setInputFiles(resolve(root,'.local/auth-token'));
 await page.getByRole('button',{name:'로컬 연결됨',exact:true}).waitFor();
 await page.locator('nav').getByRole('button',{name:'대화',exact:true}).click();
 await page.getByRole('button',{name:'문제 사진 첨부',exact:true}).click();
 const fetched=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/photos/'+photoId&&r.request().method()==='GET');
 await page.getByLabel('저장한 사진',{exact:true}).selectOption(photoId);
 const response=await fetched;assert(response.ok());const photo=await response.json();result.saved_photo=photo;
 assert.equal(photo.id,photoId);assert.equal(photo.revision,raw.photo.revision);assert(photo.missing_conditions.length>0);
 const dialog=page.getByRole('dialog');await dialog.locator('fieldset.photo-fields').waitFor();
 const field=prefix=>dialog.locator('fieldset.photo-fields label').filter({hasText:prefix}).locator('textarea');
 await page.waitForFunction(expected=>{const labels=[...document.querySelectorAll('fieldset.photo-fields label')];return labels.find(l=>l.textContent.trimStart().startsWith('문제 본문'))?.querySelector('textarea')?.value===expected;},photo.question);
 await dialog.getByText('표 · 읽지 못한 부분 · 누락 조건 편집',{exact:true}).click();
 assert.equal(await field(/^\s*문제 본문/).inputValue(),photo.question);
 assert.equal(await field(/^\s*SQL \/ 코드/).inputValue(),photo.sql);
 assert.equal(await field(/^\s*누락 조건/).inputValue(),photo.missing_conditions.join('\n'));
 result.solve_disabled=await dialog.getByRole('button',{name:'확정한 문제 풀이',exact:true}).isDisabled();assert(result.solve_disabled);
 result.confirm_disabled=await dialog.getByRole('button',{name:'이 원문으로 확정',exact:true}).isDisabled();
 result.hydrated_fields_match_saved_revision=true;
 result.visible_dialog_text=await dialog.innerText();
 result.rendered_fields=await dialog.locator('fieldset.photo-fields textarea').evaluateAll(es=>es.map(e=>({label:e.closest('label').childNodes[0]?.textContent,value:e.value})));
 result.captured_at=new Date().toISOString();
 writeFileSync(resolve(out,'actual-fieldset.html'),await dialog.locator('fieldset.photo-fields').evaluate(e=>e.outerHTML));
 await page.screenshot({path:resolve(out,'hydrated-missing-condition.png'),fullPage:true});
 await dialog.locator('fieldset.photo-fields').screenshot({path:resolve(out,'hydrated-fields-and-disabled-solve.png')});
 assert.equal(result.blocked.length,0);result.status='SAVED_J07_HYDRATED_SCREEN_CONFIRMED_NO_GENERATION';
 result.boundary='Follow-up read-only screen proof at capture time, not the original question latency or original screenshot.';
}catch(e){result.status='FAILED_NO_GENERATION';result.failure=String(e);await page.screenshot({path:resolve(out,'failure.png'),fullPage:true}).catch(()=>{});}
finally{save();await context.close();await browser.close();console.log(JSON.stringify({status:result.status,failure:result.failure,revision:result.saved_photo?.revision,solve_disabled:result.solve_disabled,model_TTS_OCR_calls:0}));if(result.status.startsWith('FAILED'))process.exitCode=1;}
