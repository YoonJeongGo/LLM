import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
pack = root.parent / "edu_tutor_codex_pack"
results = []
for row in (pack / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
    expected, name = row.split(maxsplit=1)
    path = (pack / name).resolve()
    if not path.is_relative_to(pack.resolve()):
        raise ValueError("Unexpected pack path")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    results.append({"file": name, "match": actual == expected})
report = {"source_pack": str(pack), "checked": len(results), "passed": all(r["match"] for r in results), "files": results}
(root / "runs/source-pack-validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k:v for k,v in report.items() if k != "files"}, ensure_ascii=False))
if not report["passed"]:
    raise SystemExit(1)
