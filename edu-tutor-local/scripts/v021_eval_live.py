"""One-pass v0.2.1 app-path evaluation. Private answers are never loaded here.

prepare/freeze-code are CPU only. execute requires an explicit root-provided GO
token and pre-existing code freeze. It uses the unchanged approved scope, at
most two app model attempts per question, no audio/OCR/training/download.
"""
from __future__ import annotations
import argparse,hashlib,json,re,sys,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"runs/v021-support/20261029/independent-eval"
SCOPE="finish-local-tutor-20261028-v1"
TERMINAL={"succeeded","failed","cancelled","interrupted","blocked"}
def stamp():return datetime.now(timezone.utc).isoformat()
def sha(data):return hashlib.sha256(data).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def use_corpus(value=None):
    """Choose an explicitly frozen direct-child corpus; never refill a scope."""
    global BASE
    if value is None:return BASE
    parent=(ROOT/"runs/v021-support/20261029").resolve()
    requested=Path(value)
    if not requested.is_absolute():requested=parent/requested if len(requested.parts)==1 else ROOT/requested
    requested=requested.resolve()
    if requested.parent!=parent or not re.fullmatch(r"independent-eval(?:-r[1-9][0-9]*)?",requested.name):
        raise ValueError("Explicit frozen v0.2.1 corpus directory required")
    if not (requested/"freeze.json").is_file():raise ValueError("Corpus must be frozen before selecting it")
    BASE=requested
    return BASE
def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+".tmp")
    tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    tmp.replace(p)
def current_hashes():
    files=sorted((ROOT/"src/edu_tutor").rglob("*.py"))
    files.extend(sorted((ROOT/"scripts").glob("v021_eval*.py")))
    files.extend(sorted((ROOT/"web/dist").rglob("*")))
    files.extend(ROOT/p for p in ("pyproject.toml",".local/text-inference-policy.json",".local/speech-provider.json",".local/model-selection.json") if (ROOT/p).is_file())
    return {p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in files if p.is_file()}
def check_corpus():
    frozen=read(BASE/"freeze.json")
    path=BASE/"public.jsonl"
    if sha(path.read_bytes())!=frozen["public_sha256"]:raise RuntimeError("Public corpus changed after freeze")
    rows=[json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if len(rows)!=28 or len({r["id"] for r in rows})!=28:raise RuntimeError("Expected28 distinct fixed questions")
    for row in rows:
        if set(row)!={"id","problem"} or any(k in row["problem"] for k in ("expected","query","intent","answer","sql")):
            raise RuntimeError("Private or candidate-derived data in public problem")
    return frozen,rows
def check_code():
    frozen=read(BASE/"code-freeze.json")
    if frozen["source_hashes"]!=current_hashes():raise RuntimeError("Product/configuration changed after code freeze; do not reuse independent evaluation")
    return frozen
class Client:
    def __init__(self):
        self.token=(ROOT/".local/auth-token").read_text(encoding="utf-8").strip()
    def call(self,path,body=None):
        req=Request("http://127.0.0.1:8000"+path,
            data=None if body is None else json.dumps(body,ensure_ascii=False).encode(),
            method="GET" if body is None else "POST",
            headers={"Authorization":"Bearer "+self.token,"Content-Type":"application/json","X-Execution-Allowance":SCOPE})
        with urlopen(req,timeout=30) as response:return json.loads(response.read())
    def budget(self):
        budget=self.call("/api/resources/budget")
        grant=budget.get("active_execution_allowance") or {}
        if grant.get("id")!=SCOPE:raise RuntimeError("Expected existing approved scope")
        if grant.get("training_remaining")!=0:raise RuntimeError("Training accounting differs from preserved baseline")
        return budget
def submit_once(client,folder,name,path,body):
    journal_path=folder/(name+"-submission.json")
    wanted={"path":path,"body":body}
    if journal_path.exists():
        journal=read(journal_path)
        if journal["request"]!=wanted:raise RuntimeError("Saved request differs; no overwrite/retry")
        if journal["status"]=="completed":return journal["response"]
        raise RuntimeError("A POST was already attempted with unknown outcome; read-only recovery required, no automatic retry")
    journal={"at":stamp(),"request":wanted,"status":"submitting"}
    save(journal_path,journal)
    try:response=client.call(path,body)
    except Exception as exc:
        save(journal_path,{**journal,"status":"failed_or_unknown_no_retry","error_type":type(exc).__name__,"error":str(exc)})
        raise
    save(journal_path,{**journal,"status":"completed","completed_at":stamp(),"response":response})
    return response
def await_job(client,folder,kind,job_id,session_id,maximum=320):
    started=time.monotonic()
    while True:
        job=client.call("/api/jobs/"+job_id)
        if job.get("session_id")!=session_id:raise RuntimeError("Job/session ownership mismatch")
        save(folder/(kind+"-job.json"),job)
        if job["state"] in TERMINAL:return job
        if time.monotonic()-started>maximum:
            save(folder/(kind+"-deadline-cancel.json"),client.call("/api/jobs/"+job_id+"/cancel",{}))
            raise TimeoutError("Owned job observation deadline reached; cancelled once, no retry")
        time.sleep(.5)
def freeze_code(args):
    corpus,_=check_corpus()
    path=BASE/"code-freeze.json"
    if path.exists():raise RuntimeError("A code freeze already exists")
    if not args.cpu_receipt or not Path(args.cpu_receipt).is_file():raise RuntimeError("Root-selected completed CPU receipt required")
    cpu=Path(args.cpu_receipt).resolve()
    if not cpu.is_relative_to(ROOT):raise RuntimeError("CPU receipt must be inside this project")
    value={"at":stamp(),"corpus_public_sha256":corpus["public_sha256"],
        "source_hashes":current_hashes(),"cpu_receipt":cpu.relative_to(ROOT).as_posix(),"cpu_receipt_sha256":sha(cpu.read_bytes()),
        "meaning":"Root accepted affected CPU checks before final fixed source app-path evaluation; actual deployment checked separately.",
        "model":"Qwen3-1.7B/base/BF16","voice":"Heami","model_selection_changes":0,"new_training":0,
        "actual_system_prompt":"Product problems.pipeline.model_messages at these frozen source hashes; freeze.json authoring SYSTEM is not injected."}
    save(path,value);print(json.dumps({"status":"code_frozen","at":value["at"],"source_count":len(value["source_hashes"])}))
def prepare(args):
    frozen,rows=check_corpus()
    prepared=BASE/"prepared-public-requests"
    prepared.mkdir(exist_ok=True)
    for row in rows:
        payload={"content":row["problem"]["raw_text"],"problem":row["problem"],"use_rag":False,"verification_mode":"tools",
            "request_id":"v021-"+frozen["public_sha256"][:12]+"-"+row["id"],"adapter":"base"}
        target=prepared/(row["id"]+".json")
        if target.exists() and read(target)!=payload:raise RuntimeError("Prepared public request changed")
        if not target.exists():save(target,payload)
    print(json.dumps({"status":"prepared_no_calls","questions":len(rows),"oracle_loaded":False,"model_calls":0}))
def execute(args):
    if args.go!="ROOT_APPROVED_FINAL_FROZEN_V021":raise RuntimeError("Explicit coordinator GO token required")
    frozen,rows=check_corpus();code=check_code();prepare(args)
    run=BASE/"live-app-v1"
    run.mkdir(exist_ok=True)
    client=Client()
    protocol={"public_sha256":frozen["public_sha256"],"code_freeze_sha256":sha((BASE/"code-freeze.json").read_bytes()),
        "corpus_directory":BASE.relative_to(ROOT).as_posix(),
        "scope":SCOPE,"model":"installed/base/BF16","questions":28,"audio":0,"vision":0,"training":0,
        "expected_oracle_loaded":False,"use_rag":False,"verification_mode":"tools","app_optional_repair_max":1,
        "runner_automatic_retries":0,"actual_system_prompt":"frozen product model_messages; not authoring prompt",
        "not_browser_audio_verification":True}
    if (run/"protocol.json").exists() and read(run/"protocol.json")!=protocol:raise RuntimeError("Previous evaluation protocol differs")
    if not (run/"protocol.json").exists():save(run/"protocol.json",protocol)
    if (run/"result.json").exists() and read(run/"result.json")["status"]=="completed":
        print(json.dumps({"status":"already_completed_no_calls"}));return
    if (run/"result.json").exists() and read(run/"result.json")["status"]=="stopped_no_retry":
        raise RuntimeError("Previous execution stopped; explicit read-only recovery review required, no automatic continuation")
    initial=read(run/"budget-before.json") if (run/"budget-before.json").exists() else client.budget()
    if not (run/"budget-before.json").exists():save(run/"budget-before.json",initial)
    grant=initial["active_execution_allowance"]
    if grant["text_remaining"]<56 or grant["seconds_remaining"]<600:raise RuntimeError("Insufficient current approved headroom; no policy change")
    if any(j["state"] not in TERMINAL for j in client.call("/api/jobs")):raise RuntimeError("Other active jobs; do not overlap GPU queue")
    save(run/"models-before.json",client.call("/api/models"))
    report={"status":"running","started_at":stamp(),"protocol":protocol,"items":[]}
    try:
        for index,row in enumerate(rows,1):
            check_code()
            folder=run/row["id"];folder.mkdir(exist_ok=True)
            if (folder/"result.json").exists():
                report["items"].append(read(folder/"result.json"));continue
            before=client.budget()
            g=before["active_execution_allowance"]
            if g["text_remaining"]<2 or g["seconds_remaining"]<1:raise RuntimeError("Existing scope exhausted before case")
            save(folder/"budget-before.json",before)
            session=submit_once(client,folder,"session","/api/sessions",{"title":"v0.2.1 독립평가 "+row["id"]+" "+frozen["public_sha256"][:8]})
            session_id=session["id"]
            payload=read(BASE/"prepared-public-requests"/(row["id"]+".json"))
            t0=time.monotonic()
            submitted=submit_once(client,folder,"chat","/api/sessions/"+session_id+"/messages",payload)
            job=await_job(client,folder,"chat",submitted["job_id"],session_id)
            result={"id":row["id"],"session_id":session_id,"chat_job_id":job["id"],"chat_state":job["state"],
                "question":row["problem"],"question_to_saved_answer_seconds":time.monotonic()-t0,
                "lesson":None,"message":None,"new_audio_calls":0,"new_vision_calls":0,"human_review":"H_PENDING"}
            if job["state"]!="succeeded":
                result["failure"]=job.get("error") or job["state"]
                save(folder/"result.json",result);report["items"].append(result)
                raise RuntimeError("Actual chat job failed; do not automatically continue or retry a runtime failure")
            messages=client.call("/api/sessions/"+session_id+"/messages")
            candidates=[m for m in messages if m.get("role")=="assistant" and m.get("request_id")==payload["request_id"]]
            if len(candidates)!=1:raise RuntimeError("Expected exactly one saved actual answer")
            result["message"]=candidates[0]
            for attempt in candidates[0].get("model_attempts") or []:
                metadata=attempt.get("generation_snapshot") or {}
                if (metadata.get("model_id")!="Qwen/Qwen3-1.7B" or metadata.get("adapter_id")!="base"
                    or metadata.get("requested_precision")!="bf16"
                    or metadata.get("revision")!="70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"):
                    save(folder/"identity-failure.json",result)
                    raise RuntimeError("Actual model identity differs from frozen base/BF16 selection")
            lesson=submit_once(client,folder,"lesson","/api/lessons",{"session_id":session_id,"message_id":candidates[0]["id"]})
            generated=submit_once(client,folder,"lesson-generate","/api/lessons/"+lesson["id"]+"/generate",{})
            lesson_job=await_job(client,folder,"lesson",generated["job_id"],session_id)
            result["lesson_job_state"]=lesson_job["state"]
            result["lesson"]=client.call("/api/lessons/"+lesson["id"])
            result["question_to_plan_seconds"]=time.monotonic()-t0
            result["model_attempts"]=len(candidates[0].get("model_attempts") or [])
            after=client.budget();save(folder/"budget-after.json",after)
            result["actual_text_attempts"]=before["active_execution_allowance"]["text_remaining"]-after["active_execution_allowance"]["text_remaining"]
            result["charged_seconds"]=before["active_execution_allowance"]["seconds_remaining"]-after["active_execution_allowance"]["seconds_remaining"]
            if result["actual_text_attempts"]>2:raise RuntimeError("More than one app repair attempt")
            save(folder/"result.json",result);report["items"].append(result)
            save(run/"result.json",report)
            if lesson_job["state"]!="succeeded":
                raise RuntimeError("Actual lesson job failed; result preserved, no automatic continuation or retry")
            print(json.dumps({"case":index,"total":28,"id":row["id"],"chat":job["state"],"lesson":result["lesson"].get("status"),
                "plan":result["lesson"].get("plan") is not None,"text_attempts":result["actual_text_attempts"]},ensure_ascii=False),flush=True)
        check_code()
        report.update(status="completed",finished_at=stamp())
    except Exception as exc:
        report.update(status="stopped_no_retry",error_type=type(exc).__name__,error=str(exc),stopped_at=stamp())
        save(run/"result.json",report);save(run/"budget-after.json",client.budget())
        raise
    save(run/"result.json",report);save(run/"budget-after.json",client.budget())
    print(json.dumps({"status":"completed","questions":len(report["items"]),"actual_text_attempts":sum(i["actual_text_attempts"] for i in report["items"]),"audio":0,"oracle_loaded":False}))
def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["prepare","freeze-code","execute"])
    p.add_argument("--cpu-receipt")
    p.add_argument("--go")
    p.add_argument("--corpus",help="Explicit frozen corpus name or path; default is the preserved first independent set")
    args=p.parse_args()
    use_corpus(args.corpus)
    {"prepare":prepare,"freeze-code":freeze_code,"execute":execute}[args.command](args)
if __name__=="__main__":main()

