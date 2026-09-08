from __future__ import annotations

import asyncio
import logging
import re
import socket
from collections.abc import Awaitable, Callable

import paramiko

from backend.execution.markers import FinishMarker
from backend.ssh.client import SSHCredentials, connect

logger = logging.getLogger(__name__)
TerminalCallback = Callable[[str], Awaitable[None]]


class _CommandCollector:
    def __init__(self, marker: FinishMarker, callback: TerminalCallback) -> None:
        self.marker = marker
        self.callback = callback
        self.pending = ""
        self.stdout_parts: list[str] = []
        self.started = False
        self.done: asyncio.Future[tuple[str, int]] = asyncio.get_running_loop().create_future()

    async def feed(self, data: str) -> None:
        self.pending += data
        if not self.started:
            start_match = self.marker.start_pattern.search(self.pending)
            if start_match is None:
                return
            # Everything before START is shell prompt/input echo rather than the
            # command's stdout. The UI already receives a clean synthetic command line.
            self.pending = self.pending[start_match.end() :]
            self.started = True

        match = self.marker.result_pattern.search(self.pending)
        if match:
            before = self.pending[: match.start()]
            if before:
                await self._emit(before)
            exit_code = int(match.group(1))
            self.pending = self.pending[match.end() :]
            if not self.done.done():
                self.done.set_result(("".join(self.stdout_parts), exit_code))
            return

        reserve = len(self.marker.token) + 32
        if len(self.pending) > reserve:
            safe = self.pending[:-reserve]
            self.pending = self.pending[-reserve:]
            await self._emit(safe)

    async def _emit(self, data: str) -> None:
        self.stdout_parts.append(data)
        await self.callback(data)


class SSHShellSession:
    def __init__(self, credentials: SSHCredentials, timeout: float, on_terminal: TerminalCallback) -> None:
        self.credentials = credentials
        self.timeout = timeout
        self.on_terminal = on_terminal
        self.client: paramiko.SSHClient | None = None
        self.channel: paramiko.Channel | None = None
        self.reader_task: asyncio.Task[None] | None = None
        self.collector: _CommandCollector | None = None
        self.command_lock = asyncio.Lock()
        self.closed = False
        self._data_counter = 0
        self._first_data = asyncio.Event()

    async def open(self) -> None:
        self.client, self.channel = await asyncio.to_thread(connect, self.credentials, self.timeout)
        self.reader_task = asyncio.create_task(self._reader_loop(), name="ssh-reader")
        await self._wait_for_shell_quiet()

    async def _reader_loop(self) -> None:
        assert self.channel is not None
        while not self.closed:
            try:
                data = await asyncio.to_thread(self.channel.recv, 65535)
            except (socket.timeout, TimeoutError):
                continue
            except Exception as exc:
                if not self.closed:
                    logger.exception("SSH receive failed")
                    await self.on_terminal(f"\r\n[SSH receive error: {exc}]\r\n")
                break
            if not data:
                break
            self._data_counter += 1
            self._first_data.set()
            text = data.decode("utf-8", errors="replace")
            collector = self.collector
            if collector is not None and not collector.done.done():
                await collector.feed(text)
            else:
                await self.on_terminal(text)

    async def _wait_for_shell_quiet(self) -> None:
        """Let the login banner/prompt reach the terminal before Step 1 starts."""
        try:
            await asyncio.wait_for(self._first_data.wait(), timeout=2.0)
        except TimeoutError:
            return
        for _ in range(20):
            observed = self._data_counter
            await asyncio.sleep(0.1)
            if observed == self._data_counter:
                return

    async def send_input(self, data: str) -> None:
        if self.channel is None or self.closed:
            raise RuntimeError("SSH channel is not connected")
        await asyncio.to_thread(self.channel.send, data)

    async def resize(self, columns: int, rows: int) -> None:
        if self.channel is not None and not self.closed:
            await asyncio.to_thread(self.channel.resize_pty, width=columns, height=rows)

    async def run_command(self, command: str, timeout: float) -> tuple[str, int]:
        async with self.command_lock:
            marker = FinishMarker.create()
            collector = _CommandCollector(marker, self.on_terminal)
            self.collector = collector
            # Keep the wrapper on one shell line so the echoed transport line can
            # be removed reliably while command output still streams live.
            single_line = command.replace("\r", "").replace("\n", "; ")
            wrapped = marker.wrap(single_line)
            await self.on_terminal(f"\r\n\x1b[36m$ {command}\x1b[0m\r\n")
            await self.send_input(wrapped)
            try:
                return await asyncio.wait_for(collector.done, timeout=timeout)
            finally:
                self.collector = None
                if collector.pending:
                    # Usually this is the prompt arriving in the same packet after
                    # the marker. It belongs on the terminal, not in business stdout.
                    await self.on_terminal(collector.pending)

    async def close(self) -> None:
        self.closed = True
        if self.channel is not None:
            await asyncio.to_thread(self.channel.close)
        if self.client is not None:
            await asyncio.to_thread(self.client.close)
        if self.reader_task is not None:
            try:
                await asyncio.wait_for(self.reader_task, timeout=2)
            except (TimeoutError, asyncio.CancelledError):
                self.reader_task.cancel()
