// Exact route-body contract only. No browser, live API, model, TTS, or OCR calls.
import {readFileSync,writeFileSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {runInNewContext} from 'node:vm';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {authorizeJobTarget} from './job_ownership.mjs';
const base=dirname(fileURLToPath(import.meta.url));
const source=readFileSync(resolve(base,'journeys.mjs'),'utf8').replaceAll('\r\n','\n');
const marker="await context.route('**/*', async route => {",start=source.indexOf(marker)+marker.length,end=source.indexOf("\n});\npage.on('response'",start);
assert(start>marker.length&&end>start);
const body=source.slice(start,end),S='a'.repeat(32),P='b'.repeat(32),J='c'.repeat(32),F='d'.repeat(32),scope='finish-local-tutor-20261028-v1',origin='http://127.0.0.1:8000';
const visibleSource=JSON.parse(readFileSync(resolve(base,'correction-visible-source.json'),'utf8'));
const report={kind:'EXACT_HARNESS_ROUTE_BODY_MOCK_NOT_PRODUCTION_UI',model_TTS_OCR_calls:0,live_API_calls:0,harness_sha256:createHash('sha256').update(source).digest('hex'),checks:[]};
function fresh(spec={}){
 const state={URL,Error,JSON,Object,scope,origin,spec,repeatFollowup:false,visibleSource,finishing:false,ownedSessionId:S,ownedPhotoId:P,studentBudgetActive:true,
  limits:{text_requests:2,new_audio_clips:12,vision_requests:0,seconds:600},
  requestStarts:new WeakMap(),mutations:{sessions:0,budgets:0,photos:0,correction:0},counts:{text:0,speech:0,vision:0},result:{requests:[],blocked_requests:[]},save(){},authorizeJobTarget,evidenceWriter:{assertHealthy(){}},
  get:async path=>({id:path.split('/').at(-1),session_id:path.endsWith(F)?'e'.repeat(32):S,kind:'chat',state:'running'})};
 const route=runInNewContext('(async route=>{'+body+'\n})',state);
 return {state,async send(path,method='POST',data={},headers=path==='/api/sessions'||path==='/api/sessions/'+S+'/budget'?{}:{'x-student-session':S}){let outcome='none';await route({request:()=>({url:()=>path.startsWith('https:')?path:origin+path,method:()=>method,headers:()=>headers,postDataJSON:()=>data}),continue:async()=>{outcome='allowed';},abort:async()=>{outcome='blocked';}});return outcome;}};
}
async function check(name,fn){await fn();report.checks.push({name,status:'PASS'});}
await check('one new owned session; repeated session rejected',async()=>{const x=fresh();assert.equal(await x.send('/api/sessions'),'allowed');assert.equal(await x.send('/api/sessions'),'blocked');});
await check('one text submit unless explicit followup/cancellation event',async()=>{const x=fresh();assert.equal(await x.send('/api/sessions/'+S+'/messages'),'allowed');assert.equal(await x.send('/api/sessions/'+S+'/messages'),'blocked');});
await check('two followup submissions and no third',async()=>{const x=fresh({followup:{}});for(let n=0;n<3;n++)assert.equal(await x.send('/api/sessions/'+S+'/messages'),n<2?'allowed':'blocked');});
await check('preregistered third action requires completed first restore, exact question, and never permits fourth',async()=>{
 const x=fresh({followup:{question:'same frozen question'}});x.state.repeatFollowup=true;
 x.state.result.followup_cycles=[{status:'COMPLETED_AND_RESTORED'}];
 for(let n=0;n<4;n++)assert.equal(await x.send('/api/sessions/'+S+'/messages','POST',{content:'same frozen question'}),n<3?'allowed':'blocked');
 for(const status of ['PREPARING','FAILED_CYCLE_EVIDENCE',null]){
  const y=fresh({followup:{question:'same'}});y.state.repeatFollowup=true;y.state.counts.text=2;y.state.result.followup_cycles=[{status}];
  assert.equal(await y.send('/api/sessions/'+S+'/messages','POST',{content:'same'}),'blocked');
 }
 const changed=fresh({followup:{question:'same'}});changed.state.repeatFollowup=true;changed.state.counts.text=2;
 changed.state.result.followup_cycles=[{status:'COMPLETED_AND_RESTORED'}];
 assert.equal(await changed.send('/api/sessions/'+S+'/messages','POST',{content:'different'}),'blocked');
});
await check('foreign session submission blocked',async()=>{assert.equal(await fresh().send('/api/sessions/'+F+'/messages'),'blocked');});
await check('cancel ownership independently fetched before response observer',async()=>{const x=fresh();assert.equal(await x.send('/api/jobs/'+J+'/cancel'),'allowed');assert.equal(x.state.result.cancellation_target_proofs[0].session_id,S);});
await check('foreign cancellation blocked',async()=>{assert.equal(await fresh().send('/api/jobs/'+F+'/cancel'),'blocked');});
await check('one OCR request; no automatic retry',async()=>{const x=fresh();assert.equal(await x.send('/api/photos/'+P+'/transcribe'),'allowed');assert.equal(await x.send('/api/photos/'+P+'/transcribe'),'blocked');});
await check('only exact visible-source correction allowed once',async()=>{const x=fresh({allow_manual_correction:true});const payload=Object.fromEntries(['question','sql','tables','choices','unreadable_regions','missing_conditions'].map(k=>[k,visibleSource[k]]));assert.equal(await x.send('/api/photos/'+P,'PATCH',payload),'allowed');assert.equal(await x.send('/api/photos/'+P,'PATCH',payload),'blocked');});
await check('correction with fabricated condition rejected',async()=>{const x=fresh({allow_manual_correction:true});assert.equal(await x.send('/api/photos/'+P,'PATCH',{...visibleSource,sql:'SELECT 999'}),'blocked');});
await check('foreign or unauthorized photo correction rejected',async()=>{assert.equal(await fresh({allow_manual_correction:true}).send('/api/photos/'+F,'PATCH',visibleSource),'blocked');assert.equal(await fresh().send('/api/photos/'+P,'PATCH',visibleSource),'blocked');});
await check('late mutation blocked; known own cancellation allowed',async()=>{const x=fresh();x.state.finishing=true;assert.equal(await x.send('/api/sessions/'+S+'/messages'),'blocked');assert.equal(await x.send('/api/jobs/'+J+'/cancel'),'allowed');});
await check('student scope required for generation; developer and external origins blocked',async()=>{assert.equal(await fresh().send('/api/sessions/'+S+'/messages','POST',{},{}),'blocked');assert.equal(await fresh().send('/api/sessions','POST',{}, {'x-execution-allowance':scope}),'blocked');assert.equal(await fresh().send('https://example.invalid/upload'),'blocked');});
await check('actual createStudentConversation clears scope; generation waits for verified budget',async()=>{const x=fresh();x.state.studentBudgetActive=false;assert.equal(await x.send('/api/sessions','POST',{},{}),'allowed');assert.equal(await x.send('/api/sessions/'+S+'/messages'),'blocked');assert.equal(await x.send('/api/sessions/'+S+'/budget','POST',{...x.state.limits,request_id:'fixture-budget-request'},{}),'allowed');assert.equal(await x.send('/api/sessions/'+S+'/messages'),'blocked');x.state.studentBudgetActive=true;assert.equal(await x.send('/api/sessions/'+S+'/messages'),'allowed');});
await check('cap mutation or repeated budget start blocked',async()=>{const x=fresh();assert.equal(await x.send('/api/sessions/'+S+'/budget','POST',{...x.state.limits,text_requests:99,request_id:'fixture'},{}),'blocked');const y=fresh(),b={...y.state.limits,request_id:'fixture'};assert.equal(await y.send('/api/sessions/'+S+'/budget','POST',b,{}),'allowed');assert.equal(await y.send('/api/sessions/'+S+'/budget','POST',b,{}),'blocked');});
await check('GET allowed; delete and unexpected mutation rejected',async()=>{const x=fresh();assert.equal(await x.send('/api/health','GET'),'allowed');assert.equal(await x.send('/api/sessions/'+S,'DELETE'),'blocked');assert.equal(await x.send('/api/train'),'blocked');});
await check('recording failure blocks new work but permits read-only and exact owned cancellation cleanup',async()=>{
 const x=fresh();x.state.evidenceWriter.assertHealthy=()=>{throw Error('fixture writer failure');};
 assert.equal(await x.send('/api/sessions/'+S+'/messages'),'blocked');assert.equal(x.state.counts.text,0);
 assert.equal(await x.send('/api/health','GET'),'allowed');assert.equal(await x.send('/api/jobs/'+J+'/cancel'),'allowed');
});
await check('native fetch close uses boolean ok and preserves failure evidence',async()=>{
 const start=source.indexOf('  if(result.student_budget_started) {'),end=source.indexOf("  result.after = await get('/resources/budget')",start);
 assert(start>0&&end>start);
 for(const ok of [true,false]){
  const result={student_budget_started:{exists:true},owned_jobs:[],errors:[]};
  const state={result,ownedSessionId:S,get:async()=>({state:'active'}),terminal:new Set(['succeeded']),origin,headers:{Authorization:'mock'},AbortSignal,
   fetch:async()=>({ok,status:ok?200:409,json:async()=>({state:ok?'closed':'active'})})};
  await runInNewContext('(async()=>{'+source.slice(start,end)+'})()',state);
  assert.equal(result.errors.length,ok?0:1);assert.equal(result.student_budget_closed.value.state,ok?'closed':'active');
 }
});
await check('final snapshot includes late blob bytes and native events at one settled boundary',async()=>{
 const start=source.indexOf('  const finalEvidence = await page.evaluate(async () => {'),end=source.indexOf('  result.source_unchanged_at_end',start);
 const window={__finishBlobTasks:[],__finishEvents:[],__finishMedia:[],__finishSceneSamples:[],__finishBlobs:{}};
 window.__finishBlobTasks.push(Promise.resolve().then(()=>{
   window.__finishMedia.push({type:'playing',current_src:'blob:late'});
   window.__finishBlobTasks.push(Promise.resolve().then(()=>{window.__finishBlobs['blob:late']={sha256:'late-sha'};}));
 }));
 const result={errors:[]};
 await runInNewContext('(async()=>{'+source.slice(start,end)+'})()', {window,result,document:{querySelectorAll:()=>[]},performance:{now:()=>100},page:{evaluate:fn=>fn()}});
 assert.equal(result.native_media[0].current_src,'blob:late');assert.equal(result.blob_bytes['blob:late'].sha256,'late-sha');assert.equal(result.active_audio_count,0);
});
await check('short first-voice control uses UI pause and records observed session without audio seek or keepalive',async()=>{
 const start=source.indexOf('      // Use the ordinary UI pause immediately after a valid playing event.'),end=source.indexOf('\n    } else {',start);
 assert(start>0&&end>start);
 const block=source.slice(start,end),result={},calls=[];
 assert(!/currentTime\s*=|playbackRate\s*=|warmup|keepalive|\/close/.test(block));
 await runInNewContext('(async()=>{'+block+'})()', {result,originalId:'lesson',ownedSessionId:'session',
  performance:{now:()=>25},page:{getByRole:(role,opts)=>{assert.equal(opts.name,'일시정지');return{click:async()=>calls.push('UI pause')};},evaluate:fn=>fn(),locator:()=>({evaluate:fn=>fn({paused:true})})},
  get:async path=>{calls.push(path);return path==='/models'?{text_session:{resident:false,session:null}}:[];},capture:async label=>calls.push(label)});
 assert.equal(result.status,'COMPLETED_SHORT_CONTROLLED_COMPARISON_H_PENDING');
 assert.equal(result.requirements.paused_by_student_control,true);assert.equal(result.text_session_after_first.resident,false);assert.equal(calls[0],'UI pause');
});
report.status='PASS';writeFileSync(resolve(base,'harness-guard-repeat-mock.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,checks:report.checks.length,model_TTS_OCR_calls:0}));
