"""Allowlisted public model download. Inventory first, pin SHA, cap total at 20 GiB."""
import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MODELS = {"text": "Qwen/Qwen3-1.7B", "vision": "Qwen/Qwen3-VL-2B-Instruct", "tts": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"}
ROOT = Path(__file__).resolve().parents[1]
SUFFIXES = {".json", ".safetensors", ".txt", ".jinja", ".model", ".tiktoken"}


def main():
    policy_path = ROOT / ".local/phase2-policy.json"
    if policy_path.exists() and json.loads(policy_path.read_text(encoding="utf-8")).get("enabled"):
        raise RuntimeError("v0.2 검증 회차에서는 새 모델 다운로드를 실행하지 않습니다.")
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=MODELS)
    parser.add_argument("--execute", action="store_true", help="explicitly download after inventory")
    args = parser.parse_args()
    model_id = MODELS[args.kind]
    with urllib.request.urlopen(f"https://huggingface.co/api/models/{model_id}?blobs=true", timeout=30) as r:
        info = json.load(r)
    license_name = info.get("cardData", {}).get("license")
    if license_name != "apache-2.0":
        raise RuntimeError(f"License needs review: {license_name}")
    files = []
    for row in info["siblings"]:
        name = row["rfilename"]
        if Path(name).suffix in SUFFIXES or name in {"LICENSE", "README.md"}:
            # only files directly in snapshot or known nested speech tokenizer
            p = Path(name)
            if p.is_absolute() or ".." in p.parts or ":" in name or "\\" in name:
                raise RuntimeError("unsafe remote path")
            size = row.get("size")
            if not isinstance(size, int):
                raise RuntimeError(f"Missing remote size: {name}")
            files.append({"path": name, "size": size, "sha256": (row.get("lfs") or {}).get("sha256")})
    total = sum(f["size"] for f in files)
    previous = sum(p.stat().st_size for p in (ROOT / ".local/models").rglob("*") if p.is_file()) if (ROOT / ".local/models").exists() else 0
    if total + previous > 20 * 1024**3 or shutil.disk_usage(ROOT).free - total < 20 * 1024**3:
        raise RuntimeError("20 GiB cumulative download budget or 20 GiB free-space floor exceeded")
    manifest = {"model_id": model_id, "revision": info["sha"], "license": license_name, "files": files,
                "download_bytes": total, "inventory_at": datetime.now(timezone.utc).isoformat(), "download_complete": False}
    out = ROOT / "runs" / "downloads"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{args.kind}-inventory.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"model_id": model_id, "revision": info["sha"], "license": license_name, "bytes": total, "files": len(files)}, ensure_ascii=False), flush=True)
    if not args.execute:
        return
    folder = ROOT / ".local/models" / args.kind
    folder.mkdir(parents=True, exist_ok=True)
    for item in files:
        target = folder / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.stat().st_size == item["size"]:
            if not item["sha256"] or hashlib.file_digest(target.open("rb"), "sha256").hexdigest() == item["sha256"]:
                continue
        print(f"Downloading {item['path']} ({item['size']} bytes)", flush=True)
        temporary = target.with_name(target.name + ".partial")
        url = f"https://huggingface.co/{model_id}/resolve/{info['sha']}/{item['path']}"
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as stream:
            shutil.copyfileobj(response, stream, 1024 * 1024)
        if temporary.stat().st_size != item["size"]:
            raise RuntimeError("Download size mismatch")
        with temporary.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        if item["sha256"] and checksum != item["sha256"]:
            raise RuntimeError("Download checksum mismatch")
        item["sha256"] = checksum
        temporary.replace(target)
    manifest["download_complete"] = True
    manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    (folder / "model-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Download complete; runtime validation still required", flush=True)


if __name__ == "__main__":
    main()
