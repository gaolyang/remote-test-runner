from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.testcase.models import StepStatus, TestCase


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RuntimeSession:
    case_filename: str
    testcase: TestCase
    target: str
    port: int
    username: str
    password: str | None = field(default=None, repr=False)
    key_filename: str | None = field(default=None, repr=False)
    session_id: str = field(default_factory=lambda: uuid4().hex)
    status: str = "STARTING"
    message: str = "Waiting for browser terminal"
    start_time: str = field(default_factory=utc_now)
    end_time: str | None = None
    current_step_index: int = -1
    current_step_id: str | None = None
    step_results: list[dict[str, Any]] = field(default_factory=list)
    transcript: str = ""
    result_dir: str | None = None
    websocket_ready: asyncio.Event = field(default_factory=asyncio.Event)
    abort_event: asyncio.Event = field(default_factory=asyncio.Event)
    render_acks: dict[str, asyncio.Event] = field(default_factory=dict)
    command_confirmations: dict[str, asyncio.Event] = field(default_factory=dict)
    subscribers: set[asyncio.Queue[dict[str, Any]]] = field(default_factory=set)
    ssh: Any = field(default=None, repr=False)
    task: asyncio.Task[None] | None = field(default=None, repr=False)

    async def publish(self, event_type: str, **payload: Any) -> None:
        event = {"type": event_type, **payload}
        for queue in tuple(self.subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self.subscribers.discard(queue)

    async def terminal_output(self, data: str) -> None:
        self.transcript += data
        await self.publish("terminal_output", data=data)

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self.subscribers.discard(queue)

    def acknowledge_render(self, event_id: str) -> bool:
        event = self.render_acks.get(event_id)
        if event is None:
            return False
        event.set()
        return True

    def confirm_command(self, step_id: str) -> bool:
        event = self.command_confirmations.get(step_id)
        if event is None:
            return False
        event.set()
        return True

    def snapshot(self, include_transcript: bool = True) -> dict[str, Any]:
        step = None
        if 0 <= self.current_step_index < len(self.testcase.steps):
            current = self.testcase.steps[self.current_step_index]
            step = {
                "id": str(current.id),
                "name": current.name,
                "role": current.role.value,
                "expected": current.expected.model_dump(),
            }
        step_items: list[dict[str, Any]] = []
        results_by_id = {str(item["id"]): item for item in self.step_results}
        for definition in self.testcase.steps:
            step_id = str(definition.id)
            result = results_by_id.get(step_id)
            step_items.append(
                {
                    "id": step_id,
                    "name": definition.name,
                    "role": definition.role.value,
                    "status": result["status"] if result else StepStatus.PENDING.value,
                    "evidence": result.get("evidence", []) if result else [],
                }
            )
        data: dict[str, Any] = {
            "session_id": self.session_id,
            "case_id": self.testcase.testcase.id,
            "case_name": self.testcase.testcase.name,
            "target": self.target,
            "username": self.username,
            "status": self.status,
            "message": self.message,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "current_step_index": self.current_step_index,
            "current_step": step,
            "total_steps": len(self.testcase.steps),
            "steps": step_items,
            "step_results": self.step_results,
            "result_dir": self.result_dir,
        }
        if include_transcript:
            data["transcript"] = self.transcript
        return data


class SessionRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, RuntimeSession] = {}
        self._lock = asyncio.Lock()

    async def add(self, session: RuntimeSession) -> None:
        async with self._lock:
            self._sessions[session.session_id] = session

    def get(self, session_id: str) -> RuntimeSession | None:
        return self._sessions.get(session_id)

    def list(self) -> list[RuntimeSession]:
        return list(self._sessions.values())


registry = SessionRegistry()
