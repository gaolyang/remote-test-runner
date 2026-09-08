from __future__ import annotations

from datetime import datetime
from pathlib import Path


class SessionLogger:
    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, title: str, body: str = "") -> None:
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        block = f"[{timestamp}]\n{title}\n"
        if body:
            block += f"{body.rstrip()}\n"
        block += "\n"
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(block)

