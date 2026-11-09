"""Development regression on disclosed historical SQL60 x2. No inference."""
from pathlib import Path
import argparse,hashlib,json,sys
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from edu_tutor.training.finish_app_score import app_score_response,summarize_app
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding="utf-8-sig"))
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--version",required=True)
    args=p.parse_args()
    if not args.version or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in args.version):
        raise ValueError("Explicit version with safe filename characters required")
    out=ROOT/"runs/v021-support/20261029/development-regression"/args.version
    if out.exists():raise RuntimeError("Regression version already exists; do not overwrite or silently rerun")
    dataset=ROOT/"runs/finish-v2/20261028/education/final/test.jsonl"
    records={r["id"]:r for r in (json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line) if "expected" in r}
    assert len(records)==60
    source_names=[p.relative_to(ROOT).as_posix() for p in (ROOT/"src/edu_tutor").rglob("*.py")]
    source_hashes={p:sha(ROOT/p) for p in source_names}
    out.mkdir(parents=True)
    all_results=[]
    for configuration,folder_name in (("base","final-base-bf16-v1"),("adapter1","final-adapter1-bf16-v1")):
        source=ROOT/"runs/finish-v2/20261029/education"/folder_name/"result.json"
        source_hash=sha(source);saved=read(source)
        if saved["status"]!="completed":raise RuntimeError("Prior completed raw result required")
        raw={r["id"]:r for r in saved["items"] if r["id"] in records}
        assert len(raw)==60
        items=[]
        for index,(ident,record) in enumerate(records.items(),1):
            output=raw[ident]
            try:score=app_score_response(record,output.get("actual_answer") or "",output["finish_reason"])
            except Exception as exc:
                score={"id":ident,"accepted":False,"accepted_result_correct":False,"plan_generated":False,
                    "support_status":"app_exception","failure":type(exc).__name__+": "+str(exc),"human_review":"H_PENDING"}
            score.update(raw_answer=output.get("actual_answer"),source_job_id=output.get("job_id"))
            items.append(score)
            if index%10==0:print(json.dumps({"configuration":configuration,"processed":index,"total":60}),flush=True)
        if sha(source)!=source_hash or sha(dataset)!=saved["protocol"]["dataset_sha256"]:
            raise RuntimeError("Original raw evidence or disclosed dataset changed")
        if source_hashes!={p:sha(ROOT/p) for p in source_names}:raise RuntimeError("Product source changed during regression")
        result={"at":datetime.now(timezone.utc).isoformat(),"classification":"DEVELOPMENT_REGRESSION_PREVIOUSLY_DISCLOSED_FINAL",
            "not_new_independent_accuracy":True,"configuration":configuration,"version":args.version,
            "source_raw_result":source.relative_to(ROOT).as_posix(),"source_raw_sha256":source_hash,
            "disclosed_dataset":dataset.relative_to(ROOT).as_posix(),"dataset_sha256":sha(dataset),
            "source_hashes":source_hashes,"items":items,"summary":summarize_app(items),
            "model_calls":0,"audio_calls":0,"vision_calls":0,"new_search_calls":0,"human_review":"H_PENDING",
            "original_0_of_60_record_preserved":True}
        target=out/(configuration+".json")
        target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        all_results.append({"configuration":configuration,"summary":result["summary"],"evidence":target.relative_to(ROOT).as_posix()})
    comparison={"at":datetime.now(timezone.utc).isoformat(),"classification":"DEVELOPMENT_REGRESSION_NOT_INDEPENDENT","conditions":all_results,"new_model_calls":0}
    (out/"comparison.json").write_text(json.dumps(comparison,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(comparison,ensure_ascii=False))
if __name__=="__main__":main()

