import hashlib
import json
import threading

import pytest

from edu_tutor.models import runtime
from edu_tutor.models.worker import emit
from edu_tutor.models.vision_runtime import transcribe
from edu_tutor.speech.provider import pronunciation


def test_metadata_event_can_describe_worker_kind(capsys):
    emit("metadata", kind="text", finish_reason="eos")
    value = json.loads(capsys.readouterr().out)
    assert value == {"type": "metadata", "kind": "text", "finish_reason": "eos"}


def test_partial_answer_is_never_completed(monkeypatch, tmp_path, nf4_inference_fixture):
    monkeypatch.setattr(runtime, "model_status", lambda *_: {"ready": True})
    monkeypatch.setattr(runtime, "run_worker", lambda *_args, **_kwargs: iter([
        {"type": "delta", "text": "아직 완성되지 않은 답변"},
        {"type": "metadata", "finish_reason": "length_or_timeout", "requested_precision": "nf4",
         "inference": nf4_inference_fixture}, {"type":"done"}]))
    result = runtime.generate([{"role":"user","content":"질문"}],root=tmp_path)
    assert next(result) == "아직 완성되지 않은 답변"
    with pytest.raises(runtime.GenerationIncomplete):
        next(result)


def test_eos_answer_completes(monkeypatch, tmp_path, nf4_inference_fixture):
    monkeypatch.setattr(runtime, "model_status", lambda *_: {"ready": True})
    monkeypatch.setattr(runtime, "run_worker", lambda *_args, **_kwargs: iter([
        {"type": "delta", "text": "설명"}, {"type": "metadata", "finish_reason": "eos",
         "requested_precision": "nf4", "inference": nf4_inference_fixture}, {"type":"done"}]))
    assert list(runtime.generate([{"role":"user","content":"질문"}],root=tmp_path)) == ["설명"]


def test_vision_only_accepts_registered_local_photos(tmp_path):
    outside = tmp_path / "not-a-photo.png"
    outside.write_bytes(b"not really an image")
    with pytest.raises(ValueError, match="registered"):
        transcribe(outside, root=tmp_path)


def test_speech_dictionary_preserves_values():
    assert pronunciation("COUNT(*) = 3, COUNT(v) = 2, NULL = 1") == "카운트 별표 = 3, COUNT(v) = 2, 널 = 1"


@pytest.mark.parametrize("terminal", ["done", "missing", "error"])
def test_vision_requires_validated_worker_completion(monkeypatch, tmp_path, terminal):
    photo = tmp_path / ".local/photos/sample.png"
    photo.parent.mkdir(parents=True)
    photo.write_bytes(b"fixture: worker is replaced")
    manifest = tmp_path / ".local/models/vision/model-manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}")
    consumed = []

    def events(*args, **kwargs):
        yield {"type": "transcription", "original_text": "score NULL"}
        consumed.append("after_transcription")
        if terminal == "error":
            raise runtime.ModelUnavailable("worker exit failed")
        if terminal == "done":
            yield {"type": "done"}
        consumed.append("validated_exit")

    monkeypatch.setattr(runtime, "run_worker", events)
    if terminal == "done":
        assert transcribe(photo, root=tmp_path) == {"original_text": "score NULL"}
        assert consumed == ["after_transcription", "validated_exit"]
    else:
        with pytest.raises((RuntimeError, runtime.ModelUnavailable)):
            transcribe(photo, root=tmp_path)
        assert "after_transcription" in consumed
