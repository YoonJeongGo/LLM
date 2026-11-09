"""Live API/model evidence runner. Never substitutes fixtures for inference.

Run only after the local server and the requested model runtimes are ready:
  python scripts/integration_live.py --stage text
  python scripts/integration_live.py --stage media
  python scripts/integration_live.py --stage restart-check

The runner leaves its own sessions/photos/materials intact for browser review.
It does not stop/restart servers, download models, or change adapter selection.
API+GPU evidence is T2 here. T3 requires a separate real-browser connection.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


class Evidence:
    def __init__(self, root, stage, base_url):
        self.root, self.stage = root, stage
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.folder = root / "runs/integration-live" / f"{stamp}-{stage}-{uuid4().hex[:6]}"
        self.folder.mkdir(parents=True)
        self.value = {"started_at": now(), "stage": stage, "base_url": base_url,
                      "tier": "T0" if stage == "restart-check" else "T2",
                      "scope": "live localhost API and actual model workers" if stage != "restart-check" else "local API persistence check",
                      "browser_integration": "not_run", "human_review": "not_reviewed",
                      "fixture_policy": "Self-authored problem inputs only. Model outputs come from real API workers.",
                      "steps": [], "status": "running"}

    def add(self, name, status, **data):
        self.value["steps"].append({"name": name, "status": status, "timestamp": now(), **data})
        write_json(self.folder / "report.json", self.value)
        print(json.dumps({"step": name, "status": status}, ensure_ascii=False), flush=True)

    def finish(self):
        self.value["finished_at"] = now()
        self.value["status"] = "passed" if all(s["status"] == "pass" for s in self.value["steps"]) else "partial_or_failed"
        write_json(self.folder / "report.json", self.value)
        print(json.dumps({"status": self.value["status"], "artifact": str(self.folder / "report.json")}, ensure_ascii=False), flush=True)
        return 0 if self.value["status"] == "passed" else 2


class Live:
    def __init__(self, root, base_url, evidence):
        token = (root / ".local/auth-token").read_text(encoding="utf-8").strip()
        self.http = httpx.Client(base_url=base_url, headers={"Authorization": "Bearer " + token}, timeout=30,
                                 follow_redirects=False, trust_env=False)
        self.evidence = evidence

    def request(self, method, path, **kwargs):
        response = self.http.request(method, path, **kwargs)
        if response.status_code >= 400:
            # Never log request headers or bearer credentials.
            raise RuntimeError(f"{method} {path}: HTTP {response.status_code}: {response.text[:500]}")
        return response.json()

    def wait(self, job_id, timeout=340):
        started = time.monotonic()
        terminal = {"succeeded", "failed", "cancelled", "interrupted", "blocked"}
        while time.monotonic() - started < timeout:
            job = self.request("GET", f"/api/jobs/{job_id}")
            if job["state"] in terminal:
                write_json(self.evidence.folder / f"job-{job_id}.json", job)
                return job
            time.sleep(.8)
        self.request("POST", f"/api/jobs/{job_id}/cancel")
        raise TimeoutError(f"Live API job exceeded {timeout}s and cancellation was requested: {job_id}")

    def health(self):
        health = self.request("GET", "/api/health")
        missing = self.http.get("/api/sessions", headers={"Authorization": ""})
        hostile = self.http.post("/api/sessions", json={}, headers={"Origin": "https://example.invalid"})
        state = self.request("GET", "/api/models")
        self.evidence.add("live_api_auth_origin", "pass" if health["status"] == "ok" and missing.status_code == 401 and hostile.status_code == 403 else "fail",
                          unauthenticated_status=missing.status_code, hostile_origin_status=hostile.status_code,
                          model={k: state.get(k) for k in ("model_id", "revision", "active_adapter", "ready", "installed", "validation")})


def text_stage(live, evidence):
    from edu_tutor.evaluation.sql_sandbox import extract_sql
    note = "직접 작성한 API 통합 시험용 참고 자료입니다. COUNT(*)는 전체 행을 셉니다. COUNT(열)는 해당 열의 NULL 값을 제외합니다. SQLite에서 SQL NULL은 값이 없음을 뜻하며 문자열 'NULL'과 다릅니다."
    document = live.request("POST", "/api/documents", files={"file": ("integration-count-note.md", note.encode("utf-8"), "text/markdown")},
                            data={"title": "통합 검증 COUNT 참고 자료", "rights": "이 통합 검사에서 직접 작성한 설명. 외부 교재를 복사하지 않음.", "subject": "SQL 기초"})
    live.request("POST", f"/api/documents/{document['id']}/review", json={"approved": True})
    hits = live.request("GET", "/api/search", params={"q": "COUNT NULL"})
    evidence.add("reviewed_document_retrieval", "pass" if any(h["document_id"] == document["id"] for h in hits) else "fail",
                 document_id=document["id"], chunk_ids=[h["chunk_id"] for h in hits])
    session = live.request("POST", "/api/sessions", json={"title": "실제 API 통합 검증 · COUNT와 NULL"})
    question = ('SQLite의 sample(v INTEGER) 표에 (1), (NULL), (3) 세 행이 있습니다. 전체 행 수와 NULL이 아닌 값 수를 구하는 SELECT문을 만드세요. '
                '열 별칭은 total_rows, non_null_rows를 사용하세요. 응답은 {"sql":"SQL문","explanation":"짧은 한국어 설명"} JSON 객체 하나로 주세요.')
    submitted = live.request("POST", f"/api/sessions/{session['id']}/messages",
                             json={"content": question, "request_id": uuid4().hex, "use_rag": True, "adapter": "base"})
    job = live.wait(submitted["job_id"])
    if job["state"] != "succeeded":
        evidence.add("actual_chat_generation", "fail", job_id=job["id"], state=job["state"], error=job.get("error"))
        return
    messages = live.request("GET", f"/api/sessions/{session['id']}/messages")
    answer = next(m for m in messages if m["id"] == job["result"]["message_id"])
    write_json(evidence.folder / "actual-chat.json", {"question": question, "answer": answer, "open_book": True})
    evidence.add("actual_chat_generation", "pass", session_id=session["id"], message_id=answer["id"], job_id=job["id"],
                 provenance=answer.get("provenance"), source_ids=[s["chunk_id"] for s in answer.get("sources", [])],
                 limitation="Open-book pipeline smoke; not an independent educational-quality benchmark.")
    fixture = {"tables": [{"name": "sample", "columns": [{"name": "v", "type": "INTEGER"}], "rows": [[1], [None], [3]]}]}
    try:
        candidate_sql = extract_sql(answer["content"])
        result = live.request("POST", "/api/evaluations/sql", json={"sql": candidate_sql, "fixture": fixture,
                              "expected": {"columns": ["total_rows", "non_null_rows"], "rows": [[3, 2]], "row_order": "ordered", "numeric_abs_tolerance": 0}})
        evidence.add("actual_model_sql_execution", "pass" if result.get("match") else "fail", candidate_sql=candidate_sql, result=result)
    except ValueError as exc:
        evidence.add("actual_model_sql_execution", "fail", error=str(exc), reason="Actual model output did not satisfy the unambiguous SQL extraction contract.")
    lesson = live.request("POST", "/api/lessons", json={"session_id": session["id"], "message_id": answer["id"]})
    lesson_job = live.request("POST", f"/api/lessons/{lesson['id']}/generate")
    final_job = live.wait(lesson_job["job_id"])
    lesson = live.request("GET", f"/api/lessons/{lesson['id']}")
    write_json(evidence.folder / "actual-lesson.json", lesson)
    evidence.add("actual_structured_lesson", "pass" if final_job["state"] == "succeeded" and lesson.get("plan") and lesson["status"] == "structured_unverified" else "fail",
                 lesson_id=lesson["id"], job_id=lesson_job["job_id"], state=final_job["state"], lesson_status=lesson["status"],
                 reason=lesson.get("reason"), content_review="not_reviewed")
    checkpoint = {"session_id": session["id"], "message_id": answer["id"], "lesson_id": lesson["id"], "document_id": document["id"],
                  "message_count": len(messages), "created_at": now(), "evidence_dir": str(evidence.folder)}
    write_json(evidence.root / "runs/integration-live/latest-text.json", checkpoint)
    evidence.value["checkpoint"] = checkpoint


def vision_fixtures(root):
    from PIL import Image, ImageDraw, ImageFont
    directory = root / "tests/fixtures"
    directory.mkdir(parents=True, exist_ok=True)
    font_path = Path("C:/Windows/Fonts/malgun.ttf")
    if not font_path.is_file():
        raise FileNotFoundError("Malgun Gothic is required for the self-authored Korean image fixtures")
    font = ImageFont.truetype(str(font_path), 31)
    small = ImageFont.truetype(str(font_path), 28)
    values = []
    for kind in ("clear", "table", "cut"):
        image = Image.new("RGB", (1100, 620), "white")
        draw = ImageDraw.Draw(image)
        if kind == "clear":
            lines = ["직접 작성한 SQL 기초 문제", "SQLite: scores(value INTEGER)", "행: 10, NULL, 30", "COUNT(*)와 COUNT(value)의 결과를 구하세요."]
            for index, line in enumerate(lines):
                draw.text((45, 45 + index * 90), line, font=font, fill="black")
        elif kind == "table":
            draw.text((45, 35), "직접 작성한 표 문제 — SQLite", font=font, fill="black")
            rows = [["id", "team", "score"], ["1", "A", "10"], ["2", "A", "NULL"], ["3", "B", "30"]]
            for row, cells in enumerate(rows):
                for col, cell in enumerate(cells):
                    x, y = 60 + col * 280, 110 + row * 80
                    draw.rectangle((x, y, x + 280, y + 80), outline="black", width=2)
                    draw.text((x + 22, y + 20), cell, font=small, fill="black")
            draw.text((45, 480), "team별 COUNT(score)를 구하세요.", font=font, fill="black")
        else:
            draw.text((45, 45), "직접 작성한 일부 잘린 문제", font=font, fill="black")
            draw.text((45, 155), "SELECT name FROM employees", font=font, fill="black")
            draw.text((45, 245), "WHERE salary >=", font=font, fill="black")
            draw.line((42, 345, 1050, 345), fill="#999999", width=4)
            draw.text((45, 390), "[이 아래의 조건과 선택지가 잘려 있습니다]", font=small, fill="#333333")
        file = directory / f"vision_{kind}.png"
        image.save(file, "PNG")
        values.append({"kind": kind, "path": file, "sha256": hashlib.sha256(file.read_bytes()).hexdigest()})
    return values


def tts_stage(live, evidence, checkpoint):
    lesson_id = checkpoint["lesson_id"]
    lesson = live.request("GET", f"/api/lessons/{lesson_id}")
    step_ids = [step["id"] for step in lesson["plan"]["steps"][:3]] if lesson.get("plan") else ["answer"]
    for step_id in step_ids:
        try:
            submitted = live.request("POST", f"/api/lessons/{lesson_id}/speech", json={"voice": "Sohee", "step_id": step_id, "request_id": uuid4().hex})
            job = live.wait(submitted["job_id"])
            if job["state"] != "succeeded":
                evidence.add("actual_tts_" + step_id, "fail", job_id=job["id"], state=job["state"], error=job.get("error"))
                continue
            prepared = live.request("GET", f"/api/lessons/{lesson_id}/speech")
            audio = next(s for s in prepared["steps"] if s["step_id"] == step_id)
            response = live.http.get(audio["audio_url"])
            response.raise_for_status()
            raw = response.content
            with wave.open(io.BytesIO(raw), "rb") as wav:
                duration = wav.getnframes() / wav.getframerate()
                frames = wav.readframes(wav.getnframes())
                width = wav.getsampwidth()
            non_silent = any(frames) if width == 2 else None
            checksum_match = hashlib.sha256(raw).hexdigest() == audio["checksum"]
            (evidence.folder / f"speech-{step_id}.wav").write_bytes(raw)
            evidence.add("actual_tts_" + step_id, "pass" if duration > .1 and non_silent and checksum_match else "fail",
                         audio=audio, decoded_duration=duration, non_silent=non_silent, checksum_match=checksum_match,
                         listening_review="not_run", browser_playback="not_run")
        except Exception as exc:
            evidence.add("actual_tts_" + step_id, "fail", error=f"{type(exc).__name__}: {exc}")


def photos_stage(live, evidence):
    session = live.request("POST", "/api/sessions", json={"title": "실제 사진 원문 확인 통합 검증"})
    for fixture in vision_fixtures(evidence.root):
        kind = fixture["kind"]
        try:
            photo = live.request("POST", "/api/photos", files={"file": (fixture["path"].name, fixture["path"].read_bytes(), "image/png")})
            rejected = live.http.post(f"/api/photos/{photo['id']}/solve", json={"session_id": session["id"]})
            evidence.add("unconfirmed_photo_gate_" + kind, "pass" if rejected.status_code == 409 else "fail",
                         photo_id=photo["id"], http_status=rejected.status_code)
            submitted = live.request("POST", f"/api/photos/{photo['id']}/transcribe")
            job = live.wait(submitted["job_id"])
            candidate = live.request("GET", f"/api/photos/{photo['id']}")
            write_json(evidence.folder / f"vision-{kind}.json", {"fixture": str(fixture["path"]), "sha256": fixture["sha256"], "photo": candidate, "job": job})
            evidence.add("actual_vision_" + kind, "pass" if job["state"] == "succeeded" and candidate["original_text"] and not candidate["confirmed"] else "fail",
                         photo_id=photo["id"], job_id=job["id"], state=job["state"], recognition_status=candidate["recognition_status"],
                         recognition_accuracy="not_human_reviewed", limitation="Three self-authored images do not establish general recognition accuracy.")
            if kind == "clear":
                # Explicit test input edits are retained as user corrections, never credited to vision.
                corrected = live.request("PATCH", f"/api/photos/{photo['id']}", json={
                    "question": "SQLite에서 scores(value INTEGER)의 행은 10, NULL, 40입니다. COUNT(*)와 COUNT(value)를 설명하세요. 답은 한국어 두 문장으로 해주세요.",
                    "sql": "", "tables": [{"name": "scores", "columns": ["value"], "rows": [[10], [None], [40]]}],
                    "choices": [], "unreadable_regions": [], "missing_conditions": []})
                still_rejected = live.http.post(f"/api/photos/{photo['id']}/solve", json={"session_id": session["id"]})
                confirmed = live.request("POST", f"/api/photos/{photo['id']}/confirm")
                solved = live.request("POST", f"/api/photos/{photo['id']}/solve", json={"session_id": session["id"], "request_id": uuid4().hex})
                solve_job = live.wait(solved["job_id"])
                messages = live.request("GET", f"/api/sessions/{session['id']}/messages")
                actual_input = next(m["content"] for m in messages if m["role"] == "user" and m["request_id"] == solved["request_id"])
                evidence.add("edited_confirmed_photo_solve", "pass" if still_rejected.status_code == 409 and confirmed["confirmed"] and corrected["revision"] > photo["revision"] and "40" in actual_input and solve_job["state"] == "succeeded" else "fail",
                             photo_id=photo["id"], revision=confirmed["revision"], job_id=solve_job["id"], state=solve_job["state"],
                             correction_source="explicit test user edit, not recognition output")
        except Exception as exc:
            evidence.add("photo_flow_" + kind, "fail", error=f"{type(exc).__name__}: {exc}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--stage", choices=["text", "media", "tts", "photos", "restart-check"], required=True)
    args = parser.parse_args()
    url = urlsplit(args.url)
    if url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost"} or url.username is not None or url.password is not None or url.path not in {"", "/"} or url.query or url.fragment:
        parser.error("Only localhost API URLs are supported")
    root = args.root.resolve()
    evidence = Evidence(root, args.stage, args.url)
    try:
        live = Live(root, args.url, evidence)
        live.health()
        checkpoint_file = root / "runs/integration-live/latest-text.json"
        if args.stage == "text":
            text_stage(live, evidence)
        elif args.stage in {"media", "tts"}:
            try:
                checkpoint = json.loads(checkpoint_file.read_text(encoding="utf-8"))
                evidence.value["text_checkpoint"] = checkpoint
                tts_stage(live, evidence, checkpoint)
            except (FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
                evidence.add("tts_missing_actual_text_checkpoint", "blocked",
                             error=f"{type(exc).__name__}: {exc}",
                             reason="실제 모델 답변의 강의가 없어 음성 검증을 진행하지 않았습니다.")
            if args.stage == "media":
                photos_stage(live, evidence)
        elif args.stage == "photos":
            photos_stage(live, evidence)
        else:
            checkpoint = json.loads(checkpoint_file.read_text(encoding="utf-8"))
            exported = live.request("GET", f"/api/sessions/{checkpoint['session_id']}/export")
            preserved = any(m["id"] == checkpoint["message_id"] for m in exported["messages"])
            evidence.add("preserved_session_after_external_restart", "pass" if preserved else "fail", session_id=checkpoint["session_id"],
                         note="This check does not restart the server or claim orphan-job recovery unless a separate restart command is recorded.")
    except Exception as exc:
        evidence.add("stage_error", "fail", error=f"{type(exc).__name__}: {exc}")
    return evidence.finish()


if __name__ == "__main__":
    raise SystemExit(main())
