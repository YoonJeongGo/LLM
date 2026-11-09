"""At most four 45s child checks for this recovery, with no weights/GPU work."""
import faulthandler
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone

import psutil
from edu_tutor.speech import session

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/student-latency/20261027/tts-startup-recovery"


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def run(mode):
    assert mode in {"control", "control_host", "control_host_fixed", "direct", "production"}
    journal_path = OUT / "diagnostic-attempts.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8")) if journal_path.exists() else []
    if len(journal) >= 4 or any(r["mode"] == mode for r in journal):
        raise SystemExit("Diagnostic bound or same-mode no-retry guard reached")
    row = {"ordinal": len(journal)+1, "mode": mode, "at": datetime.now(timezone.utc).isoformat(),
           "timeout_seconds": 45, "model_loads": 0, "tts_calls": 0}
    journal.append(row)
    save(journal_path, journal)
    env = os.environ.copy()
    env.update(PYTHONUTF8="0", PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1", PYTHONFAULTHANDLER="1",
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1",
        TOKENIZERS_PARALLELISM="false", CUDA_VISIBLE_DEVICES="")
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    paths = [str(ROOT / "src"), *[str(Path(p).resolve()) if p else str(ROOT) for p in sys.path]]
    env["EDU_TTS_PARENT_SYS_PATH"] = json.dumps(list(dict.fromkeys(paths)), ensure_ascii=False)
    env["EDU_TTS_PARENT_PREFIX"], env["EDU_TTS_PARENT_EXEC_PREFIX"] = sys.prefix, sys.exec_prefix
    module = "scripts.tts_startup_production_probe" if mode == "production" else "scripts.tts_startup_probe"
    command = ([str(ROOT / ".venv/Scripts/python.exe"), "-u", "-m", module]
               if mode in {"control", "control_host", "control_host_fixed"} else session._python_command(ROOT, module=module))
    events, messages = [], queue.Queue()
    ident = uuid.uuid4().hex
    record = {**row, "command": command, "shell": False, "parent_pid": os.getpid(),
        "parent_executable": sys.executable, "request_id": ident, "events": events,
        "execution_context": "restricted_tool" if mode == "control" else "host_tool_matching_local_server",
        "probe_source_sha256": hashlib.sha256((ROOT/(module.replace('.', '/')+'.py')).read_bytes()).hexdigest(),
        "diagnostic_only_overrides": {"CUDA_VISIBLE_DEVICES": "", "PYTHONFAULTHANDLER": "1", "PYTHONUNBUFFERED": "1"}}
    actual = None
    started = time.monotonic()
    with (OUT / (mode+".stderr.log")).open("wb") as err, (OUT / (mode+".stdout.log")).open("wb") as raw:
        p = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=err, shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        record["popen_pid"] = p.pid
        record["popen_create_time"] = psutil.Process(p.pid).create_time()
        def reader():
            try:
                for line in p.stdout:
                    raw.write(line); raw.flush(); messages.put(line)
            finally:
                messages.put(None)
        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        p.stdin.write((json.dumps({"root": str(ROOT), "request_id": ident})+"\n").encode()); p.stdin.flush()
        shutdown_sent = False
        try:
            while time.monotonic()-started < 43:
                try:
                    line = messages.get(timeout=.1)
                except queue.Empty:
                    if p.poll() is not None: break
                    continue
                if line is None: break
                event = json.loads(line.decode("utf-8"))
                assert event.get("request_id") == ident, "Probe protocol identity mismatch"
                events.append(event)
                if actual is None:
                    actual = psutil.Process(event["pid"])
                    assert actual.pid == p.pid or actual.ppid() == p.pid
                    assert actual.create_time() >= record["popen_create_time"]-.01
                    record["handshake"] = {"pid": actual.pid, "parent_pid": actual.ppid(),
                        "create_time": actual.create_time(), "executable": actual.exe(), "relationship_verified": True}
                if event.get("stage") in {"imports_ready", "production_ready_no_weights"} and not shutdown_sent:
                    p.stdin.write((json.dumps({"command": "shutdown", "request_id": ident})+"\n").encode())
                    p.stdin.flush(); shutdown_sent = True
            p.wait(timeout=max(.1, 44-(time.monotonic()-started)))
        except BaseException as exc:
            record["failure"] = f"{type(exc).__name__}: {exc}"
        finally:
            if actual and actual.is_running() and p.poll() is None:
                actual.terminate()
            if p.poll() is None:
                p.terminate()
            p.wait(timeout=1)
            thread.join(timeout=.5)
            p.stdout.close()
            try: p.stdin.close()
            except OSError as exc: record["stdin_close_error"] = str(exc)
    record.update(exit_code=p.returncode, elapsed_seconds=time.monotonic()-started)
    stderr = (OUT/(mode+".stderr.log")).read_bytes()
    record["native_diagnostic"] = any(value in stderr.lower() for value in (b"access violation", b"fatal python error", b"windows fatal exception"))
    record["parent_native_diagnostic"] = bool((OUT/(mode+".parent-native.log")).read_bytes())
    record["environment_checks_passed"] = all(e["checks"].get("verified") for e in events if "checks" in e)
    record["stdout_protocol_only"] = all(e.get("type") == "startup_probe" for e in events)
    record["status"] = "PASS" if (p.returncode == 0 and not record.get("failure") and not record["native_diagnostic"]
        and not record["parent_native_diagnostic"] and record["environment_checks_passed"]
        and events and events[-1].get("stage") == "closed") else "FAILED_PREPARATION"
    save(OUT/(mode+".json"), record)
    journal[-1].update(status=record["status"], exit_code=p.returncode, elapsed_seconds=record["elapsed_seconds"])
    save(journal_path, journal)
    print(json.dumps({k: record.get(k) for k in ("mode", "status", "exit_code", "elapsed_seconds", "handshake", "native_diagnostic", "failure")}, ensure_ascii=False))
    if record["status"] != "PASS": raise SystemExit(1)


if __name__ == "__main__":
    # Parent native diagnostics are preserved too; never hidden by child success.
    with (OUT/(sys.argv[1]+".parent-native.log")).open("ab") as native:
        faulthandler.enable(file=native, all_threads=True)
        try:
            run(sys.argv[1])
        finally:
            # End-of-process cleanup only, after the child and checks finish;
            # do not leave a handler targeting an already closed log file.
            faulthandler.disable()
