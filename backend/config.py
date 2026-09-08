from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_root: Path
    testcase_dir: Path
    results_dir: Path
    frontend_dir: Path
    public_base_url: str
    ssh_connect_timeout: float
    command_timeout: float
    render_ack_timeout: float

    @classmethod
    def load(cls) -> "Settings":
        project_root = Path(__file__).resolve().parents[1]
        return cls(
            project_root=project_root,
            testcase_dir=Path(os.getenv("RTR_TESTCASE_DIR", project_root / "testcases")).resolve(),
            results_dir=Path(os.getenv("RTR_RESULTS_DIR", project_root / "results")).resolve(),
            frontend_dir=(project_root / "frontend").resolve(),
            public_base_url=os.getenv("RTR_PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
            ssh_connect_timeout=float(os.getenv("RTR_SSH_CONNECT_TIMEOUT", "15")),
            command_timeout=float(os.getenv("RTR_COMMAND_TIMEOUT", "300")),
            render_ack_timeout=float(os.getenv("RTR_RENDER_ACK_TIMEOUT", "20")),
        )


settings = Settings.load()
settings.testcase_dir.mkdir(parents=True, exist_ok=True)
settings.results_dir.mkdir(parents=True, exist_ok=True)

