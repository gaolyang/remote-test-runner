from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from uuid import uuid4

from backend.config import Settings
from backend.evidence.manager import EvidenceManager
from backend.evidence.screenshot import ScreenshotError
from backend.execution.risk import find_command_risks
from backend.execution.output import clean_command_output
from backend.result.evaluator import evaluate
from backend.session import RuntimeSession, utc_now
from backend.ssh.client import SSHCredentials
from backend.ssh.session import SSHShellSession
from backend.testcase.models import StepStatus

logger = logging.getLogger(__name__)


class ExecutionEngine:
    def __init__(self, settings: Settings, evidence: EvidenceManager) -> None:
        self.settings = settings
        self.evidence = evidence

    async def run(self, session: RuntimeSession, testcase_source: Path) -> None:
        result_dir, session_log = self.evidence.create_archive(session, testcase_source)
        session_log.write("TEST START", f"Case: {session.testcase.testcase.id}\nTarget: {session.target}")
        self._write_metadata(session, result_dir)
        try:
            try:
                await asyncio.wait_for(session.websocket_ready.wait(), timeout=60)
            except TimeoutError as exc:
                raise RuntimeError("Browser terminal did not connect within 60 seconds") from exc

            session.status = "CONNECTING"
            session.message = f"Connecting to {session.target}:{session.port}"
            await session.publish("session_state", state=session.snapshot(include_transcript=False))
            password = session.password or os.getenv("RTR_SSH_PASSWORD")
            credentials = SSHCredentials(
                host=session.target,
                port=session.port,
                username=session.username,
                password=password,
                key_filename=session.key_filename,
            )
            ssh = SSHShellSession(credentials, self.settings.ssh_connect_timeout, session.terminal_output)
            session.ssh = ssh
            await ssh.open()
            # Secrets are no longer needed after Paramiko authentication.
            session.password = None
            password = None
            session.status = "RUNNING"
            session.message = "SSH connected"
            await session.publish("session_state", state=session.snapshot(include_transcript=False))

            for index, step in enumerate(session.testcase.steps):
                if session.abort_event.is_set():
                    raise asyncio.CancelledError("Test aborted by user")
                session.current_step_index = index
                session.current_step_id = str(step.id)
                result = {
                    "id": str(step.id),
                    "name": step.name,
                    "role": step.role.value,
                    "status": StepStatus.RUNNING.value,
                    "command": step.action.command,
                    "expected": step.expected.model_dump(),
                    "exit_code": None,
                    "stdout": "",
                    "checks": [],
                    "evidence": [],
                    "start_time": utc_now(),
                    "end_time": None,
                }
                session.step_results.append(result)
                session.message = f"Running step {index + 1}/{len(session.testcase.steps)}"
                await session.publish("step_started", state=session.snapshot(include_transcript=False))

                risks = find_command_risks(step.action.command)
                if risks:
                    result["status"] = StepStatus.MANUAL_CONFIRM_REQUIRED.value
                    confirmation = asyncio.Event()
                    session.command_confirmations[str(step.id)] = confirmation
                    session.message = "Potential dangerous command detected. Manual confirmation required."
                    await session.publish(
                        "manual_confirm_required",
                        step_id=str(step.id),
                        risks=risks,
                        state=session.snapshot(include_transcript=False),
                    )
                    await self._wait_for_confirmation_or_abort(session, confirmation)
                    session.command_confirmations.pop(str(step.id), None)
                    result["status"] = StepStatus.RUNNING.value
                    session.message = "Dangerous command manually confirmed"
                    await session.publish("step_started", state=session.snapshot(include_transcript=False))

                session_log.write(
                    f"STEP {step.id} START",
                    f"Name:\n{step.name}\n\nCommand:\n{step.action.command}",
                )
                if step.interaction is not None:
                    interaction_done = asyncio.Event()
                    session.interaction_confirmations[str(step.id)] = interaction_done
                    result["status"] = StepStatus.WAITING_FOR_OPERATOR.value
                    session.message = step.interaction.instructions
                    await session.publish(
                        "interaction_required",
                        step_id=str(step.id),
                        instructions=step.interaction.instructions,
                        state=session.snapshot(include_transcript=False),
                    )
                    command_task = asyncio.create_task(
                        ssh.run_command(step.action.command, step.interaction.timeout)
                    )
                    try:
                        await self._wait_for_confirmation_or_abort(
                            session, interaction_done, timeout=step.interaction.timeout
                        )
                        result["status"] = StepStatus.RUNNING.value
                        session.message = "操作员已完成交互，等待命令结束"
                        await session.publish("interaction_completed", state=session.snapshot(include_transcript=False))
                        raw_stdout, exit_code = await command_task
                    finally:
                        session.interaction_confirmations.pop(str(step.id), None)
                        if not command_task.done():
                            command_task.cancel()
                else:
                    raw_stdout, exit_code = await ssh.run_command(
                        step.action.command, self.settings.command_timeout
                    )
                stdout = clean_command_output(raw_stdout)
                evaluation = evaluate(step.expected, exit_code, stdout)
                result.update(
                    status=evaluation.status.value,
                    exit_code=exit_code,
                    stdout=stdout,
                    checks=evaluation.checks,
                    end_time=utc_now(),
                )
                session.message = f"Step {step.id} {evaluation.status.value}"

                policy = step.resolved_evidence()
                if policy.capture and policy.trigger == "command_complete":
                    event_id = uuid4().hex
                    render_event = asyncio.Event()
                    session.render_acks[event_id] = render_event
                    await session.publish(
                        "step_complete",
                        event_id=event_id,
                        capture_requested=True,
                        state=session.snapshot(include_transcript=False),
                    )
                    try:
                        await asyncio.wait_for(render_event.wait(), timeout=self.settings.render_ack_timeout)
                    except TimeoutError:
                        logger.warning("Terminal render acknowledgement timed out for %s", event_id)
                    finally:
                        session.render_acks.pop(event_id, None)
                    try:
                        screenshot_path = await self.evidence.capture_automatic(session, str(step.id))
                        result["evidence"].append(screenshot_path)
                        await session.publish("evidence_captured", path=screenshot_path, step_id=str(step.id))
                    except ScreenshotError as exc:
                        result["evidence_error"] = str(exc)
                        await session.publish("evidence_error", message=str(exc), step_id=str(step.id))
                else:
                    await session.publish(
                        "step_complete",
                        event_id=None,
                        capture_requested=False,
                        state=session.snapshot(include_transcript=False),
                    )

                session_log.write(
                    f"STEP {step.id} END",
                    "\n".join(
                        [
                            "Output:",
                            stdout,
                            "Exit Code:",
                            str(exit_code),
                            "Result:",
                            evaluation.status.value,
                            "Evidence:",
                            "\n".join(result["evidence"]) or "None",
                        ]
                    ),
                )
                self._write_result(session, result_dir)

            session.status = self._overall_status(session)
            session.message = f"Test finished: {session.status}"
        except asyncio.CancelledError:
            session.status = "ABORTED"
            session.message = "Test aborted"
            session_log.write("TEST ABORTED")
        except Exception as exc:
            logger.exception("Session %s failed", session.session_id)
            session.status = "ERROR"
            session.message = str(exc)
            await session.terminal_output(f"\r\n\x1b[31m[RTR ERROR] {exc}\x1b[0m\r\n")
            await session.publish("error", message=str(exc))
            session_log.write("TEST ERROR", str(exc))
        finally:
            session.password = None
            session.end_time = utc_now()
            if session.ssh is not None:
                await session.ssh.close()
            self._write_result(session, result_dir)
            self._write_metadata(session, result_dir)
            session_log.write("TEST END", f"Status: {session.status}")
            await session.publish("session_finished", state=session.snapshot(include_transcript=False))

    async def _wait_for_confirmation_or_abort(
        self, session: RuntimeSession, confirmation: asyncio.Event, timeout: float | None = None
    ) -> None:
        confirm_task = asyncio.create_task(confirmation.wait())
        abort_task = asyncio.create_task(session.abort_event.wait())
        done, pending = await asyncio.wait(
            {confirm_task, abort_task}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        if not done:
            raise TimeoutError("Timed out while awaiting operator interaction")
        if abort_task in done:
            raise asyncio.CancelledError("Test aborted while awaiting confirmation")

    @staticmethod
    def _overall_status(session: RuntimeSession) -> str:
        statuses = {step["status"] for step in session.step_results}
        if StepStatus.ERROR.value in statuses:
            return StepStatus.ERROR.value
        if StepStatus.FAIL.value in statuses:
            return StepStatus.FAIL.value
        return StepStatus.PASS.value

    @staticmethod
    def _write_result(session: RuntimeSession, result_dir: Path) -> None:
        EvidenceManager.write_json(
            result_dir / "result.json",
            {
                "case_id": session.testcase.testcase.id,
                "session_id": session.session_id,
                "status": session.status,
                "steps": session.step_results,
            },
        )

    @staticmethod
    def _write_metadata(session: RuntimeSession, result_dir: Path) -> None:
        EvidenceManager.write_json(
            result_dir / "metadata.json",
            {
                "case_id": session.testcase.testcase.id,
                "target": session.target,
                "port": session.port,
                "username": session.username,
                "start_time": session.start_time,
                "end_time": session.end_time,
                "status": session.status,
                "session_id": session.session_id,
            },
        )
