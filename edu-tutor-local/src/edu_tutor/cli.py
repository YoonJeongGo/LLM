from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .paths import initialize


def dump(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def new_run(root, kind):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = root / "runs" / f"{stamp}-{kind}-{uuid4().hex[:6]}"
    path.mkdir(parents=True)
    return path


def main():
    parser = argparse.ArgumentParser(description="한국어 AI 강의실 — 로컬 실행 도구")
    parser.add_argument("--root", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--output", type=Path)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8000)
    baseline = sub.add_parser("baseline")
    baseline.add_argument("--config", default="configs/local_8gb.yaml")
    baseline.add_argument("--question", default="SQLite에서 NULL과 COUNT(*)와 COUNT(열)의 차이를 작은 표로 설명해 주세요.")
    baseline.add_argument("--adapter", default=None)
    data = sub.add_parser("data").add_subparsers(dest="data_command", required=True)
    validate = data.add_parser("validate")
    validate.add_argument("--dataset", required=True, type=Path)
    validate.add_argument("--profile", choices=["demo", "production"], default="demo")
    train = sub.add_parser("train")
    train.add_argument("--smoke", action="store_true")
    train.add_argument("--tiny", action="store_true")
    train.add_argument("--profile", choices=["demo"], default="demo")
    train.add_argument("--config", default="configs/local_8gb.yaml")
    jobs = sub.add_parser("jobs").add_subparsers(dest="jobs_command", required=True)
    jobs.add_parser("list")
    cancel = jobs.add_parser("cancel")
    cancel.add_argument("--id", required=True)
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--run", required=True)
    sub.add_parser("backup")
    args = parser.parse_args()
    root = initialize(args.root)
    try:
        if args.command == "doctor":
            from .doctor import collect_doctor
            value = collect_doctor(root)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
            dump(value)
        elif args.command == "serve":
            import uvicorn
            from .api import create_app
            print(f"AI 강의실: http://127.0.0.1:{args.port}")
            print(f"관리 토큰 파일: {root / '.local/auth-token'} (화면의 연결 입력란에 붙여 넣으세요)")
            uvicorn.run(create_app(root), host="127.0.0.1", port=args.port, access_log=False)
        elif args.command == "baseline":
            from .models.runtime import run_worker
            folder = new_run(root, "baseline")
            events = list(run_worker({"kind": "text", "messages": [
                {"role": "system", "content": "당신은 한국어 데이터베이스 기초 강사입니다. 조건이 부족하면 질문하고, 모르는 내용을 지어내지 마세요. 공개된 풀이를 간결하게 설명하세요."},
                {"role": "user", "content": args.question}], "adapter": args.adapter, "max_new_tokens": 512}, root=root))
            value = next((e for e in events if e["type"] == "metadata"), {})
            value["question"] = args.question
            (folder / "baseline.json").write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
            dump({"artifact": str(folder), **value})
            if value.get("finish_reason") != "eos":
                sys.exit(2)
        elif args.command == "data":
            from .training.data import validate_dataset
            paths = sorted(args.dataset.glob("*.jsonl")) if args.dataset.is_dir() else [args.dataset]
            dump(validate_dataset(paths, profile=args.profile))
        elif args.command == "train":
            if args.tiny:
                from .training.tiny import tiny_lora_smoke
                folder = new_run(root, "tiny")
                dump(tiny_lora_smoke(folder))
            else:
                import httpx
                import time
                if (root / args.config).resolve() != (root / "configs/local_8gb.yaml").resolve():
                    raise ValueError("현재 로컬 관리자 실행은 configs/local_8gb.yaml의 고정 예산을 사용합니다.")
                token_file = root / ".local/auth-token"
                if not token_file.exists():
                    raise RuntimeError("먼저 edu_tutor serve를 실행하세요. CLI와 웹은 같은 작업 관리자를 사용합니다.")
                headers = {"Authorization": "Bearer " + token_file.read_text().strip()}
                with httpx.Client(base_url="http://127.0.0.1:8000", headers=headers, timeout=15) as client:
                    response = client.post("/api/train", json={"profile": "smoke" if args.smoke else "demo", "request_id": uuid4().hex})
                    response.raise_for_status()
                    job = response.json()
                    print("학습 작업: " + job["id"], flush=True)
                    while job["state"] not in {"succeeded", "failed", "blocked", "cancelled", "interrupted"}:
                        time.sleep(1)
                        response = client.get("/api/jobs/" + job["id"])
                        response.raise_for_status()
                        job = response.json()
                    dump(job)
                    if job["state"] != "succeeded":
                        sys.exit(1)
        elif args.command == "jobs":
            from .storage.db import Store, utcnow
            store = Store(root)
            if args.jobs_command == "list":
                dump(store.list("jobs"))
            else:
                # Send the authenticated cancel to the running owner, not a new manager.
                import httpx
                token = (root / ".local/auth-token").read_text().strip()
                response = httpx.post(f"http://127.0.0.1:8000/api/jobs/{args.id}/cancel", headers={"Authorization": "Bearer " + token}, timeout=10)
                response.raise_for_status()
                dump(response.json())
        elif args.command == "evaluate":
            import httpx
            import time
            token = (root / ".local/auth-token").read_text().strip()
            with httpx.Client(base_url="http://127.0.0.1:8000", headers={"Authorization":"Bearer " + token}, timeout=15) as client:
                response = client.post("/api/evaluations", json={"run_id":args.run, "request_id":uuid4().hex})
                response.raise_for_status()
                job = response.json()
                print("평가 작업: " + job["id"], flush=True)
                while job["state"] not in {"succeeded", "failed", "blocked", "cancelled", "interrupted"}:
                    time.sleep(1)
                    response = client.get("/api/jobs/" + job["id"])
                    response.raise_for_status()
                    job = response.json()
                dump(job)
                if job["state"] != "succeeded":
                    sys.exit(1)
        elif args.command == "backup":
            import sqlite3
            from .storage.db import Store
            store = Store(root)
            folder = new_run(root, "backup")
            with store.connect() as source, sqlite3.connect(folder / "tutor.sqlite3") as target:
                source.backup(target)
            dump({"database_backup": str(folder / "tutor.sqlite3"), "uploads_included": False, "models_included": False})
    except Exception as exc:
        dump({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        sys.exit(1)
