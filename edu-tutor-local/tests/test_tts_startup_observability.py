"""In-process startup protocol checks: no subprocess, model or numerical imports."""
import io
import json

from edu_tutor.speech import session_worker


def test_library_stdout_is_preserved_as_diagnostics_and_json_protocol_stays_clean(tmp_path, monkeypatch):
    class Lease:
        def __init__(self, *_args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

    class Engine:
        def __init__(self, *_args):
            self.process_start_time = 123.0

        def process(self, _payload, _request_id, emit, progress):
            print("fixture library startup warning")
            progress("model_ready", fixture_only=True)
            emit("audio", fixture_only=True, no_wave_generated=True)
            return {"fixture_only": True}

        def close(self):
            print("fixture library cleanup warning")
            return {"model_resident": False, "fixture_only": True}

    command = {"command": "synthesize", "instance_id": "fixture-instance", "request_id": "fixture-request",
        "payload": {"root": str(tmp_path), "run_dir": str(tmp_path)}, "request_timeout_seconds": 10}
    shutdown = {"command": "shutdown", "instance_id": "fixture-instance", "request_id": None}
    stdout, stderr = io.StringIO(), io.StringIO()
    monkeypatch.setattr(session_worker.sys, "stdin", io.StringIO(json.dumps(command)+"\n"+json.dumps(shutdown)+"\n"))
    monkeypatch.setattr(session_worker.sys, "stdout", stdout)
    monkeypatch.setattr(session_worker.sys, "stderr", stderr)
    monkeypatch.setattr(session_worker, "GPULease", Lease)
    monkeypatch.setattr(session_worker, "SessionEngine", Engine)
    monkeypatch.setattr(session_worker, "environment_snapshot", lambda _root: {"fixture_only": True})
    monkeypatch.setattr(session_worker, "interpreter_checks", lambda *_args, **_kwargs:
                        {"applicable": True, "verified": True, "checks": {"fixture_only": True}})
    session_worker.main()

    events = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert [e["type"] for e in events if e["type"] != "progress"] == ["request_started", "audio", "done", "closed"]
    assert "fixture library startup warning" in stderr.getvalue()
    assert "fixture library cleanup warning" in stderr.getvalue()
    assert "fixture library" not in stdout.getvalue()
    assert all("worker_pid" in e and "worker_elapsed_seconds" in e for e in events)
    assert all(e["process_start_time"] == 123.0 for e in events if e["type"] != "progress")
    saved = [json.loads(line) for line in (tmp_path / "worker-progress.jsonl").read_text().splitlines()]
    assert [e["stage"] for e in saved] == ["process_started", "interpreter_verified", "model_ready", "closed"]
    assert all(e["request_id"] == "fixture-request" for e in saved)
