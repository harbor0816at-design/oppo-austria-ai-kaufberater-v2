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


def test_readyz_reports_missing_default_production_dependencies():
    with TestClient(app) as client:
        response = client.get("/readyz")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["deepseek_configured"] is False
        assert body["checks"]["source_b_configured"] is False
