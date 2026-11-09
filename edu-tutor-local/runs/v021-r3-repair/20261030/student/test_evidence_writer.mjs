// CPU/file fixtures only. No model, browser, live API, speech, or ledger access.
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {runInNewContext} from 'node:vm';
import {EvidenceWriter} from './evidence_writer.mjs';
const base=dirname(fileURLToPath(import.meta.url));
const folder=resolve(base,'../logger-repair/tests');mkdirSync(folder,{recursive:true});
const temp=mkdtempSync(resolve(folder,'run-'));const checks=[];
async function check(name,fn){await fn();checks.push({name,status:'PASS'});}
function recover(path){
 const value={};let revision=0;
 for(const line of readFileSync(path,'utf8').trimEnd().split('\n')){
  const record=JSON.parse(line);if(record.type!=='checkpoint')continue;
  assert(record.revision>revision);revision=record.revision;Object.assign(value,record.set);
  for(const [key,patch] of Object.entries(record.append)){
   assert.equal(value[key]?.length||0,patch.from);value[key]??=[];value[key].push(...patch.items);
  }
 }
 return value;
}
await check('ordered raw responses, longer event prefix and nested cycle updates survive coalescing and final equality',async()=>{
 const path=resolve(temp,'complete.json'),errors=[];
 const writer=new EvidenceWriter(path,{onError:e=>errors.push(String(e))});
 const result={recording_mode:'incremental_worker_journal_v1',status:'RUNNING',spec:{question:'NULL/0 원문'},requests:[],responses:[],events:[],native_media:[],screenshots:[],samples:[],errors:[],blocked_requests:[],followup_cycles:[{status:'PREPARING',nested:{row:[null,0,-4]}}]};
 writer.checkpoint(result);await writer.flush();assert(!existsSync(path));
 const stringify=JSON.stringify;
 JSON.stringify=(value,...rest)=>{assert.notEqual(value,result,'main thread full serialization');return stringify(value,...rest);};
 try{
  for(let i=0;i<100;i++){
   result.requests.push({i});result.responses.push({i,raw:'행'+i,table:[[null,0,-4]],late:false});
   result.events=[...result.events,{i,epoch:i%2,raw:'unchanged'}];writer.checkpoint(result);
  }
  result.followup_cycles[0].status='RESTORED';result.followup_cycles[0].nested.row.push(5);
  writer.checkpoint(result);await writer.flush();
  assert.deepEqual(recover(path+'.journal.jsonl'),result);
  result.status='COMPLETED';result.completed_at='fixture';
  const receipt=await writer.finalize(result);
  assert.deepEqual(JSON.parse(readFileSync(path,'utf8')),result);assert.deepEqual(recover(path+'.journal.jsonl'),result);
  assert.equal(receipt.full_json_writes,1);assert.equal(receipt.parent_stats.max_pending_messages,1);
  assert.equal(receipt.parent_stats.full_result_posts,0);assert(receipt.parent_stats.checkpoint_messages<receipt.parent_stats.checkpoint_requests);
  assert.deepEqual(errors,[]);assert.throws(()=>writer.checkpoint(result),/closing/);
 }finally{JSON.stringify=stringify;await writer.worker.terminate();}
});
await check('normal failure records and required cleanup evidence are finalized once',async()=>{
 const path=resolve(temp,'failure.json'),writer=new EvidenceWriter(path);
 const result={recording_mode:'incremental_worker_journal_v1',status:'RUNNING',responses:[],events:[],errors:[]};
 writer.checkpoint(result);await writer.flush();
 result.responses.push({body:'preserved original failure'});result.status='FAILED_NO_RETRY';
 result.failure='fixture model refusal';result.owned_jobs=[{id:'owned',state:'cancelled'}];result.student_budget_closed={state:'closed'};
 await writer.finalize(result);assert.deepEqual(JSON.parse(readFileSync(path,'utf8')),result);
});
await check('array truncation is a recording failure, with prior durable journal retained',async()=>{
 const path=resolve(temp,'truncated.json'),errors=[],writer=new EvidenceWriter(path,{onError:e=>errors.push(String(e))});
 const result={responses:[{original:true}],events:[]};writer.checkpoint(result);await writer.flush();
 result.responses=[];writer.checkpoint(result);await assert.rejects(writer.flush(),/shrank/);
 await assert.rejects(writer.finalize(result),/shrank/);assert(!existsSync(path));assert.equal(errors.length,1);
 assert.deepEqual(recover(path+'.journal.jsonl').responses,[{original:true}]);
});
await check('existing final/attempt cannot be overwritten or automatically retried',async()=>{
 const path=resolve(temp,'protected.json');writeFileSync(path,'protected');
 const writer=new EvidenceWriter(path);writer.checkpoint({status:'RUNNING'});
 await assert.rejects(writer.flush(),/existing actual/);await assert.rejects(writer.finalize({}),/existing actual/);
 assert.equal(readFileSync(path,'utf8'),'protected');
});
await check('receipt publication failure leaves actual explicitly uncommitted',async()=>{
 const path=resolve(temp,'uncommitted.json');writeFileSync(path+'.writer.json','owned conflict fixture');
 const writer=new EvidenceWriter(path);const result={recording_mode:'incremental_worker_journal_v1',status:'COMPLETED',events:[{raw:true}]};
 await assert.rejects(writer.finalize(result),/EEXIST/);
 assert.deepEqual(JSON.parse(readFileSync(path,'utf8')),result);
 assert.equal(readFileSync(path+'.writer.json','utf8'),'owned conflict fixture');
 // New collector gate is tested separately: this completed-looking JSON is NOT a committed run.
});
await check('exact harness failure finalization runs owned cancellation, budget closure and browser cleanup first',async()=>{
 const source=readFileSync(resolve(base,'journeys.mjs'),'utf8').replaceAll('\r\n','\n');
 const start=source.lastIndexOf('} finally {\n  finishing = true;')+'} finally {'.length;
 const end=source.indexOf('  console.log(JSON.stringify({ id, version',start);
 assert(start>0&&end>start);const calls=[];
 const result={errors:['fixture writer failure'],blocked_requests:[],student_budget_started:{exists:true}};
 const state={result,finishing:false,ownedSessionId:'own',ownedJobIds:new Set(['owned-job']),pendingResponses:new Set(),terminal:new Set(['cancelled']),
  page:{locator:()=>({innerText:async()=>''}),evaluate:async()=>({events:[{raw:'last'}],native_media:[],scene_samples:[],blob_bytes:{}})},
  nav:async()=>calls.push('nav'),get:async path=>path==='/jobs/owned-job'?{id:'owned-job',state:'running'}:path==='/models'?{text_session:{resident:false}}:[],
  waitJob:async()=>{calls.push('cancel-terminal');return{id:'owned-job',state:'cancelled'};},
  origin:'http://fixture.invalid',headers:{Authorization:'fixture'},AbortSignal,
  fetch:async path=>{calls.push(path.endsWith('/cancel')?'cancel':'budget-close');return{ok:true,status:200,json:async()=>({state:'closed'})};},
  frozen:{source_hashes:{}},sources:()=>({}),context:{close:async()=>calls.push('context-close')},browser:{close:async()=>calls.push('browser-close')},
  evidenceWriter:{finalize:async()=>{calls.push('finalize');throw Error('fixture disk failure');}}};
 await assert.rejects(runInNewContext('(async()=>{'+source.slice(start,end)+'})()',state),/fixture disk failure/);
 assert.deepEqual(calls.slice(-3),['context-close','browser-close','finalize']);
 assert(calls.includes('cancel')&&calls.includes('cancel-terminal')&&calls.includes('budget-close'));
 assert.equal(calls.filter(x=>x==='finalize').length,1);assert.equal(result.status,'FAILED_EVIDENCE_INTEGRITY');
});
const report={status:'PASS',checks,fixture_dir:temp,model_calls:0,browser_calls:0,live_API_calls:0};
writeFileSync(resolve(temp,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
