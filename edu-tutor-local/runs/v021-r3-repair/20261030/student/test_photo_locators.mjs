import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname,resolve} from 'node:path';
import assert from 'node:assert/strict';
const base=dirname(fileURLToPath(import.meta.url));
const require=createRequire(new URL('../../../../web/package.json',import.meta.url));
const {chromium}=require('@playwright/test');
const original=resolve(base,'../../../v021-support/20261029/student');
const source=JSON.parse(readFileSync(resolve(base,'correction-visible-source.json'),'utf8'));
const actualHTML=readFileSync(resolve(original,'saved-J06-correction-ui/actual-fieldset-before.html'),'utf8');
const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage();
await page.route('**/*',r=>r.abort());
try{
 await page.setContent('<div role="dialog">'+actualHTML+'</div>');
 const exactCount=await page.getByLabel('문제 본문',{exact:true}).count();
 const fields=[[/^\s*문제 본문/,source.question],[/^\s*SQL \/ 코드/,source.sql],[/^\s*보기/,source.choices.join('\n')],[/^\s*읽지 못한 부분/,source.unreadable_regions.join('\n')],[/^\s*누락 조건/,source.missing_conditions.join('\n')]];
 for(const [prefix,value] of fields){const locator=page.getByRole('dialog').locator('fieldset.photo-fields label').filter({hasText:prefix}).locator('textarea');assert.equal(await locator.count(),1);await locator.fill(value);assert.equal(await locator.inputValue(),value);}
 const result={status:'PASS',scope:'CPU browser uses exact preserved actual J06 fieldset HTML; not a new app journey',exact_old_locator_count:exactCount,corrected_fields:fields.length,live_API_calls:0,model_TTS_OCR_calls:0};
 writeFileSync(resolve(base,'photo-locator-cpu.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser.close();}
