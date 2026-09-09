"""Comprobaciones de disponibilidad de la interfaz visual local."""

from fastapi.testclient import TestClient

from app.main import app


def test_root_redirects_to_the_visual_interface() -> None:
    """The local prototype opens its visual workflow from the root URL."""
    with TestClient(app) as client:
        response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/ui/"


def test_visual_interface_serves_the_complete_manual_testing_workflow() -> None:
    """The HTML page exposes controls for ingestion, Bloom and feedback testing."""
    with TestClient(app) as client:
        response = client.get("/ui/")
    assert response.status_code == 200
    assert "Aula<span>Video</span>" in response.text
    assert "Revisar respuestas" in response.text
    assert "/ui/app.js" in response.text
