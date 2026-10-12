"""Servicio de dominio para la gestión académica de grupos, temas y calificaciones."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import PipelineError
from app.models.group import Attempt, Group, GroupMembership, Topic
from app.models.material import DidacticMaterial
from app.models.user import User
from app.models.video import Video
from app.repositories.group_repository import GroupRepository
from app.schemas.contracts import (
    AttemptGradeUpdate,
    AttemptSubmitRequest,
    GroupGradesResponse,
    MemberGradeSummary,
    MemberTopicGrade,
    TopicCreate,
    TopicMaterialsResponse,
    TopicResponse,
    TopicSummaryResponse,
    TopicUpdate,
)
from app.services.grading_service import (
    QuizAttemptGradingService,
    compute_final_score,
    compute_member_topic_summary,
)
from app.services.material_service import MaterialService


class GroupService:
    """Encapsula las reglas de negocio de grupos, temas, intentos y libro de calificaciones."""

    def __init__(
        self,
        repository: GroupRepository | None = None,
        settings: Settings | None = None,
        material_service: MaterialService | None = None,
        grading_service: QuizAttemptGradingService | None = None,
    ) -> None:
        self.repository = repository or GroupRepository()
        self.settings = settings or get_settings()
        self.material_service = material_service or MaterialService()
        self._grading_service = grading_service

    # -------------------------------------------------------------------------
    # Gestión de Temas
    # -------------------------------------------------------------------------
    def create_topic(
        self,
        session: Session,
        group: Group,
        creator: User,
        payload: TopicCreate,
    ) -> Topic:
        """Valida y asocia videos y cuestionarios para crear un tema en el grupo."""
        video = None
        material = None

        if payload.video_id is not None:
            video = session.get(Video, payload.video_id)
            if not video:
                raise PipelineError("El video especificado no existe.", code="VIDEO_NOT_FOUND", status_code=404)

            if payload.material_id is not None:
                material = session.get(DidacticMaterial, payload.material_id)
                if not material or material.video_id != video.id:
                    raise PipelineError(
                        "El material no existe o no corresponde a este video.",
                        code="MATERIAL_NOT_FOUND",
                        status_code=404,
                    )
                if material.material_type != "quiz":
                    raise PipelineError(
                        "El material asociado debe ser de tipo 'quiz'.",
                        code="INVALID_MATERIAL_TYPE",
                        status_code=400,
                    )
            else:
                # Auto-detección del último quiz generado para este video
                material = (
                    session.query(DidacticMaterial)
                    .filter(DidacticMaterial.video_id == video.id, DidacticMaterial.material_type == "quiz")
                    .order_by(DidacticMaterial.id.desc())
                    .first()
                )

        topic = self.repository.create_topic(
            session,
            group_id=group.id,
            video_id=payload.video_id,
            material_id=material.id if material else payload.material_id,
            title=payload.title.strip(),
            description=payload.description or "",
            created_by=creator.id,
            is_active=payload.is_active,
            is_published=payload.is_active,
        )
        session.commit()
        session.refresh(topic)
        return topic

    def list_topics_with_materials(self, session: Session, group: Group) -> list[TopicResponse]:
        """Devuelve los temas activos del grupo vinculando sus IDs de resumen didáctico."""
        topics = self.repository.list_active_topics(session, group.id)
        responses: list[TopicResponse] = []
        for t in topics:
            summary_id = None
            quiz_id = t.material_id
            if t.video_id:
                summary_mat = (
                    session.query(DidacticMaterial.id)
                    .filter(
                        DidacticMaterial.video_id == t.video_id,
                        DidacticMaterial.material_type == "summary",
                        (DidacticMaterial.owner_id == group.admin_id)
                        | (DidacticMaterial.owner_id == t.created_by)
                        | (DidacticMaterial.owner_id.is_(None)),
                    )
                    .order_by(DidacticMaterial.id.desc())
                    .first()
                )
                if summary_mat:
                    summary_id = summary_mat[0]

                if not quiz_id:
                    quiz_mat = (
                        session.query(DidacticMaterial.id)
                        .filter(
                            DidacticMaterial.video_id == t.video_id,
                            DidacticMaterial.material_type == "quiz",
                            (DidacticMaterial.owner_id == group.admin_id)
                            | (DidacticMaterial.owner_id == t.created_by)
                            | (DidacticMaterial.owner_id.is_(None)),
                        )
                        .order_by(DidacticMaterial.id.desc())
                        .first()
                    )
                    if quiz_mat:
                        quiz_id = quiz_mat[0]
                        t.material_id = quiz_id
                        session.commit()

            responses.append(
                TopicResponse(
                    id=t.id,
                    group_id=t.group_id,
                    video_id=t.video_id,
                    material_id=t.material_id,
                    quiz_id=quiz_id,
                    summary_id=summary_id,
                    title=t.title,
                    description=t.description or "",
                    created_by=t.created_by,
                    is_active=t.is_active,
                    created_at=t.created_at,
                )
            )
        return responses

    def update_topic(
        self,
        session: Session,
        group: Group,
        topic_id: int,
        payload: TopicUpdate,
    ) -> Topic:
        """Modifica título, descripción, video, cuestionario o estado activo de un tema."""
        topic = self.repository.get_topic(session, topic_id)
        if not topic or topic.group_id != group.id:
            raise PipelineError("El tema no existe en este grupo.", code="TOPIC_NOT_FOUND", status_code=404)

        if payload.title is not None:
            topic.title = payload.title.strip()
        if payload.description is not None:
            topic.description = payload.description.strip()
        if payload.video_id is not None:
            topic.video_id = payload.video_id
        if payload.material_id is not None:
            topic.material_id = payload.material_id
        if payload.is_active is not None:
            topic.is_active = payload.is_active

        session.commit()
        session.refresh(topic)
        return topic

    def delete_topic(self, session: Session, group: Group, topic_id: int) -> None:
        """Elimina un tema del grupo."""
        topic = self.repository.get_topic(session, topic_id)
        if not topic or topic.group_id != group.id:
            raise PipelineError("El tema no existe en este grupo.", code="TOPIC_NOT_FOUND", status_code=404)
        session.delete(topic)
        session.commit()

    # -------------------------------------------------------------------------
    # Materiales Compartidos vs Personales de un Tema
    # -------------------------------------------------------------------------
    def get_topic_materials(
        self,
        session: Session,
        group: Group,
        topic_id: int,
        current_user: User,
    ) -> TopicMaterialsResponse:
        """Resuelve el quiz y resumen oficiales del docente frente a los generados por el alumno."""
        topic = self.repository.get_topic(session, topic_id)
        if not topic or topic.group_id != group.id:
            raise PipelineError("El tema no existe en este grupo.", code="TOPIC_NOT_FOUND", status_code=404)

        svc = self.material_service

        # 1. Cuestionario compartido del tema
        shared_quiz = None
        if topic.material_id:
            m = session.get(DidacticMaterial, topic.material_id)
            if m:
                shared_quiz = svc._as_response(session, m.id, m.video_id, m.material_type, m.content_json)
        if not shared_quiz and topic.video_id:
            m = (
                session.query(DidacticMaterial)
                .filter(
                    DidacticMaterial.video_id == topic.video_id,
                    DidacticMaterial.material_type == "quiz",
                    (DidacticMaterial.owner_id == group.admin_id)
                    | (DidacticMaterial.owner_id == topic.created_by)
                    | (DidacticMaterial.owner_id.is_(None)),
                )
                .order_by(DidacticMaterial.id.desc())
                .first()
            )
            if m:
                shared_quiz = svc._as_response(session, m.id, m.video_id, m.material_type, m.content_json)
                topic.material_id = m.id
                session.commit()

        # 2. Resumen compartido del tema
        shared_summary = None
        if topic.video_id:
            m = (
                session.query(DidacticMaterial)
                .filter(
                    DidacticMaterial.video_id == topic.video_id,
                    DidacticMaterial.material_type == "summary",
                    (DidacticMaterial.owner_id == group.admin_id)
                    | (DidacticMaterial.owner_id == topic.created_by)
                    | (DidacticMaterial.owner_id.is_(None)),
                )
                .order_by(DidacticMaterial.id.desc())
                .first()
            )
            if m:
                shared_summary = svc._as_response(session, m.id, m.video_id, m.material_type, m.content_json)

        # 3. Materiales personales del alumno para este video
        personal_quiz = None
        personal_summary = None
        if topic.video_id:
            shared_quiz_id = shared_quiz.id if shared_quiz else None
            shared_summary_id = shared_summary.id if shared_summary else None

            pq = (
                session.query(DidacticMaterial)
                .filter(
                    DidacticMaterial.video_id == topic.video_id,
                    DidacticMaterial.material_type == "quiz",
                    DidacticMaterial.owner_id == current_user.id,
                    DidacticMaterial.id != shared_quiz_id,
                )
                .order_by(DidacticMaterial.id.desc())
                .first()
            )
            if pq:
                personal_quiz = svc._as_response(session, pq.id, pq.video_id, pq.material_type, pq.content_json)

            ps = (
                session.query(DidacticMaterial)
                .filter(
                    DidacticMaterial.video_id == topic.video_id,
                    DidacticMaterial.material_type == "summary",
                    DidacticMaterial.owner_id == current_user.id,
                    DidacticMaterial.id != shared_summary_id,
                )
                .order_by(DidacticMaterial.id.desc())
                .first()
            )
            if ps:
                personal_summary = svc._as_response(session, ps.id, ps.video_id, ps.material_type, ps.content_json)

        return TopicMaterialsResponse(
            topic_id=topic.id,
            video_id=topic.video_id,
            shared_quiz=shared_quiz,
            shared_summary=shared_summary,
            personal_quiz=personal_quiz,
            personal_summary=personal_summary,
        )

    # -------------------------------------------------------------------------
    # Intentos y Calificación
    # -------------------------------------------------------------------------
    def submit_topic_attempt(
        self,
        session: Session,
        group: Group,
        topic_id: int,
        user: User,
        payload: AttemptSubmitRequest,
    ) -> Attempt:
        """Evalúa un intento de tema con corrección determinista + IA grounded y persiste la nota con penalización."""
        topic = self.repository.get_topic(session, topic_id)
        if not topic or topic.group_id != group.id:
            raise PipelineError("El tema no existe en este grupo.", code="TOPIC_NOT_FOUND", status_code=404)
        if not topic.is_active:
            raise PipelineError("Este tema se encuentra pausado.", code="TOPIC_INACTIVE", status_code=400)

        material = session.get(DidacticMaterial, topic.material_id)
        if not material:
            raise PipelineError(
                "El cuestionario asociado no se encuentra disponible.",
                code="MATERIAL_MISSING",
                status_code=500,
            )

        grading_svc = self._grading_service or QuizAttemptGradingService(self.settings)
        eval_result = grading_svc.grade_submission(session, topic.material_id, payload)
        raw_score = eval_result.raw_score

        previous_attempts_count = self.repository.count_user_attempts(session, topic.id, user.id)
        attempt_number = previous_attempts_count + 1

        final_score = compute_final_score(
            raw_score=raw_score,
            attempt_number=attempt_number,
            penalty_per_attempt=self.settings.penalty_per_attempt,
        )

        attempt = self.repository.save_attempt(
            session,
            topic_id=topic.id,
            user_id=user.id,
            attempt_number=attempt_number,
            raw_score=raw_score,
            final_score=final_score,
            answers_json=json.dumps(eval_result.answers_snapshot, ensure_ascii=False),
        )
        session.commit()
        session.refresh(attempt)
        return attempt

    def update_attempt_grade(
        self,
        session: Session,
        group: Group,
        topic_id: int,
        attempt_id: int,
        payload: AttemptGradeUpdate,
    ) -> Attempt:
        """Ajusta manualmente la nota de un intento por parte del docente con comentarios."""
        topic = self.repository.get_topic(session, topic_id)
        if not topic or topic.group_id != group.id:
            raise PipelineError("El tema no existe en este grupo.", code="TOPIC_NOT_FOUND", status_code=404)

        attempt = self.repository.get_attempt(session, attempt_id)
        if not attempt or attempt.topic_id != topic.id:
            raise PipelineError("El intento no existe en este tema.", code="ATTEMPT_NOT_FOUND", status_code=404)

        return self.repository.update_attempt_score(
            session, attempt, final_score=payload.final_score, review_notes=payload.review_notes
        )

    # -------------------------------------------------------------------------
    # Libro de Calificaciones y Estadísticas
    # -------------------------------------------------------------------------
    def get_group_grades(
        self,
        session: Session,
        group: Group,
        current_user: User,
    ) -> GroupGradesResponse:
        """Genera el libro de calificaciones: matriz completa para admin, individual para miembro."""
        is_admin = group.admin_id == current_user.id
        topics = self.repository.list_active_topics(session, group.id)
        topics_responses = self.list_topics_with_materials(session, group)
        total_topics = len(topics)

        members = self.repository.get_group_members(session, group.id) if is_admin else [current_user]
        members_summary: list[MemberGradeSummary] = []

        for member in members:
            member_topics_grade: list[MemberTopicGrade] = []
            topic_grades_dict: dict[str, Any] = {}
            completed_count = 0
            final_scores: list[float] = []

            for t in topics:
                attempts = self.repository.list_user_attempts(session, t.id, member.id)
                if attempts:
                    completed_count += 1
                    best_att = max(attempts, key=lambda a: (a.final_score, a.raw_score))
                    latest_att = max(attempts, key=lambda a: a.attempt_number)
                    final_scores.append(best_att.final_score)

                    review_notes = None
                    try:
                        ans_data = json.loads(latest_att.answers_json) if latest_att.answers_json else {}
                        if isinstance(ans_data, dict):
                            review_notes = ans_data.get("review_notes")
                    except Exception:
                        pass

                    grade_item = MemberTopicGrade(
                        topic_id=t.id,
                        topic_title=t.title,
                        status="evaluated",
                        total_attempts=len(attempts),
                        attempts_count=len(attempts),
                        best_final_score=best_att.final_score,
                        best_raw_score=best_att.raw_score,
                        latest_final_score=latest_att.final_score,
                        latest_attempt_id=latest_att.id,
                        latest_submitted_at=latest_att.submitted_at,
                        review_notes=review_notes,
                    )
                    member_topics_grade.append(grade_item)

                    info = {
                        "submitted": True,
                        "attempts_count": len(attempts),
                        "raw_score": latest_att.raw_score,
                        "final_score": latest_att.final_score,
                        "attempt_id": latest_att.id,
                        "review_notes": review_notes,
                    }
                    topic_grades_dict[str(t.id)] = info
                else:
                    grade_item = MemberTopicGrade(
                        topic_id=t.id,
                        topic_title=t.title,
                        status="pending",
                        total_attempts=0,
                        attempts_count=0,
                        best_final_score=None,
                        best_raw_score=None,
                        latest_final_score=None,
                        latest_attempt_id=None,
                        latest_submitted_at=None,
                        review_notes=None,
                    )
                    member_topics_grade.append(grade_item)

                    info = {
                        "submitted": False,
                        "attempts_count": 0,
                        "raw_score": None,
                        "final_score": None,
                        "attempt_id": None,
                        "review_notes": None,
                    }
                    topic_grades_dict[str(t.id)] = info

            avg_score = round(sum(final_scores) / len(final_scores), 2) if final_scores else None

            members_summary.append(
                MemberGradeSummary(
                    user_id=member.id,
                    user_name=member.nombre,
                    user_email=member.email,
                    nombre=member.nombre,
                    email=member.email,
                    completed_topics=completed_count,
                    total_topics=total_topics,
                    average_score=avg_score,
                    topics=member_topics_grade,
                    topic_grades=topic_grades_dict,
                )
            )

        return GroupGradesResponse(
            group_id=group.id,
            group_name=group.name,
            is_admin=is_admin,
            total_topics=total_topics,
            topics=topics_responses,
            members=members_summary,
        )

    def get_topic_summary(
        self,
        session: Session,
        group: Group,
        topic_id: int,
    ) -> TopicSummaryResponse:
        """Devuelve el desglose de desempeño de un tema específico por miembro."""
        topic = self.repository.get_topic(session, topic_id)
        if not topic or topic.group_id != group.id:
            raise PipelineError("El tema no existe en este grupo.", code="TOPIC_NOT_FOUND", status_code=404)

        members = self.repository.get_group_members(session, group.id)
        members_summary = []

        for member in members:
            attempts = self.repository.list_user_attempts(session, topic.id, member.id)
            summary = compute_member_topic_summary(
                user_id=member.id,
                user_name=member.nombre,
                user_email=member.email,
                attempts=attempts,
            )
            members_summary.append(summary)

        return TopicSummaryResponse(
            topic_id=topic.id,
            group_id=group.id,
            title=topic.title,
            members_summary=members_summary,
        )
