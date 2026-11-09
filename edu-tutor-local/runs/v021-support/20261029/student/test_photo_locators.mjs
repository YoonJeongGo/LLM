import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname,resolve} from 'node:path';
import assert from 'node:assert/strict';
const base=dirname(fileURLToPath(import.meta.url));
const require=createRequire(new URL('../../../../web/package.json',import.meta.url));
const {chromium}=require('@playwright/test');
const old=JSON.parse(readFileSync(resolve(base,'final-v021-r3-student-v3/J06/actual.json'),'utf8'));
const candidate=old.photo;
const source=JSON.parse(readFileSync(resolve(base,'correction-visible-source.json'),'utf8'));
const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage();
await page.route('**/*',r=>r.abort());
try{
 await page.setContent('<div role="dialog"><fieldset class="photo-fields">'+
  [['문제 본문',candidate.question],['SQL / 코드',candidate.sql],['보기',(candidate.choices||[]).join('\n')],['읽지 못한 부분',(candidate.unreadable_regions||[]).join('\n')],['누락 조건',(candidate.missing_conditions||[]).join('\n')]].map(([label,value])=>'<label>'+label+' <textarea>'+esc(value)+'</textarea></label>').join('')+'</fieldset></div>');
 const exactCount=await page.getByLabel('문제 본문',{exact:true}).count();
 const fields=[[/^\s*문제 본문(?:\s|$)/,source.question],[/^\s*SQL \/ 코드(?:\s|$)/,source.sql],[/^\s*보기(?:\s|$)/,source.choices.join('\n')],[/^\s*읽지 못한 부분(?:\s|$)/,source.unreadable_regions.join('\n')],[/^\s*누락 조건(?:\s|$)/,source.missing_conditions.join('\n')]];
 for(const [prefix,value] of fields){const locator=page.getByRole('dialog').locator('fieldset.photo-fields label').filter({hasText:prefix}).locator('textarea');assert.equal(await locator.count(),1);await locator.fill(value);assert.equal(await locator.inputValue(),value);}
 const result={status:'PASS',scope:'CPU browser DOM reproduction from actual J06 saved candidate; not a new app journey',exact_old_locator_count:exactCount,corrected_fields:fields.length,live_API_calls:0,model_TTS_OCR_calls:0};
 writeFileSync(resolve(base,'photo-locator-cpu.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser.close();}
