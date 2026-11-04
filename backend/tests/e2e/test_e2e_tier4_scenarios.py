"""Tier 4: Realistic Classroom Lifecycle Scenarios.

Simulates end-to-end classroom workflows across multiple users and roles:
- Scenario 1: Complete Course Activity Lifecycle (F1, F2, F4, F5)
- Scenario 2: Quiz Taking, Hiding Answers & Individual Review (F1, F2, F4, F6)
- Scenario 3: Large Video Catalog Management & Search (F3)
- Scenario 4: Collaborative Study with Personal Summaries (F5, F4)
- Scenario 5: Video Timestamp Navigation & Topic Study (F6, F4)
Total: 5 high-complexity scenarios.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
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

try:
    from app.services.timestamp_service import TimestampCalibrationService
except ImportError:
    TimestampCalibrationService = None


def test_s1_complete_course_activity_lifecycle(
    client: TestClient, db_session: Session
) -> None:
    """Scenario 1: Complete classroom activity lifecycle from group creation to inline grading."""
    suffix = uuid.uuid4().hex[:6]
    # 1. Teacher registers
    teacher_id, teacher_token, t_hdr = register_and_login(
        client, f"s1_prof_{suffix}@escuela.edu", "Profesor García"
    )

    # 2. Ingests video, creates quiz and official summary
    video = create_test_video(db_session, owner_id=teacher_id, title="Revolución Industrial y Energía")
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id, open_questions=[])
    summary = create_test_summary(db_session, video_id=video.id, owner_id=teacher_id, synopsis="Sinopsis oficial de la unidad")

    # 3. Creates group and topic
    group_id, code, topic_id = create_test_group_and_topic(
        client, teacher_token, video.id, quiz.id, group_name="Historia Contemporánea Grupo A"
    )

    # 4. Two students enroll
    alice_id, alice_token, a_hdr = register_and_login(client, f"alice_{suffix}@alumno.edu", "Alice Alumna")
    bob_id, bob_token, b_hdr = register_and_login(client, f"bob_{suffix}@alumno.edu", "Bob Alumno")

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(alice_token))
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(bob_token))

    # 5. Alice consults materials and submits 100% attempt
    a_mats = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/materials", headers=a_hdr).json()
    assert a_mats["shared_summary"] is not None
    assert "correct_option" not in a_mats["shared_quiz"]["content"]["multiple_choice"][0]

    a_att = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}, {"question_index": 1, "selected_option": 1}]},
        headers=a_hdr,
    ).json()
    assert a_att["raw_score"] == 100.0

    # 6. Bob submits attempt 1 (50%) and attempt 2 (retry with penalty)
    client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}, {"question_index": 1, "selected_option": 0}]},
        headers=b_hdr,
    )
    b_att2 = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}, {"question_index": 1, "selected_option": 1}]},
        headers=b_hdr,
    ).json()
    assert b_att2["attempt_number"] == 2
    assert b_att2["final_score"] == 90.0

    # 7. Teacher reviews activity summary
    sum_data = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/summary", headers=t_hdr).json()
    members = {m["user_id"]: m for m in sum_data["members_summary"]}
    assert members[alice_id]["total_attempts"] == 1
    assert members[bob_id]["total_attempts"] == 2

    # 8. Teacher overrides Bob's grade inline
    client.patch(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts/{b_att2['id']}",
        json={"final_score": 93.0, "review_notes": "Buen progreso en segundo intento."},
        headers=t_hdr,
    )

    # 9. Bob checks my-attempts
    bob_atts = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/my-attempts", headers=b_hdr).json()
    assert len(bob_atts) == 2
    assert bob_atts[1]["final_score"] == 93.0


def test_s2_quiz_taking_hiding_answers_and_individual_review(
    client: TestClient, db_session: Session
) -> None:
    """Scenario 2: Teacher verifies unmasked view and exports; student verifies masked view, submits, and gets reviewed."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"s2_prof_{suffix}@test.com", "Profesor Cuestionarios")
    student_id, student_token, s_hdr = register_and_login(client, f"s2_stud_{suffix}@test.com", "Estudiante Cuestionarios")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    # Teacher exports with answers
    exp_t = client.get(f"/api/v1/materials/{quiz.id}/export?format=markdown&include_answers=true", headers=t_hdr)
    assert exp_t.status_code == 200
    assert "Respuesta correcta" in exp_t.text or "Explicación" in exp_t.text or "Patente" in exp_t.text

    # Student exports without answers
    exp_s = client.get(f"/api/v1/materials/{quiz.id}/export?format=markdown&include_answers=false", headers=s_hdr)
    assert exp_s.status_code == 200
    assert "Respuesta correcta" not in exp_s.text

    # Student submits attempt
    sub_res = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}]},
        headers=s_hdr,
    )
    assert sub_res.status_code == 201
    att_id = sub_res.json()["id"]

    # Teacher inspects and reviews
    patch_res = client.patch(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts/{att_id}",
        json={"final_score": 98.0, "review_notes": "Casi perfecto."},
        headers=t_hdr,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["final_score"] == 98.0


def test_s3_large_video_catalog_management_and_search(
    client: TestClient, db_session: Session
) -> None:
    """Scenario 3: Manage video catalog with multiple entries, filtering by title, and sorting chronologically."""
    suffix = uuid.uuid4().hex[:6]
    user_id, token, hdr = register_and_login(client, f"s3_user_{suffix}@test.com", "Curador Multimedia")

    now = datetime.now(timezone.utc)
    # Register 4 videos across different dates and subjects
    v_ai_old = create_test_video(db_session, owner_id=user_id, title=f"Inteligencia Artificial Fundamentos {suffix}", created_at=now - timedelta(days=20))
    v_bio = create_test_video(db_session, owner_id=user_id, title=f"Biologia Molecular {suffix}", created_at=now - timedelta(days=15))
    v_ai_new = create_test_video(db_session, owner_id=user_id, title=f"Inteligencia Artificial Deep Learning {suffix}", created_at=now - timedelta(days=5))
    v_hist = create_test_video(db_session, owner_id=user_id, title=f"Historia de Mesoamerica {suffix}", created_at=now)

    # 1. Default ordering: newest first
    res_default = client.get("/api/v1/videos", headers=hdr).json()["items"]
    filtered_all = [v for v in res_default if v["id"] in (v_ai_old.id, v_bio.id, v_ai_new.id, v_hist.id)]
    assert filtered_all[0]["id"] == v_hist.id

    # 2. Inverted ordering: oldest first
    res_asc = client.get("/api/v1/videos?order=asc", headers=hdr).json()["items"]
    filtered_asc = [v for v in res_asc if v["id"] in (v_ai_old.id, v_bio.id, v_ai_new.id, v_hist.id)]
    assert filtered_asc[0]["id"] == v_ai_old.id

    # 3. Filter by search="Inteligencia Artificial" with order=asc
    res_search = client.get("/api/v1/videos?search=inteligencia+artificial&order=asc", headers=hdr).json()["items"]
    filtered_search = [v for v in res_search if v["id"] in (v_ai_old.id, v_ai_new.id)]
    assert len(filtered_search) == 2
    assert filtered_search[0]["id"] == v_ai_old.id
    assert filtered_search[1]["id"] == v_ai_new.id

    # 4. Attach selected video to topic
    group_id, code, topic_id = create_test_group_and_topic(
        client, token, video_id=v_ai_new.id, topic_title="Unidad IA Avanzada"
    )
    assert topic_id is not None


def test_s4_collaborative_study_with_personal_summaries(
    client: TestClient, db_session: Session
) -> None:
    """Scenario 4: Teacher provides official study summary; students generate and edit independent personal notes."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"s4_prof_{suffix}@test.com", "Profesor Coordinador")
    s1_id, s1_tok, s1_hdr = register_and_login(client, f"s4_s1_{suffix}@test.com", "Alumno Estudio A")
    s2_id, s2_tok, s2_hdr = register_and_login(client, f"s4_s2_{suffix}@test.com", "Alumno Estudio B")

    video = create_test_video(db_session, owner_id=teacher_id)
    official_sum = create_test_summary(db_session, video_id=video.id, owner_id=teacher_id, synopsis="Guía Oficial del Docente")
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s1_tok))
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s2_tok))

    # S1 creates personal summary
    s1_sum = create_test_summary(db_session, video_id=video.id, owner_id=s1_id, synopsis="Notas de S1")
    # S2 creates personal summary
    s2_sum = create_test_summary(db_session, video_id=video.id, owner_id=s2_id, synopsis="Notas de S2")

    # S1 tries to edit official summary -> 403
    fail_edit = client.put(
        f"/api/v1/materials/{official_sum.id}",
        json={"content": {"synopsis": "Sobrescritura ilícita"}},
        headers=s1_hdr,
    )
    assert fail_edit.status_code == 403

    # S1 edits own summary -> 200
    ok_edit = client.put(
        f"/api/v1/materials/{s1_sum.id}",
        json={"content": {"synopsis": "Notas de S1 enriquecidas con ejemplos", "glossary": [], "didactic_blocks": [], "evidence_sufficient": True}},
        headers=s1_hdr,
    )
    assert ok_edit.status_code == 200

    # S2 personal summary remains untouched
    s2_mats = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/materials", headers=s2_hdr).json()
    assert s2_mats["personal_summary"]["id"] == s2_sum.id
    assert s2_mats["personal_summary"]["content"]["synopsis"] == "Notas de S2"


def test_s5_video_timestamp_navigation_and_topic_study(
    sample_segments: list[dict[str, Any]]
) -> None:
    """Scenario 5: Timestamp calibration guides students to 5-10s prior context without clipping."""
    assert TimestampCalibrationService is not None, "TimestampCalibrationService must be implemented"
    service = TimestampCalibrationService()

    # Topic begins at 25.0s ("Esto permitió un ahorro térmico...")
    # Preceding segment is segment 3 (starts at 18.0s, ends at 24.5s)
    # The lead-in from 18.0s to 25.0s is 7.0s, perfectly in [5.0, 10.0]
    calibrated_25 = service.calibrate(sample_segments, topic_start_time=25.0, topic_text="ahorro térmico")
    lead_in = 25.0 - calibrated_25
    assert 5.0 <= lead_in <= 10.0
    assert calibrated_25 == 18.0

    # Formatted timestamp should be valid
    if hasattr(service, "to_timestamp_string"):
        ts_str = service.to_timestamp_string(calibrated_25)
        assert ts_str == "00:00:18" or ts_str == "00:18"
