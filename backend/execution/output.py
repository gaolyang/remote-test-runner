from __future__ import annotations

import re


_CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1a\x1c-\x1f\x7f]")


def clean_command_output(output: str) -> str:
    """Convert PTY command output into readable, rule-engine-safe text."""
    output = _OSC.sub("", output)
    output = _CSI.sub("", output)
    output = _CONTROL.sub("", output)
    output = output.replace("\r\n", "\n").replace("\r", "\n")
    return output.strip("\n")
