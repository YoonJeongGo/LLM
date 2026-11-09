// Exercise the exact UI orchestration body with synthetic event/DOM objects.
// This does not launch a browser or contact an API/model/TTS/OCR service.
import {readFileSync,writeFileSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {runInNewContext} from 'node:vm';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {questionPlan,cycleEvidence} from './followup_cycle.mjs';
const base=dirname(fileURLToPath(import.meta.url));
const source=readFileSync(resolve(base,'journeys.mjs'),'utf8');
const start=source.indexOf('async function runFollowups(originalId) {'),end=source.indexOf('async function waitJob(id) {',start);
assert(start>0&&end>start);
const body=source.slice(start,end);
assert(!/(?:currentTime|playbackRate)\s*=(?!=)|keepalive|warmup/.test(body));
const checks=[];
const spec={id:'N01',kind:'write_sql',question:'unchanged initial',followup:{question:'unchanged followup',column:'v',row_index:0,value:0,source_row:[0]}};
assert.equal(questionPlan(spec,{repeatCase:'N01'}).length,3);
assert.equal(questionPlan({...spec,id:'N02'},{repeatCase:'N01'}).length,2);
assert.equal(questionPlan(spec,{repeatCase:'N01'}).at(-1).cohort,'repeat_stability_only');
assert.throws(()=>questionPlan(spec,{repeatCase:'N01',controlled:true}));
checks.push('question/source untouched; N01 third action explicitly separate; N02 remains two');
const capStart=source.indexOf('const limits = '),capEnd=source.indexOf('\nconst frozen =',capStart);
assert(capStart>0&&capEnd>capStart);
const limitsFor=(repeatFollowup,spec={followup:{}})=>runInNewContext(source.slice(capStart,capEnd)+'\nlimits',
  {spec,repeatFollowup,stopAfterFirstVoice:false});
assert.equal(limitsFor(true).new_audio_clips,23);assert.equal(limitsFor(false).new_audio_clips,18);
assert.equal(limitsFor(false,{}).new_audio_clips,12);assert.equal(limitsFor(true).text_requests,4);
const boundStart=source.indexOf("for (const [field, remaining] of [['text_requests'"),boundEnd=source.indexOf('\nif (JSON.stringify(before.model)',boundStart);
assert(boundStart>0&&boundEnd>boundStart);
for(const parentAudio of [47,22]) {
 const bounded=()=>runInNewContext(source.slice(boundStart,boundEnd),{limits:limitsFor(true),Error,
  before:{budget:{active_execution_allowance:{text_remaining:4,audio_remaining:parentAudio,vision_remaining:0,seconds_remaining:600}}}});
 if(parentAudio===47)bounded();else assert.throws(bounded,/Remaining parent budget/);
}
checks.push('repeat-only 23 audio cap includes two cancelled prefetch attempts; ordinary18/J0812 unchanged; current-parent lower bound enforced');
async function mock({repeat=true,omitEnded=false,changedBoard=false,changedStage=false}={}) {
 const table={id:'source',rows:[[0]]},board=[{id:'source',type:'table',rows:[[{id:'cell',text:'0'}]]}];
 const history=[],native=[],result={followup_cycles:[]},calls=[],captured=[];
 let cycles=0,mediaId=1;
 const get=async path=>{
  calls.push(path);
  if(path==='/models')return{text_session:{resident:true,fixture_only:true}};
  if(path==='/lessons/original')return{id:'original',source_session_id:'session',source_message_id:'answer',plan:{steps:[{id:'s1'}]}};
  if(path==='/sessions/session/messages')return[{id:'answer',evidence:{working_tables:[table]}}];
  if(path.startsWith('/lessons/supp'))return{id:path.split('/').at(-1),plan:{steps:[{id:'a'},{id:'b'}]}};
  throw Error('unexpected GET '+path);
 };
 const page={
  locator:()=>({getByRole:()=>({click:async()=>{}}),evaluate:async()=>({step_id:changedStage&&cycles?'s2':'s1',lesson_record_id:'original',playing:true})}),
  getByLabel:()=>({fill:async question=>assert.equal(question,spec.followup.question)}),
  getByRole:(_,options)=>({click:async()=>{
   assert.equal(options.name,'강의 멈추고 질문');cycles++;const t=cycles*100;
   const media={media_id:mediaId,epoch:cycles,current_src:'blob:'+mediaId,currentTime:1.2};
   history.push({type:'interruption_submitted',lesson_record_id:'original',step_id:'s1',at_ms:t,media,selected_cell_id:'cell',board_content:board},
    {type:'interruption_stopped',lesson_record_id:'original',at_ms:t+1},
    {type:'audio_playing',lesson_record_id:'supp'+cycles,step_id:'a',supplement:true,at_ms:t+10,media:{playbackRate:1,volume:1}});
   native.push({type:'pause',lesson_id:'original',at_ms:t+1,...media},
    {type:'ended',lesson_id:'supp'+cycles,step_id:'a',at_ms:t+20});
   if(!omitEnded)native.push({type:'ended',lesson_id:'supp'+cycles,step_id:'b',at_ms:t+30});
   mediaId=cycles*10;
   history.push({type:'lesson_resumed',lesson_record_id:'original',at_ms:t+40},
    {type:'audio_playing',lesson_record_id:'original',step_id:'s1',at_ms:t+50,media:{media_id:mediaId,currentTime:1.2},
      selected_cell_id:'cell',cells:[{id:'cell',selected:true}],board_content:changedBoard?[]:board});
  }}),
  waitForFunction:async()=>{},evaluate:async()=>native,
 };
 const context={spec,result,repeatFollowup:repeat,get,page,JSON,Error,cycleEvidence,
  save(){},capture:async label=>captured.push(label),events:async()=>history,
  firstPlaying:async count=>history.filter(e=>e.type==='audio_playing').slice(count).find(e=>e.supplement)};
 let error=null;
 try{await runInNewContext(body+'\nrunFollowups("original")',context);}catch(e){error=String(e);}
 return {cycles,result,captured,error};
}
const repeated=await mock();assert.equal(repeated.error,null);assert.equal(repeated.cycles,2);
assert(repeated.result.followup_cycles.every(c=>c.status==='COMPLETED_AND_RESTORED'));
assert.equal(repeated.result.followup_cycles[1].cohort,'repeat_stability_only');
assert(repeated.captured.includes('repeat-2-original-resumed'));
checks.push('two short-step supplements naturally end before two separate original-board/cell/audio restores');
const ordinary=await mock({repeat:false});assert.equal(ordinary.cycles,1);assert.equal(ordinary.error,null);
checks.push('option off keeps exactly one interruption');
for(const mode of [{omitEnded:true},{changedBoard:true}]){
 const failure=await mock(mode);assert.equal(failure.cycles,1);assert.match(failure.error,/mechanical evidence failed/);
}
checks.push('failed or incomplete first supplement stops before any repeat');
const changed=await mock({changedStage:true});assert.equal(changed.cycles,1);assert.match(changed.error,/stage changed/);
checks.push('original stage ending before repeat stops without seek/restart');
const report={status:'PASS',scope:'Synthetic exact harness orchestration; not real playback or model evidence',checks,
 actual_model_TTS_OCR_calls:0,live_API_calls:0,harness_sha256:createHash('sha256').update(source).digest('hex')};
writeFileSync(resolve(base,'repeat-followup-mock.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
