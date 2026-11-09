"""T0 evaluation state/protocol tests. All model events are explicit fixtures."""
import json
import threading

import pytest

from edu_tutor.models import runtime
from edu_tutor.models.evaluate import PROTOCOL, run_evaluation
from edu_tutor.evaluation import sql_sandbox


@pytest.fixture
def evaluation_root(tmp_path):
    folder = tmp_path / "data/demo"
    folder.mkdir(parents=True)
    records = [
        {"id": "sql-fixture", "messages": [
            {"role": "user", "content": "숫자 1을 answer 열로 반환하세요."},
            {"role": "assistant", "content": "REFERENCE_ANSWER_NEVER_FORWARD"}],
         "fixture": {"sentinel": "PRIVATE_FIXTURE_NEVER_FORWARD"},
         "expected": {"sql": "SELECT 1 AS answer", "columns": ["answer"], "rows": [[1]]}},
        {"id": "clarify-fixture", "messages": [
            {"role": "user", "content": "매출을 비교해 주세요."},
            {"role": "assistant", "content": "REFERENCE_CLARIFICATION_NEVER_FORWARD"}]},
    ]
    (folder / "test.jsonl").write_text("\n".join(json.dumps(row) for row in records), encoding="utf-8")
    return tmp_path


def item(identity="sql-fixture", finish_reason="eos"):
    return {"type": "evaluation_item", "id": identity,
            "text": '{"sql":"SELECT 1 AS answer","explanation":"상수 반환"}' if identity == "sql-fixture" else "비교 기간과 매출 자료가 필요합니다.",
            "finish_reason": finish_reason, "output_tokens": 10, "latency_seconds": 0.1,
            "peak_vram_bytes": 123, "revision": "fixture_revision"}


@pytest.fixture(autouse=True)
def fixture_grader(monkeypatch):
    # SQL execution is covered separately; this module isolates protocol/status.
    monkeypatch.setattr(sql_sandbox, "evaluate_sql", lambda sql, record: {"match": sql == "SELECT 1 AS answer"})


def saved_report(root):
    return json.loads((root / "result/evaluation.json").read_text(encoding="utf-8"))


def test_fixed_protocol_passes_only_public_questions_and_preserves_review_boundary(evaluation_root, monkeypatch):
    cancel = threading.Event()
    def worker(payload, **options):
        assert options == {"root": evaluation_root, "timeout": 900, "cancel_event": cancel}
        assert payload["job_id"] == "fixture-job"
        assert payload["adapter"] == "fixture-adapter"
        assert set(payload) == {"kind", "questions", "adapter", "job_id"}
        assert all(set(question) == {"id", "question"} for question in payload["questions"])
        serialized = json.dumps(payload)
        assert "REFERENCE_" not in serialized and "PRIVATE_FIXTURE" not in serialized
        assert "expected" not in serialized and "assistant" not in serialized
        yield {"type": "metadata", "ignored": True}
        yield item()
        yield item("clarify-fixture")
    monkeypatch.setattr(runtime, "run_worker", worker)
    report = run_evaluation(evaluation_root, evaluation_root / "result", "fixture-adapter",
                            cancel_event=cancel, job_id="fixture-job")
    assert report["status"] == "completed"
    assert (report["sql_correct"], report["sql_total"], report["total"], report["truncated"]) == (1, 1, 2, 0)
    assert PROTOCOL["max_new_tokens"] == 256 and PROTOCOL["do_sample"] is False and PROTOCOL["rag"] is False
    assert report["human_review"] == "not_reviewed"
    assert report["items"][1]["clarification_quality"] == "not_reviewed"
    assert saved_report(evaluation_root) == report


@pytest.mark.parametrize("completed_items", [0, 1, 2])
def test_cancellation_never_becomes_completed_even_after_last_item(evaluation_root, monkeypatch, completed_items):
    cancel = threading.Event()
    def worker(payload, **options):
        assert options["cancel_event"] is cancel
        for event in [item(), item("clarify-fixture")][:completed_items]:
            yield event
        cancel.set()
    monkeypatch.setattr(runtime, "run_worker", worker)
    report = run_evaluation(evaluation_root, evaluation_root / "result", cancel_event=cancel)
    assert report["status"] == "cancelled"
    assert len(report["items"]) == completed_items
    assert "sql_correct" not in report and "total" not in report
    assert saved_report(evaluation_root)["status"] == "cancelled"


@pytest.mark.parametrize("events", [[], [item()], [item(), item()]])
def test_missing_or_duplicate_output_cannot_mark_evaluation_complete(evaluation_root, monkeypatch, events):
    monkeypatch.setattr(runtime, "run_worker", lambda *args, **kwargs: iter(events))
    with pytest.raises(RuntimeError, match="누락"):
        run_evaluation(evaluation_root, evaluation_root / "result")
    report = saved_report(evaluation_root)
    assert report["status"] == "failed"
    assert len(report["items"]) == len(events)
    assert "sql_correct" not in report and "total" not in report


def test_worker_failure_preserves_partial_evidence_without_completed_totals(evaluation_root, monkeypatch):
    def worker(*args, **kwargs):
        yield item()
        raise TimeoutError("fixture timeout")
    monkeypatch.setattr(runtime, "run_worker", worker)
    with pytest.raises(TimeoutError, match="fixture timeout"):
        run_evaluation(evaluation_root, evaluation_root / "result")
    report = saved_report(evaluation_root)
    assert report["status"] == "failed" and len(report["items"]) == 1
    assert report["error"] == "fixture timeout" and "total" not in report


def test_worker_cancellation_error_preserves_partial_items_and_cancelled_status(evaluation_root, monkeypatch):
    cancel = threading.Event()
    def worker(*args, **kwargs):
        yield item()
        cancel.set()
        raise runtime.ModelUnavailable("RuntimeError: Evaluation cancelled")
    monkeypatch.setattr(runtime, "run_worker", worker)
    report = run_evaluation(evaluation_root, evaluation_root / "result", cancel_event=cancel)
    assert report["status"] == "cancelled" and len(report["items"]) == 1
    assert report["error"] == "RuntimeError: Evaluation cancelled"
    assert "total" not in report and "sql_correct" not in report
    assert saved_report(evaluation_root) == report


def test_truncated_sql_is_never_graded_as_completed_answer(evaluation_root, monkeypatch):
    monkeypatch.setattr(runtime, "run_worker", lambda *args, **kwargs: iter([item(finish_reason="length"), item("clarify-fixture")]))
    def forbidden_grading(*args):
        pytest.fail("A truncated SQL response must not be executed or credited")
    monkeypatch.setattr(sql_sandbox, "evaluate_sql", forbidden_grading)
    report = run_evaluation(evaluation_root, evaluation_root / "result")
    assert report["status"] == "completed"  # All questions attempted; completion is separately counted.
    assert report["sql_correct"] == 0 and report["truncated"] == 1
    assert report["items"][0]["sql_match"] is False


def test_unknown_response_id_fails_closed(evaluation_root, monkeypatch):
    monkeypatch.setattr(runtime, "run_worker", lambda *args, **kwargs: iter([item("unknown")]))
    with pytest.raises(KeyError):
        run_evaluation(evaluation_root, evaluation_root / "result")
    assert saved_report(evaluation_root)["status"] == "failed"
