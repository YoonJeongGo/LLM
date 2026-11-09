"""A01 contract tests with simulated probes; these do not inspect a real GPU."""
import importlib.metadata
import json
import socket
import subprocess
import sys
import urllib.request

import pytest

from edu_tutor import doctor


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("doctor attempted a network request")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    # Windows platform.platform() itself invokes `ver`; isolate OS discovery so
    # subprocess assertions below cover only the doctor's explicit probes.
    monkeypatch.setattr(doctor.platform, "platform", lambda: "Windows-fixture")
    monkeypatch.setattr(doctor.platform, "release", lambda: "fixture")
    monkeypatch.setattr(doctor.platform, "system", lambda: "Windows")


def package_versions(monkeypatch, torch_installed):
    def version(name):
        if name == "torch" and torch_installed:
            return "2.9.1+cpu"
        raise importlib.metadata.PackageNotFoundError(name)
    monkeypatch.setattr(doctor.importlib.metadata, "version", version)


def test_no_torch_no_gpu_stays_unknown_without_download_or_torch_probe(tmp_path, monkeypatch):
    package_versions(monkeypatch, False)
    commands = []
    def probe(command, **options):
        commands.append(command)
        assert command[0] == "nvidia-smi"
        assert options["timeout"] == 10
        raise FileNotFoundError("no NVIDIA driver")
    monkeypatch.setattr(doctor.subprocess, "check_output", probe)
    report = doctor.collect_doctor(tmp_path)
    assert report["gpu"] is None
    assert report["cuda"] is None
    assert all(value is None for value in report["packages"].values())
    assert any("CUDA/BF16 unknown" in error for error in report["errors"])
    assert report["network"]["status"] == "not_probed"
    assert len(commands) == 1
    assert not list(tmp_path.iterdir())  # No cache, model, or run directories created.
    json.dumps(report, allow_nan=False)


def test_verified_cpu_only_is_distinct_from_unknown(tmp_path, monkeypatch):
    package_versions(monkeypatch, True)
    commands = []
    def probe(command, **options):
        commands.append(command)
        if command[0] == "nvidia-smi":
            return ""
        assert command[:2] == [sys.executable, "-c"]
        assert options["timeout"] == 40
        assert "from_pretrained" not in command[2]
        assert "download" not in command[2]
        return '{"available": false, "version": null, "bf16": null}'
    monkeypatch.setattr(doctor.subprocess, "check_output", probe)
    report = doctor.collect_doctor(tmp_path)
    assert report["gpu"] == []
    assert report["cuda"] == {"available": False, "version": None, "bf16": None}
    assert report["network"]["status"] == "not_probed"
    assert len(commands) == 2
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("failure", ["timeout", "invalid_json", "process_failure"])
def test_cuda_probe_failure_is_unknown_not_false(tmp_path, monkeypatch, failure):
    package_versions(monkeypatch, True)
    def probe(command, **options):
        if command[0] == "nvidia-smi":
            return "Fixture GPU, 8192, 4096, fixture-driver\n"
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, options["timeout"])
        if failure == "process_failure":
            raise subprocess.CalledProcessError(1, command)
        return "native diagnostic that is not JSON"
    monkeypatch.setattr(doctor.subprocess, "check_output", probe)
    report = doctor.collect_doctor(tmp_path)
    assert report["cuda"] is None
    assert report["gpu"][0]["total_mib"] == "8192"
    assert any("torch probe failed" in error for error in report["errors"])
    assert report["network"]["status"] == "not_probed"


def test_missing_ram_dependency_has_reason_and_no_fabricated_capacity(tmp_path, monkeypatch):
    package_versions(monkeypatch, False)
    monkeypatch.setitem(sys.modules, "psutil", None)
    monkeypatch.setattr(doctor.subprocess, "check_output", lambda *args, **kwargs: "")
    report = doctor.collect_doctor(tmp_path)
    assert report["ram"] is None
    assert "psutil not installed" in report["errors"]

