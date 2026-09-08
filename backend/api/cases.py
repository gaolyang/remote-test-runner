from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.testcase.parser import TestCaseLoadError, load_testcase, safe_case_path

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.get("")
async def list_cases() -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for path in sorted((*settings.testcase_dir.glob("*.yaml"), *settings.testcase_dir.glob("*.yml"))):
        try:
            testcase = load_testcase(path)
        except TestCaseLoadError as exc:
            cases.append({"filename": path.name, "valid": False, "error": str(exc)})
            continue
        cases.append(
            {
                "filename": path.name,
                "valid": True,
                "id": testcase.testcase.id,
                "name": testcase.testcase.name,
                "description": testcase.testcase.description,
                "step_count": len(testcase.steps),
            }
        )
    return cases


@router.get("/{filename}")
async def get_case(filename: str) -> dict[str, object]:
    try:
        path = safe_case_path(settings.testcase_dir, filename)
        testcase = load_testcase(path)
    except TestCaseLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return testcase.model_dump(mode="json")
