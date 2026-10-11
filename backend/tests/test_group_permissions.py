"""Pruebas de permisos, grupos con código, reintentos con penalización y visualización de intentos."""

import json
import uuid
import pytest
from fastapi.testclient import TestClient

from app.db.database import get_session
from app.main import app
from app.models.material import DidacticMaterial
from app.models.video import Video


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def register_and_login(client: TestClient, email: str, name: str, password: str = "password123") -> tuple[int, str]:
    reg_res = client.post("/api/v1/auth/register", json={"email": email, "nombre": name, "password": password})
    assert reg_res.status_code == 201, reg_res.text
    user_id = reg_res.json()["id"]

    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_res.status_code == 200, login_res.text
    token = login_res.json()["access_token"]
    return user_id, token


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_dummy_video_and_quiz(owner_id: int) -> tuple[int, int]:
    """Crea un Video y un DidacticMaterial tipo 'quiz' en SQLite asociados al usuario."""
    session_gen = get_session()
    session = next(session_gen)
    try:
        suffix = uuid.uuid4().hex[:6]
        video = Video(
            youtube_id=f"yt_{suffix}",
            source_url="https://www.youtube.com/watch?v=dummy",
            title="Video de prueba",
            language="es",
            duration_seconds=120,
            transcript_path="",
            owner_id=owner_id,
        )
        session.add(video)
        session.flush()

        quiz_data = {
            "multiple_choice": [
                {
                    "question": "¿Cuál es la capital de Francia?",
                    "options": ["Madrid", "Berlín", "París", "Roma"],
                    "correct_option": 2,
                    "explanation": "París es la capital.",
                    "evidence_timestamp": "00:00:10",
                    "bloom_level": "remember",
                },
                {
                    "question": "¿2 + 2?",
                    "options": ["3", "4", "5", "6"],
                    "correct_option": 1,
                    "explanation": "2 + 2 = 4.",
                    "evidence_timestamp": "00:00:20",
                    "bloom_level": "remember",
                },
            ],
            "open_questions": [],
            "evidence_sufficient": True,
        }
        material = DidacticMaterial(
            video_id=video.id,
            material_type="quiz",
            content_json=json.dumps(quiz_data),
            owner_id=owner_id,
        )
        session.add(material)
        session.commit()
        return video.id, material.id
    finally:
        session.close()


def test_group_creation_join_code_and_mine(client: TestClient) -> None:
    suffix = uuid.uuid4().hex[:6]
    alice_id, alice_token = register_and_login(client, f"alice_{suffix}@test.com", "Alice")
    bob_id, bob_token = register_and_login(client, f"bob_{suffix}@test.com", "Bob")

    # 1. Alice crea un grupo
    res = client.post("/api/v1/groups", json={"name": "Ciencias 101"}, headers=auth_header(alice_token))
    assert res.status_code == 201
    group_data = res.json()
    assert group_data["admin_id"] == alice_id
    assert len(group_data["code"]) == 6
    group_code = group_data["code"]
    group_id = group_data["id"]

    # 2. Bob se une con el código
    join_res = client.post("/api/v1/groups/join", json={"code": group_code}, headers=auth_header(bob_token))
    assert join_res.status_code == 200
    assert join_res.json()["id"] == group_id

    # 3. Verificar /api/v1/groups/mine para Alice y Bob
    mine_alice = client.get("/api/v1/groups/mine", headers=auth_header(alice_token)).json()
    assert len(mine_alice["admin_groups"]) == 1
    assert mine_alice["admin_groups"][0]["id"] == group_id
    assert len(mine_alice["member_groups"]) == 0

    mine_bob = client.get("/api/v1/groups/mine", headers=auth_header(bob_token)).json()
    assert len(mine_bob["admin_groups"]) == 0
    assert len(mine_bob["member_groups"]) == 1
    assert mine_bob["member_groups"][0]["id"] == group_id


def test_topic_creation_and_retry_penalty_flow(client: TestClient) -> None:
    suffix = uuid.uuid4().hex[:6]
    admin_id, admin_token = register_and_login(client, f"prof_{suffix}@test.com", "Profesor")
    student_id, student_token = register_and_login(client, f"stud_{suffix}@test.com", "Estudiante")

    # Crear grupo
    res_grp = client.post("/api/v1/groups", json={"name": "Historia"}, headers=auth_header(admin_token))
    group_id = res_grp.json()["id"]
    group_code = res_grp.json()["code"]

    # Alumno se une
    client.post("/api/v1/groups/join", json={"code": group_code}, headers=auth_header(student_token))

    # Crear video y quiz de propiedad del profesor
    video_id, material_id = create_dummy_video_and_quiz(admin_id)

    # El estudiante no puede crear topic (solo admin)
    topic_fail = client.post(
        f"/api/v1/groups/{group_id}/topics",
        json={"video_id": video_id, "material_id": material_id, "title": "Tema 1"},
        headers=auth_header(student_token),
    )
    assert topic_fail.status_code == 403

    # El profesor crea el topic exitosamente
    topic_ok = client.post(
        f"/api/v1/groups/{group_id}/topics",
        json={"video_id": video_id, "material_id": material_id, "title": "Tema 1 - Historia"},
        headers=auth_header(admin_token),
    )
    assert topic_ok.status_code == 201
    topic_id = topic_ok.json()["id"]

    # Alumno ve topics
    topics_list = client.get(f"/api/v1/groups/{group_id}/topics", headers=auth_header(student_token))
    assert topics_list.status_code == 200
    assert len(topics_list.json()) == 1

    # Intento 1 del alumno: 100% de aciertos
    attempt1_res = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 2}, {"question_index": 1, "selected_option": 1}]},
        headers=auth_header(student_token),
    )
    assert attempt1_res.status_code == 201
    att1 = attempt1_res.json()
    assert att1["attempt_number"] == 1
    assert att1["raw_score"] == 100.0
    assert att1["final_score"] == 100.0  # Sin penalización

    # Intento 2 del alumno: 100% de aciertos pero segundo intento -> penalización de 10 puntos
    attempt2_res = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 2}, {"question_index": 1, "selected_option": 1}]},
        headers=auth_header(student_token),
    )
    assert attempt2_res.status_code == 201
    att2 = attempt2_res.json()
    assert att2["attempt_number"] == 2
    assert att2["raw_score"] == 100.0
    assert att2["final_score"] == 90.0  # 100 - 10*(2-1) = 90.0

    # Intento 3 del alumno: 50% de aciertos (1 de 2 correcta) -> raw=50, penalización=20 -> final=30.0
    attempt3_res = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 2}, {"question_index": 1, "selected_option": 0}]},
        headers=auth_header(student_token),
    )
    assert attempt3_res.status_code == 201
    att3 = attempt3_res.json()
    assert att3["attempt_number"] == 3
    assert att3["raw_score"] == 50.0
    assert att3["final_score"] == 30.0  # 50 - 10*(3-1) = 30.0

    # Alumno consulta sus intentos
    my_attempts_res = client.get(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/my-attempts",
        headers=auth_header(student_token),
    )
    assert my_attempts_res.status_code == 200
    assert len(my_attempts_res.json()) == 3

    # Alumno intenta consultar todos los intentos del grupo -> 403
    forbidden_attempts = client.get(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        headers=auth_header(student_token),
    )
    assert forbidden_attempts.status_code == 403

    # Profesor consulta todos los intentos del grupo -> 200 con respuestas
    admin_attempts_res = client.get(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        headers=auth_header(admin_token),
    )
    assert admin_attempts_res.status_code == 200
    all_atts = admin_attempts_res.json()
    assert len(all_atts) == 3
    assert "answers_json" in all_atts[0]

    # Alumno intenta consultar el resumen consolidado -> 403 Forbidden
    forbidden_summary = client.get(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/summary",
        headers=auth_header(student_token),
    )
    assert forbidden_summary.status_code == 403

    # Profesor consulta el resumen consolidado -> 200 OK con mejor, último y promedio
    summary_res = client.get(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/summary",
        headers=auth_header(admin_token),
    )
    assert summary_res.status_code == 200
    summary_data = summary_res.json()
    assert summary_data["topic_id"] == topic_id
    assert summary_data["group_id"] == group_id

    # Buscar el resumen del estudiante
    stud_summary = next(
        (m for m in summary_data["members_summary"] if m["user_id"] == student_id),
        None,
    )
    assert stud_summary is not None
    assert stud_summary["total_attempts"] == 3
    # Mejor intento (final_score = 100.0)
    assert stud_summary["best_attempt"]["attempt_number"] == 1
    assert stud_summary["best_attempt"]["final_score"] == 100.0
    # Último intento (attempt_number = 3)
    assert stud_summary["latest_attempt"]["attempt_number"] == 3
    assert stud_summary["latest_attempt"]["final_score"] == 30.0
    # Promedio de final_score: (100 + 90 + 30) / 3 = 73.33
    assert stud_summary["average_final_score"] == 73.33


def test_group_member_management_and_topic_creation_and_export(client: TestClient) -> None:
    suffix = uuid.uuid4().hex[:6]
    admin_id, admin_token = register_and_login(client, f"prof_{suffix}@test.com", "Profesor")
    user2_id, user2_token = register_and_login(client, f"user2_{suffix}@test.com", "Alumno2")

    # 1. Crear grupo
    res_g = client.post("/api/v1/groups", json={"name": "Historia del Arte"}, headers=auth_header(admin_token))
    assert res_g.status_code == 201
    group = res_g.json()
    group_id = group["id"]
    old_code = group["code"]

    # 2. Regenerar código
    res_regen = client.post(f"/api/v1/groups/{group_id}/regenerate-code", headers=auth_header(admin_token))
    assert res_regen.status_code == 200
    new_code = res_regen.json()["code"]
    assert new_code != old_code
    assert len(new_code) == 6

    # 3. Unirse con nuevo código
    res_join = client.post("/api/v1/groups/join", json={"code": new_code}, headers=auth_header(user2_token))
    assert res_join.status_code == 200

    # 4. Listar miembros
    res_members = client.get(f"/api/v1/groups/{group_id}/members", headers=auth_header(admin_token))
    assert res_members.status_code == 200
    members = res_members.json()
    assert len(members) == 2
    admin_member = next(m for m in members if m["user_id"] == admin_id)
    assert admin_member["is_admin"] is True
    student_member = next(m for m in members if m["user_id"] == user2_id)
    assert student_member["is_admin"] is False

    # 5. Crear video y quiz
    video_id, material_id = create_dummy_video_and_quiz(admin_id)

    # 6. Crear tema enviando solo video_id (sin material_id) -> auto-detección
    res_top = client.post(
        f"/api/v1/groups/{group_id}/topics",
        json={"title": "Actividad de Historia", "video_id": video_id},
        headers=auth_header(admin_token),
    )
    assert res_top.status_code == 201
    created_topic = res_top.json()
    assert created_topic["material_id"] == material_id
    assert created_topic["video_id"] == video_id
    topic_id = created_topic["id"]

    # 7. Eliminar tema
    res_del_top = client.delete(f"/api/v1/groups/{group_id}/topics/{topic_id}", headers=auth_header(admin_token))
    assert res_del_top.status_code == 204

    # 8. Expulsar alumno
    res_kick = client.delete(f"/api/v1/groups/{group_id}/members/{user2_id}", headers=auth_header(admin_token))
    assert res_kick.status_code == 204

    # 9. Verificar exportación de materiales a PDF, DOCX y Markdown
    res_md = client.get(f"/api/v1/materials/{material_id}/export?format=markdown", headers=auth_header(admin_token))
    assert res_md.status_code == 200

    res_pdf = client.get(f"/api/v1/materials/{material_id}/export?format=pdf", headers=auth_header(admin_token))
    assert res_pdf.status_code == 200
    assert res_pdf.headers["content-type"] == "application/pdf"

    res_docx = client.get(f"/api/v1/materials/{material_id}/export?format=docx", headers=auth_header(admin_token))
    assert res_docx.status_code == 200
    assert "openxmlformats" in res_docx.headers["content-type"]


def test_attempt_submission_with_open_answers(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica que el endpoint de intento evalúe preguntas abiertas y calcule raw_score correctamente."""
    from unittest.mock import MagicMock
    from app.services.grading_service import QuizAttemptGradingService

    suffix = uuid.uuid4().hex[:6]
    admin_id, admin_token = register_and_login(client, f"prof_{suffix}@test.com", "Profesor")
    student_id, student_token = register_and_login(client, f"stud_{suffix}@test.com", "Estudiante")

    # Crear grupo
    res_grp = client.post("/api/v1/groups", json={"name": "Biología"}, headers=auth_header(admin_token))
    group_id = res_grp.json()["id"]
    group_code = res_grp.json()["code"]

    # Alumno se une
    client.post("/api/v1/groups/join", json={"code": group_code}, headers=auth_header(student_token))

    # Crear material con MC y pregunta abierta
    session_gen = get_session()
    session = next(session_gen)
    try:
        video = Video(
            youtube_id=f"yt_{suffix}",
            source_url="https://www.youtube.com/watch?v=open_q_test",
            title="Video abierto",
            language="es",
            duration_seconds=120,
            transcript_path="",
            owner_id=admin_id,
        )
        session.add(video)
        session.flush()

        quiz_data = {
            "multiple_choice": [
                {
                    "question": "¿Pregunta MC?",
                    "options": ["A", "B", "C", "D"],
                    "correct_option": 0,
                    "explanation": "Exp MC",
                    "evidence_timestamp": "00:00:10",
                    "bloom_level": "remember",
                }
            ],
            "open_questions": [
                {
                    "question": "¿Explica el fenómeno?",
                    "expected_points": ["Punto 1", "Punto 2"],
                    "evidence_timestamp": "00:00:30",
                    "bloom_level": "understand",
                }
            ],
            "evidence_sufficient": True,
        }
        material = DidacticMaterial(
            video_id=video.id,
            material_type="quiz",
            content_json=json.dumps(quiz_data),
            owner_id=admin_id,
        )
        session.add(material)
        session.commit()
        vid_id, mat_id = video.id, material.id
    finally:
        session.close()

    # Publicar topic
    res_top = client.post(
        f"/api/v1/groups/{group_id}/topics",
        json={"title": "Actividad Mixta", "video_id": vid_id, "material_id": mat_id},
        headers=auth_header(admin_token),
    )
    assert res_top.status_code == 201
    topic_id = res_top.json()["id"]

    # Mockear VectorStore y Gemini en QuizAttemptGradingService
    mock_vectors = MagicMock()
    mock_vectors.retrieve.return_value = [{"text": "Evidencia recuperada de prueba", "start": "00:00:20", "end": "00:00:40"}]

    mock_gemini = MagicMock()
    mock_gemini.generate_json.return_value = json.dumps({
        "evaluations": [
            {
                "question_index": 0,
                "score": 0.8,
                "is_correct": True,
                "feedback_text": "Respuesta fundamentada en la evidencia.",
                "missing_points": ["Punto 2"],
            }
        ],
        "evidence_sufficient": True,
    })

    # Monkeypatching para inyectar mocks al servicio de evaluación
    orig_init = QuizAttemptGradingService.__init__

    def patched_init(self, settings=None, materials=None, vectors=None, gemini=None):
        orig_init(self, settings=settings, materials=materials, vectors=mock_vectors, gemini=mock_gemini)

    monkeypatch.setattr(QuizAttemptGradingService, "__init__", patched_init)

    # Estudiante envía respuestas mixtas
    payload = {
        "multiple_choice_answers": [{"question_index": 0, "selected_option": 0}],  # 1.0
        "open_answers": [{"question_index": 0, "answer": "El fenómeno consiste en Punto 1."}],  # 0.8
    }
    att_res = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json=payload,
        headers=auth_header(student_token),
    )
    assert att_res.status_code == 201
    att_data = att_res.json()
    # (1.0 + 0.8) / 2 * 100 = 90.0
    assert att_data["raw_score"] == 90.0
    assert att_data["final_score"] == 90.0
    assert att_data["attempt_number"] == 1



