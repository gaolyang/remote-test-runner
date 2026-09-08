from __future__ import annotations

import re


_PREFIX = r"(?:^|[;&|]\s*)(?:sudo\s+)?"
RISK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("rm -rf", re.compile(_PREFIX + r"rm\s+(?:-[A-Za-z]*r[A-Za-z]*f\b|-[A-Za-z]*f[A-Za-z]*r\b)", re.I)),
    ("mkfs", re.compile(_PREFIX + r"mkfs(?:\.[\w-]+)?\b", re.I)),
    ("dd", re.compile(_PREFIX + r"dd\s+[^\n;&|]*\bof=/dev/", re.I)),
    ("shutdown", re.compile(_PREFIX + r"shutdown\b", re.I)),
    ("reboot", re.compile(_PREFIX + r"reboot\b", re.I)),
    ("poweroff", re.compile(_PREFIX + r"poweroff\b", re.I)),
    ("fdisk", re.compile(_PREFIX + r"fdisk\b", re.I)),
    ("parted", re.compile(_PREFIX + r"parted\b", re.I)),
)


def find_command_risks(command: str) -> list[str]:
    return [name for name, pattern in RISK_PATTERNS if pattern.search(command)]
