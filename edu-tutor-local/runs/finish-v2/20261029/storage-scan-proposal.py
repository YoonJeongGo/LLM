"""Candidate exact-scope scan. Each call creates fresh directory entries."""
import os
from pathlib import Path


def mutable_bytes(root):
    total = 0
    pending = [Path(root) / part for part in ("runs", ".local")]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir():
                            if not entry.is_symlink() and not entry.is_junction():
                                pending.append(entry.path)
                        else:
                            # File symlinks retain the previous target-size rule.
                            # On Windows, this uses current enumeration metadata
                            # for regular files. Entries never outlive this scan.
                            total += entry.stat().st_size
                    except FileNotFoundError:
                        # A concurrently removed file cannot consume storage.
                        continue
        except FileNotFoundError:
            # Missing roots or directories removed during this scan.
            continue
    return total
