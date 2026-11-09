"""Small source/runtime record, excluding credentials, model weights and data."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone


def snapshot(root):
    root = Path(root)
    files = []
    for directory in ('src', 'tests', 'scripts', 'schemas', 'configs', 'web/src', 'web/tests', 'web/dist'):
        for p in (root / directory).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc', '.png', '.wav'}:
                files.append(p)
    for pattern in ('*.toml','requirements*.txt','web/package*.json','web/*config.*'):
        files.extend(p for p in root.glob(pattern) if p.is_file())
    manifest = {str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(set(files))}
    return {'created_at':datetime.now(timezone.utc).isoformat(),'files':manifest,
            'source_sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest(),
            'scope':'code, tests, scripts, schemas, config, build; excludes credentials, user data, weights, environments'}


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];value=snapshot(root)
    out=root/args.output;out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(value['source_sha256'])
