from __future__ import annotations

import re
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import yaml
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.config import settings
from backend.testcase.parser import TestCaseLoadError, load_testcase, safe_case_path
from backend.testcase.excel_import import ExcelImportError, parse_testcase_upload

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.post("/import", status_code=201)
async def import_cases(
    file: UploadFile = File(...),
    overwrite: bool = Form(False),
) -> dict[str, object]:
    filename = file.filename or "upload.xlsx"
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件不能超过 10 MB")
    try:
        testcases = parse_testcase_upload(filename, content)
    except ExcelImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    outputs: list[tuple[object, Path, str]] = []
    conflicts: list[str] = []
    for testcase in testcases:
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", testcase.testcase.id)
        path = settings.testcase_dir / f"{safe_name}.yaml"
        if path.exists():
            conflicts.append(path.name)
        yaml_text = yaml.safe_dump(
            testcase.model_dump(mode="json", exclude_none=True), allow_unicode=True, sort_keys=False
        )
        outputs.append((testcase, path, yaml_text))
    if conflicts and not overwrite:
        names = "、".join(conflicts)
        raise HTTPException(
            status_code=409,
            detail=f"以下用例编号已存在：{names}。勾选“同编号时更新”后可重新导入。",
        )

    backup_dir = settings.testcase_dir / ".import-backups"
    backup_count = 0
    if conflicts:
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        for _, path, _ in outputs:
            if path.exists():
                backup_path = backup_dir / f"{path.stem}_{timestamp}.yaml"
                shutil.copy2(path, backup_path)
                backup_count += 1

    for _, path, yaml_text in outputs:
        temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary_path.write_text(yaml_text, encoding="utf-8")
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)
    return {
        "imported": len(outputs),
        "created": len(outputs) - len(conflicts),
        "updated": len(conflicts),
        "backups": backup_count,
        "cases": [
            {"id": testcase.testcase.id, "name": testcase.testcase.name, "filename": path.name, "step_count": len(testcase.steps)}
            for testcase, path, _ in outputs
        ],
    }


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
