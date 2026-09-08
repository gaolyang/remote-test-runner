from __future__ import annotations

import asyncio
import ipaddress
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, field_validator

from backend.config import settings
from backend.evidence.manager import EvidenceManager
from backend.evidence.screenshot import ScreenshotError, ScreenshotService
from backend.execution.engine import ExecutionEngine
from backend.session import RuntimeSession, registry
from backend.testcase.parser import TestCaseLoadError, load_testcase, safe_case_path

router = APIRouter(tags=["sessions"])
screenshot_service = ScreenshotService(settings.public_base_url)
evidence_manager = EvidenceManager(settings.results_dir, screenshot_service)
execution_engine = ExecutionEngine(settings, evidence_manager)


class StartSessionRequest(BaseModel):
    testcase: str
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=128)
    password: str | None = Field(default=None, max_length=4096)
    key_filename: str | None = Field(default=None, max_length=4096)

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        value = value.strip()
        try:
            ipaddress.ip_address(value)
            return value
        except ValueError:
            if not re.fullmatch(r"(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", value):
                raise ValueError("host must be a valid IP address or hostname")
            return value


def require_session(session_id: str) -> RuntimeSession:
    session = registry.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/api/sessions", status_code=201)
async def start_session(request: StartSessionRequest) -> dict[str, str]:
    try:
        case_path = safe_case_path(settings.testcase_dir, request.testcase)
        testcase = load_testcase(case_path)
    except TestCaseLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not request.password and not request.key_filename and not os.getenv("RTR_SSH_PASSWORD"):
        # Agent/key discovery may still authenticate; this is intentionally allowed.
        pass
    if request.key_filename and not Path(request.key_filename).expanduser().is_file():
        raise HTTPException(status_code=400, detail="SSH private key file does not exist")
    session = RuntimeSession(
        case_filename=request.testcase,
        testcase=testcase,
        target=request.host,
        port=request.port,
        username=request.username,
        password=request.password,
        key_filename=str(Path(request.key_filename).expanduser()) if request.key_filename else None,
    )
    await registry.add(session)
    session.task = asyncio.create_task(
        execution_engine.run(session, case_path), name=f"test-session-{session.session_id}"
    )
    return {"session_id": session.session_id}


@router.get("/api/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, object]:
    return require_session(session_id).snapshot(include_transcript=True)


@router.post("/api/sessions/{session_id}/rendered")
async def terminal_rendered(session_id: str, payload: dict[str, str]) -> dict[str, bool]:
    event_id = payload.get("event_id", "")
    acknowledged = require_session(session_id).acknowledge_render(event_id)
    return {"acknowledged": acknowledged}


@router.post("/api/sessions/{session_id}/confirm/{step_id}")
async def confirm_command(session_id: str, step_id: str) -> dict[str, bool]:
    confirmed = require_session(session_id).confirm_command(step_id)
    if not confirmed:
        raise HTTPException(status_code=409, detail="Step is not awaiting confirmation")
    return {"confirmed": True}


@router.post("/api/sessions/{session_id}/capture")
async def manual_capture(session_id: str) -> dict[str, str]:
    session = require_session(session_id)
    if not session.result_dir:
        raise HTTPException(status_code=409, detail="Result archive is not ready")
    try:
        path = await evidence_manager.capture_manual(session)
    except ScreenshotError as exc:
        raise HTTPException(status_code=500, detail=f"Screenshot failed: {exc}") from exc
    if session.step_results:
        session.step_results[-1].setdefault("evidence", []).append(path)
    await session.publish("evidence_captured", path=path, step_id=session.current_step_id)
    return {"path": path}


@router.post("/api/sessions/{session_id}/abort")
async def abort_session(session_id: str) -> dict[str, bool]:
    session = require_session(session_id)
    session.abort_event.set()
    if session.task and not session.task.done():
        session.task.cancel()
    return {"aborted": True}


@router.websocket("/ws/terminal/{session_id}")
async def terminal_websocket(websocket: WebSocket, session_id: str) -> None:
    session = registry.get(session_id)
    if session is None:
        await websocket.close(code=4404, reason="Session not found")
        return
    await websocket.accept()
    queue = session.subscribe()
    session.websocket_ready.set()
    await websocket.send_json({"type": "snapshot", "state": session.snapshot(include_transcript=True)})

    async def sender() -> None:
        while True:
            await websocket.send_json(await queue.get())

    async def receiver() -> None:
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")
            if message_type == "input" and session.ssh is not None:
                await session.ssh.send_input(str(message.get("data", "")))
            elif message_type == "resize" and session.ssh is not None:
                columns = max(20, min(500, int(message.get("columns", 120))))
                rows = max(5, min(200, int(message.get("rows", 30))))
                await session.ssh.resize(columns, rows)
            elif message_type == "terminal_rendered":
                session.acknowledge_render(str(message.get("event_id", "")))

    sender_task = asyncio.create_task(sender())
    receiver_task = asyncio.create_task(receiver())
    try:
        done, pending = await asyncio.wait(
            {sender_task, receiver_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        for task in done:
            task.result()
    except (WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
        pass
    finally:
        session.unsubscribe(queue)
