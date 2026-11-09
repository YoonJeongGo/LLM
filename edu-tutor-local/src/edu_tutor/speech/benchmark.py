"""Authenticated, grant-bound two-call lifecycle comparison; never a cache hit."""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from fastapi import HTTPException

from edu_tutor.jobs.manager import TERMINAL
from edu_tutor.models.budget import policy, status as budget_status, ResourceBudgetExceeded
from edu_tutor.storage.db import utcnow
from edu_tutor.speech.provider import _spec

AUTHORIZATION = "20261027-tts-worker-reuse-2calls"
SEED = 20261027


def save(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


class ReuseBenchmark:
    def __init__(self, root, store, jobs, valid_lesson, fingerprint):
        self.root, self.store, self.jobs = Path(root), store, jobs
        self.valid_lesson, self.fingerprint = valid_lesson, fingerprint

    def start(self, *, comparison_id, phase, lesson_id, step_id, request_id):
        if not re.fullmatch(r"[a-f0-9]{32}", comparison_id) or phase not in {"cold", "warm"}:
            raise ValueError("Invalid TTS comparison identity")
        folder = self.root / "runs/student-latency/20261027/tts-worker-reuse" / comparison_id
        path = folder / "comparison.json"
        key = "benchmark:"+comparison_id
        with self.jobs.lock:
            lesson = self.valid_lesson(lesson_id)
            if lesson.get("is_demo") or not lesson.get("speech_allowed") or not lesson.get("plan"):
                raise HTTPException(409, "계산 근거가 검증된 저장 수업의 대사가 필요합니다.")
            step = next((s for s in lesson["plan"]["steps"] if s["id"] == step_id), None)
            if not step:
                raise ValueError("저장 수업의 단계를 찾을 수 없습니다.")
            binding = self.fingerprint(lesson)
            canonical_id, spec = _spec(step["speech"], self.root, "Sohee")
            model_folder = self.root / ".local/models/tts"
            manifest = json.loads((model_folder / "model-manifest.json").read_text(encoding="utf-8"))
            pinned = {item["path"]: item["sha256"] for item in manifest.get("files", [])}
            config_hashes = {name: hashlib.sha256((model_folder/name).read_bytes()).hexdigest()
                             for name in ("config.json", "generation_config.json")}
            if any(pinned.get(name) != value for name, value in config_hashes.items()):
                raise HTTPException(409, "설치된 TTS 설정이 고정 revision과 일치하지 않습니다.")
            previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
            if previous and (previous["binding"] != binding or previous["spec"] != spec or previous["config_hashes"] != config_hashes
                             or previous["lesson_id"] != lesson_id or previous["step_id"] != step_id):
                raise HTTPException(409, "비교 중 원본 대사·판서·설정이 바뀌었습니다.")
            if previous and previous.get(phase):
                if previous[phase]["request_id"] != request_id:
                    raise HTTPException(409, "이 비교 단계는 이미 요청됐습니다. 자동 재시도하지 않습니다.")
                return {"job_id": previous[phase]["job_id"], "comparison_id": comparison_id, "phase": phase}
            limits, budget = policy(self.root), budget_status(self.root)
            grant = budget.get("active_execution_allowance")
            if (not budget.get("enabled") or not grant or grant["id"] != AUTHORIZATION
                    or (limits.get("active_execution_allowance") or {}).get("runtime_scope") != "tts_session_benchmark"):
                raise ResourceBudgetExceeded("동일 TTS 두 번 비교에 대한 활성 승인이 없습니다.")
            if any(j["state"] not in TERMINAL for j in self.store.list("jobs")):
                raise HTTPException(409, "진행 중 작업이 있습니다. 비교 작업을 병행하지 않습니다.")
            if grant["audio_remaining"] < (2 if phase == "cold" else 1) or min(grant["seconds_remaining"], budget["gpu_seconds_remaining"]) < (14 if phase == "cold" else 7):
                raise ResourceBudgetExceeded("독립 두 요청의 호출·시간 한도를 확보할 수 없습니다.")
            expected_instance = None
            if phase == "cold":
                if previous:
                    raise HTTPException(409, "기존 비교 기록을 초기화하지 않습니다.")
                # The grant is for one comparison, not multiple cold starts.
                if grant["audio_remaining"] != 2:
                    raise ResourceBudgetExceeded("이미 사용한 비교 승인을 새 cold 실행으로 재시도하지 않습니다.")
                folder.mkdir(parents=True, exist_ok=False)
                previous = {"comparison_id": comparison_id, "created_at": utcnow(), "authorization_id": AUTHORIZATION,
                    "lesson_id": lesson_id, "step_id": step_id, "source_message_id": lesson["source_message_id"],
                    "binding": binding, "spec": spec, "config_hashes": config_hashes, "canonical_cache_id_not_used": canonical_id,
                    "seed": SEED, "cache_bypass": "benchmark_only", "session_key": key,
                    "per_call_timeout_seconds": min(300.0, grant["seconds_remaining"]/2, budget["gpu_seconds_remaining"]/2),
                    "budget_before": budget, "human_review": "not_reviewed", "new_question_run": False}
            else:
                if not previous or not previous.get("cold"):
                    raise HTTPException(409, "정상 cold 결과 없이 warm을 실행하지 않습니다.")
                first_job = self.store.get("jobs", previous["cold"]["job_id"])
                if request_id == previous["cold"]["request_id"]:
                    raise ValueError("두 독립 합성은 서로 다른 요청 ID가 필요합니다.")
                if not first_job or first_job["state"] != "succeeded" or not first_job.get("result", {}).get("complete"):
                    raise HTTPException(409, "첫 합성이 실패하거나 미완료여서 두 번째를 실행하지 않습니다.")
                first_audio = first_job["result"]["audio"]
                info = first_audio.get("session_info") or {}
                expected_instance = info.get("worker_instance_id")
                if not expected_instance:
                    raise HTTPException(409, "첫 합성의 worker 인스턴스 근거가 없습니다.")
            output = folder / phase
            output.mkdir(exist_ok=False)
            audio_id = hashlib.sha256((canonical_id+":"+comparison_id+":"+phase).encode()).hexdigest()
            queued_at = time.monotonic()

            def execute(job_id, cancel):
                from edu_tutor.models.runtime import run_worker
                from edu_tutor.speech import session
                entered = time.monotonic()
                self.jobs.update(job_id, state="running")
                events, audio = [], None
                success = False
                release = None
                try:
                    if self.fingerprint(self.valid_lesson(lesson_id)) != binding:
                        raise RuntimeError("비교 입력이 실행 전에 변경됐습니다.")
                    if phase == "cold":
                        session.close(self.root, reason="benchmark_cold_start")
                    payload = {"kind": "speech_batch", "job_id": job_id, "request_id": request_id,
                        "items": [{"spec": spec, "audio_id": audio_id}], "output_dir": str(output),
                        "tts_session_key": key, "tts_benchmark": True, "detailed_timing": True, "seed": SEED,
                        "expected_instance_id": expected_instance}
                    for event in run_worker(payload, root=self.root, cancel_event=cancel, timeout=previous["per_call_timeout_seconds"]):
                        events.append(event)
                        if event.get("type") == "audio":
                            audio = {k:v for k,v in event.items() if k != "type"}
                    if cancel.is_set() or not audio or not any(e.get("type") == "done" for e in events):
                        raise RuntimeError("비교 합성이 취소되거나 완료되지 않았습니다.")
                    if self.fingerprint(self.valid_lesson(lesson_id)) != binding:
                        raise RuntimeError("비교 중 원본이 바뀌어 결과를 수업에 연결하지 않습니다.")
                    info = audio.get("session_info") or {}
                    if phase == "cold":
                        if info.get("load_count_this_request") != 1 or info.get("load_count_total") != 1:
                            raise RuntimeError("cold 합성의 실제 한 번 로딩을 확인하지 못했습니다.")
                    elif (info.get("worker_instance_id") != expected_instance or info.get("model_instance_id") != first_audio["session_info"].get("model_instance_id")
                            or info.get("model_object_id") != first_audio["session_info"].get("model_object_id")
                            or info.get("load_count_this_request") != 0 or info.get("load_count_total") != 1):
                        raise RuntimeError("warm이 같은 모델 인스턴스·로딩0인지 확인하지 못했습니다.")
                    success = True
                finally:
                    if phase == "warm" or not success:
                        release = session.close(self.root, session_key=key, reason="benchmark_complete" if success else "benchmark_failed")
                    record = {"phase": phase, "comparison_id": comparison_id, "job_id": job_id, "request_id": request_id,
                        "complete": success, "audio": audio, "events": events, "release": release,
                        "parent_timing": {"clock": "parent_monotonic", "queued_to_target_seconds": entered-queued_at,
                            "target_wall_seconds": time.monotonic()-entered, "scope": "API job target including budget reservation and worker processing; no browser playing"},
                        "output_dir": str(output), "cache_hit": False, "seed": SEED}
                    save(output / "request-result.json", record)
                return record

            job = self.jobs.submit("speech", execute, request_id=request_id)
            previous[phase] = {"job_id": job["id"], "request_id": request_id, "output_dir": str(output)}
            save(path, previous)
            return {"job_id": job["id"], "comparison_id": comparison_id, "phase": phase}
