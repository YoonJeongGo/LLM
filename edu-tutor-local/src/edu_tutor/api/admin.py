from __future__ import annotations
import json
from uuid import uuid4
from typing import Literal

from fastapi import File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from edu_tutor.jobs.lease import GPULease, LeaseBusy
from edu_tutor.jobs.manager import TERMINAL
from edu_tutor.models.registry import adapters, selection
from edu_tutor.storage.db import utcnow


EDUCATION_DATASETS = {
    "finish-v2": ("configs/finish_education.yaml", (
        "runs/finish-v2/20261028/education/development/train.jsonl",
        "runs/finish-v2/20261028/education/development/validation.jsonl")),
    "finish-v2-diverse-v2": ("configs/finish_education_diverse_v2.yaml", (
        "runs/finish-v2/20261029/education/candidate-diverse-v2/train.jsonl",
        "runs/finish-v2/20261028/education/development/validation.jsonl")),
    "finish-v2-reason-v3": ("configs/finish_education_reason_v3.yaml", (
        "runs/finish-v2/20261029/education/candidate-reason-v3/train.jsonl",
        "runs/finish-v2/20261028/education/development/validation.jsonl")),
}


class TrainInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: str = Field(pattern="^(smoke|demo|education)$")
    request_id: str = Field(min_length=8, max_length=100)
    dataset_id: str = Field(default="demo", min_length=1, max_length=100)


class TokenInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=12000)


class SelectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    adapter_id: str | None = Field(default=None, max_length=100)


class EvaluationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=1, max_length=100)
    request_id: str = Field(min_length=8, max_length=100)


class EvaluationQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=100)
    messages: list[dict[str, str]] = Field(min_length=1, max_length=8)


class TextBatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_ref: Literal["installed", "qwen3-4b-instruct-2507"] = "installed"
    precision: Literal["nf4", "bf16"] = "nf4"
    request_id: str = Field(min_length=8, max_length=100)
    adapter: str = "base"
    max_new_tokens: int = Field(default=256, ge=16, le=512)
    items: list[EvaluationQuestion] = Field(min_length=1, max_length=4)


class CandidateDownloadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: Literal["qwen3-4b-instruct-2507"]
    request_id: str = Field(min_length=8, max_length=100)


class ReviewScores(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correctness: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    grounding: int = Field(ge=1, le=5)


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    item_id: str = Field(min_length=1, max_length=100)
    scores: ReviewScores
    comment: str = Field(default="", max_length=2000)


def register_admin(app, root, store, jobs):
    def dataset_report():
        from edu_tutor.training.data import validate_dataset
        return validate_dataset(sorted((root / "data/demo").glob("*.jsonl")), profile="demo")

    @app.get("/api/datasets")
    def datasets():
        return {"datasets": [{"id": "demo", "profile": "demo", "human_review": "not_reviewed", **dataset_report()}, *store.list("datasets")]}

    @app.post("/api/datasets", status_code=201)
    async def upload_dataset(file: UploadFile = File(...), title: str = Form("데이터셋")):
        from edu_tutor.training.data import validate_dataset
        raw = await file.read(5 * 1024 * 1024 + 1)
        if len(raw) > 5 * 1024 * 1024:
            raise HTTPException(413, "학습 데이터는 5MiB 이하여야 합니다.")
        try:
            records = [json.loads(line) for line in raw.decode("utf-8-sig").splitlines() if line.strip()]
        except (UnicodeError, ValueError) as exc:
            raise HTTPException(422, "UTF-8 JSONL 형식이 필요합니다.") from exc
        if len(records) > 2000:
            raise HTTPException(422, "개인용 업로드는 2,000개 예제까지 지원합니다.")
        report = validate_dataset(records=records, profile="demo", enforce_minimums=False)
        ident = uuid4().hex
        store.file("datasets", ident, ".jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8")
        value = {"id": ident, "title": title[:150], "created_at": utcnow(), "review_status": "uploaded_unreviewed", **report}
        store.record("dataset_upload", ident, sha256=report["sha256"])
        return store.put("datasets", value)

    @app.post("/api/datasets/{ident}/validate")
    def validate_uploaded(ident: str):
        from edu_tutor.training.data import validate_dataset
        if ident == "demo":
            return dataset_report()
        if not store.get("datasets", ident):
            raise HTTPException(404, "자료가 없습니다.")
        return validate_dataset([store.file("datasets", ident, ".jsonl")], profile="demo", enforce_minimums=False)

    @app.post("/api/datasets/validate")
    def validate_data():
        return dataset_report()

    @app.get("/api/training/config")
    def training_config():
        import yaml
        config = yaml.safe_load((root / "configs/local_8gb.yaml").read_text(encoding="utf-8"))
        return {"training":config["training"], "budgets":config["budgets"], "model":config["models"]["text"],
                "production_supported":False, "profile":"demo"}

    @app.get("/api/datasets/{ident}/token-audit")
    def token_audit(ident: str):
        from transformers import AutoTokenizer
        from edu_tutor.training.data import load_records
        from edu_tutor.training.masking import encode_response_only
        import yaml
        report = dataset_report() if ident == "demo" else validate_uploaded(ident)
        paths = sorted((root / "data/demo").glob("*.jsonl")) if ident == "demo" else [store.file("datasets", ident, ".jsonl")]
        records = load_records(paths)
        folder = root / ".local/models/text"
        if not (folder / "model-manifest.json").exists():
            raise HTTPException(409, "실제 토크나이저 모델을 먼저 설치하세요.")
        tokenizer = AutoTokenizer.from_pretrained(folder, local_files_only=True, trust_remote_code=False)
        config = yaml.safe_load((root / "configs/local_8gb.yaml").read_text(encoding="utf-8"))
        limit = config["training"]["max_sequence_length"]
        items = []
        for record in records:
            try:
                encoded = encode_response_only(tokenizer, record["messages"], limit)
                items.append({"id":record["id"],"split":record["split"],"valid":True, **encoded["audit"]})
            except ValueError as exc:
                items.append({"id":record["id"],"split":record["split"],"valid":False,"error":str(exc)})
        return {"dataset_sha256":report["sha256"], "max_sequence_length":limit, "total":len(items),
                "valid":sum(item["valid"] for item in items), "items":items, "tier":"T0", "uses_actual_tokenizer":True}

    @app.post("/api/train", status_code=202)
    def train(body: TrainInput):
        from edu_tutor.models import budget as budget_module
        from edu_tutor.models.execution_context import execution_allowance
        scope_id = execution_allowance.get()
        if not getattr(budget_module, "training_allowed", lambda _root: not budget_module.policy(_root).get("enabled"))(root):
            raise HTTPException(409,"현재 승인에는 사용할 수 있는 학습 예산이 없습니다.")
        from edu_tutor.models.runtime import model_status
        if not model_status(root)["ready"]:
            raise HTTPException(409, "로컬 GPU 모델 준비가 필요합니다.")
        dataset_paths = None
        config = root / "configs/local_8gb.yaml"
        if body.profile == "education":
            if body.dataset_id not in EDUCATION_DATASETS or not scope_id:
                raise HTTPException(422, "교육 실험에는 등록된 finish-v2 데이터와 명시적 승인 범위가 필요합니다.")
            config_name, data_names = EDUCATION_DATASETS[body.dataset_id]
            config = root / config_name
            dataset_paths = [root / name for name in data_names]
            if not config.is_file() or not all(path.is_file() for path in dataset_paths):
                raise HTTPException(409, "교육 데이터 검증을 먼저 완료하세요.")
        elif body.dataset_id == "demo":
            dataset_report()
        else:
            validate_uploaded(body.dataset_id)
            dataset_paths = [store.file("datasets", body.dataset_id, ".jsonl")]
        with jobs.lock:
            # An idempotent resubmit must return its original job even while active.
            for job in store.list("jobs"):
                if job["kind"] == "training" and job.get("request_id") == body.request_id:
                    return job
            if any(j["state"] not in TERMINAL for j in store.list("jobs")):
                raise HTTPException(409, "진행 중인 작업을 완료하거나 중단한 후 학습하세요.")
            def run(ident, cancel):
                from edu_tutor.training.runner import run_gpu_training
                folder = root / "runs" / ("train-" + ident)
                folder.mkdir(parents=True, exist_ok=True)
                jobs.update(ident, state="running", artifact=str(folder.relative_to(root)))
                options = {"scope_id": scope_id} if body.profile == "education" else {}
                report = run_gpu_training(config, root / ".local/models/text", folder,
                    mode=body.profile, cancel_event=cancel, job_id=ident, dataset_paths=dataset_paths, **options)
                if report.get("status") != "passed" and not cancel.is_set():
                    jobs.update(ident, result=report)
                    raise RuntimeError("학습이 제한 내 완료되지 않았습니다. 실제 step과 산출물을 확인하세요.")
                return report
            return jobs.submit("training", run, request_id=body.request_id)

    @app.get("/api/adapters")
    def list_adapters():
        return {"adapters": adapters(root), **selection(root)}

    def select(ident, action):
        with jobs.lock:
            if any(j["state"] not in TERMINAL for j in store.list("jobs")):
                raise HTTPException(409, "실행 중인 작업이 있어 모델을 교체할 수 없습니다.")
            current = selection(root)
            if ident is not None:
                candidate = next((item for item in adapters(root) if item["id"] == ident), None)
                if not candidate:
                    raise HTTPException(404, "등록된 어댑터를 찾을 수 없습니다.")
                if not candidate.get("eligible"):
                    raise HTTPException(409, "학습 및 별도 프로세스 재로딩 검증을 완료한 어댑터만 선택할 수 있습니다.")
                base = json.loads((root / ".local/models/text/model-manifest.json").read_text(encoding="utf-8"))
                if candidate["base_revision"] != base["revision"] or candidate.get("base_model_id") != base["model_id"]:
                    raise HTTPException(409, "기반 모델 revision이 일치하지 않습니다.")
            try:
                with GPULease(store.local, "selection-" + uuid4().hex):
                    value = {"active_adapter": ident, "history": current["history"] + [current["active_adapter"]], "updated_at": utcnow()}
                    path = store.local / "model-selection.json"
                    temp = path.with_suffix(".tmp")
                    temp.write_text(json.dumps(value), encoding="utf-8")
                    temp.replace(path)
                    store.record(action, ident or "base")
                    return value
            except LeaseBusy as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.post("/api/adapters/select")
    def select_adapter(body: SelectionInput):
        return select(body.adapter_id, "adapter_select")

    @app.post("/api/adapters/rollback")
    def rollback_adapter():
        current = selection(root)
        return select(current["history"][-1] if current["history"] else None, "adapter_rollback")

    @app.get("/api/evaluations")
    def evaluations():
        import hashlib
        test_file = root / "data/demo/test.jsonl"
        test_bytes = test_file.read_bytes() if test_file.is_file() else b""
        test_hash = hashlib.sha256(test_bytes).hexdigest()
        questions = {r["id"]:next((m["content"] for m in r["messages"] if m["role"] == "user"), "")
                     for r in (json.loads(line) for line in test_bytes.decode("utf-8").splitlines() if line.strip())}
        values = []
        for folder in (root / "runs").glob("*"):
            if not folder.is_dir():
                continue
            for name in ("manifest.json", "evaluation.json", "baseline.json"):
                file = folder / name
                if file.exists():
                    value = json.loads(file.read_text(encoding="utf-8"))
                    if value.get("dataset_sha256") == test_hash:
                        for item in value.get("items", []):
                            if item.get("id") in questions:
                                item["question"] = questions[item["id"]]
                    values.append({"run_id": folder.name, "artifact": name, "report": value})
        return {"reports": values, "notice": "소규모 데모 평가입니다. 파이프라인 검증용이며, 전체 교육 성능이나 일반화 성능을 보장하지 않습니다."}

    @app.post("/api/models/text-candidate/download", status_code=202)
    def candidate_download(body: CandidateDownloadInput):
        from edu_tutor.models.execution_context import execution_allowance
        from edu_tutor.models.text_candidate import SCOPE
        scope = execution_allowance.get()
        if scope != SCOPE:
            raise HTTPException(409, "후보 다운로드에는 현재 통합 승인 ID가 필요합니다.")
        with jobs.lock:
            for previous in store.list("jobs"):
                if previous["kind"] == "download" and previous.get("request_id") == body.request_id:
                    return previous
            if any(job["state"] not in TERMINAL for job in store.list("jobs")):
                raise HTTPException(409, "진행 중인 작업 완료 후 후보를 준비하세요.")
            def run(ident, cancel):
                from edu_tutor.models.candidate_download import download_candidate
                folder = "runs/candidate-download-" + ident
                jobs.update(ident, state="running", artifact=folder)
                return download_candidate(root, ident, scope, cancel,
                    progress=lambda value: jobs.update(ident, progress=value))
            return jobs.submit("download", run, request_id=body.request_id)

    @app.post("/api/evaluations/text-batch", status_code=202)
    def text_batch(body: TextBatchInput):
        """Bounded raw-model measurement; receives public questions, never answer keys."""
        from edu_tutor.models.execution_context import execution_allowance
        from edu_tutor.models.registry import resolve_adapter
        from edu_tutor.models.runtime import run_worker
        scope = execution_allowance.get()
        if not scope:
            raise HTTPException(409, "실제 평가에는 명시적인 실행 승인 범위가 필요합니다.")
        if len({item.id for item in body.items}) != len(body.items):
            raise HTTPException(422, "평가 문항 ID가 중복되었습니다.")
        for item in body.items:
            if any(set(m) != {"role", "content"} or m["role"] not in {"system", "user"}
                   or not m["content"].strip() for m in item.messages):
                raise HTTPException(422, "평가 입력에는 공개 system/user 질문만 포함하세요.")
            if sum(len(m["content"]) for m in item.messages) > 12000:
                raise HTTPException(422, "평가 문항 입력이 너무 깁니다.")
        if body.model_ref != "installed":
            from edu_tutor.models.text_candidate import resolve_candidate, SCOPE
            if scope != SCOPE or body.adapter != "base" or body.precision != "nf4":
                raise HTTPException(409, "후보 비교는 현재 통합 승인에서 base/NF4만 허용합니다.")
            try:
                resolve_candidate(root, body.model_ref, None, body.precision)
            except (ValueError, OSError) as exc:
                raise HTTPException(409, str(exc)) from exc
        adapter = resolve_adapter(body.adapter, root, use_selection=False)
        with jobs.lock:
            for previous in store.list("jobs"):
                if previous["kind"] == "evaluation" and previous.get("request_id") == body.request_id:
                    return previous
            if any(job["state"] not in TERMINAL for job in store.list("jobs")):
                raise HTTPException(409, "진행 중인 작업 완료 후 평가하세요.")
            def run(ident, cancel):
                folder = root / "runs" / ("text-batch-" + ident)
                folder.mkdir()
                report = {"status": "running", "scope": scope, "adapter": adapter,
                          "items": [], "human_review": "H_PENDING", "request": body.model_dump()}
                def save():
                    (folder / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                save()
                jobs.update(ident, state="running", artifact=str(folder.relative_to(root)))
                try:
                    payload = {"kind": "text_batch", "items": [item.model_dump() for item in body.items],
                               "adapter": adapter, "job_id": ident, "max_new_tokens": body.max_new_tokens, "precision": body.precision,
                               "model_ref": body.model_ref,
                               "execution_allowance_id": scope}
                    for event in run_worker(payload, root=root, cancel_event=cancel, timeout=300):
                        if event.get("type") == "evaluation_item":
                            report["items"].append(event)
                            jobs.update(ident, progress=len(report["items"]) / len(body.items))
                            save()
                    report["status"] = "cancelled" if cancel.is_set() else "completed"
                    if not cancel.is_set() and len(report["items"]) != len(body.items):
                        raise RuntimeError("평가 문항 일부가 누락됐습니다.")
                    return report
                except Exception as exc:
                    report.update(status="failed", error=str(exc))
                    raise
                finally:
                    save()
            return jobs.submit("evaluation", run, request_id=body.request_id)

    @app.post("/api/evaluations", status_code=202)
    def start_evaluation(body: EvaluationInput):
        from edu_tutor.models.registry import resolve_adapter
        from edu_tutor.models.runtime import model_status
        from edu_tutor.models.evaluate import run_evaluation
        if not model_status(root)["ready"]:
            raise HTTPException(409, "로컬 GPU 모델 준비가 필요합니다.")
        try:
            adapter = resolve_adapter(body.run_id, root, use_selection=False)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        with jobs.lock:
            for job in store.list("jobs"):
                if job["kind"] == "evaluation" and job.get("request_id") == body.request_id:
                    return job
            if any(j["state"] not in TERMINAL for j in store.list("jobs")):
                raise HTTPException(409, "진행 중인 작업을 완료하거나 중단한 후 평가하세요.")
            def run(ident, cancel):
                folder = root / "runs" / ("eval-" + ident)
                jobs.update(ident, state="running", artifact=str(folder.relative_to(root)))
                return run_evaluation(root, folder, adapter, cancel_event=cancel, job_id=ident)
            return jobs.submit("evaluation", run, request_id=body.request_id)

    @app.get("/api/evaluations/reviews")
    def evaluation_reviews():
        return {"reviews": store.list("evaluation_reviews")}

    @app.post("/api/evaluations/reviews", status_code=201)
    def review_evaluation(body: ReviewInput):
        import hashlib
        path = (root / "runs" / body.run_id / "evaluation.json").resolve()
        if not path.is_relative_to((root / "runs").resolve()) or not path.is_file():
            raise HTTPException(404, "평가 보고서를 찾을 수 없습니다.")
        raw = path.read_bytes()
        report = json.loads(raw)
        if report.get("status") != "completed" or not any(i.get("id") == body.item_id for i in report.get("items", [])):
            raise HTTPException(409, "완료된 평가의 실제 문항만 검토할 수 있습니다.")
        value = {"id":uuid4().hex, **body.model_dump(), "reviewed_at":utcnow(), "reviewed_by":"local_user",
                 "report_sha256":hashlib.sha256(raw).hexdigest(), "scope":"user_rubric_not_expert_certification"}
        store.record("evaluation_review", value["id"], run_id=body.run_id, item_id=body.item_id)
        return store.put("evaluation_reviews", value)

    @app.post("/api/models/tokenize")
    def tokenize(body: TokenInput):
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(root / ".local/models/text", local_files_only=True, trust_remote_code=False)
        ids = tokenizer.encode(body.text, add_special_tokens=False)
        return {"token_count": len(ids), "tokens": [{"id": ident, "text": tokenizer.decode([ident])} for ident in ids[:2048]],
                "truncated_view": len(ids) > 2048, "note": "토큰 분할 보기이며 모델의 내부 사고를 보여 주지 않습니다."}
