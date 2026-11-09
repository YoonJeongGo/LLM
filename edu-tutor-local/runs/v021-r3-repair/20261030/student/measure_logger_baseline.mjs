// No browser/API/model. Preserve the actual; measure only a fixture copy.
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {performance} from 'node:perf_hooks';
const base=dirname(fileURLToPath(import.meta.url));
const source=resolve(base,'repair-development-final06/N01/actual.json');
const out=resolve(base,'../logger-repair/baseline');mkdirSync(out,{recursive:true});
const bytes=readFileSync(source),record=JSON.parse(bytes.toString('utf8'));
const samples=[];
for(let i=0;i<2;i++){
 let observed;
 const start=performance.now();
 const route=new Promise(resolve=>setImmediate(()=>{observed=performance.now()-start;resolve();}));
 const jsonStart=performance.now(),serialized=JSON.stringify(record,null,2),jsonEnd=performance.now();
 writeFileSync(resolve(out,`fixture-${i}.json`),serialized);
 const writeEnd=performance.now();await route;
 samples.push({stringify_ms:jsonEnd-jsonStart,write_sync_ms:writeEnd-jsonEnd,total_block_ms:writeEnd-jsonStart,scheduled_callback_delay_ms:observed});
}
const result={source,source_sha256:createHash('sha256').update(bytes).digest('hex'),source_bytes:bytes.length,
 fixture_only:true,browser_calls:0,model_calls:0,measurement:'Already parsed 57MB actual; two full JSON.stringify + synchronous writes; setImmediate callback models an event-loop callback, not a browser latency measurement.',samples};
writeFileSync(resolve(out,'measurement.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
