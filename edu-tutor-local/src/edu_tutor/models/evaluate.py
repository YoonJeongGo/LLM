"""Frozen-protocol baseline/adapter evaluation. No reference answers in generation inputs."""
from __future__ import annotations
import hashlib
import json
import time
from pathlib import Path

PROTOCOL = {"version": 1, "max_new_tokens": 256, "do_sample": False, "rag": False,
            "notice": "소규모 데모 평가입니다. 파이프라인 검증용이며, 전체 교육 성능이나 일반화 성능을 보장하지 않습니다."}


def evaluation_job(payload, emit):
    # Explicit precision applies only to this bounded raw-model benchmark.
    # Legacy evaluation and all existing calls remain NF4 by default.
    precision = payload.get("precision", "nf4") if payload.get("kind") == "text_batch" else "nf4"
    if precision not in {"nf4", "bf16"}:
        raise ValueError("Unsupported benchmark precision")
    imports_started = time.perf_counter()
    import torch
    from transformers import StoppingCriteria, StoppingCriteriaList
    from .worker import load_text
    root = Path(payload["root"])
    runtime_import_seconds = time.perf_counter() - imports_started
    torch.cuda.reset_peak_memory_stats()
    load_started = time.perf_counter()
    model_ref = payload.get("model_ref", "installed") if payload.get("kind") == "text_batch" else "installed"
    if model_ref == "installed":
        model, tokenizer, meta = load_text(root, payload.get("adapter"), precision=precision)
    else:
        model, tokenizer, meta = load_text(root, payload.get("adapter"), precision=precision, model_ref=model_ref)
    from .text_eos import generation_eos_ids
    eos_ids = generation_eos_ids(model, tokenizer)
    torch.cuda.synchronize()
    load_seconds = time.perf_counter() - load_started
    inference = meta.get("inference", {})
    load_peak_allocated = torch.cuda.max_memory_allocated()
    load_peak_reserved = torch.cuda.max_memory_reserved()
    explicit = payload.get("kind") == "text_batch"
    rows = payload["items"] if explicit else payload["questions"]
    max_tokens = int(payload.get("max_new_tokens", 256)) if explicit else PROTOCOL["max_new_tokens"]
    if not 16 <= max_tokens <= 512:
        raise ValueError("Evaluation output budget must be 16..512")
    if not isinstance(rows, list) or not 1 <= len(rows) <= (4 if explicit else 12):
        raise ValueError("Evaluation batches contain 1..12 questions")
    cancelled = Path(payload["cancel_path"])
    class Stop(StoppingCriteria):
        def __call__(self, *_args, **_kwargs):
            return cancelled.exists()
    for item_index, record in enumerate(rows):
        prompt = "SQLite 문제에 답하세요. 조건이 충분하면 정확히 JSON {\"sql\":\"SELECT ...\",\"explanation\":\"짧은 설명\"}만 출력하세요. 조건이 부족하면 필요한 조건을 질문하세요."
        messages = record["messages"] if explicit else [{"role":"system","content":prompt},{"role":"user","content":record["question"]}]
        if not isinstance(messages, list) or not 1 <= len(messages) <= 8 or any(m.get("role") not in {"system", "user"} for m in messages):
            raise ValueError("Evaluation input must contain only public system/user questions")
        preparation_started = time.perf_counter()
        torch.cuda.reset_peak_memory_stats()
        inputs = tokenizer.apply_chat_template(messages,
            add_generation_prompt=True, enable_thinking=False, tokenize=True, return_dict=True, return_tensors="pt").to(model.device)
        if inputs["input_ids"].shape[-1] + max_tokens > 2048:
            raise ValueError("Evaluation input exceeds context budget")
        torch.cuda.synchronize()
        preparation_seconds = time.perf_counter() - preparation_started
        started = time.perf_counter()
        eos_options = {"eos_token_id": eos_ids}
        with torch.inference_mode():
            output = model.generate(**inputs, **eos_options, max_new_tokens=max_tokens, do_sample=False,
                pad_token_id=tokenizer.pad_token_id, stopping_criteria=StoppingCriteriaList([Stop()]))
        torch.cuda.synchronize()
        generation_seconds = time.perf_counter() - started
        tokens = output[0][inputs["input_ids"].shape[-1]:].tolist()
        free_bytes, total_bytes = torch.cuda.mem_get_info()
        if cancelled.exists():
            raise RuntimeError("Evaluation cancelled")
        emit("evaluation_item", id=record["id"], text=tokenizer.decode(tokens, skip_special_tokens=True),
             finish_reason="eos" if tokens and tokens[-1] in eos_ids else "length",
             model_ref=model_ref, model_id=meta.get("model_id"), eos_token_ids=eos_ids,
             output_tokens=len(tokens), latency_seconds=generation_seconds,
             precision=precision, inference=inference,
             phase_timing={"clock":"worker_perf_counter", "runtime_import_seconds":runtime_import_seconds if item_index == 0 else 0,
                "loader_import_seconds":inference.get("loader_import_seconds", 0) if item_index == 0 else 0,
                "load_excluding_loader_import_seconds":max(0, load_seconds-inference.get("loader_import_seconds", 0)) if item_index == 0 else 0,
                "preparation_seconds":preparation_seconds, "generation_seconds":generation_seconds,
                "notice":"First generation includes initial CUDA/kernel setup; no hidden warmup. Different precision may emit a different number of tokens."},
             memory={"load_peak_allocated_bytes":load_peak_allocated, "load_peak_reserved_bytes":load_peak_reserved,
                "request_peak_allocated_bytes":torch.cuda.max_memory_allocated(),
                "request_peak_reserved_bytes":torch.cuda.max_memory_reserved(),
                "allocated_bytes":torch.cuda.memory_allocated(), "reserved_bytes":torch.cuda.memory_reserved(),
                "device_free_bytes":free_bytes, "device_total_bytes":total_bytes,
                "scope":"Per-process allocator peaks; device free includes other processes and driver allocations"},
             peak_vram_bytes=torch.cuda.max_memory_allocated(), revision=meta["revision"],
             model_load_seconds=load_seconds if item_index == 0 else 0,
             model_load_count=1 if item_index == 0 else 0, model_object_id=id(model),
             worker_pid=__import__("os").getpid(), input_tokens=int(inputs["input_ids"].shape[-1]),
             batch_index=item_index, max_new_tokens=max_tokens)


def run_evaluation(root, output_dir, adapter=None, *, cancel_event=None, job_id=None):
    from edu_tutor.evaluation.sql_sandbox import extract_sql, evaluate_sql
    from .runtime import run_worker
    root, output_dir = Path(root), Path(output_dir)
    data_file = root / "data/demo/test.jsonl"
    records = [json.loads(line) for line in data_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    # Only public problem text is passed into the model subprocess.
    questions = [{"id": r["id"], "question": next(m["content"] for m in r["messages"] if m["role"] == "user")} for r in records]
    by_id = {r["id"]:r for r in records}
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {"tier":"T2", "protocol":PROTOCOL, "dataset_sha256":hashlib.sha256(data_file.read_bytes()).hexdigest(),
              "adapter":str(adapter) if adapter else None, "human_review":"not_reviewed", "items":[], "status":"running"}
    artifact = output_dir / "evaluation.json"
    def save():
        artifact.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    save()
    try:
        payload = {"kind":"evaluation","questions":questions,"adapter":str(adapter) if adapter else None}
        if job_id:
            payload["job_id"] = job_id
        for event in run_worker(payload, root=root, timeout=900, cancel_event=cancel_event):
            if event["type"] != "evaluation_item":
                continue
            record = by_id[event["id"]]
            item = {k:v for k,v in event.items() if k != "type"}
            item["sql_match"] = False
            if "expected" in record and event["finish_reason"] == "eos":
                try:
                    sql = extract_sql(event["text"])
                    result = evaluate_sql(sql, record)
                    item.update(sql=sql, sql_result=result, sql_match=result["match"])
                except ValueError as exc:
                    item["parse_error"] = str(exc)
            elif "expected" not in record:
                item["clarification_auto_signal"] = any(word in event["text"] for word in ["알려", "필요", "조건", "제공", "확인"])
                item["clarification_quality"] = "not_reviewed"
            report["items"].append(item)
            print(json.dumps({"id":item["id"],"finish_reason":item["finish_reason"],"sql_match":item["sql_match"]},ensure_ascii=False),flush=True)
            save()
        if cancel_event is not None and cancel_event.is_set():
            report.update(status="cancelled")
            return report
        if sorted(i["id"] for i in report["items"]) != sorted(by_id):
            raise RuntimeError("평가 일부 문항이 누락되어 완료로 기록할 수 없습니다.")
        sql_ids = {r["id"] for r in records if "expected" in r}
        report.update(status="completed", sql_correct=sum(i["sql_match"] for i in report["items"] if i["id"] in sql_ids),
                      sql_total=len(sql_ids), total=len(records), truncated=sum(i["finish_reason"] != "eos" for i in report["items"]))
    except Exception as exc:
        if cancel_event is not None and cancel_event.is_set():
            report.update(status="cancelled", error=str(exc))
            return report
        report.update(status="failed",error=str(exc))
        raise
    finally:
        save()
    return report
