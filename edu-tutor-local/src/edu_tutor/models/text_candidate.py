"""PROPOSAL ONLY: one pinned, base-only candidate; installed base is unchanged."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

SCOPE = "finish-local-tutor-20261028-v1"
CANDIDATE = "qwen3-4b-instruct-2507"
MODEL_ID = "Qwen/Qwen3-4B-Instruct-2507"
REVISION = "cdbee75f17c01a7cc42f958dc650907174af0554"
SOURCE = f"https://huggingface.co/{MODEL_ID}/tree/{REVISION}"
FILES = frozenset({"LICENSE", "README.md", "config.json", "generation_config.json",
    "merges.txt", "model.safetensors.index.json", "tokenizer.json", "tokenizer_config.json", "vocab.json",
    "model-00001-of-00003.safetensors", "model-00002-of-00003.safetensors", "model-00003-of-00003.safetensors"})
SHARD_BYTES = {"model-00001-of-00003.safetensors": 3957900840,
    "model-00002-of-00003.safetensors": 3987450520, "model-00003-of-00003.safetensors": 99630640}


def candidate_folder(root):
    root = Path(root).resolve()
    folder = root / ".local/models/text-candidates" / CANDIDATE
    if not folder.resolve().is_relative_to(root):
        raise ValueError("Candidate destination escapes project root")
    return folder


def validate_inventory(info):
    """Pin repository/revision/license, exact filenames, byte sizes and hashes."""
    if (info.get("id") != MODEL_ID or info.get("sha") != REVISION
            or info.get("cardData", {}).get("license") != "apache-2.0"):
        raise ValueError("Candidate identity/revision/license differs from reviewed source")
    rows = info.get("siblings")
    if not isinstance(rows, list):
        raise ValueError("Missing candidate file inventory")
    found = {}
    for row in rows:
        name = row.get("rfilename")
        if name not in FILES:
            continue
        if name in found:
            raise ValueError("Duplicate candidate inventory filename")
        size = row.get("size")
        if type(size) is not int or size < 1:
            raise ValueError("Missing positive candidate file size")
        lfs = row.get("lfs") or {}
        sha = lfs.get("sha256")
        if name in SHARD_BYTES:
            if size != SHARD_BYTES[name] or lfs.get("size") != size or not re.fullmatch(r"[a-f0-9]{64}", sha or ""):
                raise ValueError("Pinned weight shard size or SHA-256 unavailable")
        blob = row.get("blobId")
        if not lfs and not re.fullmatch(r"[a-f0-9]{40}", blob or ""):
            raise ValueError("Git object identity unavailable for metadata file")
        if lfs and not re.fullmatch(r"[a-f0-9]{64}", sha or ""):
            raise ValueError("LFS file checksum unavailable")
        found[name] = {"path": name, "size": size, "sha256": sha, "git_blob_sha1": blob if not lfs else None}
        if found[name] != PINNED_FILES[name]:
            raise ValueError("Official metadata differs from reviewed file pins")
    if set(found) != FILES:
        raise ValueError("Reviewed candidate files are missing")
    total = sum(item["size"] for item in found.values())
    if not sum(SHARD_BYTES.values()) < total < 8_100_000_000:
        raise ValueError("Candidate total differs from reviewed size envelope")
    return {"candidate_id": CANDIDATE, "model_id": MODEL_ID, "revision": REVISION,
        "license": "apache-2.0", "files": [found[name] for name in sorted(found)],
        "download_bytes": total, "official_source_url": SOURCE, "download_complete": False}


def file_identity(path, entry, *, guard=None):
    if not path.is_file() or path.stat().st_size != entry["size"]:
        raise ValueError("Candidate file size mismatch: " + entry["path"])
    sha256 = hashlib.sha256()
    blob = hashlib.sha1(b"blob " + str(entry["size"]).encode("ascii") + b"\0")
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            if guard is not None:
                guard()
            sha256.update(chunk); blob.update(chunk)
    actual = sha256.hexdigest()
    if entry.get("sha256") and actual != entry["sha256"]:
        raise ValueError("Candidate LFS SHA-256 mismatch: " + entry["path"])
    if entry.get("git_blob_sha1") and blob.hexdigest() != entry["git_blob_sha1"]:
        raise ValueError("Candidate pinned Git blob mismatch: " + entry["path"])
    return actual


def resolve_candidate(root, model_ref, adapter=None, precision="nf4"):
    if model_ref != CANDIDATE:
        raise ValueError("Unregistered text candidate ID")
    if adapter not in {None, "base"}:
        raise ValueError("Candidate screening is base-only; existing adapters cannot be attached")
    if precision != "nf4":
        raise ValueError("Initial 8GB candidate screening permits only NF4")
    folder = candidate_folder(root)
    meta = json.loads((folder / "model-manifest.json").read_text(encoding="utf-8"))
    if (meta.get("candidate_id") != CANDIDATE or meta.get("model_id") != MODEL_ID
            or meta.get("revision") != REVISION or meta.get("license") != "apache-2.0"
            or meta.get("authorization_id") != SCOPE or meta.get("download_complete") is not True):
        raise ValueError("Candidate manifest identity/completion differs")
    rows = meta.get("files", [])
    if len(rows) != len(FILES) or {r.get("path") for r in rows} != FILES:
        raise ValueError("Candidate manifest file set differs")
    for entry in rows:
        path = folder / entry["path"]
        pinned = PINNED_FILES[entry["path"]]
        if (not path.resolve().is_relative_to(folder.resolve()) or not path.is_file()
                or entry.get("size") != pinned["size"]
                or entry.get("git_blob_sha1") != pinned["git_blob_sha1"]
                or (pinned["sha256"] is not None and entry.get("sha256") != pinned["sha256"])
                or path.stat().st_size != entry.get("size")
                or not re.fullmatch(r"[a-f0-9]{64}", entry.get("sha256", ""))):
            raise ValueError("Candidate file is missing, altered in size or unverified")
    # Identity hashes were checked in the download transaction. Read no remote
    # files or arbitrary Python code here. Every inference reports this identity.
    return folder, meta


def candidate_eos_ids(model, tokenizer):
    values = getattr(model.generation_config, "eos_token_id", None)
    values = [values] if type(values) is int else values
    if (not isinstance(values, list) or set(values) != {151645, 151643}
            or any(type(value) is not int for value in values)
            or tokenizer.eos_token_id not in values):
        raise ValueError("Candidate EOS list differs from reviewed generation configuration")
    return list(dict.fromkeys(values))


# Official pinned-revision metadata read 2026-10-29; see proposal receipt.
PINNED_FILES = {'LICENSE': {'path': 'LICENSE', 'size': 11343, 'sha256': None, 'git_blob_sha1': '6634c8cc3133b3848ec74b9f275acaaa1ea618ab'}, 'README.md': {'path': 'README.md', 'size': 8168, 'sha256': None, 'git_blob_sha1': 'b85879f8e465b5b02bd7ea13dd7ffaf22816bf59'}, 'config.json': {'path': 'config.json', 'size': 727, 'sha256': None, 'git_blob_sha1': '6988f134db143052042f2bd6e0c897bc6a605189'}, 'generation_config.json': {'path': 'generation_config.json', 'size': 238, 'sha256': None, 'git_blob_sha1': '432531a002c181a19de338313d2375e9d7494d7e'}, 'merges.txt': {'path': 'merges.txt', 'size': 1671839, 'sha256': None, 'git_blob_sha1': '20024bfe7c83998e9aeaf98a0cd6a2ce6306c2f0'}, 'model-00001-of-00003.safetensors': {'path': 'model-00001-of-00003.safetensors', 'size': 3957900840, 'sha256': '75311d91bb08cf0b882913da464a1e722a31fb44db35208663487efb7a3d8ed6', 'git_blob_sha1': None}, 'model-00002-of-00003.safetensors': {'path': 'model-00002-of-00003.safetensors', 'size': 3987450520, 'sha256': '0b48adbb1f60e901153d91907ba11ce63bd4b8b584482e730f48808d055dfba1', 'git_blob_sha1': None}, 'model-00003-of-00003.safetensors': {'path': 'model-00003-of-00003.safetensors', 'size': 99630640, 'sha256': '7dd39ccca5e4de123c74c14af44c9bf2eb75df33b4614382af0134528e060d5d', 'git_blob_sha1': None}, 'model.safetensors.index.json': {'path': 'model.safetensors.index.json', 'size': 32819, 'sha256': None, 'git_blob_sha1': '4747b0297d3109f14db49886972e3369c9a00b2a'}, 'tokenizer.json': {'path': 'tokenizer.json', 'size': 11422654, 'sha256': 'aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4', 'git_blob_sha1': None}, 'tokenizer_config.json': {'path': 'tokenizer_config.json', 'size': 9377, 'sha256': None, 'git_blob_sha1': '51c1be0d9192e7f6e6596de71d0f07d58fbc32ac'}, 'vocab.json': {'path': 'vocab.json', 'size': 2776833, 'sha256': None, 'git_blob_sha1': '4783fe10ac3adce15ac8f358ef5462739852c569'}}
