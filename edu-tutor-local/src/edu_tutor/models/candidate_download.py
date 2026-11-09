"""PROPOSAL ONLY: bounded official download, called from authenticated job API.

No automatic retries, no default-model selection, no GPU model load. Failed
transfers conservatively retain their reserved maximum bytes. Existing files
and the legacy downloader remain untouched.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import time
from .candidate_transfer import receive as bounded_receive

from .text_candidate import (SCOPE, CANDIDATE, MODEL_ID, REVISION, SOURCE,
                             candidate_folder, validate_inventory, file_identity)

METADATA_MAX = 2_000_000
DOWNLOAD_WALL_SECONDS = 1200
REDIRECT_BYTES_PER_FILE = 262144


def download_candidate(root, job_id, scope, cancel, progress=lambda value: None):
    from .budget import policy, status, reserve, finish_download
    from edu_tutor.speech.session import dispatch
    from edu_tutor.storage.db import utcnow
    root = Path(root).resolve()
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise ValueError("Download job identity must be server-issued")
    if scope != SCOPE or not policy(root).get("enabled"):
        raise ValueError("This downloader requires the exact integrated approval scope")
    grant = status(root).get("active_execution_allowance") or {}
    if grant.get("id") != SCOPE or grant.get("accounting") != "scope_only_preserve_lifetime":
        raise ValueError("Explicit preserved-ledger scope is not effective")
    folder = candidate_folder(root)
    if folder.exists():
        # No implicit retry, resume, overwrite or cleanup of previous artifacts.
        raise ValueError("Candidate directory already exists; review its prior attempt before another action")
    staging = folder.with_name("." + folder.name + "-" + job_id + ".partial")
    if not staging.resolve().is_relative_to(root) or staging.exists():
        raise ValueError("Staging destination is unsafe or already occupied")
    run = root / "runs" / ("candidate-download-" + job_id)
    if run.exists():
        raise ValueError("Download evidence already exists")
    run.mkdir(parents=True)
    record = {"status": "starting", "at": utcnow(), "candidate_id": CANDIDATE,
        "authorization_id": SCOPE, "new_model_calls": 0, "no_retries": True,
        "download_wall_limit_seconds": DOWNLOAD_WALL_SECONDS,
        "download_time_is_model_work": False, "default_selection_changed": False}
    def save():
        temp = run / "result.json.tmp"
        temp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(run / "result.json")
    save()
    reservation = None
    reserved_bytes = 0
    started = time.monotonic()
    deadline = started + DOWNLOAD_WALL_SECONDS
    payload = {"kind": "download", "job_id": job_id, "execution_allowance_id": scope,
        "candidate_kind": "text", "candidate_id": CANDIDATE,
        "official_source_url": SOURCE, "official_source_verified": True}
    def guard():
        if cancel.is_set():
            raise RuntimeError("Candidate download cancelled; no retry")
        if time.monotonic() >= deadline:
            raise TimeoutError("Candidate download wall limit reached; no retry")
    try:
        # Queue serializes this bounded transfer with existing model dispatch;
        # it never takes over or terminates unrelated processes.
        with dispatch(root, cancel_event=cancel, timeout=300):
            reservation, _ = reserve(root, {**payload, "download_bytes": METADATA_MAX}, 300)
            reserved_bytes = METADATA_MAX
            record["metadata_reservation_id"] = reservation[2]
            save()
            metadata_transfer = bounded_receive(root, f"https://huggingface.co/api/models/{MODEL_ID}/revision/{REVISION}?blobs=true",
                run / "official-inventory.json", maximum=METADATA_MAX, transfer_maximum=METADATA_MAX,
                deadline=deadline, cancel=cancel, prefix=run/"metadata-transfer")
            metadata_bytes = metadata_transfer["transferred_bytes"]
            info = json.loads((run / "official-inventory.json").read_text(encoding="utf-8"))
            manifest = validate_inventory(info)
            finish_download(reservation, metadata_bytes, True)
            reservation = None
            record.update(status="inventory_verified", metadata_received_bytes=metadata_bytes,
                          expected_file_bytes=manifest["download_bytes"], inventory=manifest)
            save()
            guard()
            reserved_bytes = manifest["download_bytes"] + len(manifest["files"])*REDIRECT_BYTES_PER_FILE
            reservation, _ = reserve(root, {**payload, "download_bytes": reserved_bytes}, 300)
            record["file_reservation_id"] = reservation[2]
            staging.mkdir(parents=True, exist_ok=False)
            received = 0
            record["files"] = []
            for file_index, entry in enumerate(manifest["files"]):
                guard()
                partial = staging / (entry["path"] + ".partial")
                transfer = bounded_receive(root, f"https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{entry['path']}", partial,
                    maximum=entry["size"], transfer_maximum=entry["size"]+REDIRECT_BYTES_PER_FILE,
                    deadline=deadline, cancel=cancel, prefix=run/f"file-{file_index:02d}-transfer")
                amount = transfer["body_bytes"]
                received += transfer["transferred_bytes"]
                entry["sha256"] = file_identity(partial, entry, guard=guard)
                partial.rename(staging / entry["path"])
                record["files"].append({"path": entry["path"], "received_bytes": amount, "transferred_bytes": transfer["transferred_bytes"], "sha256": entry["sha256"]})
                record.update(status="downloading", received_file_bytes=received)
                save(); progress(min(1, received / manifest["download_bytes"]))
            guard()
            manifest.update(download_complete=True, authorization_id=SCOPE, completed_at=utcnow(),
                            download_reservation_id=reservation[2], transferred_body_bytes=received, source_review="docs/QWEN3_4B_CANDIDATE_REVIEW.md")
            (staging / "model-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            if (folder.exists() or not staging.resolve().is_relative_to(root)
                    or not folder.resolve().is_relative_to(root)):
                raise ValueError("Atomic candidate promotion destination changed")
            staging.rename(folder)
            finish_download(reservation, received, True)
            reservation = None
            record.update(status="completed_download_only", model_runtime_validation="NOT_RUN", folder=str(folder))
            return record
    except BaseException as exc:
        record.update(status="failed_or_cancelled", error=f"{type(exc).__name__}: {exc}",
                      preserved_staging=str(staging) if staging.exists() else None)
        if reservation is not None:
            # A failed read may have consumed bytes in a lower-level buffer.
            # Preserve the full reservation rather than undercount or retry.
            try:
                finish_download(reservation, reserved_bytes, False)
            except Exception as budget_error:
                record["budget_finalize_error"] = f"{type(budget_error).__name__}: {budget_error}"
            record["failure_byte_accounting"] = "full_reserved_maximum_retained"
        raise
    finally:
        record.update(finished_at=utcnow(), observed_wall_seconds=time.monotonic()-started)
        save()
