"""CPU-only streaming persistence contract; no model, audio, or live database."""
import json
import threading
import time

import pytest

from edu_tutor.storage.db import Store
from edu_tutor.storage.timing import capture_storage_timing
from edu_tutor.jobs.manager import JobManager


@pytest.fixture
def owner(tmp_path):
    manager = JobManager(Store(tmp_path))
    yield manager
    manager.close()


def owned_job(manager, ident="one", epoch=1):
    value = {"id": ident, "kind": "chat", "state": "running", "generation_epoch": epoch,
             "owner_instance": manager.instance, "cancel_requested": False}
    manager.store.put("jobs", value)
    manager.cancels[ident] = threading.Event()
    return value


def partial(manager, text, ident="one", epoch=1):
    manager.update_partial(ident, epoch, partial_text=text, raw_partial_text=text)


def test_ui_sees_every_prefix_but_durable_writes_are_coalesced(owner):
    owned_job(owner)
    with capture_storage_timing() as timing:
        for n in range(1, 65):
            partial(owner, "가" * n)
        assert owner.view("one")["raw_partial_text"] == "가" * 64
        assert owner.store.get("jobs", "one")["raw_partial_text"] != "가" * 64
        owner.update("one", state="succeeded", result={"complete": True})
        metrics = timing.snapshot()
    saved = owner.store.get("jobs", "one")
    assert saved["raw_partial_text"] == "가" * 64
    assert saved["partial_persistence"]["chunks"] == 64
    assert metrics["phases"]["db_write"]["count"] < 10
    assert "one" not in owner.partials


def test_idle_stream_tail_is_flushed_without_another_delta(owner):
    owned_job(owner)
    partial(owner, "첫")
    partial(owner, "첫 마지막")
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if owner.store.get("jobs", "one").get("raw_partial_text") == "첫 마지막":
            break
        time.sleep(.02)
    assert owner.store.get("jobs", "one")["raw_partial_text"] == "첫 마지막"


def test_cancel_flushes_prefix_before_ack_and_late_delta_is_rejected(owner):
    owned_job(owner)
    partial(owner, "첫")
    partial(owner, "첫 둘")
    owner.cancel("one")
    saved = owner.store.get("jobs", "one")
    assert saved["cancel_requested"] and saved["raw_partial_text"] == "첫 둘"
    partial(owner, "첫 둘 취소 후")
    owner.update("one", state="cancelled")
    assert owner.store.get("jobs", "one")["raw_partial_text"] == "첫 둘"


def test_epoch_and_identity_isolate_requests_and_stale_callbacks(owner):
    owned_job(owner)
    partial(owner, "A")
    pending = owner.partials["one"]
    owner.update("one", state="cancelled")
    owned_job(owner, "two", epoch=2)
    partial(owner, "B", ident="two", epoch=2)
    partial(owner, "B forged", ident="two", epoch=1)
    owner._partial_timer("one", pending)
    assert owner.view("two")["raw_partial_text"] == "B"
    assert owner.store.get("jobs", "one")["state"] == "cancelled"


def test_terminal_states_cannot_be_rewritten_by_late_completion(owner):
    owned_job(owner)
    partial(owner, "원문")
    owner.update("one", state="cancelled")
    owner.update("one", state="succeeded", result={"late": True})
    assert owner.view("one")["state"] == "cancelled"
    assert not owner.view("one").get("result")


def test_changed_prefix_and_oversize_output_rejected(owner):
    owned_job(owner)
    partial(owner, "원래")
    with pytest.raises(ValueError, match="prefix"):
        partial(owner, "다른")
    with pytest.raises(ValueError, match="크기"):
        partial(owner, "가" * 60001)
    assert owner.view("one")["raw_partial_text"] == "원래"


def test_background_write_failure_cancels_and_cannot_commit_success(owner, monkeypatch):
    owned_job(owner)
    partial(owner, "원문")
    partial(owner, "원문 꼬리")
    pending = owner.partials["one"]
    original = owner.store.put
    def broken(*args, **kwargs):
        raise OSError("fixture disk write failure")
    monkeypatch.setattr(owner.store, "put", broken)
    owner._partial_timer("one", pending)
    assert owner.cancels["one"].is_set()
    monkeypatch.setattr(owner.store, "put", original)
    with pytest.raises(RuntimeError, match="persistence failed"):
        owner.update("one", state="succeeded")
    owner.update("one", state="failed", error=pending["error"])
    assert owner.store.get("jobs", "one")["state"] == "failed"
    assert owner.store.get("jobs", "one")["raw_partial_text"] == "원문 꼬리"


def test_close_flushes_then_recovery_never_promotes_partial_to_completed(tmp_path):
    manager = JobManager(Store(tmp_path))
    owned_job(manager)
    partial(manager, "앞")
    partial(manager, "앞 뒤")
    manager.close()
    restored = JobManager(Store(tmp_path))
    try:
        row = restored.view("one")
        assert row["raw_partial_text"] == "앞 뒤"
        assert row["state"] == "interrupted"
        assert not row.get("result")
    finally:
        restored.close()


def test_stored_running_job_after_unclean_shutdown_is_interrupted(tmp_path):
    store = Store(tmp_path)
    store.put("jobs", {"id": "interrupted", "state": "running", "raw_partial_text": "불완전"})
    manager = JobManager(store)
    try:
        assert manager.view("interrupted")["state"] == "interrupted"
        assert manager.view("interrupted")["raw_partial_text"] == "불완전"
    finally:
        manager.close()


def test_serialization_or_commit_failure_is_not_normal_completion(owner, monkeypatch):
    owned_job(owner)
    partial(owner, "기록")
    with pytest.raises(ValueError):
        owner.update("one", state="succeeded", result={"invalid": float("nan")})
    assert owner.store.get("jobs", "one")["state"] == "running"
    owner.update("one", state="failed", error="invalid JSON")


def test_job_timing_records_host_phases_without_data(owner):
    owned_job(owner)
    with capture_storage_timing() as timing:
        partial(owner, "교육용 원문")
        owner.update("one", state="succeeded")
        snap = timing.snapshot()
    assert snap["phases"]["db_write"]["count"] == 2
    assert snap["phases"]["job_lock_wait"]["count"] >= 2
    assert "교육용 원문" not in json.dumps(snap, ensure_ascii=False)
