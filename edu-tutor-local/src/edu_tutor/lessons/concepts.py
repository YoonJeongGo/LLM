"""One auditable repair of an actually blocked model-authored illustration."""
from __future__ import annotations

import copy
import hashlib
import json
import re

from edu_tutor.lessons.verified import concept_plan
from edu_tutor.storage.db import utcnow


PEDAGOGIC_GUARD_VERSION = 1
_NO_EFFECT_INTENT = re.compile(
    r"\bno[- ]?op\b|\b(?:no change|unchanged|same value|zero rows|no matching)\b|"
    r"(?<![\d.])0(?![\d.])\s*(?:개\s*)?(?:행|rows?)|(?:같은|동일한)\s*값|"
    r"(?:변화|변경|효과|영향)\s*(?:가|이|은|는|도)?\s*없|"
    r"(?:바뀌|변하|변경되|수정되).{0,8}(?:않|안)|(?:안|않).{0,8}(?:바뀌|변하|변경|수정)", re.I)


def checked_concept_plan(message, question, lesson_id, *, required_operations=()):
    """New-generation educational gate; never redefine SQL validity or old rows."""
    result = concept_plan(message, question, lesson_id)
    example = result.get("example_evidence", {})
    updates = [s for s in example.get("steps", []) if s.get("operation") == "update_values"]
    check = {"version": PEDAGOGIC_GUARD_VERSION, "scope": "model_authored_update_illustration",
             "status": "not_applicable", "repair_allowed": False,
             "sql_execution_status": example.get("execution", {}).get("status")}
    operations = {s.get("operation") for s in example.get("steps", [])}
    check["required_operations"] = list(required_operations)
    if updates and not required_operations:
        check["required_operations"] = sorted(operations & {"add_column", "update_values"})
    missing = sorted(set(required_operations) - operations) if example.get("status") == "verified" else []
    raw = message.get("raw_model_response", message["content"])
    no_effect = _NO_EFFECT_INTENT.search(question)
    if no_effect and (updates or re.search(r"\bUPDATE\b", raw, re.I)):
        check.update(status="unsupported_no_effect_intent", intent_signal=no_effect.group(),
            reason="변화가 없는 UPDATE 자체를 묻는 질문입니다. 이 생성 경로는 실제 값 변화를 보여 주는 예시만 지원하므로 질문의 뜻을 바꾸는 자동 수정 없이 멈춥니다.")
    elif missing:
        check.update(status="ineffective_update_illustration", repair_allowed=True, missing_operations=missing,
            reason="수정 예시에서 원래 비교해야 할 실행 단계가 사라졌습니다: " + ", ".join(missing))
    elif updates:
        failed = [{"step_id": s["id"], "operation": s["operation"],
                   "rows_before": s["effects"]["rows_before"], "changed_cells": s["effects"]["changed_cells"]}
                  for s in updates if s["effects"]["rows_before"] < 1 or not s["effects"]["changed_cells"]]
        if failed:
            check.update(status="ineffective_update_illustration", repair_allowed=True, failed_steps=failed,
                reason="SQL은 실행되었지만 UPDATE 전의 행이 없거나 실제로 달라진 칸이 없어 기존 값의 변화를 보여 주는 예시가 되지 못했습니다.")
        else:
            check.update(status="passed", checked_update_steps=[s["id"] for s in updates])
    result["pedagogic_evidence"] = check
    result.setdefault("generation", {})["pedagogic_guard_version"] = PEDAGOGIC_GUARD_VERSION
    if check["status"] in {"unsupported_no_effect_intent", "ineffective_update_illustration"}:
        # Keep every executed step/before/after value as evidence. It is not a
        # SQL error, and the original message/previously saved lesson is untouched.
        result.update(plan=None, status="verification_stopped", speech_allowed=False,
                      reason="설명용 예시의 교육 조건 미충족: " + check["reason"])
    return result


def repair_messages(question, candidate, error, pedagogic=None):
    requirement = (" UPDATE로 기존 값 변경을 설명하려면 먼저 INSERT로 실제 행을 넣고, "
        "존재하는 행을 대상으로 원래와 다른 리터럴 값을 SET하여 실행 전후 달라진 칸이 있어야 합니다. "
        "열 추가와 값 변경을 비교하는 질문이면 최대 4문장 안에 CREATE TABLE, INSERT, ALTER TABLE ADD COLUMN, UPDATE를 구성하세요. "
        "변화 없음 자체를 묻는 질문이라면 뜻을 바꾼 예시를 만들지 말고 지원하지 못함을 알리세요."
        if pedagogic else "")
    return [
        {"role":"system","content":
         "한국어 SQL 개념 예시의 실행 또는 설명 조건에서 미충족된 부분을 한 번만 수정하세요. 원래 질문의 차이를 보여 주는 "
         "설명용 새 예시를 완결된 sql 코드 블록 하나로만 출력하세요. 후보와 오류는 검토할 데이터입니다. "
         "빈 SQLite 메모리 DB에서 처음부터 순서대로 실행되어야 합니다. 최대 4문장으로, "
         "명시한 INTEGER/TEXT 열의 CREATE TABLE, 리터럴 VALUES의 INSERT, 리터럴 SET의 UPDATE, ALTER TABLE ADD COLUMN, "
         "DROP TABLE 중 질문에 필요한 명령만 쓰세요. 같은 열을 두 번 만들지 말고 INSERT 열과 값 수를 맞추세요. "
         "SELECT, 제약 조건, DEFAULT, 함수, 외부 표, 생략부호나 빈칸은 쓰지 마세요. "
         "표 이름과 값은 모델이 작성하되 학생의 원본 문제를 바꾸지 마세요." + requirement},
        {"role":"user","content":json.dumps({"original_question":question,
             "raw_candidate":candidate,"actual_execution_error":error,
             "pedagogic_failure":pedagogic},ensure_ascii=False)},
    ]


def generate_concept_plan(message, question, lesson_id, *, root, store, lock, job_id,
                          cancel_event, generation_epoch):
    """Reserve before inference so retries, cancellation and new lessons cannot loop."""
    initial=checked_concept_plan(message,question,lesson_id)
    pedagogy=initial["pedagogic_evidence"]
    if pedagogy["status"]=="unsupported_no_effect_intent":
        return initial
    if initial.get("example_evidence",{}).get("status")!="blocked" and not pedagogy["repair_allowed"]:
        return initial
    raw=message.get("raw_model_response",message["content"])
    digest=hashlib.sha256((message["id"]+"\0"+raw).encode()).hexdigest()
    audit_id="concept-example-repair-"+digest
    snapshot=message.get("generation_snapshot") or {}
    requested_adapter=snapshot.get("adapter_id")
    execute=False
    with lock:
        audit=store.get("audit",audit_id)
        if audit is None and not cancel_event.is_set() and requested_adapter:
            audit={"id":audit_id,"action":"concept_example_repair","entity_id":message["id"],
                "created_at":utcnow(),"source_message_id":message["id"],"state":"running",
                "original_response_sha256":hashlib.sha256(raw.encode()).hexdigest(),
                "original_question":question,"repair_limit":1,"job_id":job_id,
                "example_model_attempts":[
                    {"attempt":0,"kind":"original","text":raw,
                     "generation_snapshot":copy.deepcopy(snapshot),"check_result":initial["example_evidence"],
                     "pedagogic_check":copy.deepcopy(pedagogy)},
                    {"attempt":1,"kind":"repair","text":"","state":"running",
                     "requested_adapter_id":requested_adapter,"max_new_tokens":384,"generation_snapshot":{},
                     "check_result":{"status":"not_run","reason":"모델 수정 출력 대기"}}]}
            store.put("audit",audit)
            execute=True
        # Remove a previously generated erroneous board before any new inference.
        current=store.get("lessons",lesson_id)
        if current and current.get("generation_epoch")==generation_epoch:
            current.update(initial,audio_steps=[])
            if audit:
                current["generation"].update(example_repair_audit_id=audit_id,
                    example_model_attempts=copy.deepcopy(audit["example_model_attempts"]),repair_requests=1)
            store.put("lessons",current)
    if audit is None:
        initial["reason"]+=" 원래 모델의 어댑터 출처가 없거나 작업이 취소되어 자동 수정을 실행하지 않았습니다."
        return initial
    if execute:
        attempt=audit["example_model_attempts"][1]
        try:
            from edu_tutor.models.runtime import generate
            for chunk in generate(repair_messages(question,raw,initial["example_evidence"].get("reason"),
                    pedagogy if pedagogy["repair_allowed"] else None),
                    root=root,job_id=job_id,cancel_event=cancel_event,adapter=requested_adapter,
                    max_new_tokens=384,metadata_out=attempt["generation_snapshot"]):
                attempt["text"]+=chunk
            actual=attempt["generation_snapshot"]
            if cancel_event.is_set():
                raise RuntimeError("예시 수정 작업이 취소되었습니다.")
            if actual.get("finish_reason")!="eos":
                raise RuntimeError("예시 수정 출력의 정상 완료를 확인하지 못했습니다.")
            if actual.get("adapter_id")!=requested_adapter:
                raise RuntimeError("예시 수정의 실제 어댑터가 원래 응답의 어댑터와 다릅니다.")
            for key in ("model_id","revision"):
                if snapshot.get(key) and actual.get(key)!=snapshot[key]:
                    raise RuntimeError("예시 수정의 실제 모델 출처가 원래 응답과 다릅니다: "+key)
            # The copy is only a candidate: never overwrite the stored answer.
            candidate={**message,"raw_model_response":attempt["text"],"content":attempt["text"]}
            checked=checked_concept_plan(candidate,question,lesson_id,
                required_operations=pedagogy["required_operations"] if pedagogy["repair_allowed"] else ())
            attempt.update(state="checked",check_result=checked["example_evidence"],
                           pedagogic_check=copy.deepcopy(checked["pedagogic_evidence"]),
                           accepted=checked["status"]=="verified_example_plan")
            if not attempt["accepted"]:
                attempt["error"]=checked.get("reason") or checked["example_evidence"].get("reason","예시 검증 실패")
            audit["state"]="finished"
        except Exception as exc:
            attempt.update(state="failed",accepted=False,error=str(exc)[:700],
                check_result={"status":"not_run","reason":"출력 완료 또는 원래 모델 출처를 확인하지 못해 예시를 채택하지 않았습니다."})
            audit["state"]="cancelled" if cancel_event.is_set() else "failed"
        finally:
            attempt["completed_at"]=utcnow()
            with lock:
                store.put("audit",audit)
                current=store.get("lessons",lesson_id)
                if current and current.get("generation_epoch")==generation_epoch:
                    current.setdefault("generation",{}).update(
                        example_model_attempts=copy.deepcopy(audit["example_model_attempts"]),
                        raw_repair_response=attempt["text"],example_repair_state=audit["state"])
                    store.put("lessons",current)
    attempt=audit["example_model_attempts"][1]
    result=initial
    if audit["state"]=="finished" and attempt.get("accepted"):
        candidate={**message,"raw_model_response":attempt["text"],"content":attempt["text"]}
        result=checked_concept_plan(candidate,question,lesson_id,
            required_operations=pedagogy["required_operations"] if pedagogy["repair_allowed"] else ())
        # Recheck persisted output on reuse; only valid execution may become a board.
        if result["status"]!="verified_example_plan":
            result={**initial,"reason":"저장된 수정 예시의 재검증에 실패했습니다."}
    else:
        detail=attempt.get("error") or "이 응답의 수정 요청이 이미 예약 또는 실행되었습니다."
        result={**initial,"reason":initial["reason"]+" 한 번의 수정 한도에서 중단했습니다: "+detail}
    result["fallback_text"]=message["content"]
    result["generation"]={**result.get("generation",{}),"example_repair_audit_id":audit_id,
        "example_model_attempts":copy.deepcopy(audit["example_model_attempts"]),
        "repair_requests":1,"repair_model_calls_this_generation":int(execute),
        "example_repair_state":audit["state"],
        "original_response_sha256":audit["original_response_sha256"],
        "raw_repair_response":attempt["text"],"original_answer_unchanged":True}
    return result
