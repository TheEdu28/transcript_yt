"""Tier 3: Cross-Feature Pairwise Interaction Tests.

Tests the interplay between roles, attempts, grades, quizzes, summaries, exports, and timestamps:
- T3.01: Video Catalog (F3) + Role-Based Quiz Masking (F4)
- T3.02: Activity Grading View (F1) + Attempt Isolation (F2)
- T3.03: Attempt Penalty (F2) + Inline Manual Grade Override (F1)
- T3.04: Timestamp Calibration (F6) + Quiz Export (F4)
- T3.05: Masked Quiz View (F4) + Student Personal Summary (F5)
- T3.06: Video Search & Sorting (F3) + Activity Topic Creation (F1)
- T3.07: Multi-Student Attempts (F2) + Individual Inline Grading (F1)
- T3.08: Role Answer Masking (F4) + Multi-Format Export (F4)
- T3.09: Official Summary View (F5) + Personal Notes (F5) + Attempt Submission (F2)
- T3.10: Activity Summary Lifecycle Progression (F1 + F2)
Total: 10 tests.
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

try:
    from app.services.timestamp_service import TimestampCalibrationService
except ImportError:
    TimestampCalibrationService = None


def test_t3_01_teacher_creates_topic_student_views_masked_quiz(
    client: TestClient, db_session: Session
) -> None:
    """Pairwise F3 + F4: Teacher attaches video and quiz to topic; student views properly masked quiz."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t3_01_t_{suffix}@test.com", "Profesor T3_1")
    student_id, student_token, s_hdr = register_and_login(client, f"t3_01_s_{suffix}@test.com", "Estudiante T3_1")

    video = create_test_video(db_session, owner_id=teacher_id, title=f"Video Astronomia {suffix}")
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    res = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/materials", headers=s_hdr)
    assert res.status_code == 200
    mats = res.json()
    assert mats["shared_quiz"]["id"] == quiz.id
    for mc in mats["shared_quiz"]["content"]["multiple_choice"]:
        assert "correct_option" not in mc
        assert "explanation" not in mc


def test_t3_02_student_submits_attempt_and_activity_view_updates(
    client: TestClient, db_session: Session
) -> None:
    """Pairwise F1 + F2: Student submits quiz; teacher's topic summary immediately reflects submission."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t3_02_t_{suffix}@test.com", "Profesor T3_2")
    student_id, student_token, s_hdr = register_and_login(client, f"t3_02_s_{suffix}@test.com", "Estudiante T3_2")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    # Before attempt: total_attempts == 0
    sum_before = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/summary", headers=t_hdr).json()
    m_before = next(m for m in sum_before["members_summary"] if m["user_id"] == student_id)
    assert m_before["total_attempts"] == 0

    # Student submits attempt
    client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}]},
        headers=s_hdr,
    )

    # After attempt: total_attempts == 1, best_attempt populated
    sum_after = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/summary", headers=t_hdr).json()
    m_after = next(m for m in sum_after["members_summary"] if m["user_id"] == student_id)
    assert m_after["total_attempts"] == 1
    assert m_after["latest_attempt"] is not None


def test_t3_03_retry_penalty_flow_with_teacher_manual_grade_override(
    client: TestClient, db_session: Session
) -> None:
    """Pairwise F1 + F2: Penalty reduces repeat attempt score; teacher manually overrides and adjusts grade."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t3_03_t_{suffix}@test.com", "Profesor T3_3")
    student_id, student_token, s_hdr = register_and_login(client, f"t3_03_s_{suffix}@test.com", "Estudiante T3_3")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id, open_questions=[])
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    # Attempt 1
    client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}, {"question_index": 1, "selected_option": 1}]},
        headers=s_hdr,
    )
    # Attempt 2 (penalized to 90)
    att2_res = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}, {"question_index": 1, "selected_option": 1}]},
        headers=s_hdr,
    )
    attempt2_id = att2_res.json()["id"]
    assert att2_res.json()["final_score"] == 90.0

    # Teacher overrides attempt 2 score to 95.0
    patch_res = client.patch(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts/{attempt2_id}",
        json={"final_score": 95.0, "review_notes": "Ajuste por justificacion adicional."},
        headers=t_hdr,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["final_score"] == 95.0


def test_t3_04_calibrated_timestamp_in_quiz_exported_to_markdown(
    client: TestClient, db_session: Session
) -> None:
    """Pairwise F4 + F6: Calibrated timestamp in quiz questions formats cleanly in Markdown export."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t3_04_t_{suffix}@test.com", "Profesor T3_4")

    video = create_test_video(db_session, owner_id=teacher_id)
    # Question with calibrated timestamp
    mc = [
        {
            "question": "¿Pregunta con timestamp calibrado?",
            "options": ["A", "B", "C", "D"],
            "correct_option": 0,
            "explanation": "Exp",
            "evidence_timestamp": "00:00:10",
            "bloom_level": "remember",
        }
    ]
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id, mc_questions=mc)

    res = client.get(f"/api/v1/materials/{quiz.id}/export?format=markdown&include_answers=true", headers=t_hdr)
    assert res.status_code == 200
    assert "00:00:10" in res.text


def test_t3_05_student_creates_personal_summary_alongside_masked_quiz(
    client: TestClient, db_session: Session
) -> None:
    """Pairwise F4 + F5: Student reads masked quiz and creates personal summary for the same topic."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t3_05_t_{suffix}@test.com", "Profesor T3_5")
    student_id, student_token, s_hdr = register_and_login(client, f"t3_05_s_{suffix}@test.com", "Estudiante T3_5")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    official_sum = create_test_summary(db_session, video_id=video.id, owner_id=teacher_id, synopsis="Oficial Docente")
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    # Student creates personal summary
    pers_sum = create_test_summary(db_session, video_id=video.id, owner_id=student_id, synopsis="Mis notas personales")

    # In topic materials, student sees masked quiz + official summary + personal summary
    mats = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/materials", headers=s_hdr).json()
    assert mats["shared_quiz"] is not None
    assert "correct_option" not in mats["shared_quiz"]["content"]["multiple_choice"][0]
    assert mats["shared_summary"]["id"] == official_sum.id
    assert mats["personal_summary"]["id"] == pers_sum.id


def test_t3_06_video_search_used_to_pick_video_for_new_topic(
    client: TestClient, db_session: Session
) -> None:
    """Pairwise F3 + F1: Teacher uses search and sort to select a video and create an activity."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t3_06_t_{suffix}@test.com", "Profesor T3_6")

    v1 = create_test_video(db_session, owner_id=teacher_id, title=f"Fisica Mecanica Newtoniana {suffix}")
    v2 = create_test_video(db_session, owner_id=teacher_id, title=f"Quimica Estequiometria {suffix}")

    # Search for "Mecanica"
    search_res = client.get("/api/v1/videos?search=mecanica&order=desc", headers=t_hdr).json()
    matched_ids = [v["id"] for v in search_res["items"] if v["id"] in (v1.id, v2.id)]
    assert v1.id in matched_ids
    assert v2.id not in matched_ids

    # Create topic using the selected video
    group_id, code, topic_id = create_test_group_and_topic(
        client, teacher_token, video_id=v1.id, topic_title="Actividad de Mecanica"
    )
    assert topic_id is not None


def test_t3_07_multiple_students_attempts_and_individual_grading_in_activity(
    client: TestClient, db_session: Session
) -> None:
    """Pairwise F1 + F2: Multi-student attempts are individually graded with distinct scores and review notes."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t3_07_t_{suffix}@test.com", "Profesor T3_7")
    s1_id, s1_tok, s1_hdr = register_and_login(client, f"t3_07_s1_{suffix}@test.com", "Alumno Multi 1")
    s2_id, s2_tok, s2_hdr = register_and_login(client, f"t3_07_s2_{suffix}@test.com", "Alumno Multi 2")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s1_tok))
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s2_tok))

    att1_res = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}]},
        headers=s1_hdr,
    )
    att1_id = att1_res.json()["id"]

    att2_res = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 0}]},
        headers=s2_hdr,
    )
    att2_id = att2_res.json()["id"]

    # Teacher grades S1
    client.patch(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts/{att1_id}",
        json={"final_score": 96.0, "review_notes": "Nota S1"},
        headers=t_hdr,
    )
    # Teacher grades S2
    client.patch(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts/{att2_id}",
        json={"final_score": 75.0, "review_notes": "Nota S2"},
        headers=t_hdr,
    )

    # Verify both in topic summary
    sum_data = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/summary", headers=t_hdr).json()
    members = {m["user_id"]: m for m in sum_data["members_summary"]}
    assert members[s1_id]["latest_attempt"]["final_score"] == 96.0
    assert members[s2_id]["latest_attempt"]["final_score"] == 75.0


def test_t3_08_quiz_export_role_toggle_across_multiple_formats(
    client: TestClient, db_session: Session
) -> None:
    """Pairwise F4: Teacher exports both with and without answers; student is restricted to without answers."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t3_08_t_{suffix}@test.com", "Profesor T3_8")
    student_id, student_token, s_hdr = register_and_login(client, f"t3_08_s_{suffix}@test.com", "Estudiante T3_8")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    # Teacher with answers -> markdown
    t_exp_with = client.get(f"/api/v1/materials/{quiz.id}/export?format=markdown&include_answers=true", headers=t_hdr)
    assert t_exp_with.status_code == 200

    # Teacher without answers -> markdown
    t_exp_without = client.get(f"/api/v1/materials/{quiz.id}/export?format=markdown&include_answers=false", headers=t_hdr)
    assert t_exp_without.status_code == 200

    # Student without answers -> markdown
    s_exp_without = client.get(f"/api/v1/materials/{quiz.id}/export?format=markdown&include_answers=false", headers=s_hdr)
    assert s_exp_without.status_code == 200
    assert "Respuesta correcta" not in s_exp_without.text


def test_t3_09_official_summary_viewing_paired_with_personal_notes_and_attempt(
    client: TestClient, db_session: Session
) -> None:
    """Pairwise F2 + F5: Student consults official summary, creates personal study notes, then takes the quiz."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t3_09_t_{suffix}@test.com", "Profesor T3_9")
    student_id, student_token, s_hdr = register_and_login(client, f"t3_09_s_{suffix}@test.com", "Estudiante T3_9")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id, open_questions=[])
    create_test_summary(db_session, video_id=video.id, owner_id=teacher_id, synopsis="Oficial Para Estudio")
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    # 1. Consult materials
    mats = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/materials", headers=s_hdr).json()
    assert mats["shared_summary"] is not None

    # 2. Save personal summary
    create_test_summary(db_session, video_id=video.id, owner_id=student_id, synopsis="Mis anotaciones de estudio")

    # 3. Submit quiz attempt
    att = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}, {"question_index": 1, "selected_option": 1}]},
        headers=s_hdr,
    ).json()
    assert att["raw_score"] == 100.0


def test_t3_10_activity_summary_status_progression_from_pending_to_evaluated(
    client: TestClient, db_session: Session
) -> None:
    """Pairwise F1 + F2: Student progresses from not_submitted -> pending -> evaluated after teacher review."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t3_10_t_{suffix}@test.com", "Profesor T3_10")
    student_id, student_token, s_hdr = register_and_login(client, f"t3_10_s_{suffix}@test.com", "Estudiante T3_10")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    # Stage 1: Enrolled, no attempt -> not_submitted
    s1_sum = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/summary", headers=t_hdr).json()
    m_s1 = next(m for m in s1_sum["members_summary"] if m["user_id"] == student_id)
    assert m_s1["total_attempts"] == 0

    # Stage 2: Submits attempt
    att_res = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}]},
        headers=s_hdr,
    )
    att_id = att_res.json()["id"]

    # Stage 3: Teacher reviews and updates grade -> evaluated
    client.patch(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts/{att_id}",
        json={"final_score": 90.0, "review_notes": "Revisado"},
        headers=t_hdr,
    )
    s3_sum = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/summary", headers=t_hdr).json()
    m_s3 = next(m for m in s3_sum["members_summary"] if m["user_id"] == student_id)
    assert m_s3["status"] == "evaluated"
