from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "voicetranslate-api"}


def test_versioned_health_endpoints() -> None:
    for path in ("/api/v1/health/live", "/api/v1/health/ready"):
        response = client.get(path)

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
