from dataclasses import replace
from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.api import cases as cases_api
from backend.config import settings
from backend.main import app


client = TestClient(app)


def test_health_and_home() -> None:
    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/")
    assert response.status_code == 200
    assert "Remote Test Runner" in response.text
    assert 'id="overwrite-cases"' in response.text


def test_case_api_lists_demo() -> None:
    response = client.get("/api/cases")
    assert response.status_code == 200
    items = response.json()
    assert any(item.get("id") == "TC_DEMO_001" and item.get("valid") for item in items)


def test_case_api_rejects_missing_case() -> None:
    response = client.get("/api/cases/not-found.yaml")
    assert response.status_code == 400


def test_case_api_imports_excel_as_yaml(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cases_api, "settings", replace(settings, testcase_dir=tmp_path))
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["测试编号", "测试名称", "测试执行步骤"])
    sheet.append(["TC_UPLOAD_001", "上传检查", "whoami\nhostname"])
    stream = BytesIO()
    workbook.save(stream)

    response = client.post(
        "/api/cases/import",
        files={"file": ("cases.xlsx", stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 201
    assert response.json()["cases"][0]["step_count"] == 2
    generated = (tmp_path / "TC_UPLOAD_001.yaml").read_text(encoding="utf-8")
    assert "name: 上传检查" in generated
    assert "command: hostname" in generated


def test_case_api_can_update_existing_yaml_with_backup(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cases_api, "settings", replace(settings, testcase_dir=tmp_path))
    existing = tmp_path / "TC_UPLOAD_001.yaml"
    existing.write_text("old yaml", encoding="utf-8")
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["测试编号", "测试名称", "测试执行步骤"])
    sheet.append(["TC_UPLOAD_001", "最新上传用例", "uname -a"])
    stream = BytesIO()
    workbook.save(stream)
    upload = {
        "file": (
            "latest.xlsx",
            stream.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }

    conflict = client.post("/api/cases/import", files=upload, data={"overwrite": "false"})
    assert conflict.status_code == 409
    assert "TC_UPLOAD_001.yaml" in conflict.json()["detail"]
    assert existing.read_text(encoding="utf-8") == "old yaml"

    updated = client.post("/api/cases/import", files=upload, data={"overwrite": "true"})
    assert updated.status_code == 201
    assert updated.json()["updated"] == 1
    assert updated.json()["backups"] == 1
    assert "name: 最新上传用例" in existing.read_text(encoding="utf-8")
    backups = list((tmp_path / ".import-backups").glob("TC_UPLOAD_001_*.yaml"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "old yaml"
