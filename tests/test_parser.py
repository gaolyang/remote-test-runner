from pathlib import Path

from backend.testcase.parser import load_testcase


def test_demo_case_loads() -> None:
    path = Path(__file__).resolve().parents[1] / "testcases" / "TC_DEMO_001.yaml"
    testcase = load_testcase(path)
    assert testcase.testcase.id == "TC_DEMO_001"
    assert len(testcase.steps) == 4

