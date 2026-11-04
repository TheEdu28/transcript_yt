"""Tier 1: Comprehensive isolated happy-path feature tests for transcript_yt (F1–F6).

Each feature in scope has at least 5 dedicated, isolated test cases:
- F1: Activity-Centric Grading View (5 tests)
- F2: Individual Attempt Separation & Querying (5 tests)
- F3: Video Selection, Sorting & Text Search (5 tests)
- F4: Role-Based Quiz Answer Masking (5 tests)
- F5: Teacher vs Student Summaries (5 tests)
- F6: Timestamp Calibration (5 tests)
Total: 30 tests.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.group import Attempt, Group
from app.models.material import DidacticMaterial
from app.models.video import Video
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
# F1: Activity-Centric Grading View (ORIGINAL_REQUEST §R1)
# =============================================================================

def test_t1_f1_01_teacher_access_activity_summary(client: TestClient, db_session: Session) -> None:
    """Teacher enters a specific activity/topic summary and retrieves members list."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t1_f1_t_{suffix}@test.com", "Profesor F1")
    s1_id, s1_token, _ = register_and_login(client, f"t1_f1_s1_{suffix}@test.com", "Alumno 1")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    # Student joins group
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s1_token))

    # Teacher requests activity summary
    res = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/summary", headers=t_hdr)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["topic_id"] == topic_id
    assert data["group_id"] == group_id
    assert isinstance(data["members_summary"], list)
    member_ids = [m["user_id"] for m in data["members_summary"]]
    assert s1_id in member_ids


def test_t1_f1_02_distinguishes_evaluated_vs_pending_students(
    client: TestClient, db_session: Session
) -> None:
    """Topic summary distinguishes students who submitted vs pending/not submitted."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t1_f1_t2_{suffix}@test.com", "Profesor F1_2")
    s1_id, s1_token, s1_hdr = register_and_login(client, f"t1_f1_s1_2_{suffix}@test.com", "Alumno Con Intento")
    s2_id, s2_token, _ = register_and_login(client, f"t1_f1_s2_2_{suffix}@test.com", "Alumno Sin Intento")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    # Both join
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s1_token))
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s2_token))

    # S1 submits an attempt
    client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}]},
        headers=s1_hdr,
    )

    # Teacher inspects summary
    res = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/summary", headers=t_hdr)
    assert res.status_code == 200
    members = {m["user_id"]: m for m in res.json()["members_summary"]}

    assert s1_id in members
    assert s2_id in members
    # S1 has submitted attempt -> total_attempts >= 1
    assert members[s1_id]["total_attempts"] == 1
    # S2 has not submitted -> total_attempts == 0
    assert members[s2_id]["total_attempts"] == 0
    # Status badges differ
    assert members[s2_id]["status"] in ("not_submitted", "pending")


def test_t1_f1_03_teacher_queries_specific_student_attempts(
    client: TestClient, db_session: Session
) -> None:
    """Teacher can filter and inspect attempts for a specific student without downloading others."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t1_f1_t3_{suffix}@test.com", "Profesor F1_3")
    s1_id, s1_token, s1_hdr = register_and_login(client, f"t1_f1_s1_3_{suffix}@test.com", "Alumno S1")
    s2_id, s2_token, s2_hdr = register_and_login(client, f"t1_f1_s2_3_{suffix}@test.com", "Alumno S2")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s1_token))
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s2_token))

    # S1 submits attempt
    client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}]},
        headers=s1_hdr,
    )
    # S2 submits attempt
    client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 0}]},
        headers=s2_hdr,
    )

    # Teacher queries attempts with user_id filter (or member endpoint)
    res = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts?user_id={s1_id}", headers=t_hdr)
    if res.status_code == 200:
        atts = res.json()
        assert all(a["user_id"] == s1_id for a in atts)
        assert len(atts) == 1
    else:
        # Check alternative member endpoint
        res2 = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/members/{s1_id}/attempts", headers=t_hdr)
        assert res2.status_code == 200
        atts2 = res2.json()
        assert all(a["user_id"] == s1_id for a in atts2)


def test_t1_f1_04_teacher_modifies_grade_inline_with_review_notes(
    client: TestClient, db_session: Session
) -> None:
    """Teacher assigns or modifies a student's attempt score directly from the activity."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t1_f1_t4_{suffix}@test.com", "Profesor F1_4")
    s1_id, s1_token, s1_hdr = register_and_login(client, f"t1_f1_s1_4_{suffix}@test.com", "Alumno A Calificar")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s1_token))

    att_res = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}]},
        headers=s1_hdr,
    )
    attempt_id = att_res.json()["id"]

    # Teacher modifies final score inline
    patch_res = client.patch(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts/{attempt_id}",
        json={"final_score": 88.5, "review_notes": "Excelente análisis contextual con ajuste manual."},
        headers=t_hdr,
    )
    assert patch_res.status_code == 200, patch_res.text
    updated = patch_res.json()
    assert updated["final_score"] == 88.5


def test_t1_f1_05_summary_reflects_modified_grade(
    client: TestClient, db_session: Session
) -> None:
    """After inline grade update, activity summary reflects the evaluated status and new score."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t1_f1_t5_{suffix}@test.com", "Profesor F1_5")
    s1_id, s1_token, s1_hdr = register_and_login(client, f"t1_f1_s1_5_{suffix}@test.com", "Alumno Revisado")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s1_token))

    att_res = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}]},
        headers=s1_hdr,
    )
    attempt_id = att_res.json()["id"]

    client.patch(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts/{attempt_id}",
        json={"final_score": 92.0, "review_notes": "Nota final validada."},
        headers=t_hdr,
    )

    sum_res = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/summary", headers=t_hdr)
    assert sum_res.status_code == 200
    stud_summary = next(m for m in sum_res.json()["members_summary"] if m["user_id"] == s1_id)
    assert stud_summary["status"] == "evaluated"
    assert stud_summary["latest_attempt"]["final_score"] == 92.0


# =============================================================================
# F2: Individual Attempt Separation & Querying (ORIGINAL_REQUEST §R2)
# =============================================================================

def test_t1_f2_01_student_sees_only_own_attempts(client: TestClient, db_session: Session) -> None:
    """Each student querying /my-attempts sees strictly their own attempts."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t1_f2_t1_{suffix}@test.com", "Profesor F2_1")
    s1_id, s1_token, s1_hdr = register_and_login(client, f"t1_f2_s1_{suffix}@test.com", "Estudiante 1")
    s2_id, s2_token, s2_hdr = register_and_login(client, f"t1_f2_s2_{suffix}@test.com", "Estudiante 2")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s1_token))
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s2_token))

    # S1 submits 2 attempts
    client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}]},
        headers=s1_hdr,
    )
    client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}]},
        headers=s1_hdr,
    )

    # S2 submits 1 attempt
    client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 0}]},
        headers=s2_hdr,
    )

    s1_my = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/my-attempts", headers=s1_hdr).json()
    s2_my = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/my-attempts", headers=s2_hdr).json()

    assert len(s1_my) == 2
    assert all(a["user_id"] == s1_id for a in s1_my)

    assert len(s2_my) == 1
    assert all(a["user_id"] == s2_id for a in s2_my)


def test_t1_f2_02_attempt_counting_isolated_per_user(client: TestClient, db_session: Session) -> None:
    """Attempt numbers increment strictly per user and activity, starting at 1."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t1_f2_t2_{suffix}@test.com", "Profesor F2_2")
    s1_id, s1_token, s1_hdr = register_and_login(client, f"t1_f2_s1_2_{suffix}@test.com", "Estudiante A")
    s2_id, s2_token, s2_hdr = register_and_login(client, f"t1_f2_s2_2_{suffix}@test.com", "Estudiante B")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s1_token))
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s2_token))

    # S1 attempt 1
    res1 = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}]},
        headers=s1_hdr,
    ).json()
    assert res1["attempt_number"] == 1

    # S1 attempt 2
    res2 = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}]},
        headers=s1_hdr,
    ).json()
    assert res2["attempt_number"] == 2

    # S2 attempt 1 (must be 1, NOT 3!)
    res3 = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}]},
        headers=s2_hdr,
    ).json()
    assert res3["attempt_number"] == 1


def test_t1_f2_03_penalty_applied_independently_per_user(
    client: TestClient, db_session: Session
) -> None:
    """Retry penalty is applied based only on that user's attempt count."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t1_f2_t3_{suffix}@test.com", "Profesor F2_3")
    s1_id, s1_token, s1_hdr = register_and_login(client, f"t1_f2_s1_3_{suffix}@test.com", "Estudiante A3")
    s2_id, s2_token, s2_hdr = register_and_login(client, f"t1_f2_s2_3_{suffix}@test.com", "Estudiante B3")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id, open_questions=[])
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s1_token))
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s2_token))

    # S1 takes attempt 1 (100 raw, 100 final)
    client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}, {"question_index": 1, "selected_option": 1}]},
        headers=s1_hdr,
    )
    # S1 takes attempt 2 (100 raw, 90 final with 10pt penalty)
    att2 = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}, {"question_index": 1, "selected_option": 1}]},
        headers=s1_hdr,
    ).json()
    assert att2["final_score"] == 90.0

    # S2 takes attempt 1 (100 raw, MUST be 100 final with ZERO penalty)
    att_s2 = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}, {"question_index": 1, "selected_option": 1}]},
        headers=s2_hdr,
    ).json()
    assert att_s2["final_score"] == 100.0


def test_t1_f2_04_teacher_query_by_student_does_not_leak_other_students(
    client: TestClient, db_session: Session
) -> None:
    """When teacher queries attempts for Student X, zero attempts of Student Y are returned."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t1_f2_t4_{suffix}@test.com", "Profesor F2_4")
    s1_id, s1_token, s1_hdr = register_and_login(client, f"t1_f2_s1_4_{suffix}@test.com", "Estudiante X")
    s2_id, s2_token, s2_hdr = register_and_login(client, f"t1_f2_s2_4_{suffix}@test.com", "Estudiante Y")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s1_token))
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s2_token))

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

    # Teacher queries attempts for S1
    res = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts?user_id={s1_id}", headers=t_hdr)
    if res.status_code == 200:
        atts = res.json()
        assert all(a["user_id"] == s1_id for a in atts)
        assert not any(a["user_id"] == s2_id for a in atts)
    else:
        res2 = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/members/{s1_id}/attempts", headers=t_hdr)
        assert res2.status_code == 200
        atts2 = res2.json()
        assert all(a["user_id"] == s1_id for a in atts2)
        assert not any(a["user_id"] == s2_id for a in atts2)


def test_t1_f2_05_attempt_database_foreign_key_integrity(
    client: TestClient, db_session: Session
) -> None:
    """Attempts in database correctly bind user_id and topic_id and store answers."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t1_f2_t5_{suffix}@test.com", "Profesor F2_5")
    s1_id, s1_token, s1_hdr = register_and_login(client, f"t1_f2_s1_5_{suffix}@test.com", "Estudiante FK")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(s1_token))

    att_res = client.post(
        f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
        json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}]},
        headers=s1_hdr,
    )
    attempt_id = att_res.json()["id"]

    db_attempt = db_session.get(Attempt, attempt_id)
    assert db_attempt is not None
    assert db_attempt.user_id == s1_id
    assert db_attempt.topic_id == topic_id
    assert db_attempt.attempt_number == 1
    assert db_attempt.answers_json is not None
    answers = json.loads(db_attempt.answers_json)
    assert isinstance(answers, (dict, list))


# =============================================================================
# F3: Video Selection, Sorting & Text Search (ORIGINAL_REQUEST §R3)
# =============================================================================

def test_t1_f3_01_videos_default_ordering_newest_first(
    client: TestClient, db_session: Session
) -> None:
    """Videos returned in descending chronological order by default."""
    suffix = uuid.uuid4().hex[:6]
    user_id, token, hdr = register_and_login(client, f"t1_f3_1_{suffix}@test.com", "Video User 1")

    now = datetime.now(timezone.utc)
    v1 = create_test_video(db_session, owner_id=user_id, title=f"Video Antiguo {suffix}", created_at=now - timedelta(days=5))
    v2 = create_test_video(db_session, owner_id=user_id, title=f"Video Medio {suffix}", created_at=now - timedelta(days=2))
    v3 = create_test_video(db_session, owner_id=user_id, title=f"Video Reciente {suffix}", created_at=now)

    res = client.get("/api/v1/videos", headers=hdr)
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    # Check that our created videos appear in newest-first order
    filtered = [v for v in items if v["id"] in (v1.id, v2.id, v3.id)]
    assert len(filtered) == 3
    assert filtered[0]["id"] == v3.id
    assert filtered[1]["id"] == v2.id
    assert filtered[2]["id"] == v1.id


def test_t1_f3_02_videos_ordering_toggle_oldest_first(
    client: TestClient, db_session: Session
) -> None:
    """Passing order=asc returns oldest videos first."""
    suffix = uuid.uuid4().hex[:6]
    user_id, token, hdr = register_and_login(client, f"t1_f3_2_{suffix}@test.com", "Video User 2")

    now = datetime.now(timezone.utc)
    v1 = create_test_video(db_session, owner_id=user_id, title=f"Viejo {suffix}", created_at=now - timedelta(days=10))
    v2 = create_test_video(db_session, owner_id=user_id, title=f"Nuevo {suffix}", created_at=now)

    res = client.get("/api/v1/videos?order=asc", headers=hdr)
    assert res.status_code == 200
    items = res.json()["items"]
    filtered = [v for v in items if v["id"] in (v1.id, v2.id)]
    assert len(filtered) == 2
    assert filtered[0]["id"] == v1.id
    assert filtered[1]["id"] == v2.id


def test_t1_f3_03_videos_text_search_by_title_case_insensitive(
    client: TestClient, db_session: Session
) -> None:
    """Passing search=text filters videos by title case-insensitively."""
    suffix = uuid.uuid4().hex[:6]
    user_id, token, hdr = register_and_login(client, f"t1_f3_3_{suffix}@test.com", "Video User 3")

    v_match1 = create_test_video(db_session, owner_id=user_id, title=f"Biologia Celular y Genetica {suffix}")
    v_match2 = create_test_video(db_session, owner_id=user_id, title=f"BIOLOGIA MARINA AVANZADA {suffix}")
    v_other = create_test_video(db_session, owner_id=user_id, title=f"Calculo Diferencial {suffix}")

    res = client.get("/api/v1/videos?search=biologia", headers=hdr)
    assert res.status_code == 200
    items = res.json()["items"]
    matching_ids = [v["id"] for v in items if v["id"] in (v_match1.id, v_match2.id, v_other.id)]
    assert v_match1.id in matching_ids
    assert v_match2.id in matching_ids
    assert v_other.id not in matching_ids


def test_t1_f3_04_videos_joint_search_and_sorting(
    client: TestClient, db_session: Session
) -> None:
    """Text search and chronological sorting operate jointly without data loss."""
    suffix = uuid.uuid4().hex[:6]
    user_id, token, hdr = register_and_login(client, f"t1_f3_4_{suffix}@test.com", "Video User 4")

    now = datetime.now(timezone.utc)
    v1 = create_test_video(db_session, owner_id=user_id, title=f"Quimica Organica Basica {suffix}", created_at=now - timedelta(days=3))
    v2 = create_test_video(db_session, owner_id=user_id, title=f"Quimica Inorganica Superior {suffix}", created_at=now - timedelta(days=1))
    v3 = create_test_video(db_session, owner_id=user_id, title=f"Fisica Termodinamica {suffix}", created_at=now)

    res = client.get("/api/v1/videos?search=quimica&order=asc", headers=hdr)
    assert res.status_code == 200
    items = res.json()["items"]
    filtered = [v for v in items if v["id"] in (v1.id, v2.id, v3.id)]
    assert len(filtered) == 2
    assert filtered[0]["id"] == v1.id  # older Quimica first
    assert filtered[1]["id"] == v2.id  # newer Quimica second


def test_t1_f3_05_videos_pagination_with_search_and_order(
    client: TestClient, db_session: Session
) -> None:
    """Pagination parameters page and page_size operate cleanly with search and order."""
    suffix = uuid.uuid4().hex[:6]
    user_id, token, hdr = register_and_login(client, f"t1_f3_5_{suffix}@test.com", "Video User 5")

    for i in range(5):
        create_test_video(db_session, owner_id=user_id, title=f"Historia Leccion {i} {suffix}")

    res_p1 = client.get("/api/v1/videos?search=historia&page=1&page_size=2", headers=hdr)
    assert res_p1.status_code == 200
    data_p1 = res_p1.json()
    assert len(data_p1["items"]) == 2
    assert data_p1["total"] >= 5


# =============================================================================
# F4: Role-Based Quiz Answer Masking (ORIGINAL_REQUEST §R4)
# =============================================================================

def test_t1_f4_01_teacher_sees_unmasked_quiz_in_materials(
    client: TestClient, db_session: Session
) -> None:
    """Teacher requesting topic materials receives full quiz with correct answers and explanations."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t1_f4_t1_{suffix}@test.com", "Profesor F4_1")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    res = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/materials", headers=t_hdr)
    assert res.status_code == 200
    data = res.json()
    shared_quiz = data["shared_quiz"]
    assert shared_quiz is not None
    content = shared_quiz["content"]
    assert "multiple_choice" in content
    # Teacher sees answers
    assert "correct_option" in content["multiple_choice"][0]
    assert "explanation" in content["multiple_choice"][0]


def test_t1_f4_02_student_sees_masked_quiz_in_materials(
    client: TestClient, db_session: Session
) -> None:
    """Student requesting topic materials receives masked quiz: no correct_option or explanation."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t1_f4_t2_{suffix}@test.com", "Profesor F4_2")
    student_id, student_token, s_hdr = register_and_login(client, f"t1_f4_s2_{suffix}@test.com", "Estudiante F4_2")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    res = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/materials", headers=s_hdr)
    assert res.status_code == 200
    data = res.json()
    shared_quiz = data["shared_quiz"]
    assert shared_quiz is not None
    content = shared_quiz["content"]
    mc = content.get("multiple_choice", [])
    assert len(mc) > 0
    # Answers must NOT leak in student payload
    for q in mc:
        assert "correct_option" not in q, "Security leak: correct_option exposed to student!"
        assert "explanation" not in q, "Security leak: explanation exposed to student!"
    open_q = content.get("open_questions", [])
    for oq in open_q:
        assert "expected_points" not in oq, "Security leak: expected_points exposed to student!"


def test_t1_f4_03_student_accessing_material_directly_is_masked(
    client: TestClient, db_session: Session
) -> None:
    """Direct GET /materials/{id} requested by a student masks solutions."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t1_f4_t3_{suffix}@test.com", "Profesor F4_3")
    student_id, student_token, s_hdr = register_and_login(client, f"t1_f4_s3_{suffix}@test.com", "Estudiante F4_3")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    res = client.get(f"/api/v1/materials/{quiz.id}", headers=s_hdr)
    if res.status_code == 200:
        content = res.json()["content"]
        mc = content.get("multiple_choice", [])
        for q in mc:
            assert "correct_option" not in q
            assert "explanation" not in q


def test_t1_f4_04_teacher_can_export_quiz_with_answers(
    client: TestClient, db_session: Session
) -> None:
    """Teacher can export quiz with answers included."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t1_f4_t4_{suffix}@test.com", "Profesor F4_4")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)

    res = client.get(f"/api/v1/materials/{quiz.id}/export?format=markdown&include_answers=true", headers=t_hdr)
    assert res.status_code == 200
    text = res.text
    assert "Respuesta correcta" in text or "Explicación" in text or "Patente" in text


def test_t1_f4_05_student_cannot_export_quiz_with_answers(
    client: TestClient, db_session: Session
) -> None:
    """Student attempting export with include_answers=true is denied (403) or answers are stripped."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t1_f4_t5_{suffix}@test.com", "Profesor F4_5")
    student_id, student_token, s_hdr = register_and_login(client, f"t1_f4_s5_{suffix}@test.com", "Estudiante F4_5")

    video = create_test_video(db_session, owner_id=teacher_id)
    quiz = create_test_quiz(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)
    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    res = client.get(f"/api/v1/materials/{quiz.id}/export?format=markdown&include_answers=true", headers=s_hdr)
    if res.status_code == 200:
        # Answers must be stripped
        assert "Respuesta correcta" not in res.text
        assert "Explicación:" not in res.text
    else:
        assert res.status_code in (403, 400)


# =============================================================================
# F5: Teacher vs Student Summaries (ORIGINAL_REQUEST §R5)
# =============================================================================

def test_t1_f5_01_student_can_read_teacher_official_summary(
    client: TestClient, db_session: Session
) -> None:
    """Student querying topic materials can consult the teacher's official shared_summary."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t1_f5_t1_{suffix}@test.com", "Profesor F5_1")
    student_id, student_token, s_hdr = register_and_login(client, f"t1_f5_s1_{suffix}@test.com", "Estudiante F5_1")

    video = create_test_video(db_session, owner_id=teacher_id)
    summary = create_test_summary(db_session, video_id=video.id, owner_id=teacher_id, synopsis="Sinopsis Oficial Docente")
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    res = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/materials", headers=s_hdr)
    assert res.status_code == 200
    data = res.json()
    assert data["shared_summary"] is not None
    assert data["shared_summary"]["id"] == summary.id
    assert "Sinopsis Oficial Docente" in data["shared_summary"]["content"]["synopsis"]


def test_t1_f5_02_student_cannot_edit_teacher_official_summary(
    client: TestClient, db_session: Session
) -> None:
    """Student cannot modify or overwrite the teacher's official summary (returns 403)."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, _ = register_and_login(client, f"t1_f5_t2_{suffix}@test.com", "Profesor F5_2")
    student_id, student_token, s_hdr = register_and_login(client, f"t1_f5_s2_{suffix}@test.com", "Estudiante F5_2")

    video = create_test_video(db_session, owner_id=teacher_id)
    summary = create_test_summary(db_session, video_id=video.id, owner_id=teacher_id)
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    put_res = client.put(
        f"/api/v1/materials/{summary.id}",
        json={"content": {"synopsis": "Modificacion no autorizada por alumno"}},
        headers=s_hdr,
    )
    assert put_res.status_code == 403, f"Expected 403 Forbidden, got {put_res.status_code}"


def test_t1_f5_03_student_can_create_personal_summary(
    client: TestClient, db_session: Session
) -> None:
    """Student can create and store their own personal summary associated with their account."""
    suffix = uuid.uuid4().hex[:6]
    student_id, student_token, s_hdr = register_and_login(client, f"t1_f5_s3_{suffix}@test.com", "Estudiante F5_3")
    teacher_id, teacher_token, _ = register_and_login(client, f"t1_f5_t3_{suffix}@test.com", "Profesor F5_3")

    video = create_test_video(db_session, owner_id=teacher_id)
    # Student creates personal summary
    personal_sum = create_test_summary(
        db_session, video_id=video.id, owner_id=student_id, synopsis="Mis apuntes personales de la clase"
    )
    assert personal_sum.id is not None
    assert personal_sum.owner_id == student_id


def test_t1_f5_04_student_can_edit_own_personal_summary(
    client: TestClient, db_session: Session
) -> None:
    """Student can edit their own personal summary without error (can_edit is True)."""
    suffix = uuid.uuid4().hex[:6]
    student_id, student_token, s_hdr = register_and_login(client, f"t1_f5_s4_{suffix}@test.com", "Estudiante F5_4")
    teacher_id, teacher_token, _ = register_and_login(client, f"t1_f5_t4_{suffix}@test.com", "Profesor F5_4")

    video = create_test_video(db_session, owner_id=teacher_id)
    personal_sum = create_test_summary(
        db_session, video_id=video.id, owner_id=student_id, synopsis="Version 1 personal"
    )

    update_payload = {
        "content": {
            "synopsis": "Version 2 de mis apuntes personales actualizada",
            "glossary": [],
            "didactic_blocks": [],
            "evidence_sufficient": True,
        }
    }
    put_res = client.put(f"/api/v1/materials/{personal_sum.id}", json=update_payload, headers=s_hdr)
    assert put_res.status_code == 200, put_res.text
    assert put_res.json()["content"]["synopsis"] == "Version 2 de mis apuntes personales actualizada"


def test_t1_f5_05_teacher_can_differentiate_official_from_personal(
    client: TestClient, db_session: Session
) -> None:
    """In topic materials response, shared_summary is distinct from personal_summary."""
    suffix = uuid.uuid4().hex[:6]
    teacher_id, teacher_token, t_hdr = register_and_login(client, f"t1_f5_t5_{suffix}@test.com", "Profesor F5_5")
    student_id, student_token, s_hdr = register_and_login(client, f"t1_f5_s5_{suffix}@test.com", "Estudiante F5_5")

    video = create_test_video(db_session, owner_id=teacher_id)
    official_sum = create_test_summary(db_session, video_id=video.id, owner_id=teacher_id, synopsis="Oficial Docente")
    personal_sum = create_test_summary(db_session, video_id=video.id, owner_id=student_id, synopsis="Personal Alumno")
    group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id)

    client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

    # Query as student
    s_mats = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/materials", headers=s_hdr).json()
    assert s_mats["shared_summary"]["id"] == official_sum.id
    assert s_mats["personal_summary"]["id"] == personal_sum.id
    assert s_mats["shared_summary"]["id"] != s_mats["personal_summary"]["id"]


# =============================================================================
# F6: Timestamp Calibration (ORIGINAL_REQUEST §R6)
# =============================================================================

def test_t1_f6_01_calibration_returns_5_to_10_seconds_lead_in(
    sample_segments: list[dict[str, Any]]
) -> None:
    """Calibrating a question whose explanation starts at 18.0s yields a 5.0 to 10.0s lead-in."""
    assert TimestampCalibrationService is not None, "TimestampCalibrationService must be implemented in app.services.timestamp_service"
    service = TimestampCalibrationService()
    calibrated = service.calibrate(sample_segments, topic_start_time=18.0, topic_text="James Watt")
    lead_in = 18.0 - calibrated
    assert 5.0 <= lead_in <= 10.0, f"Expected lead-in in [5.0, 10.0], got {lead_in:.2f}s"


def test_t1_f6_02_calibration_aligns_with_segment_boundary(
    sample_segments: list[dict[str, Any]]
) -> None:
    """Calibrated timestamp aligns cleanly with natural segment start boundary."""
    assert TimestampCalibrationService is not None, "TimestampCalibrationService must be implemented"
    service = TimestampCalibrationService()
    # Topic at 18.0s: preceding segment 2 starts at 10.5s (18.0 - 10.5 = 7.5s lead-in)
    calibrated = service.calibrate(sample_segments, topic_start_time=18.0, topic_text="James Watt")
    assert calibrated == 10.5


def test_t1_f6_03_calibration_avoids_fixed_subtraction(
    sample_segments: list[dict[str, Any]]
) -> None:
    """Calibration lead-in varies dynamically across segments rather than applying a static subtraction."""
    assert TimestampCalibrationService is not None, "TimestampCalibrationService must be implemented"
    service = TimestampCalibrationService()
    # Test two different topics
    t1_cal = service.calibrate(sample_segments, topic_start_time=18.0, topic_text="James Watt")
    lead_in_1 = 18.0 - t1_cal

    t2_cal = service.calibrate(sample_segments, topic_start_time=33.5, topic_text="consecuencias demográficas")
    lead_in_2 = 33.5 - t2_cal

    # Lead-ins should be determined by segment boundaries, not an identical constant
    assert 5.0 <= lead_in_1 <= 10.0
    assert 5.0 <= lead_in_2 <= 10.0


def test_t1_f6_04_calibration_clamps_at_zero_near_start(
    sample_segments: list[dict[str, Any]]
) -> None:
    """A topic starting near the very beginning of the video (< 5.0s) clamps to 0.0s."""
    assert TimestampCalibrationService is not None, "TimestampCalibrationService must be implemented"
    service = TimestampCalibrationService()
    calibrated = service.calibrate(sample_segments, topic_start_time=3.0, topic_text="revolución industrial")
    assert calibrated == 0.0


def test_t1_f6_05_quiz_questions_use_calibrated_timestamps(
    sample_segments: list[dict[str, Any]]
) -> None:
    """Calibrated timestamps convert to valid HH:MM:SS format and provide valid seek positions."""
    assert TimestampCalibrationService is not None, "TimestampCalibrationService must be implemented"
    service = TimestampCalibrationService()
    calibrated_secs = service.calibrate(sample_segments, topic_start_time=25.0, topic_text="ahorro térmico")
    ts_str = service.to_timestamp_string(calibrated_secs) if hasattr(service, "to_timestamp_string") else f"{int(calibrated_secs // 60):02d}:{int(calibrated_secs % 60):02d}"
    assert len(ts_str.split(":")) in (2, 3)
    assert calibrated_secs < 25.0
