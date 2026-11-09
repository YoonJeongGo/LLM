"""Grade sealed v0.2.1 actual app records after execution; no generation/network."""
from __future__ import annotations
import argparse,copy,hashlib,json,sys
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import sqlglot
from sqlglot import exp
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
sys.path.insert(0,str(ROOT/"scripts"))
from edu_tutor.evaluation.sql_sandbox import execute_sql,compare_results
from edu_tutor.problems.sql_response import extract_sql_candidate
from edu_tutor.training.finish_claims import check_explicit_result_claim
from edu_tutor.training.finish_app_score import support_outcome
from v021_eval_live import BASE,check_code,check_corpus,read,save,sha
import v021_eval_live as live
def rows(path):return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s]
def oracle():
    frozen,_=check_corpus()
    path=BASE/"private-oracle.jsonl"
    if sha(path.read_bytes())!=frozen["private_sha256"]:raise RuntimeError("Private oracle changed after freeze")
    return {r["id"]:r for r in rows(path)}
def compare(actual,expected):
    aligned={**actual,"columns":expected["columns"]} if len(actual.get("columns",[]))==len(expected["columns"]) else actual
    return compare_results(aligned,expected)
def intent_signature(sql, table):
    """Independent bounded AST contract; not arbitrary SQL equivalence."""
    query=sqlglot.parse_one(sql,read="sqlite")
    if not isinstance(query,exp.Select) or any(query.args.get(k) for k in ("joins","with_","limit","offset","distinct")) or query.find(exp.Subquery):
        raise ValueError("Outside independently comparable single-table form")
    source=query.args.get("from_")
    if not source or not isinstance(source.this,exp.Table):raise ValueError("Missing single table")
    aliases={n.alias.casefold():n.this for n in query.expressions if isinstance(n,exp.Alias)}
    def node(n,alias_ok=False):
        if n is None:return None
        if isinstance(n,(exp.Alias,exp.Paren,exp.Where,exp.Having)):return node(n.this,alias_ok)
        if isinstance(n,exp.Column):
            if alias_ok and n.name.casefold() in aliases:return node(aliases[n.name.casefold()])
            return ("column",n.name.casefold())
        if isinstance(n,exp.Star):return ("star",)
        if isinstance(n,exp.Null):return ("null",)
        if isinstance(n,exp.Literal):return ("text",n.this) if n.is_string else ("number",float(n.this))
        if isinstance(n,exp.Neg):
            child=node(n.this,alias_ok)
            if child[0]!="number":raise ValueError("Nonliteral negation")
            return ("number",-child[1])
        if isinstance(n,exp.Count) and isinstance(n.this,exp.Literal):return ("count",("star",))
        if isinstance(n,exp.AggFunc):
            return (type(n).__name__.lower(),node(n.this,alias_ok))
        if isinstance(n,exp.Distinct):return ("distinct",tuple(node(x,alias_ok) for x in n.expressions))
        if isinstance(n,(exp.And,exp.Or)):
            kind=type(n)
            def flatten(part):
                if isinstance(part,exp.Paren):return flatten(part.this)
                if isinstance(part,kind):return flatten(part.this)+flatten(part.expression)
                return [node(part,alias_ok)]
            return (kind.__name__.lower(),tuple(sorted(flatten(n),key=repr)))
        if isinstance(n,exp.Not):return ("not",node(n.this,alias_ok))
        if isinstance(n,exp.Is):return ("is",node(n.this,alias_ok),node(n.expression,alias_ok))
        if isinstance(n,(exp.EQ,exp.NEQ,exp.GT,exp.GTE,exp.LT,exp.LTE)):
            left,right=node(n.this,alias_ok),node(n.expression,alias_ok)
            kind=type(n).__name__.lower()
            if left[0] in {"number","text"} and right[0]=="column":
                left,right=right,left
                kind={"gt":"lt","gte":"lte","lt":"gt","lte":"gte"}.get(kind,kind)
            if kind in {"eq","neq"} and repr(left)>repr(right):left,right=right,left
            return (kind,left,right)
        raise ValueError("Unproved AST form:"+type(n).__name__)
    selection=[]
    for n in query.expressions:
        if isinstance(n,exp.Star):selection.extend(("column",c["name"].casefold()) for c in table["columns"])
        else:selection.append(node(n))
    return {"table":source.this.name.casefold(),"select":selection,
        "where":node(query.args.get("where")),
        "group":sorted((node(n) for n in (query.args.get("group") or exp.Group()).expressions),key=repr),
        "having":node(query.args.get("having"),True),
        "order":[(node(n.this,True),bool(n.args.get("desc")),bool(n.args.get("nulls_first")))
                 for n in (query.args.get("order") or exp.Order()).expressions]}
def intent_contract(sql, expected_sql, table):
    try:
        candidate=intent_signature(sql,table)
        reference=intent_signature(expected_sql,table)
    except Exception as exc:return {"status":"not_automatically_comparable","matches":None,"reason":type(exc).__name__+": "+str(exc)}
    equal=candidate==reference
    return {"status":"bounded_AST_contract_match" if equal else "bounded_AST_contract_not_matched",
            "matches":equal,"candidate":candidate,"reference":reference,
            "notice":"A mismatch does not prove every alternative SQL inequivalent; unsupported equivalence remains unproved."}
def raw_score(public,private,text,metadata):
    item={"id":public["id"],"raw_text":text,"finish_reason":metadata.get("finish_reason"),
        "actual_generation_metadata":metadata,"sql_executed":False,"result_correct":False if private.get("expected") else None,
        "free_prose_quality":"H_PENDING","explicit_claim_coverage_is_not_all_prose":True}
    if not text or metadata.get("finish_reason")!="eos":
        return {**item,"failure":"incomplete_or_empty_generation"}
    try:sql=extract_sql_candidate(text)
    except ValueError as exc:return {**item,"failure":"extraction:"+str(exc)}
    actual=execute_sql(sql,{"tables":public["problem"]["tables"]},dialect="sqlite")
    item.update(sql=sql,actual=actual,sql_executed=actual.get("status")=="executed")
    if private.get("expected"):
        item["result_correct"]=compare(actual,private["expected"])
        item["intent_contract"]=intent_contract(sql,private["expected"]["sql"],public["problem"]["tables"][0])
        item["automatic_sql_contract_and_result_correct"]=item["result_correct"] and item["intent_contract"]["matches"] is True
    item["explicit_claim_check"]=check_explicit_result_claim({"id":public["id"],"actual_answer":text,"sql":sql,"actual":actual})
    return item
def summarize(items):
    accepted=[i for i in items if i["app_accepted_lesson"]]
    correct=[i for i in accepted if i["app_contract_and_result_correct"]]
    claims=[i.get("raw_first",{}).get("explicit_claim_check") or {} for i in items]
    return {"questions":len(items),"substantive_response_rate":{"numerator":len(accepted),"denominator":len(items)},
        "correct_among_answered":{"numerator":len(correct),"denominator":len(accepted),"value":len(correct)/len(accepted) if accepted else None},
        "overall_result_match_rate":{"numerator":len(correct),"denominator":len(items)},
        "raw_first_executable":sum(i["raw_first"]["sql_executed"] for i in items),
        "raw_first_fixture_result_correct":sum(i["raw_first"]["result_correct"] is True for i in items),
        "raw_first_contract_and_result_correct":sum(i["raw_first"].get("automatic_sql_contract_and_result_correct") is True for i in items),
        "raw_last_fixture_result_correct":sum(i["raw_last"]["result_correct"] is True for i in items),
        "raw_correct_but_app_stopped":sum(i["raw_first"]["result_correct"] is True and not i["app_accepted_lesson"] for i in items),
        "app_corrected_candidate":sum(i["app_corrected_candidate"] for i in items),
        "app_accepted_fixture_result_matches":sum(i["app_result_correct"] is True for i in items),
        "app_accepted_intent_equivalence_unproved":sum(i["app_accepted_lesson"] and i["app_result_correct"] is True and not i["app_contract_and_result_correct"] for i in items),
        "support_outcomes":dict(Counter(i["support_status"] for i in items)),
        "raw_first_explicit_result_claims_present":sum(bool(i.get("claims")) for i in claims),
        "raw_first_explicit_result_claim_mismatches":sum(i.get("explicit_numeric_mismatch") is True for i in claims),
        "explanation_accuracy":"UNDEFINED_NOT_FULLY_AUTOMATICALLY_GRADED","education_review":"H_PENDING",
        "browser_audio":"NOT_RUN_IN_THIS_28_QUESTION_EVALUATION"}
def grade():
    check_code()
    private=oracle();_,public=check_corpus()
    live=read(BASE/"live-app-v1/result.json")
    if live["status"]!="completed":raise RuntimeError("Complete one-pass actual records required; partial run remains ungraded")
    actual={i["id"]:i for i in live["items"]}
    if set(actual)!=set(private):raise RuntimeError("Missing/duplicate independent cases")
    result=[]
    for visible in public:
        ident=visible["id"];key=private[ident];entry=actual[ident]
        message=entry.get("message") or {};lesson=entry.get("lesson") or {};evidence=message.get("evidence") or {}
        attempts=message.get("model_attempts") or []
        if not attempts:attempts=[{"text":message.get("raw_model_response",""),"generation_snapshot":message.get("generation_snapshot") or {}}]
        first=raw_score(visible,key,attempts[0].get("text",""),attempts[0].get("generation_snapshot") or {})
        last=first if len(attempts)==1 else raw_score(visible,key,attempts[-1].get("text",""),attempts[-1].get("generation_snapshot") or {})
        accepted=evidence.get("status")=="verified" and lesson.get("plan") is not None and lesson.get("speech_allowed") is True
        actual_execution=evidence.get("execution") or {}
        app_correct=accepted and compare(actual_execution,key["expected"]) if key.get("expected") else None
        app_sql=evidence.get("sql") or evidence.get("candidate_sql") or (evidence.get("app_correction") or {}).get("corrected_sql")
        app_contract=intent_contract(app_sql,key["expected"]["sql"],visible["problem"]["tables"][0]) if app_sql and key.get("expected") else {"matches":None,"status":"not_available"}
        item={"id":ident,"cohort":key["cohort"],"family":key["family"],"expected_behavior":key["expected_behavior"],
            "raw_first":first,"raw_last":last,"model_attempt_count":len(attempts),"actual_text_attempts":entry.get("actual_text_attempts"),
            "app_accepted_lesson":accepted,"app_result_correct":app_correct,
            "app_intent_contract":app_contract,
            "app_contract_and_result_correct":app_correct is True and app_contract["matches"] is True,
            "app_corrected_candidate":bool(evidence.get("app_correction")),
            "support_status":support_outcome(evidence,lesson),"app_model_claim_check":evidence.get("raw_model_explanation") or evidence.get("model_claim_check"),
            "app_calculation_status":evidence.get("calculation",{}).get("status"),
            "app_reasons":evidence.get("reasons"),"question_to_plan_seconds":entry.get("question_to_plan_seconds"),
            "source":str((BASE/"live-app-v1"/ident/"result.json").relative_to(ROOT)),
            "plan_step_count":len((lesson.get("plan") or {}).get("steps",[])),
            "human_review":"H_PENDING"}
        if key["family"]=="missing_input":item["boundary_expected_behavior_met"]=not accepted and item["support_status"]=="needs_input"
        elif key["family"]=="unsupported":item["boundary_expected_behavior_met"]=not accepted and item["support_status"]=="unsupported_intent"
        else:item["boundary_expected_behavior_met"]=None
        result.append(item)
    supported=[i for i in result if i["cohort"]=="supported"]
    boundary=[i for i in result if i["cohort"]=="boundary"]
    report={"at":datetime.now(timezone.utc).isoformat(),"classification":"new_frozen_independent_actual_app_path_evaluation",
        "source_sha256":sha((BASE/"live-app-v1/result.json").read_bytes()),"corpus_freeze_sha256":sha((BASE/"freeze.json").read_bytes()),
        "code_freeze_sha256":sha((BASE/"code-freeze.json").read_bytes()),"items":result,"support20":summarize(supported),
        "boundary8":{"questions":len(boundary),"items":boundary,"missing_unsupported_correctly_distinguished":sum(i["boundary_expected_behavior_met"] is True for i in boundary),
                     "missing_unsupported_denominator":4,"cpu_injected_errors_included_in_live_metrics":False},
        "limits":"Value checks preserve duplicate rows and requested ordering; alias labels ignored only when output arity matches. Values and explicit claim checks do not prove all semantic/prose/education correctness.",
        "new_model_calls_for_grading":0,"new_audio_calls":0,"new_vision_calls":0,"human_review":"H_PENDING"}
    target=BASE/"live-app-v1/graded.json"
    if target.exists():raise RuntimeError("Independent grade already exists; preserve it rather than overwrite")
    save(target,report)
    print(json.dumps({"support20":report["support20"],"boundary_classification":report["boundary8"]["missing_unsupported_correctly_distinguished"]},ensure_ascii=False))
def injected():
    check_code()
    private=oracle();_,public=check_corpus();by_id={i["id"]:i for i in public}
    from edu_tutor.problems.models import normalize_problem
    from edu_tutor.problems.app_correction import verify_with_app_correction
    from edu_tutor.problems.evidence import display_answer
    from edu_tutor.lessons.verified import generate_verified_plan
    result=[]
    for ident,key in private.items():
        if key.get("injection") is None:continue
        visible=by_id[ident];problem=normalize_problem(visible["problem"])
        raw=json.dumps({k:key["injection"][k] for k in ("sql","explanation")},ensure_ascii=False)
        evidence=verify_with_app_correction(problem,raw,problem["raw_text"])
        message={"id":"injected-"+ident,"problem":problem,"evidence":evidence,"content":display_answer(evidence),"raw_model_response":raw}
        lesson=generate_verified_plan(message,problem["raw_text"],"injected-lesson-"+ident)
        spoken=" ".join(s.get("speech","") for s in (lesson.get("plan") or {}).get("steps",[]))
        original=(evidence.get("app_correction") or {}).get("original_candidate") or evidence
        candidate_mismatch=original.get("intent",{}).get("status")=="mismatch"
        corrected=bool(evidence.get("app_correction")) and evidence.get("status")=="verified" and compare(evidence.get("execution") or {},key["expected"])
        if key["family"]=="sql_mismatch":
            contract=candidate_mismatch and (evidence.get("status")!="verified" or corrected)
        else:
            contract=key["injection"]["explanation"] not in spoken and lesson.get("plan") is not None and compare(evidence.get("execution") or {},key["expected"])
        result.append({"id":ident,"family":key["family"],"contract_met":contract,"candidate_intent_mismatch":candidate_mismatch,
            "separate_app_correction":corrected,"raw_injected":key["injection"],"evidence":evidence,"lesson":lesson,
            "raw_false_sentence_repeated":key["injection"]["explanation"] in spoken,
            "meaning":"CPU-authored candidate fault; not an actual model failure or independent live item"})
    report={"at":datetime.now(timezone.utc).isoformat(),"mode":"private_fault_injection_CPU_only",
        "cases":len(result),"passed":sum(i["contract_met"] for i in result),"items":result,
        "model_calls":0,"audio_calls":0,"vision_calls":0,"human_review":"H_PENDING",
        "wrong_sql_contract":"Do not approve the wrong candidate as intended. Separately proved app correction is allowed only when original mismatch remains explicit."}
    target=BASE/"injected-cpu-v1.json"
    if target.exists():raise RuntimeError("Fault injection evidence already exists; do not overwrite")
    save(target,report);print(json.dumps({"cases":report["cases"],"passed":report["passed"],"model_calls":0}))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("command",choices=["grade","injected"])
    p.add_argument("--corpus")
    args=p.parse_args()
    BASE=live.use_corpus(args.corpus)
    {"grade":grade,"injected":injected}[args.command]()

