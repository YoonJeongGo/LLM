"""Append-only revalidation of a saved SQL answer, never new text inference."""
from __future__ import annotations

import copy
import hashlib
import json

from edu_tutor.lessons.verified import generate_verified_plan
from edu_tutor.problems.evidence import display_answer
from edu_tutor.problems.app_correction import verify_with_app_correction as verify_answer
from edu_tutor.storage.db import new_id, utcnow


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def reprocess_saved_lesson(source, message, question, request_id):
    if message.get("role") != "assistant" or message.get("verification_mode") != "tools":
        raise ValueError("원문과 검증 모드가 보존된 SQL 답변이 필요합니다.")
    problem = message.get("problem")
    raw = message.get("raw_model_response")
    if not problem or problem.get("task_kind") not in {"query_result", "write_sql"} or not isinstance(raw, str) or not raw.strip():
        raise ValueError("저장된 SQL 문제·원시 답변이 필요합니다. 모델을 새로 호출하지 않습니다.")
    if source.get("problem") != problem or message.get("original_problem") != problem:
        raise ValueError("저장된 문제 원본과 강의 입력이 일치하지 않습니다.")
    attempts = message.get("model_attempts") or []
    if attempts and (attempts[0].get("text") != raw or attempts[0].get("incomplete")):
        raise ValueError("원시 답변의 완성 여부 또는 기록 일치를 확인하지 못했습니다.")
    if (message.get("generation_snapshot") or {}).get("finish_reason") not in {None, "eos"}:
        raise ValueError("중간에 잘린 모델 답변은 완성된 답변으로 재사용하지 않습니다.")
    metadata = {"mode": "saved_response_cpu_reverification", "request_id": request_id,
        "source_lesson_id": source["id"], "source_message_id": message["id"],
        "source_lesson_sha256": digest(source), "source_message_sha256": digest(message),
        "question_sha256": digest(question), "raw_model_response_sha256": digest(raw),
        "problem_sha256": digest(problem), "created_at": utcnow(), "new_model_calls": 0,
        "new_text_inference": False, "generation_snapshot_is_historical": True,
        "human_review": "not_reviewed"}
    evidence = verify_answer(problem, raw, question, message.get("hypothesis"))
    # A CPU reprocessing request never invokes the optional model repair path.
    evidence.update(can_repair=False, repair_skipped="saved_response_cpu_only")
    derived = copy.deepcopy(message)
    derived.update(id=new_id(), created_at=metadata["created_at"], content=display_answer(evidence),
        evidence=evidence, provenance="tool_derived" if evidence["status"] == "verified" else "saved_response_rechecked",
        reprocessing=metadata, reprocessed_from_message_id=message["id"],
        verification={"status": evidence["status"], "sql_execution": evidence["execution"]["status"],
                      "human_review": "not_reviewed"})
    # Original inference timings remain in the immutable source record, not as a
    # misleading latency claim on this model-free attempt.
    derived.pop("latency", None)
    lesson_id = new_id()
    result = generate_verified_plan(derived, question, lesson_id)
    lesson = {"id": lesson_id, "is_demo": False, "source_message_id": derived["id"],
        "problem": copy.deepcopy(problem), "original_problem": copy.deepcopy(problem),
        "evidence": evidence, "generation_epoch": 0, "valid": True, "audio_steps": [],
        "created_at": metadata["created_at"], "reprocessing": metadata, **result}
    return derived, lesson
