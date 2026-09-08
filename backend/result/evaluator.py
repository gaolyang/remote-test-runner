from __future__ import annotations

from dataclasses import dataclass

from backend.testcase.models import Expected, StepStatus


@dataclass(frozen=True)
class Evaluation:
    status: StepStatus
    checks: list[dict[str, object]]


def evaluate(expected: Expected, exit_code: int, stdout: str) -> Evaluation:
    checks: list[dict[str, object]] = []
    if expected.exit_code is not None:
        checks.append({
            "rule": "exit_code",
            "expected": expected.exit_code,
            "actual": exit_code,
            "passed": exit_code == expected.exit_code,
        })
    for needle in expected.stdout_contains:
        checks.append({
            "rule": "stdout_contains",
            "expected": needle,
            "passed": needle in stdout,
        })
    if expected.stdout_empty is not None:
        is_empty = not stdout.strip()
        checks.append({
            "rule": "stdout_empty",
            "expected": expected.stdout_empty,
            "actual": is_empty,
            "passed": is_empty == expected.stdout_empty,
        })
    passed = all(bool(check["passed"]) for check in checks)
    return Evaluation(status=StepStatus.PASS if passed else StepStatus.FAIL, checks=checks)

