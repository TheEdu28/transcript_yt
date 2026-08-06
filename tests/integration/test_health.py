"""Comprobación mínima de integración FastAPI."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_check() -> None:
    """Ensure the API can be instantiated without external services."""
    client = TestClient(app)
    assert client.get("/api/v1/health").json() == {"status": "ok"}

