from __future__ import annotations

import re
import secrets
from dataclasses import dataclass


@dataclass(frozen=True)
class FinishMarker:
    token: str

    @classmethod
    def create(cls) -> "FinishMarker":
        return cls(token=f"__RTR_FINISHED_{secrets.token_hex(8)}__")

    @property
    def marker_id(self) -> str:
        return self.token.removeprefix("__RTR_FINISHED_").removesuffix("__")

    @property
    def start_token(self) -> str:
        return f"__RTR_STARTED_{self.marker_id}__"

    @property
    def start_pattern(self) -> re.Pattern[str]:
        return re.compile(rf"(?:\r?\n)?{re.escape(self.start_token)}\r?\n")

    @property
    def result_pattern(self) -> re.Pattern[str]:
        return re.compile(rf"(?:\r?\n)?{re.escape(self.token)}:(-?\d+)\r?\n")

    def wrap(self, command: str) -> str:
        return (
            f"__rtr_token='{self.marker_id}'; "
            "printf '\\n__RTR_STARTED_%s__\\n' \"$__rtr_token\"; "
            f"{{ {command}; }}; __RTR_RET=$?; "
            "printf '\\n__RTR_FINISHED_%s__:%s\\n' \"$__rtr_token\" \"$__RTR_RET\"\n"
        )

    def extract(self, text: str) -> tuple[str, int] | None:
        match = self.result_pattern.search(text)
        if not match:
            return None
        cleaned = self.result_pattern.sub("\n", text)
        return cleaned, int(match.group(1))
