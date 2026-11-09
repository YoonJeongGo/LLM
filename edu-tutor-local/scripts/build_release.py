"""Source bundle with prebuilt UI. Never include local credentials/data/weights."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import zipfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
FILES = ["README.md", "AGENTS.md", "HANDOFF.md", "STATUS.json", "THIRD_PARTY_NOTICES.md", "pyproject.toml", "requirements-lock.txt", ".gitignore"]
DIRS = ["src", "configs", "data", "schemas", "scripts", "docs", "tests", "web/src", "web/scripts", "web/tests", "web/public", "web/dist"]
WEB_FILES = ["web/package.json", "web/package-lock.json", "web/index.html", "web/tsconfig.json", "web/vite.config.ts", "web/playwright.config.ts", "web/playwright.live.config.ts"]
GENERATED_DIRS = {"__pycache__", ".artifacts", ".pytest_cache", "node_modules", "test-results", "playwright-report", "coverage"}


def main():
    paths = {ROOT / name for name in FILES + WEB_FILES if (ROOT / name).is_file()}
    paths.update(path for path in (ROOT / "web").glob("*config.*") if path.is_file() and path.suffix in {".ts", ".js", ".mjs", ".json"})
    for directory in DIRS:
        paths.update(p for p in (ROOT / directory).rglob("*") if p.is_file()
                     and not set(p.relative_to(ROOT).parts) & GENERATED_DIRS and p.suffix != ".pyc")
    for path in paths:
        relative = path.relative_to(ROOT)
        if not path.resolve().is_relative_to(ROOT) or set(relative.parts) & {".local", ".venv", "node_modules", ".git", "runs"}:
            raise RuntimeError("Unsafe release member")
        if path.suffix.lower() in {".safetensors", ".bin", ".sqlite3", ".db", ".wav"} or "auth-token" in path.name:
            raise RuntimeError("Private or large runtime artifact in source bundle")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    output = ROOT / "release" / f"edu-tutor-local-{version}-{stamp}.zip"
    output.parent.mkdir(exist_ok=True)
    checksums = {}
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            relative = path.relative_to(ROOT).as_posix()
            archive.write(path, "edu-tutor-local/" + relative)
            checksums[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        archive.writestr("edu-tutor-local/RELEASE_FILES.json", json.dumps(checksums, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
    manifest = {"zip": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "files": len(paths), "size": output.stat().st_size, "runtime_data_included": False, "zip_crc_check": "pass"}
    output.with_suffix(".json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
