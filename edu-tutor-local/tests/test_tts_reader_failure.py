"""Protocol reader failures with in-memory streams only; no child or model."""
from __future__ import annotations

import io
import json
import queue
import threading
from types import SimpleNamespace

import pytest

from edu_tutor.speech import session


def reader_fixture(tmp_path, stream):
    current = session._Session.__new__(session._Session)
    current.folder = tmp_path
    current.instance_id = "cpu-memory-reader"
    current.process = SimpleNamespace(stdout=stream, pid=123)
    current.events = queue.Queue()
    current.reader_error = None
    return current


@pytest.mark.parametrize("failure", ["invalid_utf8", "read_os_error"])
def test_protocol_reader_retains_error_instead_of_silent_eof(tmp_path, capsys, failure):
    class BrokenPipeRead:
        def __iter__(self):
            raise OSError(22, "CPU fixture stdout read failed")
    stream = (io.TextIOWrapper(io.BytesIO(b'{"type":"done"}\xff\n'), encoding="utf-8")
              if failure == "invalid_utf8" else BrokenPipeRead())
    current = reader_fixture(tmp_path, stream)
    current._read()
    assert current.events.get_nowait() is None
    assert current.events.empty()  # No malformed completion event escaped.
    error = json.loads((tmp_path / "reader-error.json").read_text(encoding="utf-8"))
    assert error["operation"] == "read_utf8_protocol_stdout"
    assert error["error_type"] == ("UnicodeDecodeError" if failure == "invalid_utf8" else "OSError")
    assert error == current.reader_error
    assert error["error_type"] in capsys.readouterr().err


def test_request_reports_reader_failure_with_evidence_path(tmp_path, monkeypatch):
    current = reader_fixture(tmp_path, io.TextIOWrapper(io.BytesIO(b'\xff\n'), encoding="utf-8"))
    current._read()
    current.key = "fixture-owner"
    current.closed = threading.Event()
    current.active = False
    current.idle_timer = None
    current.requests = 0
    current.record = {}
    current.process.poll = lambda: None
    current._record = lambda **fields: current.record.update(fields)
    current.send = lambda envelope: None
    coordinator = session._Coordinator()
    coordinator.current = current
    monkeypatch.setattr(session, "_coordinator", lambda root: coordinator)
    stopped = []
    monkeypatch.setattr(session, "close", lambda root, key, reason: stopped.append((key, reason)))
    payload = {"kind": "speech", "tts_session_key": current.key, "tts_benchmark": True,
               "job_id": "fixture-request"}
    with pytest.raises(session.SessionUnavailable, match="UnicodeDecodeError.*reader-error.json"):
        list(session.run(payload, root=tmp_path, timeout=8))
    assert stopped == [(current.key, "request_failed_or_cancelled")]
    reports = list(tmp_path.glob("request-*/request-result.json"))
    assert len(reports) == 1
    result = json.loads(reports[0].read_text(encoding="utf-8"))
    assert result["status"] == "failed_or_cancelled"
    assert "UnicodeDecodeError" in result["error"]


def test_normal_protocol_eof_is_not_labeled_reader_error(tmp_path):
    current = reader_fixture(tmp_path, io.StringIO('{"type":"done"}\n'))
    current._read()
    assert json.loads(current.events.get_nowait())["type"] == "done"
    assert current.events.get_nowait() is None
    assert current.reader_error is None
    assert not (tmp_path / "reader-error.json").exists()
