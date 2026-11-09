"""CPU development reprocessing of a completed, now disclosed independent run."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,sys,hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
sys.path.insert(0,str(ROOT/"scripts"))
import v021_eval_live as live
from edu_tutor.problems.models import normalize_problem
from edu_tutor.problems.app_correction import verify_with_app_correction
from edu_tutor.problems.evidence import display_answer
from edu_tutor.lessons.verified import generate_verified_plan
from edu_tutor.training.finish_app_score import support_outcome
from v021_eval_grade import compare,intent_contract
def read(p):return json.loads(p.read_text(encoding="utf-8-sig"))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def lines(p):return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line]
def score(public,private,attempt):
    raw=attempt.get("text","")
    reason=(attempt.get("generation_snapshot") or {}).get("finish_reason")
    if not raw or reason!="eos":
        return {"accepted":False,"correct":False,"support_status":"invalid_candidate_or_mismatch","failure":"incomplete_or_empty_generation"}
    # The private oracle is not passed to any product construction function.
    problem=normalize_problem(public["problem"])
    evidence=verify_with_app_correction(problem,raw,problem["raw_text"])
    message={"id":"saved-regression-"+public["id"],"problem":problem,"evidence":evidence,
        "content":display_answer(evidence),"raw_model_response":raw}
    lesson=generate_verified_plan(message,problem["raw_text"],"saved-regression-lesson-"+public["id"])
    accepted=evidence.get("status")=="verified" and lesson.get("plan") is not None and lesson.get("speech_allowed") is True
    expected=private.get("expected")
    matches=accepted and compare(evidence.get("execution") or {},expected) if expected else None
    contract=intent_contract(evidence["sql"],expected["sql"],problem["tables"][0]) if expected and evidence.get("sql") else {"matches":None}
    return {"accepted":accepted,"correct":matches is True and contract["matches"] is True,
        "fixture_result_match":matches,"private_AST_contract":contract,"support_status":support_outcome(evidence,lesson),
        "app_correction":bool(evidence.get("app_correction")),"raw_model_response":raw,
        "evidence":evidence,"lesson":lesson,"human_review":"H_PENDING"}
def summary(items,key):
    selected=[i[key] for i in items if i["cohort"]=="supported"]
    accepted=sum(i["accepted"] for i in selected);correct=sum(i["correct"] for i in selected)
    return {"denominator":len(selected),"accepted":accepted,"correct":correct,
        "correct_among_answered":{"numerator":correct,"denominator":accepted,"value":correct/accepted if accepted else None},
        "app_corrected_candidates":sum(i.get("app_correction") is True for i in selected)}
def main():
    p=argparse.ArgumentParser();p.add_argument("--corpus",required=True);p.add_argument("--version",required=True)
    args=p.parse_args()
    if not args.version or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in args.version):
        raise ValueError("Explicit safe version name required")
    base=live.use_corpus(args.corpus)
    frozen,public=live.check_corpus()
    source=base/"live-app-v1/result.json"
    actual=read(source)
    if actual.get("status")!="completed":raise RuntimeError("Only a completed, already evaluated corpus may become development regression")
    private_path=base/"private-oracle.jsonl"
    if sha(private_path)!=frozen["private_sha256"]:raise RuntimeError("Private oracle changed")
    private={r["id"]:r for r in lines(private_path)}
    byid={r["id"]:r for r in actual["items"]}
    hashes=live.current_hashes()
    originals={source:sha(source),base/"live-app-v1/graded.json":sha(base/"live-app-v1/graded.json"),
        base/"freeze.json":sha(base/"freeze.json"),base/"public.jsonl":sha(base/"public.jsonl"),private_path:sha(private_path)}
    target=base/"development-reprocessing"/args.version
    if target.exists():raise RuntimeError("Preserve prior development reprocessing; choose a new explicit version")
    target.mkdir(parents=True)
    items=[]
    for index,visible in enumerate(public,1):
        prior=byid[visible["id"]];message=prior.get("message") or {}
        attempts=message.get("model_attempts") or [{"text":message.get("raw_model_response",""),"generation_snapshot":message.get("generation_snapshot") or {}}]
        first=score(visible,private[visible["id"]],attempts[0])
        last=first if len(attempts)==1 else score(visible,private[visible["id"]],attempts[-1])
        item={"id":visible["id"],"cohort":private[visible["id"]]["cohort"],"family":private[visible["id"]]["family"],
            "raw_first":first,"raw_last":last,"original_model_attempts":len(attempts)}
        items.append(item)
        if index%7==0:print(json.dumps({"processed":index,"total":28}),flush=True)
    if hashes!=live.current_hashes():raise RuntimeError("Source changed while reprocessing; do not claim one-version result")
    if any(sha(path)!=value for path,value in originals.items()):raise RuntimeError("Original independent result/oracle changed")
    report={"at":datetime.now(timezone.utc).isoformat(),"classification":"DEVELOPMENT_REPROCESSING_AFTER_DISCLOSURE_NOT_NEW_INDEPENDENT_EVALUATION",
        "source_execution":source.relative_to(ROOT).as_posix(),"original_hashes":{p.relative_to(ROOT).as_posix():v for p,v in originals.items()},
        "current_source_hashes":hashes,"original_frozen_code_hash":sha(base/"code-freeze.json"),
        "items":items,"support20_first":summary(items,"raw_first"),"support20_last":summary(items,"raw_last"),
        "new_model_calls":0,"new_audio_calls":0,"new_vision_calls":0,"human_review":"H_PENDING"}
    (target/"result.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"first":report["support20_first"],"last":report["support20_last"],"new_model_calls":0},ensure_ascii=False))
if __name__=="__main__":main()

