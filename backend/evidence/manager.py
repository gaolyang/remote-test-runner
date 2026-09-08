from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.evidence.logger import SessionLogger
from backend.evidence.screenshot import ScreenshotService
from backend.session import RuntimeSession


class EvidenceManager:
    def __init__(self, results_root: Path, screenshot_service: ScreenshotService) -> None:
        self.results_root = results_root
        self.screenshot_service = screenshot_service
        self.manual_counts: dict[tuple[str, str], int] = {}

    def create_archive(self, session: RuntimeSession, testcase_source: Path) -> tuple[Path, SessionLogger]:
        date_dir = self.results_root / datetime.now().astimezone().date().isoformat()
        result_dir = date_dir / session.testcase.testcase.id
        if result_dir.exists():
            suffix = datetime.now().astimezone().strftime("%H%M%S") + "_" + session.session_id[:6]
            result_dir = date_dir / f"{session.testcase.testcase.id}_{suffix}"
        (result_dir / "evidence").mkdir(parents=True, exist_ok=False)
        shutil.copy2(testcase_source, result_dir / "testcase.yaml")
        session.result_dir = str(result_dir)
        return result_dir, SessionLogger(result_dir / "session.log")

    async def capture_automatic(self, session: RuntimeSession, step_id: str) -> str:
        filename = f"step{self._format_step(step_id)}_command_complete.png"
        path = Path(session.result_dir or "") / "evidence" / filename
        await self.screenshot_service.capture_step(session.session_id, path)
        return str(path)

    async def capture_manual(self, session: RuntimeSession) -> str:
        step_id = session.current_step_id or "00"
        key = (session.session_id, step_id)
        count = self.manual_counts.get(key, 0) + 1
        self.manual_counts[key] = count
        filename = f"step{self._format_step(step_id)}_manual_{count:02d}.png"
        path = Path(session.result_dir or "") / "evidence" / filename
        await self.screenshot_service.capture_step(session.session_id, path)
        return str(path)

    @staticmethod
    def _format_step(step_id: str) -> str:
        return f"{int(step_id):02d}" if step_id.isdigit() else step_id

    @staticmethod
    def write_json(path: Path, data: dict[str, Any]) -> None:
        temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
