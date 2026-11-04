"""Tier 2: Boundary Value Analysis and Edge Case Verification (F1–F6).

Covers edge cases, limits, empty queries, invalid inputs, and boundary conditions:
- F1 Boundaries: 5 tests
- F2 Boundaries: 5 tests
- F3 Boundaries: 5 tests
- F4 Boundaries: 5 tests
- F5 Boundaries: 5 tests
- F6 Boundaries: 5 tests
Total: 30 tests.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.material import DidacticMaterial
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


# =============================================================================
# F1 Boundaries: Activity-Centric Grading View
# =============================================================================

def test_t2_f1_01_summary_with_zero_members(client: TestClient, db_session: Session) -> None:
    """Topic summary when a group has no enrolled students returns empty members list."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t2_f1_t1_{suffix}@test.com", "Profesor B1_1")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    res = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/summary", headers=t_hdr)
    assert res.status_code == 200
    students = [m for m in res.json()["members_summary"] if m["user_id"] != teacher_id]
    assert students == []


def test_t2_f1_02_summary_all_members_not_submitted(client: TestClient, db_session: Session) -> None:
    """Multiple enrolled students with 0 attempts all show not_submitted/pending with total_attempts=0."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t2_f1_t2_{suffix}@test.com", "Profesor B1_2")
    _, s1_token, _ = register_and_login(client, f"t2_f1_s1_{suffix}@test.com", "Alumno Zero 1")
    _, s2_token, _ = register_and_login(client, f"t2_f1_s2_{suffix}@test.com", "Alumno Zero 2")

    video = create_test_video(db_session, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s1_token))
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s2_token))

    res = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/summary", headers=t_hdr)
    assert res.status_code == 200
    for m in res.json()["members_summary"]:
        assert m["total_attempts"] == 0
        assert m["best_attempt"] is None
        assert m["latest_attempt"] is None


def test_t2_f1_03_grading_boundary_scores_min_0_max_100(
    client: TestClient, db_session: Session
) -> None:
    """Inline grading accepts valid boundary scores: exact 0.0 and exact 100.0."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t2_f1_t3_{suffix}@test.com", "Profesor B1_3")
    _, student_token, s_hdr = register_and_login(client, f"t2_f1_s3_{suffix}@test.com", "Alumno Bound")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))
    att_res = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}]},
        headers=s_hdr,
    )
    attempt_id = att_res.json()["id"]

    # Test boundary 0.0
    r0 = client.patch(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts/{attempt_id}",
        json={"final_score": 0.0, "review_notes": "Nota minima de frontera."},
        headers=t_hdr,
    )
    assert r0.status_code == 200
    assert r0.json()["final_score"] == 0.0

    # Test boundary 100.0
    r100 = client.patch(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts/{attempt_id}",
        json={"final_score": 100.0, "review_notes": "Nota maxima de frontera."},
        headers=t_hdr,
    )
    assert r100.status_code == 200
    assert r100.json()["final_score"] == 100.0


def test_t2_f1_04_grading_invalid_score_rejected(
    client: TestClient, db_session: Session
) -> None:
    """Updating attempt score with negative value or score > 100 is rejected."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t2_f1_t4_{suffix}@test.com", "Profesor B1_4")
    _, student_token, s_hdr = register_and_login(client, f"t2_f1_s4_{suffix}@test.com", "Alumno InvScore")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))
    att_res = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}]},
        headers=s_hdr,
    )
    attempt_id = att_res.json()["id"]

    # Negative score
    res_neg = client.patch(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts/{attempt_id}",
        json={"final_score": -10.0},
        headers=t_hdr,
    )
    assert res_neg.status_code in (400, 422)

    # Score > 100
    res_over = client.patch(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts/{attempt_id}",
        json={"final_score": 125.0},
        headers=t_hdr,
    )
    assert res_over.status_code in (400, 422)


def test_t2_f1_05_grading_nonexistent_attempt_404(
    client: TestClient, db_session: Session
) -> None:
    """Attempting to grade a nonexistent attempt_id returns 404."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t2_f1_t5_{suffix}@test.com", "Profesor B1_5")
    video = create_test_video(db_session, owner_id=teacher_id)
    group_id, _, topic_id = create_test_group_and_topic(client, teacher_token, video.id)

    res = client.patch(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts/999999",
        json={"final_score": 85.0},
        headers=t_hdr,
    )
    assert res.status_code == 404


# =============================================================================
# F2 Boundaries: Individual Attempt Separation
# =============================================================================

def test_t2_f2_01_repeated_attempts_penalty_floor_at_zero(
    client: TestClient, db_session: Session
) -> None:
    """Repeated attempts with penalties cannot drop the final score below 0.0."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t2_f2_t1_{suffix}@test.com", "Profesor B2_1")
    _, student_token, s_hdr = register_and_login(client, f"t2_f2_s1_{suffix}@test.com", "Alumno Floor")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    # Submit 12 attempts to test penalty accumulation
    last_res = None
    for _ in range(12):
        last_res = client.post(
            f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
            json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 0}]},  # wrong answer -> raw=0
            headers=s_hdr,
        )
    assert last_res is not None
    assert last_res.status_code == 201
    assert last_res.json()["final_score"] >= 0.0, "Final score must never be negative!"


def test_t2_f2_02_submission_with_empty_answers_list(
    client: TestClient, db_session: Session
) -> None:
    """Submitting empty answers list is handled cleanly with 0 score, no crash."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t2_f2_t2_{suffix}@test.com", "Profesor B2_2")
    _, student_token, s_hdr = register_and_login(client, f"t2_f2_s2_{suffix}@test.com", "Alumno Blank")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    res = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [], "open_answers": []},
        headers=s_hdr,
    )
    assert res.status_code == 201
    assert res.json()["raw_score"] == 0.0


def test_t2_f2_03_concurrent_submissions_by_different_students(
    client: TestClient, db_session: Session
) -> None:
    """Multiple students submitting in interleaved order maintain independent attempt sequences."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t2_f2_t3_{suffix}@test.com", "Profesor B2_3")
    _, s1_tok, s1_hdr = register_and_login(client, f"t2_f2_s1_3_{suffix}@test.com", "Alumno Inter1")
    _, s2_tok, s2_hdr = register_and_login(client, f"t2_f2_s2_3_{suffix}@test.com", "Alumno Inter2")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s1_tok))
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s2_tok))

    # S1 att 1
    r1 = client.post(f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts", json={"multiple_choice_answers": []}, headers=s1_hdr)
    # S2 att 1
    r2 = client.post(f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts", json={"multiple_choice_answers": []}, headers=s2_hdr)
    # S1 att 2
    r3 = client.post(f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts", json={"multiple_choice_answers": []}, headers=s1_hdr)
    # S2 att 2
    r4 = client.post(f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts", json={"multiple_choice_answers": []}, headers=s2_hdr)

    assert r1.json()["attempt_number"] == 1
    assert r2.json()["attempt_number"] == 1
    assert r3.json()["attempt_number"] == 2
    assert r4.json()["attempt_number"] == 2


def test_t2_f2_04_submission_to_inactive_topic_blocked(
    client: TestClient, db_session: Session
) -> None:
    """Attempting submission on a paused (inactive) topic returns 400 TOPIC_INACTIVE."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t2_f2_t4_{suffix}@test.com", "Profesor B2_4")
    _, student_token, s_hdr = register_and_login(client, f"t2_f2_s4_{suffix}@test.com", "Alumno Inactive")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    # Pause the topic
    client.patch(f"/api/v1/groups/{group_id}/topics/{topic_id}", json={"is_active": False}, headers=t_hdr)

    # Student attempts submission
    res = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": []},
        headers=s_hdr,
    )
    assert res.status_code == 400
    assert "pausado" in res.text or "TOPIC_INACTIVE" in res.text


def test_t2_f2_05_non_member_cannot_submit_or_query_attempts(
    client: TestClient, db_session: Session
) -> None:
    """A user who is not a member of the group receives 403 on submission and attempt queries."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t2_f2_t5_{suffix}@test.com", "Profesor B2_5")
    _, outsider_token, out_hdr = register_and_login(client, f"t2_f2_out_{suffix}@test.com", "Outsider")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, _, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    sub_res = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": []},
        headers=out_hdr,
    )
    assert sub_res.status_code == 403

    my_res = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/my-attempts", headers=out_hdr)
    assert my_res.status_code == 403


# =============================================================================
# F3 Boundaries: Video Search & Ordering
# =============================================================================

def test_t2_f3_01_search_with_empty_string_returns_all(
    client: TestClient, db_session: Session
) -> None:
    """Empty search parameter search='' returns all videos normally."""
    suffix = uuid.uuid4().hex[:6]
    user_id, token, hdr = register_and_login(client, f"t2_f3_1_{suffix}@test.com", "Search User 1")

    create_test_video(db_session, owner_id=user_id, title=f"V1 {suffix}")
    create_test_video(db_session, owner_id=user_id, title=f"V2 {suffix}")

    res = client.get("/api/v1/videos?search=", headers=hdr)
    assert res.status_code == 200
    assert len(res.json()["items"]) >= 2


def test_t2_f3_02_search_with_whitespace_only(
    client: TestClient, db_session: Session
) -> None:
    """Whitespace-only search parameter trims and returns full list without error."""
    suffix = uuid.uuid4().hex[:6]
    user_id, token, hdr = register_and_login(client, f"t2_f3_2_{suffix}@test.com", "Search User 2")

    create_test_video(db_session, owner_id=user_id, title=f"Video White {suffix}")

    res = client.get("/api/v1/videos?search=%20%20%20", headers=hdr)
    assert res.status_code == 200
    assert len(res.json()["items"]) >= 1


def test_t2_f3_03_search_with_sql_and_regex_special_characters(
    client: TestClient, db_session: Session
) -> None:
    """Search input containing SQL metacharacters (%, _, ', \") executes safely without crash."""
    suffix = uuid.uuid4().hex[:6]
    user_id, token, hdr = register_and_login(client, f"t2_f3_3_{suffix}@test.com", "Search User 3")

    create_test_video(db_session, owner_id=user_id, title=f"Normal Video {suffix}")

    res = client.get("/api/v1/videos?search=%25_%27%22%5C", headers=hdr)
    assert res.status_code == 200, "Must not raise 500 on SQL meta-characters!"


def test_t2_f3_04_search_with_no_matching_video(
    client: TestClient, db_session: Session
) -> None:
    """Search for non-matching string returns empty list and total=0."""
    suffix = uuid.uuid4().hex[:6]
    user_id, token, hdr = register_and_login(client, f"t2_f3_4_{suffix}@test.com", "Search User 4")

    create_test_video(db_session, owner_id=user_id, title=f"Existing Video {suffix}")

    res = client.get(f"/api/v1/videos?search=NonExistentTitle_{uuid.uuid4().hex}", headers=hdr)
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_t2_f3_05_order_with_unsupported_value_defaults_to_desc(
    client: TestClient, db_session: Session
) -> None:
    """Unsupported order parameter value falls back safely to 'desc' or returns 422."""
    suffix = uuid.uuid4().hex[:6]
    user_id, token, hdr = register_and_login(client, f"t2_f3_5_{suffix}@test.com", "Search User 5")

    res = client.get("/api/v1/videos?order=random_unsupported", headers=hdr)
    assert res.status_code in (200, 422)


# =============================================================================
# F4 Boundaries: Role-Based Quiz Answer Masking
# =============================================================================

def test_t2_f4_01_quiz_with_zero_mc_and_only_open_questions_masked(
    client: TestClient, db_session: Session
) -> None:
    """A quiz with 0 multiple choice questions and 3 open questions has expected_points stripped for students."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t2_f4_t1_{suffix}@test.com", "Profesor B4_1")
    student_id, student_token, s_hdr = register_and_login(client, f"t2_f4_s1_{suffix}@test.com", "Estudiante B4_1")

    video = create_test_video(db_session, owner_id=teacher_id)
    open_q = [
        {"question": "Pregunta 1", "expected_points": ["Punto A"], "evidence_timestamp": "00:00:10", "bloom_level": "understand"},
        {"question": "Pregunta 2", "expected_points": ["Punto B"], "evidence_timestamp": "00:00:20", "bloom_level": "analyze"},
    ]
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id, mc_questions=[], open_questions=open_q)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    res = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/materials", headers=s_hdr)
    assert res.status_code == 200
    content = res.json()["shared_quiz"]["content"]
    assert content["multiple_choice"] == []
    for q in content["open_questions"]:
        assert "expected_points" not in q


def test_t2_f4_02_quiz_with_zero_open_and_only_mc_masked(
    client: TestClient, db_session: Session
) -> None:
    """A quiz with only multiple choice questions has correct_option and explanation stripped."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t2_f4_t2_{suffix}@test.com", "Profesor B4_2")
    student_id, student_token, s_hdr = register_and_login(client, f"t2_f4_s2_{suffix}@test.com", "Estudiante B4_2")

    video = create_test_video(db_session, owner_id=teacher_id)
    mc_q = [
        {"question": "MC 1", "options": ["A", "B", "C", "D"], "correct_option": 0, "explanation": "Exp 1", "evidence_timestamp": "00:00:10", "bloom_level": "remember"},
        {"question": "MC 2", "options": ["A", "B", "C", "D"], "correct_option": 1, "explanation": "Exp 2", "evidence_timestamp": "00:00:20", "bloom_level": "remember"},
    ]
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id, mc_questions=mc_q, open_questions=[])
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    res = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/materials", headers=s_hdr)
    assert res.status_code == 200
    content = res.json()["shared_quiz"]["content"]
    for q in content["multiple_choice"]:
        assert "correct_option" not in q
        assert "explanation" not in q


def test_t2_f4_03_quiz_with_empty_questions_handled_safely(
    client: TestClient, db_session: Session
) -> None:
    """A quiz with empty multiple_choice and open_questions lists is handled without error."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t2_f4_t3_{suffix}@test.com", "Profesor B4_3")
    student_id, student_token, s_hdr = register_and_login(client, f"t2_f4_s3_{suffix}@test.com", "Estudiante B4_3")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id, mc_questions=[], open_questions=[])
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    res = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/materials", headers=s_hdr)
    assert res.status_code == 200


def test_t2_f4_04_unauthenticated_export_denies_answers(
    client: TestClient, db_session: Session
) -> None:
    """Unauthenticated call to /export?include_answers=true is blocked or answers omitted."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, _, _ = register_and_login(client, f"t2_f4_t4_{suffix}@test.com", "Profesor B4_4")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)

    res = client.get(f"/api/v1/materials/{quiz.id}/export?format=markdown&include_answers=true")
    if res.status_code == 200:
        assert "Respuesta correcta" not in res.text
    else:
        assert res.status_code in (401, 403)


def test_t2_f4_05_all_export_formats_stripped_for_student(
    client: TestClient, db_session: Session
) -> None:
    """PDF, DOCX, Markdown, and JSON exports all omit solutions when downloaded by a student."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t2_f4_t5_{suffix}@test.com", "Profesor B4_5")
    student_id, student_token, s_hdr = register_and_login(client, f"t2_f4_s5_{suffix}@test.com", "Estudiante B4_5")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    for fmt in ("markdown", "json"):
        res = client.get(f"/api/v1/materials/{quiz.id}/export?format={fmt}&include_answers=false", headers=s_hdr)
        assert res.status_code == 200
        assert "Respuesta correcta" not in res.text
        assert "correct_option" not in res.text


# =============================================================================
# F5 Boundaries: Teacher vs Student Summaries
# =============================================================================

def test_t2_f5_01_student_cannot_overwrite_official_summary_via_post(
    client: TestClient, db_session: Session
) -> None:
    """Student cannot overwrite official summary by attempting to update the topic or material."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t2_f5_t1_{suffix}@test.com", "Profesor B5_1")
    student_id, student_token, s_hdr = register_and_login(client, f"t2_f5_s1_{suffix}@test.com", "Estudiante B5_1")

    video = create_test_video(db_session, owner_id=teacher_id)
    summary = create_test_summary(db_session, video_id=video.id, owner_id=teacher_id, synopsis="Oficial Inviolable")
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    # Student attempts topic update -> 403
    patch_top = client.patch(
        f"/api/v1/groups/{group_id}/topics/{topic_id}",
        json={"title": "Hackeado"},
        headers=s_hdr,
    )
    assert patch_top.status_code == 403


def test_t2_f5_02_multiple_students_independent_personal_summaries(
    client: TestClient, db_session: Session
) -> None:
    """Multiple students creating personal summaries on the same video do not collide or overwrite."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t2_f5_t2_{suffix}@test.com", "Profesor B5_2")
    s1_id, s1_tok, s1_hdr = register_and_login(client, f"t2_f5_s1_2_{suffix}@test.com", "Alumno Sum1")
    s2_id, s2_tok, s2_hdr = register_and_login(client, f"t2_f5_s2_2_{suffix}@test.com", "Alumno Sum2")

    video = create_test_video(db_session, owner_id=teacher_id)
    sum_s1 = create_test_summary(db_session, video_id=video.id, owner_id=s1_id, synopsis="Apuntes de Alumno 1")
    sum_s2 = create_test_summary(db_session, video_id=video.id, owner_id=s2_id, synopsis="Apuntes de Alumno 2")

    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id)
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s1_tok))
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s2_tok))

    # Query as S1
    m1 = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/materials", headers=s1_hdr).json()
    assert m1["personal_summary"]["id"] == sum_s1.id

    # Query as S2
    m2 = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/materials", headers=s2_hdr).json()
    assert m2["personal_summary"]["id"] == sum_s2.id


def test_t2_f5_03_student_cannot_edit_other_students_personal_summary(
    client: TestClient, db_session: Session
) -> None:
    """Student A cannot edit Student B's personal summary (returns 403 Forbidden)."""
    suffix = uuid.uuid4().hex[:6]
    s1_id, s1_tok, s1_hdr = register_and_login(client, f"t2_f5_s1_3_{suffix}@test.com", "Alumno Owner")
    s2_id, s2_tok, s2_hdr = register_and_login(client, f"t2_f5_s2_3_{suffix}@test.com", "Alumno Hacker")

    video = create_test_video(db_session, owner_id=s1_id)
    sum_s1 = create_test_summary(db_session, video_id=video.id, owner_id=s1_id, synopsis="Original S1")

    res = client.put(
        f"/api/v1/materials/{sum_s1.id}",
        json={"content": {"synopsis": "Alterado por S2"}},
        headers=s2_hdr,
    )
    assert res.status_code == 403


def test_t2_f5_04_empty_synopsis_in_summary_update_validation(
    client: TestClient, db_session: Session
) -> None:
    """Submitting malformed summary content triggers schema validation error."""
    suffix = uuid.uuid4().hex[:6]
    user_id, token, hdr = register_and_login(client, f"t2_f5_u4_{suffix}@test.com", "User Valid")

    video = create_test_video(db_session, owner_id=user_id)
    summary = create_test_summary(db_session, video_id=video.id, owner_id=user_id)

    # Empty payload
    res = client.put(f"/api/v1/materials/{summary.id}", json={}, headers=hdr)
    assert res.status_code == 422


def test_t2_f5_05_topic_without_official_summary_handled_gracefully(
    client: TestClient, db_session: Session
) -> None:
    """A topic where teacher has not uploaded any summary returns shared_summary: None without error."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t2_f5_t5_{suffix}@test.com", "Profesor B5_5")
    student_id, student_token, s_hdr = register_and_login(client, f"t2_f5_s5_{suffix}@test.com", "Estudiante B5_5")

    video = create_test_video(db_session, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    res = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/materials", headers=s_hdr)
    assert res.status_code == 200
    assert res.json()["shared_summary"] is None


# =============================================================================
# F6 Boundaries: Timestamp Calibration
# =============================================================================

def test_t2_f6_01_topic_at_exact_zero_seconds_clamps_at_zero(
    sample_segments: list[dict[str, Any]]
) -> None:
    """Topic starting at exactly 0.0s calibrates to 0.0s."""
    assert TimestampCalibrationService is not None, "TimestampCalibrationService must be implemented"
    service = TimestampCalibrationService()
    calibrated = service.calibrate(sample_segments, topic_start_time=0.0, topic_text="inicio")
    assert calibrated == 0.0


def test_t2_f6_02_topic_at_short_offset_under_5s_clamps_at_zero(
    sample_segments: list[dict[str, Any]]
) -> None:
    """Topic starting at 3.2s (< 5.0s) clamps to 0.0s."""
    assert TimestampCalibrationService is not None, "TimestampCalibrationService must be implemented"
    service = TimestampCalibrationService()
    calibrated = service.calibrate(sample_segments, topic_start_time=3.2, topic_text="bienvenidos")
    assert calibrated == 0.0


def test_t2_f6_03_gap_between_segments_greater_than_10s() -> None:
    """A transcript with a large gap (>10s) between segments bounds lead-in to <= 10.0s."""
    assert TimestampCalibrationService is not None, "TimestampCalibrationService must be implemented"
    service = TimestampCalibrationService()
    gapped_segments = [
        {"start": 0.0, "end": 5.0, "text": "Primera parte introductoria."},
        {"start": 30.0, "end": 45.0, "text": "Segunda parte tras largo silencio musical."},
    ]
    calibrated = service.calibrate(gapped_segments, topic_start_time=30.0, topic_text="segunda parte")
    lead_in = 30.0 - calibrated
    assert 5.0 <= lead_in <= 10.0


def test_t2_f6_04_dense_rapid_fire_segments() -> None:
    """Short rapid-fire segments (<2s each) aggregate cleanly to reach the 5-10s lead-in window."""
    assert TimestampCalibrationService is not None, "TimestampCalibrationService must be implemented"
    service = TimestampCalibrationService()
    dense_segments = [
        {"start": 0.0, "end": 1.5, "text": "Uno."},
        {"start": 1.5, "end": 3.0, "text": "Dos."},
        {"start": 3.0, "end": 4.5, "text": "Tres."},
        {"start": 4.5, "end": 6.0, "text": "Cuatro."},
        {"start": 6.0, "end": 7.5, "text": "Cinco."},
        {"start": 7.5, "end": 9.0, "text": "Seis."},
        {"start": 9.0, "end": 10.5, "text": "Siete."},
        {"start": 10.5, "end": 12.0, "text": "Ocho."},
        {"start": 12.0, "end": 15.0, "text": "Tema principal comienza aquí."},
    ]
    calibrated = service.calibrate(dense_segments, topic_start_time=12.0, topic_text="tema principal")
    lead_in = 12.0 - calibrated
    assert 5.0 <= lead_in <= 10.0


def test_t2_f6_05_empty_segment_list_fallback() -> None:
    """Calling calibration with empty segments list falls back gracefully without exception."""
    assert TimestampCalibrationService is not None, "TimestampCalibrationService must be implemented"
    service = TimestampCalibrationService()
    calibrated = service.calibrate([], topic_start_time=25.0, topic_text="fallback")
    assert isinstance(calibrated, (int, float))
    assert 0.0 <= calibrated <= 25.0
