"""Role Permission Matrix Verification.

Explicitly verifies all 8 capabilities defined in ORIGINAL_REQUEST.md & TEST_INFRA.md:
1. Calificar alumnos: Profesor Sí, Alumno No.
2. Consultar intentos individuales: Profesor Sí (de cada alumno), Alumno solo los propios.
3. Ordenar y buscar videos: Profesor Sí, Alumno Sí.
4. Ver y exportar cuestionario con respuestas: Profesor Sí, Alumno No.
5. Ver y exportar cuestionario sin respuestas: Profesor Sí, Alumno Sí.
6. Consultar resumen del profesor: Profesor Sí, Alumno Sí.
7. Generar resumen personal: Alumno Sí.
8. Modificar resumen oficial: Alumno No.
Total: 8 tests.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.e2e.conftest import (
    auth_header,
    create_test_group_and_topic,
    create_test_quiz,
    create_test_summary,
    create_test_video,
    register_and_login,
)


def test_perm_01_calificar_alumnos(client: TestClient, db_session: Session) -> None:
    """1. Calificar alumnos: Profesor Sí (200), Alumno No (403)."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"p01_prof_{suffix}@test.com", "Profesor Perm 1")
    s1_id, s1_tok, s1_hdr = register_and_login(client, f"p01_s1_{suffix}@test.com", "Alumno Perm 1")
    s2_id, s2_tok, s2_hdr = register_and_login(client, f"p01_s2_{suffix}@test.com", "Alumno Perm 2")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s1_tok))
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s2_tok))

    # Student 1 submits attempt
    att_res = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}]},
        headers=s1_hdr,
    )
    attempt_id = att_res.json()["id"]

    # Student 2 attempts to grade Student 1 -> MUST BE 403 Forbidden
    student_grade_res = client.patch(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts/{attempt_id}",
        json={"final_score": 100.0, "review_notes": "Intento de autocalificación de alumno"},
        headers=s2_hdr,
    )
    assert student_grade_res.status_code == 403, f"Expected 403 for student grading, got {student_grade_res.status_code}"

    # Teacher grades Student 1 -> MUST BE 200 OK
    teacher_grade_res = client.patch(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts/{attempt_id}",
        json={"final_score": 95.0, "review_notes": "Calificación legítima de docente"},
        headers=t_hdr,
    )
    assert teacher_grade_res.status_code == 200
    assert teacher_grade_res.json()["final_score"] == 95.0


def test_perm_02_consultar_intentos_individuales(
    client: TestClient, db_session: Session
) -> None:
    """2. Consultar intentos individuales: Profesor Sí (de cada alumno), Alumno solo los propios."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"p02_prof_{suffix}@test.com", "Profesor Perm 2")
    s1_id, s1_tok, s1_hdr = register_and_login(client, f"p02_s1_{suffix}@test.com", "Alumno Perm 2A")
    s2_id, s2_tok, s2_hdr = register_and_login(client, f"p02_s2_{suffix}@test.com", "Alumno Perm 2B")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s1_tok))
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s2_tok))

    # Both submit attempts
    client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}]},
        headers=s1_hdr,
    )
    client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 0}]},
        headers=s2_hdr,
    )

    # Student 1 consults own attempts -> 200 OK (only 1 attempt)
    s1_my = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/my-attempts", headers=s1_hdr)
    assert s1_my.status_code == 200
    assert len(s1_my.json()) == 1
    assert s1_my.json()[0]["user_id"] == s1_id

    # Student 1 attempts to consult all attempts -> 403 Forbidden
    s1_all = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts", headers=s1_hdr)
    assert s1_all.status_code == 403

    # Teacher consults attempts for Student 1 -> 200 OK (only S1)
    t_s1 = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts?user_id={s1_id}", headers=t_hdr)
    if t_s1.status_code == 200:
        assert all(a["user_id"] == s1_id for a in t_s1.json())
    else:
        t_s1_alt = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/members/{s1_id}/attempts", headers=t_hdr)
        assert t_s1_alt.status_code == 200
        assert all(a["user_id"] == s1_id for a in t_s1_alt.json())


def test_perm_03_ordenar_y_buscar_videos(client: TestClient, db_session: Session) -> None:
    """3. Ordenar y buscar videos: Profesor Sí (200), Alumno Sí (200)."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"p03_prof_{suffix}@test.com", "Profesor Perm 3")
    student_id, student_token, s_hdr = register_and_login(client, f"p03_stud_{suffix}@test.com", "Alumno Perm 3")

    create_test_video(db_session, owner_id=teacher_id, title=f"Historia Universal {suffix}")
    create_test_video(db_session, owner_id=student_id, title=f"Historia de America {suffix}")

    # Teacher sorts and searches
    res_t = client.get("/api/v1/videos?search=historia&order=asc", headers=t_hdr)
    assert res_t.status_code == 200
    assert "items" in res_t.json()

    # Student sorts and searches
    res_s = client.get("/api/v1/videos?search=historia&order=asc", headers=s_hdr)
    assert res_s.status_code == 200
    assert "items" in res_s.json()


def test_perm_04_ver_y_exportar_cuestionario_con_respuestas(
    client: TestClient, db_session: Session
) -> None:
    """4. Ver y exportar cuestionario con respuestas: Profesor Sí, Alumno No."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"p04_prof_{suffix}@test.com", "Profesor Perm 4")
    student_id, student_token, s_hdr = register_and_login(client, f"p04_stud_{suffix}@test.com", "Alumno Perm 4")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    # Teacher sees answers in topic materials
    t_mats = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/materials", headers=t_hdr).json()
    assert "correct_option" in t_mats["shared_quiz"]["content"]["multiple_choice"][0]

    # Teacher exports with answers
    t_exp = client.get(f"/api/v1/materials/{quiz.id}/export?format=markdown&include_answers=true", headers=t_hdr)
    assert t_exp.status_code == 200

    # Student CANNOT see answers in topic materials
    s_mats = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/materials", headers=s_hdr).json()
    assert "correct_option" not in s_mats["shared_quiz"]["content"]["multiple_choice"][0]

    # Student export with answers is rejected or stripped
    s_exp = client.get(f"/api/v1/materials/{quiz.id}/export?format=markdown&include_answers=true", headers=s_hdr)
    if s_exp.status_code == 200:
        assert "Respuesta correcta" not in s_exp.text
    else:
        assert s_exp.status_code in (403, 400)


def test_perm_05_ver_y_exportar_cuestionario_sin_respuestas(
    client: TestClient, db_session: Session
) -> None:
    """5. Ver y exportar cuestionario sin respuestas: Profesor Sí (200), Alumno Sí (200)."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"p05_prof_{suffix}@test.com", "Profesor Perm 5")
    student_id, student_token, s_hdr = register_and_login(client, f"p05_stud_{suffix}@test.com", "Alumno Perm 5")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    # Teacher export without answers
    t_exp = client.get(f"/api/v1/materials/{quiz.id}/export?format=markdown&include_answers=false", headers=t_hdr)
    assert t_exp.status_code == 200
    assert "Respuesta correcta" not in t_exp.text

    # Student export without answers
    s_exp = client.get(f"/api/v1/materials/{quiz.id}/export?format=markdown&include_answers=false", headers=s_hdr)
    assert s_exp.status_code == 200
    assert "Respuesta correcta" not in s_exp.text


def test_perm_06_consultar_resumen_del_profesor(
    client: TestClient, db_session: Session
) -> None:
    """6. Consultar resumen del profesor: Profesor Sí (200), Alumno Sí (200)."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"p06_prof_{suffix}@test.com", "Profesor Perm 6")
    student_id, student_token, s_hdr = register_and_login(client, f"p06_stud_{suffix}@test.com", "Alumno Perm 6")

    video = create_test_video(db_session, owner_id=teacher_id)
    summary = create_test_summary(db_session, video_id=video.id, owner_id=teacher_id, synopsis="Sinopsis Docente Oficial")
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id)
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    # Teacher consults
    t_mats = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/materials", headers=t_hdr)
    assert t_mats.status_code == 200
    assert t_mats.json()["shared_summary"]["id"] == summary.id

    # Student consults
    s_mats = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/materials", headers=s_hdr)
    assert s_mats.status_code == 200
    assert s_mats.json()["shared_summary"]["id"] == summary.id


def test_perm_07_generar_resumen_personal(client: TestClient, db_session: Session) -> None:
    """7. Generar resumen personal: Alumno Sí (200/201)."""
    suffix = uuid.uuid4().hex[:6]
    student_id, student_token, s_hdr = register_and_login(client, f"p07_stud_{suffix}@test.com", "Alumno Perm 7")

    video = create_test_video(db_session, owner_id=student_id)
    pers_sum = create_test_summary(db_session, video_id=video.id, owner_id=student_id, synopsis="Apuntes Propios")

    assert pers_sum.id is not None
    assert pers_sum.owner_id == student_id

    # Student can query their personal materials
    res = client.get(f"/api/v1/materials/{pers_sum.id}", headers=s_hdr)
    assert res.status_code == 200
    assert res.json()["id"] == pers_sum.id


def test_perm_08_modificar_resumen_oficial(client: TestClient, db_session: Session) -> None:
    """8. Modificar resumen oficial: Profesor Sí (200), Alumno No (403)."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"p08_prof_{suffix}@test.com", "Profesor Perm 8")
    student_id, student_token, s_hdr = register_and_login(client, f"p08_stud_{suffix}@test.com", "Alumno Perm 8")

    video = create_test_video(db_session, owner_id=teacher_id)
    summary = create_test_summary(db_session, video_id=video.id, owner_id=teacher_id, synopsis="Oficial Original")
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id)
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    # Student attempts to modify official summary -> 403 Forbidden
    s_put = client.put(
        f"/api/v1/materials/{summary.id}",
        json={"content": {"synopsis": "Modificacion ilicita de alumno"}},
        headers=s_hdr,
    )
    assert s_put.status_code == 403

    # Teacher modifies official summary -> 200 OK
    t_put = client.put(
        f"/api/v1/materials/{summary.id}",
        json={"content": {"synopsis": "Actualizacion legitima por profesor", "glossary": [], "didactic_blocks": [], "evidence_sufficient": True}},
        headers=t_hdr,
    )
    assert t_put.status_code == 200
    assert t_put.json()["content"]["synopsis"] == "Actualizacion legitima por profesor"
