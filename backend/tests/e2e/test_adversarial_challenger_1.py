"""Adversarial Challenge Test Suite by Challenger 1.

Stress-tests requirements R1–R6:
1. Timestamp calibration extreme edge cases, boundaries, zero offsets, gaps, and malformed inputs (R6).
2. Role permissions and quiz answer leakage / direct export exploits (R4).
3. Activity grading and attempt isolation across multiple students and boundary scores (R1 & R2).
4. Video search and sorting with SQL/regex injection characters, unicode, and extreme query lengths (R3).
5. Teacher vs student summary isolation and unauthorized overwrites/edits (R5).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.material import DidacticMaterial
from app.services.timestamp_service import TimestampCalibrationService
from tests.e2e.conftest import (
    auth_header,
    create_test_group_and_topic,
    create_test_quiz,
    create_test_summary,
    create_test_video,
    register_and_login,
)


# =============================================================================
# 1. TIMESTAMP CALIBRATION STRESS HARNESS (R6)
# =============================================================================

class TestTimestampCalibrationAdversarial:
    """Stress-test TimestampCalibrationService against edge cases, gaps, and extreme boundaries."""

    @pytest.fixture
    def service(self) -> TimestampCalibrationService:
        return TimestampCalibrationService()

    def test_clamp_negative_or_zero_start_times(self, service: TimestampCalibrationService) -> None:
        """Negative and zero start times must safely clamp to 0.0s."""
        segments = [
            {"start": 0.0, "end": 10.0, "text": "Introducción."},
            {"start": 10.0, "end": 20.0, "text": "Tema principal."},
        ]
        assert service.calibrate(segments, topic_start_time=0.0) == 0.0
        assert service.calibrate(segments, topic_start_time=-5.0) == 0.0
        assert service.calibrate(segments, topic_start_time=-100.0) == 0.0

    def test_sub_five_seconds_clamp(self, service: TimestampCalibrationService) -> None:
        """Start times strictly below MIN_LEAD_IN (5.0s) must clamp to 0.0s."""
        segments = [{"start": 0.0, "end": 15.0, "text": "Comienzo rápido."}]
        for t in [0.01, 1.0, 2.5, 4.0, 4.99]:
            calibrated = service.calibrate(segments, topic_start_time=t)
            assert calibrated == 0.0, f"Failed at t={t}: got {calibrated}"

    def test_boundary_at_exact_five_seconds(self, service: TimestampCalibrationService) -> None:
        """At exactly 5.0 seconds, calibration should not raise and clamp or return valid lead-in."""
        segments = [{"start": 0.0, "end": 10.0, "text": "Segmento inicial."}]
        calibrated = service.calibrate(segments, topic_start_time=5.0)
        assert 0.0 <= calibrated <= 5.0

    def test_extreme_gap_between_segments(self, service: TimestampCalibrationService) -> None:
        """Long silence / gap between segments (e.g. 500s) must keep lead-in within reasonable bounds."""
        segments = [
            {"start": 0.0, "end": 10.0, "text": "Intro."},
            {"start": 600.0, "end": 620.0, "text": "Explicación tras largo silencio."},
        ]
        calibrated = service.calibrate(segments, topic_start_time=605.0)
        lead_in = 605.0 - calibrated
        # Must not jump back to 10.0s (which would be 595s lead-in)
        assert 5.0 <= lead_in <= 10.0, f"Lead in was {lead_in}, expected 5.0-10.0s"

    def test_zero_duration_segments(self, service: TimestampCalibrationService) -> None:
        """Segments where start == end must be handled without ZeroDivisionError."""
        segments = [
            {"start": 0.0, "end": 0.0, "text": "Punto."},
            {"start": 10.0, "end": 10.0, "text": "Marca."},
            {"start": 20.0, "end": 30.0, "text": "Contenido real."},
        ]
        calibrated = service.calibrate(segments, topic_start_time=25.0)
        assert 0.0 <= calibrated <= 25.0

    def test_unordered_or_overlapping_segments(self, service: TimestampCalibrationService) -> None:
        """Overlapping speech segments from Whisper transcripts handled safely."""
        segments = [
            {"start": 0.0, "end": 8.0, "text": "Voz 1."},
            {"start": 5.0, "end": 12.0, "text": "Voz 2 superpuesta."},
            {"start": 10.0, "end": 20.0, "text": "Discusión grupal."},
        ]
        calibrated = service.calibrate(segments, topic_start_time=15.0)
        lead_in = 15.0 - calibrated
        assert 5.0 <= lead_in <= 10.0

    def test_topic_start_far_beyond_last_segment(self, service: TimestampCalibrationService) -> None:
        """Topic timestamp far after the transcript ended."""
        segments = [
            {"start": 0.0, "end": 10.0, "text": "Segmento 1."},
            {"start": 10.0, "end": 20.0, "text": "Segmento 2."},
        ]
        calibrated = service.calibrate(segments, topic_start_time=300.0)
        lead_in = 300.0 - calibrated
        assert 5.0 <= lead_in <= 10.0

    def test_time_conversions_roundtrip(self, service: TimestampCalibrationService) -> None:
        """HH:MM:SS and MM:SS conversions with valid strings."""
        assert service.to_timestamp_string(0.0) in ("00:00", "00:00:00")
        assert service.to_timestamp_string(3665.0) == "01:01:05"

        assert service.from_timestamp_string("00:00") == 0.0
        assert service.from_timestamp_string("00:00:10") == 10.0
        assert service.from_timestamp_string("01:01:05") == 3665.0
        assert service.from_timestamp_string("") == 0.0

    def test_calibrate_quiz_with_missing_timestamps(self, service: TimestampCalibrationService) -> None:
        """Quiz where some questions lack evidence_timestamp handles gracefully."""
        quiz = {
            "multiple_choice": [
                {"question": "Q1", "evidence_timestamp": None},
                {"question": "Q2", "evidence_timestamp": "00:00:15"},
            ],
            "open_questions": [
                {"question": "Q3"},
            ],
        }
        segments = [{"start": 0.0, "end": 30.0, "text": "Todo el video."}]
        result = service.calibrate_quiz(quiz, segments)
        assert result["multiple_choice"][0]["evidence_timestamp"] is None
        assert result["multiple_choice"][1]["evidence_timestamp"] is not None
        assert result["open_questions"][0].get("evidence_timestamp") is None


# =============================================================================
# 2. QUIZ ANSWER MASKING & DIRECT EXPORT EXPLOITS (R4)
# =============================================================================

class TestQuizMaskingAndExportExploits:
    """Stress-test role permissions and answer masking against leakage and export hacks."""

    def test_student_cannot_leak_answers_via_materials_endpoints(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Student accessing topic materials or direct material endpoint never receives answers."""
        suffix = uuid.uuid4().hex[:6]
        teacher_id, teacher_token, t_hdr = register_and_login(client, f"adv_t_{suffix}@test.com", "Profesor Adv")
        student_id, student_token, s_hdr = register_and_login(client, f"adv_s_{suffix}@test.com", "Estudiante Adv")

        video = create_test_video(db_session, owner_id=teacher_id)
        mc_q = [{
            "question": "What is 2+2?",
            "options": ["1", "2", "3", "4"],
            "correct_option": 3,
            "explanation": "2+2 equals 4 definitively.",
            "evidence_timestamp": "00:00:10",
            "bloom_level": "remember",
        }]
        open_q = [{
            "question": "Explain gravity.",
            "expected_points": ["Mass attraction", "Inverse square law"],
            "evidence_timestamp": "00:00:20",
            "bloom_level": "understand",
        }]
        quiz = create_test_quiz(db_session, video.id, teacher_id, mc_questions=mc_q, open_questions=open_q)
        group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)
        client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

        # Check 1: Topic materials endpoint
        res1 = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/materials", headers=s_hdr)
        assert res1.status_code == 200, res1.text
        content1 = res1.json()["shared_quiz"]["content"]
        assert "correct_option" not in content1["multiple_choice"][0]
        assert "explanation" not in content1["multiple_choice"][0]
        assert "expected_points" not in content1["open_questions"][0]

        # Check 2: Direct material endpoint
        res2 = client.get(f"/api/v1/materials/{quiz.id}", headers=s_hdr)
        assert res2.status_code == 200, res2.text
        content2 = res2.json()["content"]
        assert "correct_option" not in content2["multiple_choice"][0]
        assert "explanation" not in content2["multiple_choice"][0]
        assert "expected_points" not in content2["open_questions"][0]

        # Check 3: Teacher DOES receive answers
        res_t = client.get(f"/api/v1/materials/{quiz.id}", headers=t_hdr)
        assert res_t.status_code == 200
        content_t = res_t.json()["content"]
        assert content_t["multiple_choice"][0]["correct_option"] == 3
        assert "2+2 equals 4" in content_t["multiple_choice"][0]["explanation"]
        assert len(content_t["open_questions"][0]["expected_points"]) == 2

    def test_direct_export_exploit_blocked_for_student_and_anonymous(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Attempting to download export with include_answers=true is rejected with 403 Forbidden."""
        suffix = uuid.uuid4().hex[:6]
        teacher_id, teacher_token, t_hdr = register_and_login(client, f"exp_t_{suffix}@test.com", "Profesor Exp")
        student_id, student_token, s_hdr = register_and_login(client, f"exp_s_{suffix}@test.com", "Estudiante Exp")

        video = create_test_video(db_session, owner_id=teacher_id)
        quiz = create_test_quiz(db_session, video.id, teacher_id)
        group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)
        client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

        for fmt in ("json", "markdown"):
            # Student exploit attempt
            res_s = client.get(f"/api/v1/materials/{quiz.id}/export?format={fmt}&include_answers=true", headers=s_hdr)
            assert res_s.status_code == 403, f"Expected 403 for student with {fmt}, got {res_s.status_code}"

            # Anonymous exploit attempt
            res_anon = client.get(f"/api/v1/materials/{quiz.id}/export?format={fmt}&include_answers=true")
            assert res_anon.status_code in (401, 403), f"Expected 401/403 for anonymous with {fmt}"

            # Teacher valid export
            res_t = client.get(f"/api/v1/materials/{quiz.id}/export?format={fmt}&include_answers=true", headers=t_hdr)
            assert res_t.status_code == 200


# =============================================================================
# 3. ACTIVITY GRADING & ATTEMPT QUERYING (R1 & R2)
# =============================================================================

class TestActivityGradingAndAttemptQueriesAdversarial:
    """Stress-test attempt querying isolation and grade modification boundaries."""

    def test_multi_student_attempt_isolation_and_teacher_querying(
        self, client: TestClient, db_session: Session
    ) -> None:
        """3 students: Student 1 (2 attempts), Student 2 (0 attempts), Student 3 (1 attempt)."""
        suffix = uuid.uuid4().hex[:6]
        teacher_id, teacher_token, t_hdr = register_and_login(client, f"act_t_{suffix}@test.com", "Profesor Act")
        s1_id, s1_tok, s1_hdr = register_and_login(client, f"act_s1_{suffix}@test.com", "Student 1")
        s2_id, s2_tok, s2_hdr = register_and_login(client, f"act_s2_{suffix}@test.com", "Student 2")
        s3_id, s3_tok, s3_hdr = register_and_login(client, f"act_s3_{suffix}@test.com", "Student 3")

        video = create_test_video(db_session, owner_id=teacher_id)
        quiz = create_test_quiz(db_session, video.id, teacher_id)
        group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)

        # All join
        for tok in (s1_tok, s2_tok, s3_tok):
            client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(tok))

        # S1 submits 2 attempts
        client.post(
            f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
            json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 0}]},
            headers=s1_hdr,
        )
        client.post(
            f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
            json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}]},
            headers=s1_hdr,
        )

        # S3 submits 1 attempt
        client.post(
            f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
            json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 1}]},
            headers=s3_hdr,
        )

        # Verification 1: Student 1 attempts to query Student 3's attempts -> 403
        hack1 = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/members/{s3_id}/attempts", headers=s1_hdr)
        assert hack1.status_code == 403
        hack2 = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts?user_id={s3_id}", headers=s1_hdr)
        assert hack2.status_code == 403

        # Verification 2: Student 1 calls my-attempts -> receives exactly 2 attempts
        my_att = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/my-attempts", headers=s1_hdr)
        assert my_att.status_code == 200
        assert len(my_att.json()) == 2

        # Verification 3: Student 2 (0 attempts) calls my-attempts -> receives empty list
        s2_att = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/my-attempts", headers=s2_hdr)
        assert s2_att.status_code == 200
        assert s2_att.json() == []

        # Verification 4: Teacher queries Student 2 (0 attempts) -> returns []
        t_s2_att = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/members/{s2_id}/attempts", headers=t_hdr)
        assert t_s2_att.status_code == 200
        assert t_s2_att.json() == []

        # Verification 5: Teacher queries Student 1 -> returns 2 attempts
        t_s1_att = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/members/{s1_id}/attempts", headers=t_hdr)
        assert t_s1_att.status_code == 200
        assert len(t_s1_att.json()) == 2

        # Verification 6: Topic summary accurately reflects all 3 students
        sum_res = client.get(f"/api/v1/groups/{group_id}/topics/{topic_id}/summary", headers=t_hdr)
        assert sum_res.status_code == 200
        members = sum_res.json()["members_summary"]
        by_user = {m["user_id"]: m for m in members}
        assert by_user[s1_id]["total_attempts"] == 2
        assert by_user[s2_id]["total_attempts"] == 0
        assert by_user[s2_id]["status"] == "not_submitted"
        assert by_user[s3_id]["total_attempts"] == 1

    def test_grading_boundaries_and_student_grading_blocked(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Inline grading enforces [0.0, 100.0] range and blocks students from self-grading."""
        suffix = uuid.uuid4().hex[:6]
        teacher_id, teacher_token, t_hdr = register_and_login(client, f"grd_t_{suffix}@test.com", "Teacher Grd")
        student_id, student_token, s_hdr = register_and_login(client, f"grd_s_{suffix}@test.com", "Student Grd")

        video = create_test_video(db_session, owner_id=teacher_id)
        quiz = create_test_quiz(db_session, video.id, teacher_id)
        group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id, quiz.id)
        client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

        att = client.post(
            f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts",
            json={"multiple_choice_answers": [{"question_index": 0, "selected_option": 0}]},
            headers=s_hdr,
        ).json()
        attempt_id = att["id"]

        # Student cannot grade themselves
        hack = client.patch(
            f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts/{attempt_id}",
            json={"final_score": 100.0, "review_notes": "Me puse 100"},
            headers=s_hdr,
        )
        assert hack.status_code == 403

        # Invalid score < 0
        r_neg = client.patch(
            f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts/{attempt_id}",
            json={"final_score": -1.0},
            headers=t_hdr,
        )
        assert r_neg.status_code == 422

        # Invalid score > 100
        r_high = client.patch(
            f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts/{attempt_id}",
            json={"final_score": 100.1},
            headers=t_hdr,
        )
        assert r_high.status_code == 422

        # Valid score 0.0
        r0 = client.patch(
            f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts/{attempt_id}",
            json={"final_score": 0.0, "review_notes": "Cero justificado"},
            headers=t_hdr,
        )
        assert r0.status_code == 200
        assert r0.json()["final_score"] == 0.0

        # Valid score 100.0
        r100 = client.patch(
            f"/api/v1/groups/{group_id}/topics/{topic_id}/attempts/{attempt_id}",
            json={"final_score": 100.0, "review_notes": "Excelente"},
            headers=t_hdr,
        )
        assert r100.status_code == 200
        assert r100.json()["final_score"] == 100.0


# =============================================================================
# 4. VIDEO SEARCH & SORTING ADVERSARIAL (R3)
# =============================================================================

class TestVideoSearchAndSortAdversarial:
    """Stress-test video search with SQL/Regex injection patterns, unicode, and ordering."""

    def test_sql_and_regex_special_characters_no_crash(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Search query with SQL injection, regex symbols, or unicode does not cause 500 error."""
        suffix = uuid.uuid4().hex[:6]
        user_id, token, hdr = register_and_login(client, f"vid_adv_{suffix}@test.com", "Video User")

        title = f"Introducción a Python 3.13: ¿Funciona el 100%? [Regex (test)] {suffix}"
        create_test_video(db_session, owner_id=user_id, title=title)

        dangerous_queries = [
            "'; DROP TABLE videos; --",
            "' OR '1'='1",
            "%",
            "_",
            ".*",
            "[a-z]+",
            "^Python",
            "¿Funciona?",
            "100%",
            "[Regex (test)]",
            " " * 50,
            "A" * 500,
        ]

        for q in dangerous_queries:
            res = client.get(f"/api/v1/videos?search={q}", headers=hdr)
            assert res.status_code == 200, f"Query '{q}' caused status {res.status_code}"

    def test_strict_chronological_ordering(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Videos must be ordered by created_at strictly descending or ascending."""
        suffix = uuid.uuid4().hex[:6]
        user_id, token, hdr = register_and_login(client, f"vid_ord_{suffix}@test.com", "Order User")

        now = datetime.now(timezone.utc)
        v1 = create_test_video(db_session, owner_id=user_id, title=f"Video Antiguo {suffix}", created_at=now - timedelta(days=10))
        v2 = create_test_video(db_session, owner_id=user_id, title=f"Video Medio {suffix}", created_at=now - timedelta(days=5))
        v3 = create_test_video(db_session, owner_id=user_id, title=f"Video Reciente {suffix}", created_at=now)

        # Default / desc: newest first
        res_desc = client.get("/api/v1/videos?order=desc", headers=hdr)
        assert res_desc.status_code == 200
        items_desc = [v for v in res_desc.json()["items"] if suffix in v["title"]]
        assert [v["id"] for v in items_desc] == [v3.id, v2.id, v1.id]

        # Asc: oldest first
        res_asc = client.get("/api/v1/videos?order=asc", headers=hdr)
        assert res_asc.status_code == 200
        items_asc = [v for v in res_asc.json()["items"] if suffix in v["title"]]
        assert [v["id"] for v in items_asc] == [v1.id, v2.id, v3.id]


# =============================================================================
# 5. SUMMARY ISOLATION & PERMISSION SEPARATION (R5)
# =============================================================================

class TestSummaryIsolationAdversarial:
    """Stress-test teacher vs student summary isolation, cross-student edits, and overwrite prevention."""

    def test_student_cannot_edit_teacher_official_summary(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Student receives 403 Forbidden when attempting to update official teacher summary."""
        suffix = uuid.uuid4().hex[:6]
        teacher_id, teacher_token, _ = register_and_login(client, f"sum_t_{suffix}@test.com", "Teacher Sum")
        student_id, student_token, s_hdr = register_and_login(client, f"sum_s_{suffix}@test.com", "Student Sum")

        video = create_test_video(db_session, owner_id=teacher_id)
        official_sum = create_test_summary(db_session, video.id, teacher_id, synopsis="Oficial Sagrado")
        group_id, code, topic_id = create_test_group_and_topic(client, teacher_token, video.id)
        client.post("/api/v1/groups/join", json={"code": code}, headers=auth_header(student_token))

        payload = json.loads(official_sum.content_json)
        payload["synopsis"] = "Intento de hack por alumno"

        res = client.put(
            f"/api/v1/materials/{official_sum.id}",
            json={"content": payload},
            headers=s_hdr,
        )
        assert res.status_code == 403

    def test_cross_student_personal_summary_isolation(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Student A's personal summary cannot be edited or overwritten by Student B."""
        suffix = uuid.uuid4().hex[:6]
        s1_id, s1_tok, s1_hdr = register_and_login(client, f"p_s1_{suffix}@test.com", "Student 1")
        s2_id, s2_tok, s2_hdr = register_and_login(client, f"p_s2_{suffix}@test.com", "Student 2")

        video = create_test_video(db_session, owner_id=s1_id)
        sum_s1 = create_test_summary(db_session, video.id, owner_id=s1_id, synopsis="Notas de Student 1")

        payload = json.loads(sum_s1.content_json)
        payload["synopsis"] = "Notas actualizadas de Student 1"

        # Student 1 can edit
        res1 = client.put(
            f"/api/v1/materials/{sum_s1.id}",
            json={"content": payload},
            headers=s1_hdr,
        )
        assert res1.status_code == 200

        # Student 2 cannot edit
        payload_s2 = json.loads(sum_s1.content_json)
        payload_s2["synopsis"] = "Alterado por Student 2"
        res2 = client.put(
            f"/api/v1/materials/{sum_s1.id}",
            json={"content": payload_s2},
            headers=s2_hdr,
        )
        assert res2.status_code == 403
