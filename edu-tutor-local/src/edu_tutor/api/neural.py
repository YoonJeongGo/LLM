"""Authenticated SSE transport for one bounded text-worker observation."""
from __future__ import annotations

import asyncio
import json
from typing import Literal

from fastapi import HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from edu_tutor.neural.service import NeuralConflict, NeuralService


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NeuralInput(StrictInput):
    text: str = Field(min_length=1, max_length=12000)
    observation_mode: Literal["off", "light", "detail"] = "light"
    selected_layers: list[str] = Field(default_factory=list, max_length=2)
    sample_every_steps: int = Field(default=16, ge=8, le=128)
    max_new_tokens: int = Field(default=128, ge=1, le=128)
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    generation_epoch: int = Field(ge=0)
    update_interval_ms: int = Field(default=250, ge=100, le=2000)
    adapter_id: str = Field(default="base", max_length=100)


class ObservationInput(StrictInput):
    enabled: bool
    generation_epoch: int = Field(ge=0)
    mode: Literal["light", "detail"] | None = None
    selected_layers: list[str] | None = Field(default=None, max_length=2)
    sample_every_steps: int | None = Field(default=None, ge=8, le=128)
    update_interval_ms: int | None = Field(default=None, ge=100, le=2000)


class CancelInput(StrictInput):
    generation_epoch: int = Field(ge=0)


class SaveInput(StrictInput):
    include_sensitive: bool = False


def register_neural(app, root, store, jobs):
    service = NeuralService(root, store, jobs)
    app.state.neural = service

    def call(action, *args):
        try:
            return action(*args)
        except NeuralConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/neural/state")
    def state():
        return service.state()

    @app.post("/api/neural/runs", status_code=202)
    def start(body: NeuralInput):
        if any(len(path) > 300 for path in body.selected_layers):
            raise HTTPException(422, "모듈 경로가 너무 깁니다.")
        return call(service.start, body.model_dump())

    @app.get("/api/neural/runs/{ident}")
    def run(ident: str):
        return service.get(ident)

    @app.post("/api/neural/runs/{ident}/observation")
    def observation(ident: str, body: ObservationInput):
        if any(len(path) > 300 for path in (body.selected_layers or [])):
            raise HTTPException(422, "모듈 경로가 너무 깁니다.")
        return call(service.observation, ident, body.model_dump())

    @app.post("/api/neural/runs/{ident}/cancel")
    def cancel(ident: str, body: CancelInput):
        return call(service.cancel, ident, body.generation_epoch)

    @app.post("/api/neural/runs/{ident}/save", status_code=201)
    def save(ident: str, body: SaveInput):
        return call(service.save, ident, body.include_sensitive)

    @app.get("/api/neural/records")
    def records():
        return {"records": service.records()}

    @app.get("/api/neural/records/{ident}")
    def record(ident: str):
        return service.record(ident)

    @app.get("/api/neural/runs/{ident}/events")
    async def events(ident: str, request: Request, after: int = Query(default=0, ge=0)):
        # The app's existing guard requires Authorization: Bearer. Query tokens
        # are never accepted. Snapshot is out-of-band; its sequence must not
        # suppress the retained history requested via `after`.
        service.get(ident)

        async def stream():
            subscription = service.subscribe(ident)
            cursor = after
            try:
                snapshot = service.snapshot(ident)
                yield "event: snapshot\ndata: " + json.dumps(snapshot, ensure_ascii=False, allow_nan=False) + "\n\n"
                while not await request.is_disconnected():
                    batch, terminal, interval = service.events_after(ident, cursor)
                    for event in batch:
                        if event["sequence_no"] > cursor + 1:
                            gap = {"event_type": "gap", "run_id": ident,
                                   "request_id": event["request_id"], "generation_epoch": event["generation_epoch"],
                                   "sequence_no": cursor, "source": "backend_derived", "payload": {
                                       "from_sequence_no": cursor + 1, "to_sequence_no": event["sequence_no"] - 1,
                                       "reason": "bounded_buffer_eviction"}}
                            yield "event: gap\ndata: " + json.dumps(gap, ensure_ascii=False) + "\n\n"
                        cursor = event["sequence_no"]
                        yield f"id: {cursor}\nevent: observation\ndata: " + json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n\n"
                    if terminal:
                        break
                    if not batch:
                        yield ": heartbeat\n\n"
                    await asyncio.sleep(interval / 1000)
            finally:
                service.unsubscribe(ident, subscription)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={
            "Cache-Control": "no-store", "X-Accel-Buffering": "no",
        })

    return service
