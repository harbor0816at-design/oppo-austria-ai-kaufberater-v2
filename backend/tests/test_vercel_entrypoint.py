from fastapi.testclient import TestClient

from app.main import app


def test_healthz_through_real_fastapi_entrypoint():
    with TestClient(app) as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_root_through_real_fastapi_entrypoint():
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        body = response.json()
    assert body["status"] == "ok"
    assert body["ai_provider"] == "deepseek"


def test_public_hero_endpoint_always_returns_a_json_array():
    with TestClient(app) as client:
        response = client.get("/api/ui/hero-slides")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert isinstance(response.json(), list)
    assert response.content
    assert len(response.json()) >= 3
