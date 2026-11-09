"""No-download environment inspection; absent components remain unknown."""
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from .paths import project_root


def recorded_doctor(root=None):
    """Read a prior report without importing torch or starting CUDA probes."""
    root=project_root(root)
    paths=[root/"runs/environment"/name for name in ("api-doctor.json","startup-doctor.json","doctor.json")]
    for path in sorted((p for p in paths if p.is_file()),key=lambda p:p.stat().st_mtime,reverse=True):
        try:
            if path.stat().st_size>100_000:continue
            value=json.loads(path.read_text(encoding="utf-8"))
            if Path(value.get("project_root","")).resolve()!=root:continue
            return {**value,"cached":True,"recorded_at":value.get("timestamp"),
                    "cache_notice":"이전 환경 검사 기록입니다. GPU 여유·RAM·디스크 값은 현재값이 아닐 수 있습니다. 일반 화면 열기에서는 CUDA 검사를 실행하지 않습니다.",
                    "cache_source":str(path.relative_to(root)),"refresh_endpoint":"POST /api/doctor/refresh"}
        except (OSError,ValueError,TypeError):
            continue
    return {"cached":True,"recorded_at":None,"project_root":str(root),"gpu":None,"cuda":None,"packages":{},
            "cache_notice":"저장된 환경 검사 기록이 없습니다. 현재 GPU 상태는 미확인입니다.",
            "refresh_endpoint":"POST /api/doctor/refresh","errors":["No compatible recorded environment report"]}


def collect_doctor(root=None):
    root = project_root(root)
    result = {"timestamp": datetime.now(timezone.utc).isoformat(), "os": platform.platform(),
              "python": sys.version, "executable": sys.executable, "project_root": str(root),
              "environment": "native_windows" if sys.platform == "win32" else "wsl" if "microsoft" in platform.release().lower() else platform.system().lower(),
              "execution_location": "local_windows" if sys.platform == "win32" else "unknown",
              "location_evidence": "native process filesystem and OS; not inferred from requested specification",
              "packages": {}, "gpu": None, "cuda": None, "errors": []}
    for package in ["fastapi", "torch", "transformers", "peft", "bitsandbytes", "accelerate", "qwen-tts"]:
        try:
            result["packages"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result["packages"][package] = None
    result["disk"] = dict(zip(("total", "used", "free"), shutil.disk_usage(root)))
    try:
        import psutil
        mem = psutil.virtual_memory()
        result["ram"] = {"total": mem.total, "available": mem.available}
    except ImportError:
        result["ram"] = None
        result["errors"].append("psutil not installed")
    try:
        command = ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version", "--format=csv,noheader,nounits"]
        rows = subprocess.check_output(command, timeout=10, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).strip().splitlines()
        result["gpu"] = [dict(zip(("name", "total_mib", "free_mib", "driver"), [v.strip() for v in row.split(",")])) for row in rows]
    except (OSError, subprocess.SubprocessError) as exc:
        result["errors"].append(f"nvidia-smi unavailable: {type(exc).__name__}")
    if result["packages"]["torch"]:
        # Isolate imports and CUDA init from the API process and bound hangs.
        script = "import torch,json; ok=torch.cuda.is_available(); print(json.dumps({'available':ok,'version':torch.version.cuda,'bf16':torch.cuda.is_bf16_supported() if ok else None}))"
        try:
            result["cuda"] = json.loads(subprocess.check_output([sys.executable, "-c", script], timeout=40, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            result["errors"].append(f"torch probe failed: {type(exc).__name__}")
    else:
        result["errors"].append("torch not installed; CUDA/BF16 unknown")
    result["network"] = {"status": "not_probed", "reason": "doctor never downloads models"}
    return result
