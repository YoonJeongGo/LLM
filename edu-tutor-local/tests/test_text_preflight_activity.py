"""CPU-only activity/expiry fixtures. Apply only after the proposed source review."""
import io
import json
import os
from pathlib import Path
import queue
from types import SimpleNamespace
import threading
import time

import pytest

from edu_tutor.models import budget, text_session


class Timer:
    def __init__(self, interval, callback, args=(), kwargs=None):
        self.interval, self.callback, self.args, self.kwargs = interval, callback, args, kwargs or {}
        self.cancelled = self.started = False
    def cancel(self): self.cancelled = True
    def start(self): self.started = True


@pytest.fixture
def owner(tmp_path, monkeypatch):
    clock, sent, cancel = [125.0], [], threading.Event()
    child = SimpleNamespace(instance_id="owner", request_id="previous", key="key", active=False, closed=False,
        process=SimpleNamespace(poll=lambda: None), record={"model_instance_id": "model", "worker_pid": 41},
        idle_deadline=140.0, lifetime_deadline=700.0, idle_generation=4, idle_timer=Timer(60, None),
        lifetime_timer=object(), activity_token=None, activity_job_id=None, activity_acks=queue.Queue(maxsize=1),
        settings={"idle_seconds": 60, "max_session_seconds": 600}, nonce="nonce")
    def send(packet):
        sent.append(packet)
        child.activity_acks.put({"type": "activity_ack", "instance_id": child.instance_id,
            "worker_pid": 41, "nonce": "nonce", "activity_token": packet["activity_token"],
            "previous_request_id": "previous", "job_id": packet["job_id"], "accepted": True})
    child.send = send
    key = str(tmp_path.resolve())
    monkeypatch.setitem(text_session._CURRENT, key, child)
    monkeypatch.setattr(text_session, "enabled", lambda *_: True)
    monkeypatch.setattr(text_session, "_key", lambda *_: "key")
    monkeypatch.setattr(text_session, "time", SimpleNamespace(perf_counter=lambda: clock[0]))
    monkeypatch.setattr(text_session.threading, "Timer", Timer)
    f = SimpleNamespace(root=tmp_path, child=child, clock=clock, sent=sent, cancel=cancel)
    f.payload = {"kind": "text", "job_id": "new-job", "student_session_id": "student"}
    f.call = lambda **kw: text_session.refresh_preflight_idle(f.payload, root=tmp_path,
        instance_id=kw.pop("instance_id", "owner"), previous_request_id=kw.pop("previous_request_id", "previous"),
        cancel_event=cancel, deadline=kw.pop("deadline", 400), **kw)
    yield f
    text_session._LAST.pop(key, None)


def test_once_only_renewal_keeps_model_request_and_maximum_timer(owner):
    f = owner; timer = f.child.lifetime_timer; old_generation = f.child.idle_generation
    assert f.call() is True
    assert f.child.idle_deadline == 185 and f.child.idle_timer.interval == 60
    assert f.child.lifetime_timer is timer and f.child.lifetime_deadline == 700
    assert f.child.request_id == "previous" and f.child.idle_generation == old_generation + 1
    assert f.call() is False and len(f.sent) == 1
    text_session._expire(f.root, "owner", "idle_expired", idle_generation=old_generation)
    assert not f.child.closed  # stale timer cannot close the refreshed owner


@pytest.mark.parametrize("changes", [{"instance_id": "stale"}, {"previous_request_id": "stale"}])
def test_stale_identity_cannot_refresh(owner, changes):
    assert owner.call(**changes) is False
    assert owner.sent == [] and owner.child.idle_deadline == 140


def test_expected_warm_owner_mismatch_does_not_refresh_current_owner(owner):
    owner.payload["expected_text_instance_id"] = "other"
    assert owner.call() is False
    assert owner.sent == [] and owner.child.idle_deadline == 140


@pytest.mark.parametrize("value", [None, "", 123, "x"*101])
def test_invalid_activity_job_is_noop(owner, value):
    owner.payload["job_id"] = value
    assert owner.call() is False and owner.sent == []


def test_read_only_status_does_not_refresh_owner(owner, monkeypatch):
    monkeypatch.setattr(text_session, "policy", lambda *_: {"mode": "session", "idle_seconds": 60, "max_session_seconds": 600})
    for _ in range(3):
        assert text_session.status(owner.root)["resident"]
    assert owner.child.idle_deadline == 140 and owner.child.idle_generation == 4 and owner.sent == []


@pytest.mark.parametrize("attribute,value", [("key", "foreign"), ("active", True), ("closed", True),
    ("idle_deadline", 125), ("lifetime_deadline", 125)])
def test_wrong_or_expired_owner_cannot_be_revived(owner, attribute, value):
    setattr(owner.child, attribute, value)
    assert owner.call() is False and owner.sent == []


@pytest.mark.parametrize("attribute,reason", [("idle_deadline", "idle_expired"), ("lifetime_deadline", "maximum_lifetime")])
def test_run_rechecks_expiry_even_when_timer_callback_is_delayed(owner, monkeypatch, attribute, reason):
    from contextlib import nullcontext
    from edu_tutor.speech import session
    owner.payload["expected_text_instance_id"] = "owner"
    setattr(owner.child, attribute, 125)
    monkeypatch.setattr(text_session, "policy", lambda *_: {"mode": "session", "idle_seconds": 60, "max_session_seconds": 600})
    monkeypatch.setattr(session, "execution_slot", lambda *_: nullcontext())
    closed = []
    def close(root, why, **identity):
        closed.append((why, identity))
        text_session._CURRENT.pop(str(owner.root.resolve()))
    monkeypatch.setattr(text_session, "close", close)
    monkeypatch.setattr(text_session, "_Child", lambda *_: pytest.fail("expired expected owner started a replacement"))
    with pytest.raises(RuntimeError, match="cold reload is forbidden"):
        list(text_session.run(owner.payload, root=owner.root, timeout=300))
    assert closed == [(reason, {"instance_id": "owner"})] and owner.sent == []


def test_cancel_or_deadline_before_activity_changes_nothing(owner):
    owner.cancel.set()
    with pytest.raises(RuntimeError, match="cancelled"): owner.call()
    owner.cancel.clear()
    with pytest.raises(TimeoutError, match="deadline"): owner.call(deadline=125)
    assert owner.sent == [] and owner.child.idle_deadline == 140


def test_cancellation_after_admission_leaves_only_one_bounded_idle_refresh(owner):
    original = owner.child.send
    def send(packet): original(packet); owner.cancel.set()
    owner.child.send = send
    with pytest.raises(RuntimeError, match="cancelled"): owner.call()
    assert owner.child.idle_deadline == 185 and owner.child.lifetime_deadline == 700
    assert not owner.child.closed and text_session._CURRENT[str(owner.root.resolve())] is owner.child


def test_bad_ack_fails_without_closing_or_replacing_owner(owner):
    original = owner.child.send
    def send(packet):
        original(packet); ack = owner.child.activity_acks.get_nowait(); ack["nonce"] = "foreign"
        owner.child.activity_acks.put_nowait(ack)
    owner.child.send = send
    with pytest.raises(RuntimeError, match="acknowledgment rejected"): owner.call()
    assert not owner.child.closed and owner.child.activity_acks.empty()


def test_maximum_expiry_can_remove_owner_during_ack_wait(owner):
    original = owner.child.send
    def send(packet):
        assert not text_session._LOCK._is_owned()  # no parent lock held during pipe I/O
        original(packet); owner.child.closed = True
        text_session._CURRENT.pop(str(owner.root.resolve()))
    owner.child.send = send
    with pytest.raises(RuntimeError, match="owner expired or changed"): owner.call()
    assert owner.child.closed and str(owner.root.resolve()) not in text_session._CURRENT


def test_stale_or_late_ack_never_leaks_into_generation_queue(tmp_path):
    child = object.__new__(text_session._Child)
    child.folder = tmp_path; child.activity_token = "current"; child.activity_acks = queue.Queue(maxsize=1)
    lines = [{"type": "activity_ack", "activity_token": "stale"}, {"type": "activity_ack", "activity_token": "current"}, {"type": "delta", "text": "x"}]
    child.process = SimpleNamespace(stdout=io.StringIO("".join(json.dumps(x)+"\n" for x in lines)))
    child.reader_error = None; normal = []
    child._enqueue = lambda line, *_: normal.append(line) or True
    child._read()
    assert len(normal) == 2 and json.loads(normal[0])["type"] == "delta" and normal[-1] is None
    assert child.activity_acks.get_nowait()["activity_token"] == "current"


@pytest.mark.parametrize("denial", ["scope", "closed_student", "student_count", "scope_count", "time"])
def test_denied_budget_never_runs_activity_hook(tmp_path, monkeypatch, denial):
    grant = {"id": "grant", "text_remaining": 1, "audio_remaining": 1, "vision_remaining": 1, "seconds_remaining": 300}
    student = {"exists": True, "state": "active", "parent_scope_id": "grant",
        "effective_remaining": {"text_requests": 1, "new_audio_clips": 1, "vision_requests": 1, "seconds": 300}}
    payload = {"kind": "text", "execution_allowance_id": "grant", "student_session_id": "student"}
    if denial == "scope": payload["execution_allowance_id"] = "wrong"
    if denial == "closed_student": student["state"] = "closed"
    if denial == "student_count": student["effective_remaining"]["text_requests"] = 0
    if denial == "scope_count": grant["text_remaining"] = 0
    if denial == "time": grant["seconds_remaining"] = 0
    monkeypatch.setattr(budget, "_execution_allowance", lambda *_: grant)
    monkeypatch.setattr(budget, "_student_view", lambda *_: student)
    calls = []
    with pytest.raises(budget.ResourceBudgetExceeded):
        budget._reserve_integrated(tmp_path, tmp_path/'ledger.json', {"requests": []}, {}, payload, 300,
                                   on_admitted=lambda: calls.append("activity"))
    assert calls == []


@pytest.mark.parametrize("kind,expected", [("text", ["activity", "storage"]), ("speech", ["storage"])])
def test_activity_is_after_caps_before_full_scan_and_heami_never_touches_it(tmp_path, monkeypatch, kind, expected):
    grant = {"id": "grant", "text_remaining": 1, "audio_remaining": 1, "vision_remaining": 1, "seconds_remaining": 300}
    student = {"exists": True, "state": "active", "parent_scope_id": "grant",
        "effective_remaining": {"text_requests": 1, "new_audio_clips": 1, "vision_requests": 1, "seconds": 300}}
    monkeypatch.setattr(budget, "_execution_allowance", lambda *_: grant)
    monkeypatch.setattr(budget, "_student_view", lambda *_: student)
    calls = []; state = {"requests": []}
    def storage(*_): calls.append("storage"); raise budget.ResourceBudgetExceeded("storage denied")
    monkeypatch.setattr(budget, "_storage_check", storage)
    with pytest.raises(budget.ResourceBudgetExceeded, match="storage denied"):
        budget._reserve_integrated(tmp_path, tmp_path/'ledger.json', state, {},
            {"kind": kind, "execution_allowance_id": "grant", "student_session_id": "student"}, 300,
            on_admitted=lambda: calls.append("activity"))
    assert calls == expected and state["requests"] == [] and not (tmp_path/'ledger.json').exists()


def test_actual_cpu_child_watchdog_accepts_one_refresh_and_reuses_same_object(tmp_path, monkeypatch):
    if os.name != "nt": pytest.skip("Windows owned child fixture")
    import sys
    root = Path(__file__).resolve().parents[1]
    (tmp_path/'.local').mkdir()
    (tmp_path/'.local/text-session-policy.json').write_text(json.dumps({"mode": "session", "idle_seconds": 3, "max_session_seconds": 12}))
    monkeypatch.setenv("PYTHONPATH", str(root))
    monkeypatch.setattr(text_session, "_command", lambda _root: [sys.executable, "-u", "-m", "scripts.text_resident_cpu_fixture"])
    payload = {"kind": "text", "messages": [{"role": "user", "content": "normal"}], "job_id": "first",
        "adapter": None, "max_new_tokens": 16, "execution_allowance_id": "cpu-fixture"}
    try:
        first = list(text_session.run(payload, root=tmp_path, timeout=20))
        meta = next(e for e in first if e["type"] == "metadata")
        time.sleep(1.4)
        state = text_session.status(tmp_path)["session"]
        assert text_session.refresh_preflight_idle({**payload, "job_id": "next", "student_session_id": "fixture"}, root=tmp_path,
            instance_id=state["instance_id"], previous_request_id=state["latest_request_id"], cancel_event=None, deadline=time.perf_counter()+10)
        time.sleep(2.0)  # Past the original idle3, but within the refreshed idle3.
        second = list(text_session.run({**payload, "job_id": "next", "expected_text_instance_id": state["instance_id"]}, root=tmp_path, timeout=20))
        after = next(e for e in second if e["type"] == "metadata")
        assert meta["worker_pid"] == after["worker_pid"] and meta["model_instance_id"] == after["model_instance_id"]
        assert after["model_load_count"] == 0
    finally:
        text_session.close(tmp_path, "fixture_end")
