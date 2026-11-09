// Isolated local-file measurement; no browser/API/model. Original stays untouched.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {performance} from 'node:perf_hooks';
import {EvidenceWriter} from './evidence_writer.mjs';
const base=dirname(fileURLToPath(import.meta.url));
const source=resolve(base,'repair-development-final06/N01/actual.json');
const parent=resolve(base,'../logger-repair/incremental');mkdirSync(parent,{recursive:true});
const out=mkdtempSync(resolve(parent,'run-'));const path=resolve(out,'actual.json');
const bytes=readFileSync(source),hash=createHash('sha256').update(bytes).digest('hex');
const record=JSON.parse(bytes.toString('utf8'));record.recording_mode='incremental_worker_journal_v1';
const writer=new EvidenceWriter(path);writer.checkpoint(record);await writer.flush();
// The existing 57MB state is already present before the measured new responses.
const added=record.responses.at(-1),samples=[];
for(let i=0;i<2;i++){
 record.responses.push({...added,fixture_append:i});
 const start=performance.now();writer.checkpoint(record);const requested=performance.now();
 let observed;
 // This callback is deliberately scheduled after the writer pump, so any main
 // structured-clone work is included rather than hidden by callback ordering.
 await new Promise(resolve=>setImmediate(()=>{observed=performance.now()-start;resolve();}));
 await writer.flush();
 samples.push({checkpoint_call_ms:requested-start,scheduled_callback_delay_ms:observed,durable_checkpoint_ms:performance.now()-start});
}
const finalStart=performance.now(),receipt=await writer.finalize(record),finalElapsed=performance.now()-finalStart;
assert.deepEqual(JSON.parse(readFileSync(path,'utf8')),record);
assert.equal(createHash('sha256').update(readFileSync(source)).digest('hex'),hash);
assert.equal(receipt.full_json_writes,1);assert.equal(receipt.parent_stats.max_pending_messages,1);
const result={source,source_sha256:hash,source_bytes:bytes.length,fixture_only:true,browser_calls:0,model_calls:0,
 measurement:'Already journaled 57MB state; two appended responses; callback queued after incremental main-thread dispatch; final full JSON only after measurement.',
 samples,finalize_after_measurement_ms:finalElapsed,receipt,final_deep_equality:true,original_hash_unchanged:true};
writeFileSync(resolve(out,'measurement.json'),JSON.stringify(result,null,2));
console.log(JSON.stringify({path:out,samples,finalize_after_measurement_ms:finalElapsed,full_json_writes:receipt.full_json_writes,final_deep_equality:true}));
