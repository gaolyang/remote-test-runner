from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StepRole(str, Enum):
    SETUP = "setup"
    VERIFY = "verify"
    CLEANUP = "cleanup"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    MANUAL_CONFIRM_REQUIRED = "MANUAL_CONFIRM_REQUIRED"
    WAITING_FOR_OPERATOR = "WAITING_FOR_OPERATOR"
    SKIPPED = "SKIPPED"


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["shell"] = "shell"
    command: str = Field(min_length=1)


class Expected(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exit_code: int | None = None
    stdout_contains: list[str] = Field(default_factory=list)
    stdout_empty: bool | None = None


class EvidencePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capture: bool | None = None
    trigger: Literal["command_complete", "manual"] | None = None


class InteractionPolicy(BaseModel):
    """Operator-assisted command execution in the shared SSH terminal."""

    model_config = ConfigDict(extra="forbid")
    mode: Literal["manual"] = "manual"
    instructions: str = "请在终端中完成交互，然后点击“完成交互”。"
    timeout: float = Field(default=600, gt=0, le=86400)


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int | str
    role: StepRole
    name: str = Field(min_length=1)
    action: Action
    expected: Expected = Field(default_factory=Expected)
    evidence: EvidencePolicy | None = None
    interaction: InteractionPolicy | None = None

    def resolved_evidence(self) -> EvidencePolicy:
        default_capture = self.role == StepRole.VERIFY
        if self.evidence is None:
            return EvidencePolicy(
                capture=default_capture,
                trigger="command_complete" if default_capture else None,
            )
        capture = default_capture if self.evidence.capture is None else self.evidence.capture
        trigger = self.evidence.trigger
        if capture and trigger is None:
            trigger = "command_complete"
        return EvidencePolicy(capture=capture, trigger=trigger)


class TestCaseInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=1)
    description: str = ""


class Connection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["ssh"] = "ssh"


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connection: Connection


class TestCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = "1.0"
    testcase: TestCaseInfo
    target: Target
    steps: list[Step] = Field(min_length=1)

    @field_validator("steps")
    @classmethod
    def unique_step_ids(cls, steps: list[Step]) -> list[Step]:
        ids = [str(step.id) for step in steps]
        if len(ids) != len(set(ids)):
            raise ValueError("step id must be unique within a test case")
        return steps
