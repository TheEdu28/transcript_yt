"""Fixtures and shared helpers for the transcript_yt E2E test suite."""

from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.main import app
from app.models.group import Attempt, Group, GroupMembership, Topic
from app.models.material import DidacticMaterial
from app.models.user import User
from app.models.video import Video


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Provides a thread-safe TestClient for the FastAPI app."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provides an isolated SQLAlchemy session per test."""
    session_gen = get_session()
    session = next(session_gen)
    try:
        yield session
    finally:
        session.close()


def auth_header(token: str) -> dict[str, str]:
    """Builds Authorization header from Bearer JWT token."""
    return {"Authorization": f"Bearer {token}"}


def register_and_login(
    client: TestClient, email: str, name: str, password: str = "password123"
) -> tuple[int, str, dict[str, str]]:
    """Registers a user, logs in, and returns (user_id, token, auth_headers)."""
    reg_res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "nombre": name, "password": password},
    )
    assert reg_res.status_code == 201, f"Registration failed: {reg_res.text}"
    user_id = reg_res.json()["id"]

    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["access_token"]
    return user_id, token, auth_header(token)


def create_test_video(
    session: Session,
    owner_id: int,
    title: str = "Video de Prueba E2E",
    duration_seconds: int = 180,
    created_at: datetime | None = None,
) -> Video:
    """Creates a Video entity in the database."""
    suffix = uuid.uuid4().hex[:8]
    video = Video(
        youtube_id=f"yt_{suffix}",
        source_url=f"https://www.youtube.com/watch?v={suffix}",
        title=title,
        language="es",
        duration_seconds=duration_seconds,
        transcript_path="",
        status="ready",
        owner_id=owner_id,
        created_at=created_at or datetime.now(timezone.utc),
    )
    session.add(video)
    session.commit()
    session.refresh(video)
    return video


def create_test_quiz(
    session: Session,
    video_id: int,
    owner_id: int,
    mc_questions: list[dict[str, Any]] | None = None,
    open_questions: list[dict[str, Any]] | None = None,
) -> DidacticMaterial:
    """Creates a DidacticMaterial of type 'quiz' in the database."""
    if mc_questions is None:
        mc_questions = [
            {
                "question": "¿Cuál fue el principal factor impulsor de la Revolución Industrial?",
                "options": [
                    "La invención del teléfono",
                    "La máquina de vapor y el carbón",
                    "La energía nuclear",
                    "El motor de combustión interna",
                ],
                "correct_option": 1,
                "explanation": "La máquina de vapor perfeccionada por Watt y el carbón fueron los factores clave.",
                "evidence_timestamp": "00:00:10",
                "bloom_level": "remember",
            },
            {
                "question": "¿En qué año patentó James Watt su condensador separado?",
                "options": ["1750", "1769", "1804", "1825"],
                "correct_option": 1,
                "explanation": "La patente del condensador separado se registró en 1769.",
                "evidence_timestamp": "00:00:18",
                "bloom_level": "understand",
            },
        ]
    if open_questions is None:
        open_questions = [
            {
                "question": "Explica brevemente el impacto demográfico del éxodo rural en las ciudades industriales.",
                "expected_points": [
                    "Crecimiento acelerado e improvisado de las urbes",
                    "Hacinamiento y condiciones de salubridad precarias",
                    "Aumento de mano de obra para las fábricas textiles",
                ],
                "evidence_timestamp": "00:00:33",
                "bloom_level": "analyze",
            }
        ]

    quiz_data = {
        "multiple_choice": mc_questions,
        "open_questions": open_questions,
        "evidence_sufficient": True,
    }
    material = DidacticMaterial(
        video_id=video_id,
        material_type="quiz",
        content_json=json.dumps(quiz_data, ensure_ascii=False),
        owner_id=owner_id,
    )
    session.add(material)
    session.commit()
    session.refresh(material)
    return material


def create_test_summary(
    session: Session,
    video_id: int,
    owner_id: int,
    synopsis: str = "Resumen oficial detallado de la Revolución Industrial.",
    didactic_blocks: list[dict[str, Any]] | None = None,
) -> DidacticMaterial:
    """Creates a DidacticMaterial of type 'summary' in the database conforming to SummaryResponse."""
    if didactic_blocks is None:
        didactic_blocks = [
            {
                "title": "Orígenes de la Revolución Industrial",
                "explanation": "Transformación económica y tecnológica a partir del carbón y vapor.",
                "timestamps": ["00:00:04"],
            }
        ]
    summary_data = {
        "synopsis": synopsis,
        "glossary": [{"term": "Condensador", "definition": "Dispositivo para enfriar vapor.", "timestamp": "00:00:18"}],
        "didactic_blocks": didactic_blocks,
        "evidence_sufficient": True,
    }
    material = DidacticMaterial(
        video_id=video_id,
        material_type="summary",
        content_json=json.dumps(summary_data, ensure_ascii=False),
        owner_id=owner_id,
    )
    session.add(material)
    session.commit()
    session.refresh(material)
    return material


def create_test_group_and_topic(
    client: TestClient,
    teacher_token: str,
    video_id: int,
    quiz_id: int | None = None,
    group_name: str = "Grupo de Historia",
    topic_title: str = "Tema: Revolución Industrial",
) -> tuple[int, str, int]:
    """Helper to create group and publish a topic, returning (group_id, group_code, topic_id)."""
    headers = auth_header(teacher_token)
    grp_res = client.post("/api/v1/groups", json={"name": group_name}, headers=headers)
    assert grp_res.status_code == 201, grp_res.text
    group_data = grp_res.json()
    group_id = group_data["id"]
    group_code = group_data["code"]

    topic_payload: dict[str, Any] = {
        "title": topic_title,
        "video_id": video_id,
        "is_active": True,
    }
    if quiz_id is not None:
        topic_payload["material_id"] = quiz_id

    top_res = client.post(f"/api/v1/groups/{group_id}/topics", json=topic_payload, headers=headers)
    assert top_res.status_code == 201, top_res.text
    topic_id = top_res.json()["id"]

    return group_id, group_code, topic_id


@pytest.fixture
def sample_segments() -> list[dict[str, Any]]:
    """Sample Whisper transcript segments for testing timestamp calibration."""
    return [
        {"start": 0.0, "end": 3.5, "text": "Bienvenidos a la clase sobre la revolución industrial."},
        {"start": 4.0, "end": 9.8, "text": "Hoy examinaremos los factores energéticos iniciales."},
        {"start": 10.5, "end": 17.2, "text": "El desarrollo de la máquina de vapor transformó completamente la producción."},
        {"start": 18.0, "end": 24.5, "text": "James Watt perfeccionó el condensador separado en el año 1769."},
        {"start": 25.0, "end": 32.0, "text": "Esto permitió un ahorro térmico revolucionario en las minas y telares."},
        {"start": 33.5, "end": 41.0, "text": "A continuación analizaremos las consecuencias demográficas del éxodo rural."},
    ]
