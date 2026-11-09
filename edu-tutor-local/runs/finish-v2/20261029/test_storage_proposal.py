import importlib.util
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from edu_tutor.models import budget

spec = importlib.util.spec_from_file_location("storage_scan_proposal", Path(__file__).with_name("storage-scan-proposal.py"))
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


def test_same_full_scope_and_fresh_second_scan(tmp_path):
    for name, size in [("runs/a/one", 17), ("runs/two", 43), (".local/models/a", 108), ("ignored/b", 99)]:
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"x" * size)
    assert candidate.mutable_bytes(tmp_path) == budget.mutable_bytes(tmp_path) == 168
    (tmp_path / "runs/a/one").write_bytes(b"z" * 150)
    assert candidate.mutable_bytes(tmp_path) == budget.mutable_bytes(tmp_path) == 301


def test_missing_roots_and_removed_directory(tmp_path, monkeypatch):
    assert candidate.mutable_bytes(tmp_path) == budget.mutable_bytes(tmp_path) == 0
    real = candidate.os.scandir
    def removed(path):
        if str(path).endswith("runs"):
            raise FileNotFoundError("directory disappeared")
        return real(path)
    monkeypatch.setattr(candidate.os, "scandir", removed)
    assert candidate.mutable_bytes(tmp_path) == 0


def test_entry_disappearance_is_bounded_and_permission_error_fails_closed(tmp_path, monkeypatch):
    class Entry:
        def is_dir(self): return False
        def stat(self): raise FileNotFoundError("file disappeared after enumeration")
    class Entries:
        def __enter__(self): return iter([Entry()])
        def __exit__(self, *_): pass
    monkeypatch.setattr(candidate.os, "scandir", lambda _: Entries())
    assert candidate.mutable_bytes(tmp_path) == 0
    def denied(_): raise PermissionError("cannot measure this subtree")
    monkeypatch.setattr(candidate.os, "scandir", denied)
    with pytest.raises(PermissionError): candidate.mutable_bytes(tmp_path)


def test_actual_junction_is_not_followed(tmp_path):
    if os.name != "nt": pytest.skip("Windows junction")
    (tmp_path / "runs").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "must-not-count").write_bytes(b"x" * 170)
    junction = tmp_path / "runs/junction"
    def quote(path): return "'" + str(path).replace("'", "''") + "'"
    command = "New-Item -ItemType Junction -Path " + quote(junction) + " -Value " + quote(outside) + " | Out-Null"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode: pytest.fail("Could not create local fixture junction: " + result.stderr.decode(errors="replace"))
    assert junction.is_junction()
    assert candidate.mutable_bytes(tmp_path) == budget.mutable_bytes(tmp_path) == 0


def test_actual_file_and_directory_symlinks_preserve_prior_scope(tmp_path):
    (tmp_path / "runs").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "source"
    target.write_bytes(b"y" * 51)
    try:
        (tmp_path / "runs/file-link").symlink_to(target)
        (tmp_path / "runs/dir-link").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip("Host did not permit creating fixture symlinks: " + str(exc))
    assert candidate.mutable_bytes(tmp_path) == budget.mutable_bytes(tmp_path) == 51


def test_file_symlink_target_size_and_directory_links_not_traversed(tmp_path, monkeypatch):
    class Entry:
        def __init__(self, directory, symbolic=False, junction=False):
            self.directory, self.symbolic, self.junction = directory, symbolic, junction
        def is_dir(self): return self.directory
        def is_symlink(self): return self.symbolic
        def is_junction(self): return self.junction
        def stat(self):
            assert not self.directory
            return SimpleNamespace(st_size=51)
    class Entries:
        def __init__(self, path): self.path = path
        def __enter__(self):
            return iter([Entry(False, symbolic=True), Entry(True, symbolic=True), Entry(True, junction=True)] if str(self.path).endswith("runs") else [])
        def __exit__(self, *_): pass
    monkeypatch.setattr(candidate.os, "scandir", Entries)
    assert candidate.mutable_bytes(tmp_path) == 51
