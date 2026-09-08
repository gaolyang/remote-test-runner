from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_health_and_home() -> None:
    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/")
    assert response.status_code == 200
    assert "Remote Test Runner" in response.text


def test_case_api_lists_demo() -> None:
    response = client.get("/api/cases")
    assert response.status_code == 200
    items = response.json()
    assert any(item.get("id") == "TC_DEMO_001" and item.get("valid") for item in items)


def test_case_api_rejects_missing_case() -> None:
    response = client.get("/api/cases/not-found.yaml")
    assert response.status_code == 400
