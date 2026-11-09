import {parentPort,workerData} from 'node:worker_threads';
import {openSync,writeFileSync,fsyncSync,closeSync,renameSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {performance} from 'node:perf_hooks';

const {actualPath}=workerData;
const journalPath=actualPath+'.journal.jsonl';
let fd,revision=0,finalized=false;
const result={};
const stats={journal_records:0,journal_bytes:0,journal_stringify_ms:0,journal_write_sync_ms:0,full_json_writes:0};
function journal(record) {
  const start=performance.now(),line=JSON.stringify(record)+'\n',serialized=performance.now();
  writeFileSync(fd,line);fsyncSync(fd);
  stats.journal_records++;stats.journal_bytes+=Buffer.byteLength(line);
  stats.journal_stringify_ms+=serialized-start;stats.journal_write_sync_ms+=performance.now()-serialized;
}
function fail(error) {
  try {if(fd!==undefined)closeSync(fd);}catch{}
  fd=undefined;parentPort.postMessage({type:'error',error:String(error)});parentPort.close();
}
try {
  if(existsSync(actualPath))throw Error('Refusing to replace an existing actual result');
  fd=openSync(journalPath,'wx');
  journal({type:'header',version:1,notice:'Append-only checkpoint journal. Absence of finalized actual.json means incomplete, not successful.'});
  parentPort.postMessage({type:'ready'});
  parentPort.on('message',message=>{
    try {
      if(finalized)throw Error('Evidence already finalized');
      if(message.type==='checkpoint') {
        if(!Number.isSafeInteger(message.revision)||message.revision<=revision)throw Error('Evidence revision is stale');
        for(const [key,patch] of Object.entries(message.append)) {
          if((result[key]?.length||0)!==patch.from)throw Error(`Evidence append offset mismatch: ${key}`);
        }
        journal(message); // ACK only after durable complete journal line.
        Object.assign(result,message.set);
        for(const [key,patch] of Object.entries(message.append)) {
          result[key]??=[];
          for(const item of patch.items)result[key].push(item);
        }
        revision=message.revision;parentPort.postMessage({type:'checkpoint',revision});
      } else if(message.type==='finalize') {
        if(message.revision!==revision)throw Error('Final evidence revision mismatch');
        if(existsSync(actualPath))throw Error('Refusing to overwrite an existing actual result');
        const start=performance.now(),text=JSON.stringify(result,null,2),serialized=performance.now();
        const temp=actualPath+'.finalizing';const output=openSync(temp,'wx');
        try {writeFileSync(output,text);fsyncSync(output);}finally{closeSync(output);}
        renameSync(temp,actualPath);stats.full_json_writes++;
        stats.full_json_stringify_ms=serialized-start;stats.full_json_write_ms=performance.now()-serialized;
        stats.final_bytes=Buffer.byteLength(text);stats.final_sha256=createHash('sha256').update(text).digest('hex');
        const receipt={type:'finalized',commit_complete:true,recording_mode:'incremental_worker_journal_v1',revision,journal_path:journalPath,actual_path:actualPath,
          ...stats,parent_stats:message.parent_stats,measurement_boundary:'Full JSON serialization/publication occurs only after observed journey cleanup.'};
        journal(receipt);closeSync(fd);fd=undefined;finalized=true;
        writeFileSync(actualPath+'.writer.json',JSON.stringify(receipt,null,2),{flag:'wx'});
        parentPort.postMessage(receipt);parentPort.close();
      } else throw Error('Unknown evidence writer command');
    }catch(error){fail(error);}
  });
}catch(error){fail(error);}
