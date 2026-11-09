from __future__ import annotations

import asyncio
import hmac
import hashlib
import json
import os
import secrets
import re
import threading
import time
import importlib.util
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, urlencode

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from edu_tutor.jobs.manager import JobManager, TERMINAL
from edu_tutor.jobs.inspection import active_gpu_lease, job_view
from edu_tutor.api.limits import RequestSizeLimit
from edu_tutor.lessons.plans import checked_demo_plan
from edu_tutor.paths import project_root
from edu_tutor.retrieval.index import DocumentIndex, MAX_BYTES
from edu_tutor.storage.db import Store, new_id, utcnow
from edu_tutor.vision.photos import PhotoStore
from edu_tutor.problems.models import ProblemInput, Hypothesis, normalize_problem
from edu_tutor.problems.pipeline import from_text, from_photo, hypothesis_from_question, model_messages
from edu_tutor.problems.evidence import display_answer
from edu_tutor.problems.app_correction import verify_with_app_correction as verify_answer

ORIGINS = {"http://127.0.0.1:8000", "http://localhost:8000", "http://127.0.0.1:5173", "http://localhost:5173"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionInput(StrictModel):
    title: str = Field(default="새 대화", min_length=1, max_length=150)


class StudentBudgetInput(StrictModel):
    request_id: str = Field(min_length=1, max_length=100)
    seconds: float = Field(ge=1, allow_inf_nan=False, strict=True)
    text_requests: int = Field(ge=0, strict=True)
    new_audio_clips: int = Field(ge=0, strict=True)
    vision_requests: int = Field(ge=0, strict=True)


class MessageInput(StrictModel):
    content: str = Field(min_length=1, max_length=12000)
    request_id: str | None = Field(default=None, max_length=100)
    generation_epoch: int | None = Field(default=None, ge=0)
    use_rag: bool = False
    adapter: str | None = Field(default=None, max_length=100)
    lesson_context: dict[str, Any] | None = None
    photo_id: str | None = Field(default=None, max_length=40)
    problem: ProblemInput | None = None
    hypothesis: Hypothesis | None = None
    verification_mode: Literal["tools", "model_only"] = "tools"


class ReviewInput(StrictModel):
    approved: bool


class PhotoInput(StrictModel):
    question: str | None = Field(default=None, max_length=12000)
    sql: str | None = Field(default=None, max_length=12000)
    tables: list[dict[str, Any]] | None = Field(default=None, max_length=20)
    choices: list[str] | None = Field(default=None, max_length=30)
    unreadable_regions: list[str] | None = Field(default=None, max_length=30)
    missing_conditions: list[str] | None = Field(default=None, max_length=30)


class PhotoSolveInput(StrictModel):
    session_id: str
    request_id: str | None = None
    generation_epoch: int | None = None


class LessonInput(StrictModel):
    session_id: str
    message_id: str
    photo_id: str | None = None


class LessonReprocessInput(StrictModel):
    request_id: str = Field(min_length=1, max_length=100)


class SQLInput(StrictModel):
    sql: str = Field(min_length=1, max_length=50000)
    fixture: dict[str, Any]
    dialect: str = "sqlite"
    expected: dict[str, Any] | None = None


class SpeechInput(StrictModel):
    voice: str = "default"
    step_id: str | None = None
    request_id: str | None = Field(default=None, max_length=100)


class SpeechBenchmarkInput(StrictModel):
    comparison_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    phase: Literal["cold", "warm"]
    lesson_id: str = Field(min_length=1, max_length=64)
    step_id: str = Field(min_length=1, max_length=64)
    request_id: str = Field(min_length=1, max_length=100)


class SpeechSessionCloseInput(StrictModel):
    binding_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


def ensure_token(local: Path):
    path = local / "auth-token"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        token = path.read_text(encoding="utf-8").strip()
        if len(token) < 32:
            raise RuntimeError("Existing local auth-token is invalid; preserve it and regenerate manually.")
        return token
    token = secrets.token_urlsafe(32)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(token)
    return token


def recorded_validation(root: Path):
    """Display recorded stage evidence without guessing a global tier verdict."""
    path = Path(root) / "STATUS.json"
    try:
        if path.stat().st_size > 1024 * 1024:
            raise ValueError("status file exceeds 1MiB")
        status = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(status, dict) or not isinstance(status.get("stages", {}), dict) or not isinstance(status.get("evidence", []), list):
            raise ValueError("invalid status structure")
        return {"source": "STATUS.json", "overall_status": status.get("overall_status", "not_recorded"),
                "stages": status.get("stages", {}), "evidence": status.get("evidence", []),
                "human_review": status.get("human_review", "not_reviewed")}
    except FileNotFoundError:
        return {"status": "not_recorded", "source": "STATUS.json", "reason": "검증 상태 파일이 없습니다.", "human_review": "not_reviewed"}
    except (OSError, ValueError, TypeError):
        return {"status": "not_recorded", "source": "STATUS.json", "reason": "검증 상태 파일을 올바르게 읽을 수 없습니다.", "human_review": "not_reviewed"}


def create_app(root: Path | None = None) -> FastAPI:
    root = project_root(root)
    # Windows registry associations can mislabel module scripts as text/plain.
    for suffix, content_type in {".js": "application/javascript", ".mjs": "application/javascript", ".css": "text/css",
                                 ".svg": "image/svg+xml", ".wasm": "application/wasm"}.items():
        mimetypes.add_type(content_type, suffix)
    store = Store(root)
    token = ensure_token(store.local)
    index, photos = DocumentIndex(store), PhotoStore(store)
    jobs = JobManager(store)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        if hasattr(_app.state, "neural"):
            _app.state.neural.close()
        jobs.close()

    app = FastAPI(title="Edu Tutor Local", version="0.2.1", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
    app.state.store, app.state.jobs = store, jobs
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])
    app.add_middleware(RequestSizeLimit)
    app.add_middleware(CORSMiddleware, allow_origins=sorted(ORIGINS), allow_credentials=False,
                       allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
                       allow_headers=["Authorization", "Content-Type", "X-Execution-Allowance", "X-Student-Session"])

    @app.middleware("http")
    async def guard(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and origin not in ORIGINS:
            return JSONResponse({"detail": "허용되지 않은 Origin입니다."}, status_code=403)
        if request.method == "OPTIONS" and origin in ORIGINS:
            return await call_next(request)
        if request.url.path.startswith("/api/") and not (request.url.path == "/api/health" and request.method == "GET"):
            authorization = request.headers.get("authorization", "")
            supplied = authorization[7:] if authorization.startswith("Bearer ") else ""
            if not hmac.compare_digest(supplied, token):
                return JSONResponse({"detail": "로컬 인증 토큰이 필요합니다."}, status_code=401)
        length = request.headers.get("content-length")
        if length:
            try:
                if int(length) > 11 * 1024 * 1024:
                    return JSONResponse({"detail": "요청 크기가 제한을 초과했습니다."}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Invalid content length"}, status_code=400)
        from edu_tutor.models.execution_context import execution_allowance, requested_student_session, student_session
        scope = request.headers.get("x-execution-allowance")
        requested_student = request.headers.get("x-student-session")
        if requested_student is not None and not re.fullmatch(r"[a-f0-9]{32}", requested_student):
            return JSONResponse({"detail": "올바른 학생 세션 식별자가 필요합니다."}, status_code=409)
        if scope:
            from edu_tutor.models.budget import policy
            if scope != (policy(root).get("active_execution_allowance") or {}).get("id"):
                return JSONResponse({"detail": "현재 승인과 다른 실행 범위입니다. 예산을 확인하세요."}, status_code=409)
        scope_token = execution_allowance.set(scope)
        student_request_token = requested_student_session.set(requested_student)
        student_token = student_session.set(None)
        try:
            response = await call_next(request)
        finally:
            execution_allowance.reset(scope_token)
            requested_student_session.reset(student_request_token)
            student_session.reset(student_token)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; font-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self' http://127.0.0.1:8000 http://localhost:8000; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def value_error(_request, exc):
        return JSONResponse({"detail": str(exc)[:800]}, status_code=422)

    @app.exception_handler(KeyError)
    async def missing(_request, _exc):
        return JSONResponse({"detail": "항목을 찾을 수 없습니다."}, status_code=404)

    def get(table, ident):
        item = store.get(table, ident)
        if item is None:
            raise HTTPException(404, "항목을 찾을 수 없습니다.")
        return item

    def bind_student_budget(session_id, *, kind=None):
        """Derive ownership from the saved chat/lesson/photo, never client headers."""
        get("sessions", session_id)
        from edu_tutor.models.budget import student_scope, student_budget, ResourceBudgetExceeded
        from edu_tutor.models.execution_context import execution_allowance, student_session, requested_student_session
        if student_session.get() not in (None, session_id):
            raise HTTPException(409, "다른 학생 세션의 작업을 이 예산에 연결할 수 없습니다.")
        # Historical/fixture IDs outside today's UUID format cannot have a new
        # student budget; keep their existing explicit development path.
        if not re.fullmatch(r"[a-f0-9]{32}", session_id):
            if requested_student_session.get():
                raise HTTPException(409, "선택한 학생 세션과 실제 작업의 대화가 다릅니다.")
            return None
        try:
            view = student_budget(root, session_id)
            if view["exists"] and requested_student_session.get() != session_id:
                raise HTTPException(409, "이 대화는 해당 학생 세션 예산을 명시해서 실행해야 합니다.")
            if requested_student_session.get() and (not view["exists"] or requested_student_session.get() != session_id):
                raise HTTPException(409, "선택한 학생 세션과 실제 작업의 대화가 다릅니다.")
            scope = student_scope(root, session_id, kind=kind)
        except ResourceBudgetExceeded as exc:
            raise HTTPException(409, str(exc)) from exc
        if scope:
            if execution_allowance.get() not in (None, scope):
                raise HTTPException(409, "학생 세션의 상위 승인 범위가 다릅니다.")
            execution_allowance.set(scope)
            student_session.set(session_id)
        return scope

    def check_student_photo(photo, session_id):
        from edu_tutor.models.execution_context import student_session
        owner = photo.get("session_id")
        if (owner and owner != session_id) or (student_session.get() and owner != session_id):
            raise HTTPException(409, "사진은 해당 학생 대화에서 업로드한 원본을 사용하세요.")

    def model_status():
        try:
            from edu_tutor.models.runtime import model_status as status
            return status(root=root)
        except ImportError:
            return {"installed": False, "ready": False, "model_id": None, "revision": None,
                    "path": None, "reason": "텍스트 런타임 미설치", "modules": []}

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "0.2.1", "local_only": True, "authentication_required": True}

    @app.get("/api/capabilities")
    def capabilities():
        model = model_status()
        try:
            from edu_tutor.speech.provider import status as speech_status
            speech = speech_status(root)
        except ImportError:
            speech = {"ready": False, "reason": "로컬 TTS 미설치"}
        vision_ready = (root / ".local/models/vision/model-manifest.json").is_file() and model.get("ready", False)
        from edu_tutor.models import budget as budget_module
        training_runtime_ready = bool(model.get("ready") and importlib.util.find_spec("peft"))
        training_policy_blocked = not getattr(budget_module, "training_allowed", lambda _root: not budget_module.policy(_root).get("enabled"))(root)
        return {"text": {"available": model.get("ready", False), "reason": model.get("reason")},
                "vision": {"available": vision_ready, "reason": "인식 후 반드시 원문을 확인하세요." if vision_ready else "자동 사진 인식 미준비; 수동 원문 편집 가능"},
                "speech": {"available": speech["ready"], "engine": speech.get("provider"), "voice": speech.get("voice_name", speech.get("voice")), "reason": speech.get("reason"), "listening_review": "not_run"},
                "training": {"available": training_runtime_ready and not training_policy_blocked,
                             "runtime_ready": training_runtime_ready, "policy_blocked": training_policy_blocked,
                             "reason": "현재 승인에 사용할 수 있는 학습 예산이 없습니다." if training_policy_blocked else "승인된 교육 실험의 데이터·시간·단계 한도를 확인하고 실행하세요."},
                "retrieval": {"available": True, "engine": "char-2-4-tfidf"},
                "sql": {"available": True, "dialect": "sqlite"},
                "gpu_lease": active_gpu_lease(store.local),
                "validation": recorded_validation(root)}

    @app.get("/api/models")
    @app.get("/api/models/current")
    def models():
        return model_status()

    @app.get("/api/doctor")
    def doctor():
        from edu_tutor.doctor import recorded_doctor
        return recorded_doctor(root=root)

    @app.post("/api/doctor/refresh",status_code=202)
    def refresh_doctor():
        from edu_tutor.doctor import collect_doctor
        from edu_tutor.models.budget import reserve,finish
        from edu_tutor.jobs.lease import GPULease
        with jobs.lock:
            if any(j["state"] not in TERMINAL for j in store.list("jobs")):
                raise HTTPException(409,"진행 중인 모델 작업이 끝난 뒤 환경 검사를 직접 다시 요청하세요.")
            def inspect(job_id,cancel):
                reservation,limit=reserve(root,{"kind":"diagnostic","job_id":job_id},60)
                success=False
                try:
                    if limit<60:
                        from edu_tutor.models.budget import ResourceBudgetExceeded
                        raise ResourceBudgetExceeded("환경 검사를 위한 남은 60초 예산이 부족합니다.")
                    with GPULease(store.local,job_id):
                        report=collect_doctor(root=root)
                    if cancel.is_set():return {"discarded":True}
                    target=root/"runs/environment/api-doctor.json"
                    target.parent.mkdir(parents=True,exist_ok=True)
                    temporary=target.with_suffix(".tmp")
                    temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
                    temporary.replace(target);success=True
                    return {"recorded_at":report["timestamp"],"report_path":str(target.relative_to(root))}
                finally:finish(reservation,success)
            return {"job_id":jobs.submit("diagnostic",inspect)["id"]}

    @app.get("/api/sessions")
    def list_sessions():
        return store.list("sessions")

    @app.post("/api/sessions", status_code=201)
    def create_session(body: SessionInput):
        return store.put("sessions", {"id": new_id(), "title": body.title, "generation_epoch": 0,
                                      "created_at": utcnow()})

    @app.get("/api/sessions/{ident}/budget")
    def read_student_budget(ident: str):
        get("sessions", ident)
        from edu_tutor.models.budget import student_budget, ResourceBudgetExceeded
        try:
            return student_budget(root, ident)
        except ResourceBudgetExceeded as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/sessions/{ident}/budget", status_code=201)
    def start_student_budget(ident: str, body: StudentBudgetInput):
        from edu_tutor.models.budget import student_budget, ResourceBudgetExceeded
        from edu_tutor.models.execution_context import requested_student_session
        if requested_student_session.get() not in (None, ident):
            raise HTTPException(409, "선택한 학생 세션과 예산 시작 대상이 다릅니다.")
        with jobs.lock:
            get("sessions", ident)
            if any(job.get("session_id") == ident and job["state"] not in TERMINAL for job in store.list("jobs")):
                raise HTTPException(409, "현재 대화의 작업을 마친 뒤 세션 예산을 시작하세요.")
            try:
                return student_budget(root, ident, limits=body.model_dump(exclude={"request_id"}), request_id=body.request_id)
            except ResourceBudgetExceeded as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.post("/api/sessions/{ident}/budget/close")
    def close_student_budget(ident: str):
        from edu_tutor.models.budget import student_budget, ResourceBudgetExceeded
        from edu_tutor.models.execution_context import requested_student_session
        if requested_student_session.get() not in (None, ident):
            raise HTTPException(409, "선택한 학생 세션과 예산 종료 대상이 다릅니다.")
        with jobs.lock:
            get("sessions", ident)
            if any(job.get("session_id") == ident and job["state"] not in TERMINAL for job in store.list("jobs")):
                raise HTTPException(409, "진행 중인 수업을 취소하거나 마친 뒤 예산을 종료하세요.")
            try:
                return student_budget(root, ident, close=True)
            except ResourceBudgetExceeded as exc:
                raise HTTPException(409, str(exc)) from exc

    def message_validity(message):
        problem=message.get("problem") or message.get("original_problem") or {}
        source=problem.get("source",{})
        if message.get("role")!="assistant" or source.get("kind")!="photo":
            return message
        photo=store.get("photos",source.get("photo_id",""))
        revision=photo.get("revision") if photo else None
        reason=None
        if not photo:
            reason="사진 원문이 삭제되어 이전 답변으로 새 강의를 만들 수 없습니다. 기록은 보존됩니다."
        elif revision!=problem.get("revision"):
            reason="사진 원문이 수정되어 이전 답변이 무효화되었습니다. 최신 원문을 확정하고 다시 풀이하세요."
        elif not photo.get("confirmed"):
            reason="사진 원문이 확정되지 않아 이전 답변을 사용할 수 없습니다. 원문을 확인하고 다시 풀이하세요."
        return {**message,"valid":reason is None,"current_problem_revision":revision,
                **({"invalidated_reason":reason} if reason else {})}

    @app.get("/api/sessions/{ident}/messages")
    def list_messages(ident: str):
        with jobs.lock:
            get("sessions", ident)
            return [message_validity(m) for m in store.list("messages") if m["session_id"] == ident]

    @app.get("/api/sessions/{ident}/export")
    def export_session(ident: str):
        return {"session": get("sessions", ident), "messages": list_messages(ident), "exported_at": utcnow()}

    @app.delete("/api/sessions/{ident}")
    def delete_session(ident: str):
        with jobs.lock:
            get("sessions", ident)
            for job in store.list("jobs"):
                if job.get("session_id") == ident and job["state"] not in TERMINAL:
                    jobs.cancel(job["id"])
            store.delete("sessions", ident)
            store.record("session_delete", ident)
        return {"deleted": True}

    def send_message(ident, body):
        if not body.content.strip():
            raise ValueError("질문을 입력하세요.")
        bind_student_budget(ident, kind="text")
        if body.photo_id:
            check_student_photo(photos.confirmed(body.photo_id), ident)
        if body.lesson_context and len(json.dumps(body.lesson_context)) > 20000:
            raise ValueError("강의 문맥 크기 제한을 초과했습니다.")
        started = time.monotonic()
        # Reserved server provenance must never survive a client submission,
        # including when a caller also supplies a replacement structured problem.
        context = {key:value for key,value in body.lesson_context.items() if not key.startswith("_verified_")} if body.lesson_context else None
        if body.photo_id:
            problem = from_photo(photos.confirmed(body.photo_id))
        elif body.problem:
            if body.problem.source.kind=="photo":
                raise ValueError("사진 원문은 photo_id 또는 사진 풀이 API로 지정하세요. 저장된 확정 원문만 사용합니다.")
            problem = normalize_problem(body.problem.model_dump(exclude_none=True))
        elif context and context.get("lesson_id"):
            prior_lesson = valid_lesson(context["lesson_id"])
            prior_message = get("messages", prior_lesson["source_message_id"])
            if prior_message["session_id"] != ident:
                raise ValueError("현재 대화에 연결된 강의 문맥을 사용하세요.")
            problem = prior_message.get("problem") or from_text(body.content)
            if context.get("problem_revision") and context["problem_revision"] != problem["revision"]:
                raise HTTPException(409, "원문이 수정되었습니다. 최신 강의로 다시 질문하세요.")
            from edu_tutor.lessons.verified import validated_logical_stage
            scope=validated_logical_stage(prior_lesson,prior_message,context)
            if scope:context["_verified_logical_stage"]=scope
        else:
            problem = from_text(body.content)
        hypothesis = body.hypothesis.model_dump() if body.hypothesis else hypothesis_from_question(problem, body.content, (context or {}).get("selected_cell")) if context else None
        request_id = body.request_id or new_id()
        with jobs.lock:
            session = get("sessions", ident)
            for previous in store.list("jobs"):
                if previous.get("session_id") == ident and previous.get("request_id") == request_id:
                    return {"job_id": previous["id"], "request_id": request_id,
                            "generation_epoch": previous["generation_epoch"]}
            if any(job.get("kind") == "training" and job["state"] not in TERMINAL for job in store.list("jobs")):
                raise HTTPException(409, "학습 중에는 새 답변을 생성할 수 없습니다. 학습을 완료하거나 중단한 뒤 다시 질문하세요.")
            if any(job["state"] not in TERMINAL and job.get("session_id") != ident for job in store.list("jobs")):
                raise HTTPException(409, "다른 모델 작업이 진행 중입니다. 입력은 보존하고 완료 후 직접 다시 전송하세요.")
            wait_for = []
            for previous in store.list("jobs"):
                if previous.get("session_id") == ident and previous["state"] not in TERMINAL:
                    wait_for.append(previous["id"])
                    jobs.cancel(previous["id"])
            epoch = max(session["generation_epoch"] + 1, body.generation_epoch or 0)
            session["generation_epoch"] = epoch
            store.put("sessions", session)
            user_message = {"id": new_id(), "session_id": ident, "role": "user", "content": body.content,
                            "request_id": request_id, "generation_epoch": epoch, "sources": [], "created_at": utcnow(),
                            "problem": problem, "hypothesis":hypothesis, "lesson_context":context}
            store.put("messages", user_message)
            sources = index.search(body.content, limit=2) if body.use_rag else []
            messages = model_messages(body.content, problem, sources, context, hypothesis)

            def generate(job_id, cancel):
                from edu_tutor.models.runtime import generate as runtime_generate
                try:
                    from edu_tutor.models.runtime import GenerationIncomplete
                except ImportError:
                    # Minimal injected CPU runtime doubles need not define the
                    # real worker's optional incomplete-output exception.
                    class GenerationIncomplete(RuntimeError):
                        pass
                jobs.update(job_id, state="running")
                for old_id in wait_for:
                    deadline=time.monotonic()+10
                    while get("jobs",old_id)["state"] not in TERMINAL and time.monotonic()<deadline and not cancel.is_set():
                        time.sleep(.05)
                    if get("jobs",old_id)["state"] not in TERMINAL:
                        raise RuntimeError("이전 작업의 취소 완료를 기다린 뒤 다시 전송하세요.")
                generation_snapshot = {}
                generation_started = time.monotonic()
                output = runtime_generate(messages, cancel_event=cancel, adapter=body.adapter, root=root, job_id=job_id,
                                          metadata_out=generation_snapshot)
                output = [output] if isinstance(output, str) else output
                text = ""
                incomplete = None
                try:
                    for chunk in output:
                        if cancel.is_set():
                            break
                        text += chunk
                        if len(text) > 60000:
                            raise ValueError("모델 출력 크기 제한을 초과했습니다.")
                        jobs.update_partial(job_id, epoch, partial_text=text if problem["task_kind"]=="concept" else "원본 조건과 모델 초안을 확인하고 있습니다.", raw_partial_text=text)
                except GenerationIncomplete as exc:
                    incomplete = str(exc)
                    if not body.problem and not context and not body.photo_id:
                        raise
                raw_response=text
                generation_finished = time.monotonic()
                attempts=[{"attempt":0,"text":text,"generation_snapshot":generation_snapshot,"incomplete":incomplete}]
                evidence=None
                if body.verification_mode=="tools":
                    evidence=verify_answer(problem,text,body.content,hypothesis)
                    repair_allowed = True
                    if evidence.get("can_repair"):
                        from edu_tutor.models.budget import status as budget_status
                        grant = budget_status(root).get("active_execution_allowance")
                        repair_allowed = grant is None or (grant["text_remaining"] > 0 and grant["seconds_remaining"] >= 1)
                        from edu_tutor.models.execution_context import student_session
                        student_repair_exhausted = False
                        if student_session.get():
                            from edu_tutor.models.budget import student_budget
                            remaining = student_budget(root, student_session.get())["effective_remaining"]
                            student_repair_exhausted = remaining["text_requests"] < 1 or remaining["seconds"] < 1
                            repair_allowed = repair_allowed and not student_repair_exhausted
                        if not repair_allowed:
                            evidence.update(can_repair=False, repair_skipped="student_session_budget_exhausted" if student_repair_exhausted else "explicit_execution_allowance_exhausted")
                            evidence["reasons"] = [*evidence.get("reasons", []), "추가 텍스트 호출 승인량이 없어 자동 수정을 실행하지 않았습니다."]
                    if evidence.get("can_repair") and repair_allowed and not incomplete and not cancel.is_set():
                        repair_snapshot={}
                        repair_messages=[*messages,{"role":"assistant","content":text},
                            {"role":"user","content":"원본 표와 조건을 바꾸지 말고 SQL 후보를 한 번만 수정하세요. 실제 검증 오류: "+" ".join(evidence["reasons"])+". JSON sql/explanation만 출력하세요."}]
                        repaired=""
                        try:
                            for chunk in runtime_generate(repair_messages,cancel_event=cancel,adapter=body.adapter,root=root,job_id=job_id,metadata_out=repair_snapshot):
                                repaired+=chunk
                        except GenerationIncomplete as exc:
                            incomplete=str(exc)
                        attempts.append({"attempt":1,"text":repaired,"generation_snapshot":repair_snapshot,"incomplete":incomplete})
                        if not incomplete:
                            evidence=verify_answer(problem,repaired,body.content,hypothesis)
                    if incomplete and problem["task_kind"]=="write_sql":
                        evidence.update(status="stopped",reasons=["모델 SQL 후보가 토큰/시간 제한으로 완성되지 않았습니다."],can_repair=False)
                    if evidence["status"]!="concept_unverified":text=display_answer(evidence)
                if body.verification_mode=="model_only" and incomplete:
                    text="모델 출력 미완료: "+raw_response
                with jobs.lock:
                    current = store.get("sessions", ident)
                    if jobs.closed or cancel.is_set() or current is None or current["generation_epoch"] != epoch:
                        cancel.set()
                        return {"discarded": True, "generation_epoch": epoch}
                    photo_id=problem["source"].get("photo_id")
                    current_photo=store.get("photos",photo_id) if photo_id else None
                    if photo_id and (not current_photo or current_photo["revision"]!=problem["revision"]):
                        return {"discarded":True,"reason":"사진 원문이 수정되어 이전 계산을 저장하지 않았습니다."}
                    if not text.strip():
                        raise ValueError("모델이 빈 답변을 반환했습니다.")
                    jobs.update(job_id, state="saving")
                    message = {"id": new_id(), "session_id": ident, "role": "assistant", "content": text,
                               "request_id": request_id, "generation_epoch": epoch, "sources": sources,
                               "source_note": "검색 자료 최대 2건의 앞 300자씩을 개념 참고로 사용했습니다. 답변 정확성 검증을 뜻하지 않습니다." if sources else "참고 자료 없음",
                               "created_at": utcnow(), "provenance": "tool_derived" if evidence and evidence["status"]=="verified" else "model_generated",
                               "generation_snapshot": generation_snapshot or None,
                               "raw_model_response":raw_response,"model_attempts":attempts,"problem":problem,"original_problem":problem,
                               "hypothesis":hypothesis,"lesson_context":context,"evidence":evidence,
                               "verification_mode":body.verification_mode,
                                "latency":{"request_to_verified_core_seconds":time.monotonic()-started,"model_load_seconds":generation_snapshot.get("model_load_seconds"),"model_elapsed_seconds":generation_snapshot.get("elapsed_seconds"),
                                    "request_to_generation_start_seconds":generation_started-started,
                                    "generation_call_wall_seconds":generation_finished-generation_started,
                                    "verification_and_optional_repair_seconds":time.monotonic()-generation_finished,
                                    "clock":"api_monotonic", "not_gpu_kernel_time":True},
                               "verification": {"status": evidence["status"] if evidence else "model_only_unverified", "sql_execution": evidence["execution"]["status"] if evidence else "not_run", "human_review": "not_reviewed"}}
                    store.put("messages", message)
                    result = {"message_id": message["id"], "generation_epoch": epoch,
                              "generation_snapshot": generation_snapshot or None}
                    # Persisted answer and terminal state share the cancellation lock.
                    from edu_tutor.storage.timing import storage_timing_snapshot
                    jobs.update(job_id, state="succeeded", result=result, progress=1,
                                storage_timing=storage_timing_snapshot())
                    return result

            job = jobs.submit("chat", generate, request_id=request_id, session_id=ident, generation_epoch=epoch)
            return {"job_id": job["id"], "request_id": request_id, "generation_epoch": epoch}

    @app.post("/api/sessions/{ident}/messages", status_code=202)
    def post_message(ident: str, body: MessageInput):
        return send_message(ident, body)

    @app.get("/api/jobs")
    def list_jobs():
        return [job_view(root, job) for job in store.list("jobs")]

    @app.get("/api/resources/budget")
    def resource_budget():
        from edu_tutor.models.budget import status
        return status(root)

    @app.get("/api/jobs/{ident}")
    def get_job(ident: str):
        job = jobs.view(ident)
        if job is None:
            raise HTTPException(404, "jobs not found")
        return job_view(root, job)

    @app.post("/api/jobs/{ident}/cancel")
    def cancel_job(ident: str):
        with jobs.lock:
            job = jobs.cancel(ident)
            if job.get("session_id") and job["state"] not in TERMINAL:
                session = store.get("sessions", job["session_id"])
                if session and session["generation_epoch"] == job["generation_epoch"]:
                    session["generation_epoch"] += 1
                    store.put("sessions", session)
        # A completed clip may still own an idle reusable TTS worker. Bind
        # cleanup to the exact latest job, so a late cancel cannot stop the
        # next request even when it belongs to the same lesson fingerprint.
        if job.get("kind") == "speech" and job.get("speech_session_key"):
            from edu_tutor.speech.session import close
            close(root, session_key=job["speech_session_key"], job_id=ident,
                  reason="speech_job_cancelled")
        return job

    @app.get("/api/jobs/{ident}/events")
    async def events(ident: str, request: Request):
        get("jobs", ident)
        async def stream():
            previous = ""
            while not await request.is_disconnected():
                job = job_view(root, jobs.view(ident))
                payload = json.dumps(job, ensure_ascii=False)
                if payload != previous:
                    yield "event: job\ndata: " + payload + "\n\n"
                    previous = payload
                if job["state"] in TERMINAL:
                    break
                await asyncio.sleep(0.2)
        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/documents")
    def list_documents():
        return store.list("documents")

    @app.post("/api/documents", status_code=201)
    async def upload_document(file: UploadFile = File(...), title: str = Form(""), rights: str = Form(...), subject: str = Form("기초 데이터베이스")):
        raw = await file.read(MAX_BYTES + 1)
        return await asyncio.to_thread(index.ingest, file.filename or "upload", raw, title[:200], rights[:2000], subject[:100])

    @app.get("/api/documents/{ident}")
    def read_document(ident: str):
        return get("documents", ident)

    @app.get("/api/documents/{ident}/chunks")
    def preview_document_chunks(ident: str):
        get("documents", ident)
        return [c for c in store.list("chunks") if c["document_id"] == ident]

    @app.post("/api/documents/{ident}/review")
    def review_document(ident: str, body: ReviewInput):
        return index.review(ident, body.approved)

    @app.delete("/api/documents/{ident}")
    def delete_document(ident: str):
        index.delete(ident)
        return {"deleted": True}

    @app.get("/api/search")
    def search(q: str = Query(min_length=1, max_length=4000), limit: int = Query(default=5, ge=1, le=10)):
        return index.search(q, limit)

    @app.post("/api/evaluations/sql")
    def sql_evaluation(body: SQLInput):
        from edu_tutor.evaluation.sql_sandbox import compare_results, execute_sql
        result = execute_sql(body.sql, body.fixture, dialect=body.dialect)
        if body.expected:
            result["match"] = compare_results(result, body.expected)
        return {**result, "tier": "T0", "human_review": "not_reviewed",
                "notice": "소규모 데모 평가입니다. 파이프라인 검증용이며, 전체 교육 성능이나 일반화 성능을 보장하지 않습니다."}

    @app.get("/api/lessons/demo")
    def lesson_demo():
        existing = store.get("lessons", "demo-count-null")
        plan, verification = checked_demo_plan(existing["plan"] if existing else None)
        with jobs.lock:
            # Preserve audio that another job may have prepared during the CPU check.
            value = store.get("lessons", "demo-count-null") or {"id": "demo-count-null", "is_demo": True, "status": "demo_fixture"}
            value.update(plan=plan, fixture_validation=verification)
            store.put("lessons", value)
            return value

    @app.post("/api/lessons", status_code=201)
    def create_lesson(body: LessonInput):
        with jobs.lock:
            get("sessions", body.session_id)
            message = get("messages", body.message_id)
            if message["session_id"] != body.session_id or message["role"] != "assistant":
                raise ValueError("선택한 대화의 실제 모델 답변을 선택하세요.")
            projected=message_validity(message)
            if projected.get("valid") is False:
                raise HTTPException(409,projected["invalidated_reason"])
            if body.photo_id:
                photos.confirmed(body.photo_id)
            # Genuine answer is retained verbatim. No fixture is substituted for it.
            source_problem=message.get("problem")
            return store.put("lessons", {"id": new_id(), "plan": None, "fallback_text": message["content"],
                "status": "text_fallback", "is_demo": False, "source_message_id": message["id"],
                "problem":source_problem,"original_problem":source_problem,"evidence":message.get("evidence"),"generation_epoch":0,"valid":True,
                "speech_allowed":False,
                "created_at": utcnow(), "reason": "구조화 강의 생성 미실행: 실제 답변을 설명 카드로 표시합니다."})

    def lesson_validity(lesson):
        if not lesson.get("is_demo") and not lesson.get("problem"):
            return {**lesson,"valid":False,"invalidated_reason":"이전 버전의 검증 전 강의입니다. 기록은 보존하며 원본 문제를 확인해 새로 풀이해야 합니다.","audio_steps":[]}
        source=(lesson.get("problem") or {}).get("source",{})
        photo_id=source.get("photo_id")
        if photo_id:
            photo=store.get("photos",photo_id)
            revision=photo.get("revision") if photo else None
            if not photo or revision!=lesson["problem"]["revision"] or not photo.get("confirmed"):
                return {**lesson,"valid":False,"current_problem_revision":revision,
                    "invalidated_reason":"사진 원문이 변경되었거나 확정되지 않아 이전 계산·음성·판서를 사용할 수 없습니다.","audio_steps":[]}
        return {**lesson,"valid":lesson.get("valid",True)}

    def speech_is_allowed(lesson):
        if lesson.get("is_demo"):
            _,report=checked_demo_plan(lesson.get("plan"))
            return report["machine_verification"]=="pass"
        return bool(lesson.get("speech_allowed"))

    def valid_lesson(ident):
        lesson=lesson_validity(get("lessons",ident))
        if not lesson["valid"]:
            raise HTTPException(409,lesson["invalidated_reason"])
        return lesson

    def speech_binding_fingerprint(lesson):
        binding_data = {key: lesson.get(key) for key in (
            "id", "plan", "problem", "generation_epoch", "source_message_id", "speech_allowed", "fallback_text")}
        return hashlib.sha256(json.dumps(binding_data, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")).encode()).hexdigest()

    @app.get("/api/lessons/{ident}")
    def read_lesson(ident: str):
        lesson = lesson_demo() if ident == "demo-count-null" else lesson_validity(get("lessons", ident))
        source = store.get("messages", lesson.get("source_message_id", "")) or {}
        context = source.get("lesson_context") or {}
        return {**lesson, "speech_binding_fingerprint": speech_binding_fingerprint(lesson),
                "source_session_id": source.get("session_id"),
                "source_lesson_context": {key: context[key] for key in ("lesson_id", "problem_revision")
                                          if key in context} or None}

    @app.post("/api/lessons/{ident}/reprocess", status_code=201)
    def reprocess_lesson(ident: str, body: LessonReprocessInput):
        """Recheck saved input on CPU; append records, without model/planner calls."""
        from edu_tutor.lessons.reprocessing import digest, reprocess_saved_lesson
        started = time.perf_counter()
        def source_records():
            source = valid_lesson(ident)
            if source.get("is_demo"):
                raise ValueError("데모가 아닌 저장된 모델 답변이 필요합니다.")
            message = get("messages", source["source_message_id"])
            projected = message_validity(message)
            if projected.get("valid") is False:
                raise HTTPException(409, projected["invalidated_reason"])
            get("sessions", message["session_id"])
            question_record = next((m for m in store.list("messages")
                                   if m["role"] == "user" and m["session_id"] == message["session_id"]
                                   and m.get("request_id") == message.get("request_id")), None)
            if not question_record:
                raise ValueError("저장된 원래 질문을 찾을 수 없습니다.")
            return source, message, question_record

        def existing_result():
            for candidate in store.list("lessons"):
                previous = candidate.get("reprocessing") or {}
                if previous.get("source_lesson_id") == ident and previous.get("request_id") == body.request_id:
                    return read_lesson(candidate["id"])

        with jobs.lock:
            source, message, question_record = source_records()
            existing = existing_result()
            if existing:
                return existing
        source_digest = digest([source, message, question_record])
        # SQL validation may take time. Keep cancellation/job updates responsive.
        derived, lesson = reprocess_saved_lesson(source, message, question_record["content"], body.request_id)
        with jobs.lock:
            if jobs.closed or digest(list(source_records())) != source_digest:
                raise HTTPException(409, "재검증 중 원본 또는 서버 상태가 변경되어 새 수업을 저장하지 않았습니다.")
            existing = existing_result()
            if existing:
                return existing
            metadata = lesson["reprocessing"]
            metadata["verification_and_plan_seconds"] = time.perf_counter() - started
            audit = {"id": new_id(), "action": "saved_lesson_reprocess", "entity_id": lesson["id"],
                     "created_at": utcnow(), **metadata}
            # The derived answer and its lesson are one append-only transaction.
            with store.connect() as db:
                db.execute("INSERT INTO messages(id,session_id,payload) VALUES(?,?,?)",
                           (derived["id"], derived["session_id"], json.dumps(derived, ensure_ascii=False, allow_nan=False)))
                db.execute("INSERT INTO lessons(id,payload) VALUES(?,?)",
                           (lesson["id"], json.dumps(lesson, ensure_ascii=False, allow_nan=False)))
                db.execute("INSERT INTO audit(id,payload) VALUES(?,?)",
                           (audit["id"], json.dumps(audit, ensure_ascii=False, allow_nan=False)))
            return read_lesson(lesson["id"])

    @app.post("/api/lessons/{ident}/generate", status_code=202)
    def generate_lesson(ident: str):
        lesson = valid_lesson(ident)
        if lesson["is_demo"]:
            raise ValueError("데모 강의는 모델이 만든 답변에서 생성한 강의가 아닙니다.")
        message = get("messages", lesson["source_message_id"])
        student_scope_id = bind_student_budget(message["session_id"])
        preserved_lesson = json.loads(json.dumps(lesson)) if student_scope_id else None
        history = list_messages(message["session_id"])
        question = next((m["content"] for m in history if m["role"] == "user" and m["request_id"] == message["request_id"]), None)
        if not question:
            raise ValueError("원래 질문을 찾을 수 없습니다.")
        with jobs.lock:
            lesson_epoch=lesson.get("generation_epoch",0)+1
            lesson.update(generation_epoch=lesson_epoch,audio_steps=[],speech_allowed=False)
            store.put("lessons",lesson)
        def generate(job_id, cancel):
            from edu_tutor.lessons.generation import generate_plan
            from edu_tutor.lessons.verified import generate_verified_plan
            from edu_tutor.lessons.concepts import generate_concept_plan
            jobs.update(job_id, state="running")
            timer = threading.Timer(300, cancel.set)
            timer.daemon = True
            timer.start()
            try:
                if message.get("evidence"):
                    if message["evidence"]["status"]=="concept_unverified":
                        result=generate_concept_plan(message,question,ident,root=root,store=store,
                            lock=jobs.lock,job_id=job_id,cancel_event=cancel,generation_epoch=lesson_epoch)
                    else:
                        result=generate_verified_plan(message,question,ident)
                elif message.get("problem"):
                    result={"plan":None,"fallback_text":message["content"],"status":"verification_stopped","reason":"모델 단독 진단 출력은 검증된 강의가 아닙니다.","speech_allowed":False}
                else:
                    result = generate_plan(message["content"], question, lesson_id=ident, sources=message.get("sources", []),
                        root=root, job_id=job_id, cancel_event=cancel, progress=lambda value: jobs.update(job_id, progress=value))
            except Exception as exc:
                from edu_tutor.models.budget import ResourceBudgetExceeded
                if preserved_lesson and isinstance(exc, ResourceBudgetExceeded):
                    with jobs.lock:
                        current = get("lessons", ident)
                        if current.get("generation_epoch") == lesson_epoch:
                            # Keep the new epoch so older cancelled work cannot
                            # become current again; preserve the original board/audio.
                            store.put("lessons", {**preserved_lesson, "generation_epoch": lesson_epoch})
                raise
            finally:
                timer.cancel()
            with jobs.lock:
                if jobs.closed or cancel.is_set():
                    return {"discarded": True}
                current = valid_lesson(ident)
                if current.get("generation_epoch")!=lesson_epoch:
                    return {"discarded":True,"reason":"더 최신 강의 생성이 있습니다."}
                current.update(result, audio_steps=[])
                store.put("lessons", current)
            return {"lesson_id": ident, "status": result["status"], "structured": result["plan"] is not None}
        return {"job_id": jobs.submit("lesson", generate,session_id=message["session_id"])["id"]}

    def speech_cache_view(ident, step_id=None, voice="default", include_audio_bytes=False):
        started = time.perf_counter()
        lesson = valid_lesson(ident)
        from edu_tutor.speech.provider import cached_audio, status as speech_status
        allowed = speech_is_allowed(lesson)
        steps = lesson["plan"]["steps"] if lesson.get("plan") else [{"id": "answer", "speech": lesson.get("fallback_text", "")}]
        if step_id is not None:
            steps = [s for s in steps if s["id"] == step_id]
            if not steps:
                raise HTTPException(404, "강의 단계를 찾을 수 없습니다.")
        # Voice bytes may be shared, but each replay is bound to the current
        # problem, board, script and generation. Historical rows are not edited.
        binding = speech_binding_fingerprint(lesson)
        ready, misses = [], []
        for step in steps:
            selected_voice = voice
            if voice == "default":
                # Preserve attached historical voices even after a default-engine
                # change. A new step resolves the current configured provider.
                attached_audio = next((a for a in lesson.get("audio_steps", []) if a.get("step_id") == step["id"]), None)
                if attached_audio and attached_audio.get("voice"):
                    selected_voice = attached_audio["voice"]
                    if attached_audio.get("provider") == "windows_sapi_local":
                        selected_voice = "windows_sapi:" + selected_voice
                else:
                    from edu_tutor.speech.windows_sapi import resolve_voice
                    selected_voice = resolve_voice(root, "default")
            result = cached_audio(step["speech"], root=root, voice=selected_voice) if allowed else {
                "hit": False, "code": "speech_not_allowed", "reason": "계산 근거가 확인된 강의 단위가 필요합니다."}
            if not result["hit"]:
                misses.append({"step_id": step["id"], "code": result["code"], "reason": result["reason"]})
                continue
            audio = result["audio"]
            attached = any(item.get("step_id") == step["id"] and item.get("audio_id") == audio["audio_id"]
                           for item in lesson.get("audio_steps", []))
            url = (f"/api/lessons/{quote(ident, safe='')}/speech/{quote(step['id'], safe='')}/audio?"
                   + urlencode({"voice": selected_voice, "binding": binding}))
            ready.append({**audio, "step_id": step["id"], "audio_url": url,
                          "binding_fingerprint": binding, "cache_source": "attached" if attached else "global"})
            if include_audio_bytes:
                ready[-1]["_wave_bytes"] = result["wave_bytes"]
        engine = speech_status(root)
        generation_available = allowed and engine["ready"]
        return {"available": bool(ready) or generation_available, "cached_available": bool(ready),
                "generation_available": generation_available,
                "generation_reason": engine.get("reason") if allowed else "계산 근거가 확인된 강의 단위가 필요합니다.",
                "reason": misses[0]["reason"] if misses else None,
                "steps": ready, "cache_misses": misses, "replay_only": True, "binding_fingerprint": binding,
                "timing": {"clock": "server_perf_counter", "scope": "cache_validation_only",
                           "cache_lookup_ms": (time.perf_counter() - started) * 1000}}

    @app.get("/api/lessons/{ident}/speech")
    def lesson_speech(ident: str, step_id: str | None = None, voice: str = "default"):
        return speech_cache_view(ident, step_id, voice)

    @app.get("/api/lessons/{ident}/speech/{step_id}/audio")
    def read_lesson_audio(ident: str, step_id: str, binding: str, voice: str = "default"):
        result = speech_cache_view(ident, step_id, voice, include_audio_bytes=True)
        if not hmac.compare_digest(binding, result["binding_fingerprint"]):
            raise HTTPException(409, "문제·판서·대사가 변경되어 이전에 준비한 음성을 사용할 수 없습니다.")
        if not result["steps"]:
            raise HTTPException(409, result["reason"])
        audio = result["steps"][0]
        return Response(audio["_wave_bytes"], media_type="audio/wav")

    @app.post("/api/lessons/{ident}/speech", status_code=202)
    def prepare_lesson_speech(ident: str, body: SpeechInput):
        lesson = valid_lesson(ident)
        source_message = store.get("messages", lesson.get("source_message_id", ""))
        if source_message:
            bind_student_budget(source_message["session_id"])
        else:
            from edu_tutor.models.execution_context import requested_student_session
            if requested_student_session.get():
                raise HTTPException(409, "학생 예산은 해당 대화에서 만든 실제 수업에만 사용할 수 있습니다.")
        original_binding = speech_binding_fingerprint(lesson)
        session_key = "lesson:" + ident + ":" + original_binding
        if not speech_is_allowed(lesson):
            raise HTTPException(409,"검증되지 않은 수치 답변은 음성으로 생성하지 않습니다. 원본 문제를 확인해 다시 풀이하세요.")
        steps = lesson["plan"]["steps"] if lesson.get("plan") else [{"id": "answer", "speech": lesson["fallback_text"]}]
        last_step_id = steps[-1]["id"] if steps else None
        if body.step_id:
            steps = [s for s in steps if s["id"] == body.step_id]
        if not steps:
            raise ValueError("음성을 만들 강의 단계를 찾을 수 없습니다.")
        if any(len(s["speech"]) > 1000 for s in steps):
            raise ValueError("단계당 음성 대본은 1,000자 이하여야 합니다.")
        def prepare(job_id, cancel):
            from edu_tutor.speech.provider import prepare_batch
            from edu_tutor.speech.session import policy as session_policy, close as close_session
            use_session = session_policy(root)["mode"] == "session"
            jobs.update(job_id, state="running", speech_session_key=session_key)
            timer = threading.Timer(300, cancel.set)
            timer.daemon = True
            timer.start()
            generated = []
            try:
                def on_audio(step_id,audio):
                    item = {**audio, "step_id": step_id, "audio_url": audio["url"]}
                    with jobs.lock:
                        if jobs.closed or cancel.is_set():
                            return
                        current = valid_lesson(ident)
                        if (current.get("generation_epoch",0)!=lesson.get("generation_epoch",0)
                                or speech_binding_fingerprint(current) != original_binding):
                            cancel.set()
                            return
                        current["audio_steps"] = [s for s in current.get("audio_steps", []) if s["step_id"] != step_id] + [item]
                        store.put("lessons", current)
                    generated.append(item)
                    jobs.update(job_id, progress=len(generated) / len(steps))
                if len(steps)==1:
                    from edu_tutor.speech.provider import prepare as runtime_prepare
                    audio=runtime_prepare(steps[0]["speech"],root=root,voice=body.voice,cancel_event=cancel,job_id=job_id,
                                          **({"session_key":session_key} if use_session else {}))
                    on_audio(steps[0]["id"],audio)
                else:
                    prepare_batch([{"id":s["id"],"text":s["speech"]} for s in steps],root=root,voice=body.voice,
                                  cancel_event=cancel,job_id=job_id,on_audio=on_audio,
                                  **({"session_key":session_key} if use_session else {}))
            finally:
                timer.cancel()
                # Last synthesis is complete before the lesson's last playback;
                # keep WAVs, release the resident model without waiting for idle.
                if use_session and (cancel.is_set() or not generated or any(s["id"] == last_step_id for s in steps)):
                    close_session(root, session_key=session_key, job_id=job_id, reason="lesson_complete_or_cancelled")
            return {"lesson_id": ident, "steps": generated, "complete": len(generated) == len(steps), "limit_seconds": 300}
        message=store.get("messages",lesson.get("source_message_id",""))
        return {"job_id": jobs.submit("speech", prepare, request_id=body.request_id,session_id=message["session_id"] if message else None)["id"]}

    @app.post("/api/lessons/{ident}/speech/session/close")
    def close_lesson_speech_session(ident: str, body: SpeechSessionCloseInput):
        from edu_tutor.speech.session import close
        get("lessons", ident)
        return close(root, session_key="lesson:"+ident+":"+body.binding_fingerprint, reason="explicit_lesson_close")

    @app.post("/api/tts/reuse-benchmark", status_code=202)
    def tts_reuse_benchmark(body: SpeechBenchmarkInput):
        from edu_tutor.speech.benchmark import ReuseBenchmark
        from edu_tutor.models.budget import ResourceBudgetExceeded
        try:
            return ReuseBenchmark(root, store, jobs, valid_lesson, speech_binding_fingerprint).start(**body.model_dump())
        except ResourceBudgetExceeded as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/tts/session")
    def tts_session_status():
        from edu_tutor.speech.session import status
        return status(root)

    @app.get("/api/audio/{ident}")
    def read_audio(ident: str):
        if not re.fullmatch(r"[a-f0-9]{64}", ident):
            raise HTTPException(404, "음성을 찾을 수 없습니다.")
        folder = (store.local / "audio").resolve()
        file = (folder / (ident + ".wav")).resolve()
        if file.parent != folder or not file.is_file():
            raise HTTPException(404, "음성을 찾을 수 없습니다.")
        # Legacy URLs are only playable when a currently valid attached lesson
        # still produces this exact verified key. Unattached global clips use
        # the scoped read-only route above, which also checks the board binding.
        for lesson in store.list("lessons"):
            if not lesson_validity(lesson)["valid"] or not speech_is_allowed(lesson):
                continue
            for item in lesson.get("audio_steps", []):
                if item.get("audio_id") != ident:
                    continue
                try:
                    voice = item.get("voice", "Sohee")
                    if item.get("provider") == "windows_sapi_local":
                        voice = "windows_sapi:" + voice
                    view = speech_cache_view(lesson["id"], item.get("step_id"), voice, include_audio_bytes=True)
                except HTTPException:
                    continue
                for audio in view["steps"]:
                    if audio["audio_id"] == ident:
                        return Response(audio["_wave_bytes"], media_type="audio/wav")
        raise HTTPException(409, "현재 문제·대사와 일치하는 검증된 음성을 찾을 수 없습니다.")

    @app.post("/api/photos", status_code=201)
    async def upload_photo(file: UploadFile = File(...), session_id: str | None = Form(None)):
        from edu_tutor.models.execution_context import requested_student_session
        if session_id:
            bind_student_budget(session_id)
        elif requested_student_session.get():
            raise HTTPException(409, "사진을 업로드할 학생 대화를 명시하세요.")
        raw = await file.read(10 * 1024 * 1024 + 1)
        photo = await asyncio.to_thread(photos.upload, raw)
        if session_id:
            photo["session_id"] = session_id
            store.put("photos", photo)
        return photo

    @app.get("/api/photos")
    def list_photos():
        return store.list("photos")

    @app.get("/api/photos/{ident}")
    def read_photo(ident: str):
        return get("photos", ident)

    @app.get("/api/photos/{ident}/image")
    def photo_image(ident: str):
        get("photos", ident)
        return FileResponse(store.file("photos", ident, ".png"), media_type="image/png")

    @app.patch("/api/photos/{ident}")
    def edit_photo(ident: str, body: PhotoInput):
        fields = body.model_dump(exclude_none=True)
        if len(json.dumps(fields)) > 50000:
            raise ValueError("사진 원문 크기 제한을 초과했습니다.")
        with jobs.lock:
            edited=photos.edit(ident, fields)
            for lesson in store.list("lessons"):
                if (lesson.get("problem") or {}).get("source",{}).get("photo_id")==ident:
                    lesson.update(valid=False,invalidated_reason="사진 원문 수정으로 이전 계산·음성·판서가 무효화되었습니다.",invalidated_at=utcnow())
                    store.put("lessons",lesson)
            return edited

    @app.post("/api/photos/{ident}/confirm")
    def confirm_photo(ident: str):
        with jobs.lock:
            return photos.confirm(ident)

    @app.post("/api/photos/{ident}/restructure")
    def restructure_photo(ident: str):
        """Reparse saved OCR only; never repeat a vision call or confirm it."""
        from edu_tutor.vision.structure import structure_candidate
        from edu_tutor.vision.conditions import check_transcription
        with jobs.lock:
            photo = get("photos", ident)
            if not photo.get("original_text"):
                raise ValueError("저장된 인식문이 없습니다. 원문을 직접 입력하거나 인식을 실행하세요.")
            candidate = check_transcription(structure_candidate({"original_text":photo["original_text"]}))
            if not candidate.get("tables"):
                raise ValueError("인식문에서 표 전체를 확실히 나눌 수 없습니다. 사진을 보고 표를 확인해 주세요.")
            fields = {"tables":candidate["tables"],"missing_conditions":list(dict.fromkeys([*photo.get("missing_conditions",[]),*candidate.get("missing_conditions",[])]))}
            if candidate.get("sql"):
                fields["sql"] = candidate["sql"]
            edited = edit_photo(ident, PhotoInput.model_validate(fields))
            edited.update(recognition_structure=candidate["structure_extraction"],
                          recognition_reason="저장된 인식문을 다시 정리한 미확정 후보입니다. 사진과 대조해 주세요.")
            store.put("photos", edited)
            store.record("photo_restructure", ident, revision=edited["revision"], model_calls=0)
            return edited

    @app.post("/api/photos/{ident}/solve", status_code=202)
    def solve_photo(ident: str, body: PhotoSolveInput):
        bind_student_budget(body.session_id, kind="text")
        try:
            photo = photos.confirmed(ident)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        check_student_photo(photo, body.session_id)
        content = photo["question"] + "\n확정한 원문 데이터:\n" + json.dumps({k: photo[k] for k in ("sql", "tables", "choices", "missing_conditions")}, ensure_ascii=False)
        return send_message(body.session_id, MessageInput(content=content, request_id=body.request_id,
                            generation_epoch=body.generation_epoch, photo_id=ident))

    @app.post("/api/photos/{ident}/transcribe", status_code=202)
    def transcribe_photo(ident: str):
        original = get("photos", ident)
        if original.get("session_id"):
            bind_student_budget(original["session_id"], kind="vision")
        else:
            from edu_tutor.models.execution_context import requested_student_session
            if requested_student_session.get():
                raise HTTPException(409, "이 학생 대화에 연결된 사진을 먼저 업로드하세요.")
        def transcribe(job_id, cancel):
            from edu_tutor.models.vision_runtime import transcribe as runtime_transcribe
            from edu_tutor.vision.conditions import check_transcription
            jobs.update(job_id, state="running")
            candidate = runtime_transcribe(store.file("photos", ident, ".png"), root=root, cancel_event=cancel, job_id=job_id)
            candidate = check_transcription(candidate)
            with jobs.lock:
                current = get("photos", ident)
                if cancel.is_set() or current["revision"] != original["revision"]:
                    return {"discarded": True, "reason": "인식 도중 수정한 원문을 보존했습니다."}
                allowed = {key: candidate[key] for key in ("question", "sql", "tables", "choices", "unreadable_regions", "missing_conditions") if key in candidate}
                allowed = PhotoInput.model_validate(allowed).model_dump(exclude_none=True)
                edited = photos.edit(ident, allowed)
                edited.update(original_text=candidate.get("original_text", candidate.get("question", "")),
                    recognition_status=candidate.get("recognition_status", "candidate"), recognition_reason="자동 인식 후보입니다. 원문을 검토한 뒤 확정하세요.",
                    recognition_model_revision=candidate.get("revision"), recognition_elapsed_seconds=candidate.get("elapsed_seconds"),
                    recognition_structure=candidate.get("structure_extraction"),
                    recognition_format_check=candidate["format_check"],
                    confirmed=False, confirmed_at=None, confirmed_by=None)
                store.put("photos", edited)
                return {"photo_id": ident, "revision": edited["revision"], "recognition_status": edited["recognition_status"]}
        return {"job_id": jobs.submit("vision", transcribe, session_id=original.get("session_id"))["id"]}

    @app.delete("/api/photos/{ident}")
    def delete_photo(ident: str):
        with jobs.lock:
            photos.delete(ident)
        return {"deleted": True}

    from edu_tutor.api.admin import register_admin
    register_admin(app, root, store, jobs)
    from edu_tutor.api.neural import register_neural
    register_neural(app, root, store, jobs)
    web = root / "web" / "dist"
    if web.is_dir():
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    return app
