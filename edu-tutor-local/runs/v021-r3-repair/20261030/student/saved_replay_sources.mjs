// Read-only provenance validation for historical cases or exact saved lessons.
import {readFileSync} from 'node:fs';
import {resolve,relative,isAbsolute} from 'node:path';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
const read=p=>JSON.parse(readFileSync(p,'utf8'));
const sha=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
export function replaySources(root,{manifest=null,cases=null}={}) {
  assert(!(manifest&&cases),'Use either an explicit saved-source manifest or historical case IDs');
  const declarations=manifest?read(resolve(root,manifest)).entries:(cases||'J01,J02,J03,J04,J05,J06,J07,J08').split(',').map(id=>{
    assert(/^J0[1-8]$/.test(id));
    return {id,actual_path:read(resolve(root,'runs/v021-support/20261029/student/final-v021-r3-combined',id+'.json')).actual_json};
  });
  assert(Array.isArray(declarations)&&declarations.length>0&&declarations.length<=16,'Bounded nonempty saved source list required');
  const ids=new Set();
  return declarations.map(item=>{
    assert(/^[A-Za-z0-9_-]{1,50}$/.test(item.id)&&!ids.has(item.id),'Unique safe replay case ID required');ids.add(item.id);
    const path=resolve(root,item.actual_path),inside=relative(resolve(root,'runs'),path);
    assert(inside&&!inside.startsWith('..')&&!isAbsolute(inside),'Saved source must be inside project runs');
    const old=read(path);assert(old.status!=='RUNNING'&&old.completed_at,'Only completed immutable actual records may be replayed');
    const allowed=new Set([old.actual_lesson?.id,old.first_playing?.lesson_record_id,...(old.followup_cycles||[]).map(c=>c.supplement_id)].filter(Boolean));
    const lessonId=item.lesson_id||old.actual_lesson?.id||old.first_playing?.lesson_record_id;
    assert(!lessonId||allowed.has(lessonId),'Requested lesson must be explicitly linked by the preserved actual record');
    return {id:item.id,path,source_sha256:sha(path),old,lessonId,role:item.role||'historical_saved_replay'};
  });
}
