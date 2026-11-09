// Append-only journal during observation; one atomic full JSON after cleanup.
// The main event loop never stringifies the growing full result.
import {Worker} from 'node:worker_threads';

const appendKeys=new Set(['requests','responses','events','native_media','scene_samples','screenshots','samples','errors','blocked_requests']);
const immutableKeys=new Set(['id','version','attempt','started_at','spec','provenance','before','source_hashes']);

export class EvidenceWriter {
  constructor(actualPath,{onError=()=>{}}={}) {
    this.actualPath=actualPath;this.onError=onError;this.latest=null;this.revision=0;this.written=0;
    this.cursors=new Map();this.sentImmutable=new Set();this.waiters=[];this.ready=false;this.busy=false;
    this.scheduled=false;this.closing=false;this.finalized=false;this.error=null;
    this.stats={checkpoint_requests:0,checkpoint_messages:0,max_pending_messages:0,full_result_posts:0};
    this.worker=new Worker(new URL('./evidence_writer_worker.mjs',import.meta.url),{workerData:{actualPath}});
    this.worker.on('message',message=>{
      if(message.type==='ready')this.ready=true;
      else if(message.type==='checkpoint') {this.busy=false;this.written=message.revision;this.resolveWaiters();}
      else if(message.type==='finalized') {this.finalized=true;this.finalResolve?.(message);}
      else if(message.type==='error')this.fail(Error(message.error));
      this.pump();
      if(!this.busy&&this.written===this.revision&&!this.closing)this.worker.unref();
    });
    this.worker.on('error',error=>this.fail(error));
    this.worker.on('exit',code=>{if(!this.finalized&&!this.error)this.fail(Error(`Evidence writer exited before finalization (${code})`));});
  }
  fail(error) {
    if(this.error)return;
    this.error=error;this.busy=false;
    for(const waiter of this.waiters.splice(0))waiter.reject(error);
    this.finalReject?.(error);this.onError(error);
  }
  assertHealthy(){if(this.error)throw this.error;if(this.closing)throw Error('Evidence writer is closing');}
  checkpoint(record) {
    this.assertHealthy();this.latest=record;this.revision++;this.stats.checkpoint_requests++;
    this.worker.ref();this.schedule();return this.revision;
  }
  schedule() {
    if(this.scheduled)return;
    this.scheduled=true;setImmediate(()=>{this.scheduled=false;this.pump();});
  }
  pump() {
    if(!this.ready||this.busy||this.error||this.written===this.revision||this.finalized)return;
    try {
      const set={},append={};
      for(const [key,value] of Object.entries(this.latest)) {
        if(appendKeys.has(key)) {
          if(!Array.isArray(value))throw Error(`Evidence append field is not an array: ${key}`);
          const from=this.cursors.get(key)||0;
          if(value.length<from)throw Error(`Evidence append-only array shrank: ${key}`);
          // Only newly captured entries cross the thread boundary. Old entries
          // remain in both the original result and the worker's reconstruction.
          if(value.length>from||!this.cursors.has(key))append[key]={from,items:value.slice(from)};
        } else if(!immutableKeys.has(key)||!this.sentImmutable.has(key))set[key]=value;
      }
      const revision=this.revision;
      this.busy=true;
      this.worker.postMessage({type:'checkpoint',revision,set,append});
      for(const [key,value] of Object.entries(append))this.cursors.set(key,value.from+value.items.length);
      for(const key of Object.keys(set))if(immutableKeys.has(key))this.sentImmutable.add(key);
      this.stats.checkpoint_messages++;this.stats.max_pending_messages=Math.max(this.stats.max_pending_messages,1);
    } catch(error){this.fail(error);}
  }
  resolveWaiters() {
    const pending=[];
    for(const waiter of this.waiters) {
      if(this.written>=waiter.revision)waiter.resolve();else pending.push(waiter);
    }
    this.waiters=pending;
  }
  async flush() {
    if(this.error)throw this.error;
    const revision=this.revision;
    if(this.written>=revision)return;
    this.worker.ref();this.schedule();
    await new Promise((resolve,reject)=>this.waiters.push({revision,resolve,reject}));
  }
  async finalize(record) {
    try {
      this.checkpoint(record);
      this.closing=true;
      await this.flush();
      if(this.error)throw this.error;
      this.worker.ref();
      return await new Promise((resolve,reject)=>{
        this.finalResolve=resolve;this.finalReject=reject;
        this.worker.postMessage({type:'finalize',revision:this.written,parent_stats:this.stats});
      });
    } finally {await this.worker.terminate();}
  }
}
