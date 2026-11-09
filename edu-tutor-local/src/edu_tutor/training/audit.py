"""Persist executed data/SQL/token checks without changing educational review status."""
import hashlib
import json
from pathlib import Path

from .data import load_records, validate_dataset
from .masking import encode_response_only


def audit_dataset(project_root, output_dir, tokenizer_path=None):
    from edu_tutor.evaluation.sql_sandbox import evaluate_sql
    project, output = Path(project_root), Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = sorted((project / "data/demo").glob("*.jsonl"))
    records = load_records(paths)
    report = {"tier":"T0", "dataset":validate_dataset(paths), "human_review":"not_reviewed"}
    sql_results = []
    for record in records:
        if "expected" in record:
            sql_results.append({"id":record["id"], **evaluate_sql(record["expected"]["sql"], record)})
    report["sql_machine_verified"] = {"passed":sum(bool(v["match"]) for v in sql_results),
                                      "total":len(sql_results), "results":sql_results}
    if not all(r["match"] for r in sql_results):
        raise ValueError("Authored SQL expected results do not all match")
    report["actual_qwen_template"] = {"status":"not_run", "reason":"No tokenizer_path supplied"}
    if tokenizer_path:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, local_files_only=True, trust_remote_code=False)
        audits = [{"id":r["id"], "split":r["split"], **encode_response_only(tokenizer, r["messages"])} for r in records]
        (output / "target-token-audit.json").write_text(json.dumps(audits, ensure_ascii=False, indent=2), encoding="utf-8")
        report["actual_qwen_template"] = {"status":"passed", "count":len(audits),
            "max_tokens":max(v["audit"]["valid_length"] for v in audits),
            "template_sha256":hashlib.sha256(tokenizer.chat_template.encode()).hexdigest(),
            "non_thinking":True, "prompt_and_padding_masked":True, "real_eos_retained":True,
            "source":str(Path(tokenizer_path).resolve())}
    (output / "data-audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
