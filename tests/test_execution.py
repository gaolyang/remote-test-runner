import asyncio

from backend.execution.markers import FinishMarker
from backend.execution.output import clean_command_output
from backend.execution.risk import find_command_risks
from backend.ssh.session import _CommandCollector


def test_marker_extracts_exit_code_and_removes_marker() -> None:
    marker = FinishMarker("__RTR_FINISHED_test__")
    parsed = marker.extract("hello\r\n__RTR_FINISHED_test__:7\r\n")
    assert parsed is not None
    stdout, exit_code = parsed
    assert exit_code == 7
    assert "__RTR_FINISHED" not in stdout


def test_risky_commands_are_detected() -> None:
    assert "rm -rf" in find_command_risks("rm -rf /tmp/demo")
    assert "reboot" in find_command_risks("sudo reboot")


def test_normal_command_is_not_risky() -> None:
    assert find_command_risks("uname -a") == []


def test_command_collector_handles_split_marker_and_hides_wrapper() -> None:
    async def scenario() -> tuple[str, int, str]:
        emitted: list[str] = []

        async def output(data: str) -> None:
            emitted.append(data)

        marker = FinishMarker("__RTR_FINISHED_split__")
        collector = _CommandCollector(marker, output)
        await collector.feed(
            "shell prompt and echoed wrapper\r\n__RTR_STARTED_split__\r\n"
            "Linux demo\r\n\r\n__RTR_FIN"
        )
        await collector.feed("ISHED_split__:0\r\n")
        stdout, exit_code = await collector.done
        return stdout, exit_code, "".join(emitted)

    stdout, exit_code, displayed = asyncio.run(scenario())
    assert exit_code == 0
    assert stdout == "Linux demo\r\n"
    assert displayed == stdout
    assert "printf" not in displayed


def test_clean_command_output_removes_terminal_sequences() -> None:
    raw = "\x1b]0;gly@kail\x07\x1b[31mgly\x1b[0m\r\n"
    assert clean_command_output(raw) == "gly"
