// File-only source provenance preflight. No browser/API/model calls.
import {readFileSync,writeFileSync,mkdtempSync,mkdirSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {replaySources} from './saved_replay_sources.mjs';
const base=dirname(fileURLToPath(import.meta.url)),root=resolve(base,'../../../..');
const temporary=mkdtempSync(resolve(base,'replay-source-fixture-'));mkdirSync(resolve(temporary,'runs'));
const actual={status:'COMPLETED',completed_at:'fixture',owned_session_id:'fixture-session',actual_lesson:{id:'original'},followup_cycles:[{supplement_id:'supp1'},{supplement_id:'supp2'}]};
const actualPath=resolve(temporary,'runs/actual.json');writeFileSync(actualPath,JSON.stringify(actual));
const manifest=resolve(temporary,'manifest.json');
const set=entries=>writeFileSync(manifest,JSON.stringify({entries}));
set([{id:'N01-supp1',actual_path:'runs/actual.json',lesson_id:'supp1'}]);
assert.equal(replaySources(temporary,{manifest})[0].lessonId,'supp1');
set([{id:'N01-supp2',actual_path:'runs/actual.json',lesson_id:'supp2'}]);
assert.equal(replaySources(temporary,{manifest})[0].lessonId,'supp2');
assert.throws(()=>replaySources(temporary,{manifest,cases:'J01'}));
set([{id:'unrelated',actual_path:'runs/actual.json',lesson_id:'foreign'}]);assert.throws(()=>replaySources(temporary,{manifest}),/explicitly linked/);
set([{id:'outside',actual_path:'../other.json'}]);assert.throws(()=>replaySources(temporary,{manifest}),/inside project runs/);
set([{id:'same',actual_path:'runs/actual.json'},{id:'same',actual_path:'runs/actual.json'}]);assert.throws(()=>replaySources(temporary,{manifest}),/Unique/);
const historical=replaySources(root);assert.equal(historical.length,8);
const entries=[];
for(const id of ['N01','N02']) {
 const path=resolve(base,'repair-development-final04',id,'actual.json'),record=JSON.parse(readFileSync(path,'utf8'));
 for(const cycle of record.followup_cycles)entries.push({id:id+'-supp'+cycle.index,actual_path:path,lesson_id:cycle.supplement_id,role:'Stored final04 supplementary lesson; final05 pointer regression only, not a new answer or live followup'});
}
const prepared=resolve(base,'saved-final04-supplement-sources.json');
writeFileSync(prepared,JSON.stringify({scope:'GET-only replay targets preserving final04 actual provenance',entries},null,2));
assert.equal(replaySources(root,{manifest:prepared}).length,3);
writeFileSync(resolve(base,'saved-source-preflight.json'),JSON.stringify({status:'PASS',checks:8,actual_model_TTS_OCR_calls:0,live_API_calls:0,
 historical_cases:historical.map(s=>s.id),supplement_targets:entries.map(s=>s.id),originals_unchanged:true,
 scope:'Reads preserved source records; writes only synthetic fixture and derived manifest/report.'},null,2));
console.log(JSON.stringify({status:'PASS',checks:8,actual_model_TTS_OCR_calls:0}));
