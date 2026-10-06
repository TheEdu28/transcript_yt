"""Comprobaciones de disponibilidad de la interfaz visual local."""

from fastapi.testclient import TestClient

from app.main import app


def test_root_redirects_to_the_visual_interface() -> None:
    """The local prototype opens its visual workflow from the root URL."""
    with TestClient(app) as client:
        response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/ui/"


def test_visual_interface_serves_independent_workflow_views() -> None:
    """The static UI exposes independent URLs instead of one multi-panel page."""
    with TestClient(app) as client:
        home = client.get("/ui/")
        video = client.get("/ui/video/")
        summary = client.get("/ui/resumen/?video=42")
        quiz = client.get("/ui/quiz/?video=42")
        material = client.get("/ui/material/?video=42&material=17")
    assert home.status_code == 200
    assert "Aula<span>Video</span>" in home.text
    assert "/ui/video/" in home.text
    assert video.status_code == summary.status_code == quiz.status_code == material.status_code == 200
    assert "/ui/video/page.js" in video.text
    assert "/ui/resumen/page.js" in summary.text
    assert "/ui/quiz/page.js" in quiz.text
    assert "/ui/material/page.js" in material.text
