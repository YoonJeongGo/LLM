"""Verify a source ZIP and boot its actual source in a new isolated local folder."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("zip")
    args = parser.parse_args()
    archive_path = Path(args.zip).resolve()
    if not archive_path.is_relative_to(ROOT / "release"):
        parser.error("Only this project's release ZIP may be checked")
    target = ROOT / ".local" / ("release-check-v02-" + uuid4().hex[:10])
    target.mkdir()
    secret = (ROOT / ".local/auth-token").read_bytes().strip()
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        entries = archive.infolist()
        for entry in entries:
            destination = (target / entry.filename).resolve()
            assert destination.is_relative_to(target.resolve())
            assert not entry.filename.startswith(("/", "\\"))
            parts = Path(entry.filename).parts
            assert not set(parts) & {".local", ".venv", "node_modules", "runs", ".git"}
            assert Path(entry.filename).suffix.lower() not in {".safetensors", ".bin", ".db", ".sqlite3", ".wav"}
            assert secret not in archive.read(entry.filename), "Local credential found in release"
        manifest = json.loads(archive.read("edu-tutor-local/RELEASE_FILES.json"))
        for relative, expected in manifest.items():
            assert hashlib.sha256(archive.read("edu-tutor-local/" + relative)).hexdigest() == expected
        archive.extractall(target)
    extracted = target / "edu-tutor-local"
    env = os.environ.copy()
    env.update(EDU_TUTOR_ROOT=str(extracted), PYTHONPATH=str(extracted / "src"),
               PYTHONUTF8="0", PYTHONIOENCODING="utf-8", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    code = r'''
import json, pathlib, edu_tutor
from fastapi.testclient import TestClient
from edu_tutor.api.app import create_app
root=pathlib.Path.cwd().resolve()
assert pathlib.Path(edu_tutor.__file__).resolve().is_relative_to(root)
app=create_app(root)
with TestClient(app,base_url="http://127.0.0.1") as c:
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/sessions").status_code == 401
    assert c.get("/").status_code == 200
    token=(root/".local/auth-token").read_text().strip()
    headers={"Authorization":"Bearer "+token}
    assert c.get("/api/sessions",headers=headers).json() == []
    model=c.get("/api/models",headers=headers).json()
    assert model["installed"] is False and model["ready"] is False
    assert c.get("/api/jobs",headers=headers).json() == []
    assert c.get("/api/doctor",headers=headers).status_code == 200
    assert app.version == "0.2.0"
print(json.dumps({"source_import_from_extracted_zip":True,"health_static_auth": "passed",
    "empty_records":True,"missing_model_report":"passed","model_jobs_started":0,"version":app.version}))
'''
    process = subprocess.run([sys.executable, "-c", code], cwd=extracted, env=env,
                             capture_output=True, text=True, encoding="utf-8", timeout=60)
    report = {"timestamp": datetime.now(timezone.utc).isoformat(), "zip": str(archive_path),
        "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(), "members": len(entries),
        "manifest_hashes": "passed", "credential_exclusion": "passed", "excluded_runtime_data": "passed",
        "extracted_root": str(extracted), "bootstrap_exit_code": process.returncode,
        "bootstrap_stdout": process.stdout.strip(), "bootstrap_stderr": process.stderr[-3000:],
        "scope": "Fresh source/static/auth/no-model bootstrap with existing project venv; not clean dependency installation, downloaded model copy or cross-PC validation."}
    output = ROOT / "runs/phase2/current/release-verification.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"sha256":report["sha256"],"members":len(entries),"bootstrap_exit_code":process.returncode,
                      "report":str(output)},ensure_ascii=False))
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
