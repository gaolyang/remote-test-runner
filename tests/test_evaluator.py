from backend.result.evaluator import evaluate
from backend.testcase.models import Expected, StepStatus


def test_combined_rules_pass() -> None:
    result = evaluate(Expected(exit_code=0, stdout_contains=["FusionOS"]), 0, "NAME=FusionOS\n")
    assert result.status == StepStatus.PASS
    assert all(check["passed"] for check in result.checks)


def test_nonzero_exit_can_be_expected() -> None:
    result = evaluate(Expected(exit_code=1, stdout_empty=True), 1, "\r\n")
    assert result.status == StepStatus.PASS


def test_contains_failure() -> None:
    result = evaluate(Expected(stdout_contains=["FusionOS"]), 0, "Ubuntu")
    assert result.status == StepStatus.FAIL

