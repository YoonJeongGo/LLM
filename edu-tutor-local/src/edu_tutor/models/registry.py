from __future__ import annotations
import json
from pathlib import Path
from edu_tutor.paths import project_root


def adapters(root=None):
    root = project_root(root)
    result = []
    for file in (root / "runs").glob("*/adapter/adapter-manifest.json"):
        try:
            value = json.loads(file.read_text(encoding="utf-8"))
            if value.get("tier") != "T2" or not (file.parent / "adapter_model.safetensors").exists():
                continue
            run_report = json.loads((file.parent.parent / "manifest.json").read_text(encoding="utf-8"))
            eligible = run_report.get("status") == "passed" and run_report.get("reload", {}).get("status") == "passed"
            result.append({"id": file.parent.parent.name, "base_revision": value.get("base_revision") or value.get("revision"),
                           "base_model_id": value.get("base_model_id") or value.get("model_id"), "status": "candidate" if eligible else "incomplete",
                           "eligible": eligible, "path": str(file.parent), "human_review": "not_reviewed", **{k:v for k,v in value.items() if k not in {"id","path","eligible","status"}}})
        except (ValueError, OSError):
            continue
    return result


def selection(root=None):
    path = project_root(root) / ".local/model-selection.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"active_adapter": None, "history": []}


def resolve_adapter(ident=None, root=None, *, use_selection=True):
    if ident is None and use_selection:
        ident = selection(root)["active_adapter"]
    if not ident or ident == "base":
        return None
    for item in adapters(root):
        if item["id"] == ident:
            if not item["eligible"]:
                raise ValueError("학습·재로딩 검증이 완료되지 않은 어댑터입니다.")
            return item["path"]
    raise ValueError("등록된 GPU 어댑터 ID가 아닙니다.")
