// Read-only proof for a cancellation target, independent of response-observer order.
// The caller supplies an authenticated local GET. Never submit or retry a job here.
export async function authorizeJobTarget({jobId,sessionId,get,timeoutMs=15000}) {
  if(!/^[a-f0-9]{32}$/.test(jobId||'') || !/^[a-f0-9]{32}$/.test(sessionId||''))
    throw Error('Invalid job or student session ID');
  if(!Number.isFinite(timeoutMs)||timeoutMs<=0||timeoutMs>15000)
    throw Error('Job ownership read deadline must be at most 15 seconds');
  let timer,job;
  try {
    job=await Promise.race([Promise.resolve().then(()=>get('/jobs/'+jobId)),
      new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Job ownership read deadline')),timeoutMs);})]);
  } finally { clearTimeout(timer); }
  if(job?.id!==jobId)throw Error('Job ID is missing or mismatched');
  if(job.session_id!==sessionId)throw Error('Job belongs to another or missing student session');
  return {job_id:jobId,session_id:sessionId,job_kind:job.kind,job_state:job.state,
    proof:'bounded authenticated GET exact job -> exact new student session'};
}
