from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from backend.testcase.models import TestCase


class TestCaseLoadError(ValueError):
    pass


def load_testcase(path: Path) -> TestCase:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise TestCaseLoadError(f"Unable to read YAML {path.name}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TestCaseLoadError(f"YAML {path.name} must contain an object")
    try:
        return TestCase.model_validate(raw)
    except ValidationError as exc:
        raise TestCaseLoadError(f"Invalid testcase {path.name}: {exc}") from exc


def safe_case_path(testcase_dir: Path, filename: str) -> Path:
    if Path(filename).name != filename or not filename.lower().endswith((".yaml", ".yml")):
        raise TestCaseLoadError("Invalid testcase filename")
    path = (testcase_dir / filename).resolve()
    if path.parent != testcase_dir.resolve() or not path.is_file():
        raise TestCaseLoadError(f"Testcase not found: {filename}")
    return path

