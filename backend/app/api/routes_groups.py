from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies_auth import require_group_admin, require_group_member
from app.core.config import get_settings
from app.db.database import get_session
from app.models.group import Attempt, Group, GroupMembership, Topic
from app.models.material import DidacticMaterial
from app.models.user import User
from app.models.video import Video
from app.repositories.group_repository import GroupRepository
from app.schemas.contracts import (
    AdminAttemptResponse,
    AttemptResponse,
    AttemptSubmitRequest,
    GroupCreate,
    GroupJoinRequest,
    GroupMemberAdd,
    GroupMemberDetail,
    GroupMemberResponse,
    GroupResponse,
    MyGroupsResponse,
    TopicCreate,
    TopicResponse,
    TopicSummaryResponse,
    TopicUpdate,
)
from app.services.auth_service import get_current_user
from app.services.grading_service import (
    QuizAttemptGradingService,
    compute_final_score,
    compute_member_topic_summary,
    evaluate_quiz_answers,
)

router = APIRouter(prefix="/api/v1/groups", tags=["groups"])
repo = GroupRepository()


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: GroupCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Group:
    """Crea un grupo registrando al usuario autenticado como admin y primer miembro."""
    group = repo.create_group(session, name=payload.name.strip(), admin_id=current_user.id)
    session.commit()
    session.refresh(group)
    return group


@router.post("/join", response_model=GroupResponse)
def join_group(
    payload: GroupJoinRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Group:
    """Permite al usuario autenticado unirse a un grupo mediante su código alfanumérico de 6 caracteres."""
    group = repo.get_group_by_code(session, payload.code.strip())
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "GROUP_NOT_FOUND", "message": "Código de grupo inválido o inexistente."},
        )

    membership = repo.get_membership(session, group.id, current_user.id)
    if not membership:
        repo.add_member(session, group.id, current_user.id)
        session.commit()

    return group


@router.get("", response_model=list[GroupResponse])
def list_groups(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[Group]:
    """Lista todos los grupos donde el usuario es admin o miembro (compatibilidad frontend)."""
    admin_groups, member_groups = repo.get_user_groups(session, current_user.id)
    return admin_groups + member_groups


@router.get("/mine", response_model=MyGroupsResponse)
def get_my_groups(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, list[Group]]:
    """Devuelve los grupos donde el usuario es admin y donde es miembro (dos listas separadas)."""
    admin_groups, member_groups = repo.get_user_groups(session, current_user.id)
    return {"admin_groups": admin_groups, "member_groups": member_groups}


@router.get("/{group_id}", response_model=GroupResponse)
def get_group(
    group: Group = Depends(require_group_member),
) -> Group:
    """Obtiene los detalles del grupo. Accesible para cualquier miembro o admin."""
    return group


@router.post("/{group_id}/regenerate-code", response_model=GroupResponse)
def regenerate_group_code(
    group: Group = Depends(require_group_admin),
    session: Session = Depends(get_session),
) -> Group:
    """SOLO admin: regenera el código alfanumérico único de invitación al grupo."""
    updated = repo.regenerate_code(session, group.id)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado")
    session.commit()
    session.refresh(updated)
    return updated


@router.get("/{group_id}/members", response_model=list[GroupMemberDetail])
def list_group_members(
    group: Group = Depends(require_group_member),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Cualquier miembro puede ver los integrantes actuales del grupo."""
    return repo.get_group_members_detail(session, group.id)


@router.post("/{group_id}/members", response_model=GroupMemberResponse, status_code=status.HTTP_201_CREATED)
def add_group_member(
    payload: GroupMemberAdd,
    group: Group = Depends(require_group_admin),
    session: Session = Depends(get_session),
) -> GroupMembership:
    """SOLO admin: añade un usuario al grupo directamente por su ID."""
    user = session.get(User, payload.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": f"Usuario con ID {payload.user_id} no encontrado."},
        )
    existing = repo.get_membership(session, group.id, user.id)
    if existing:
        return existing
    membership = repo.add_member(session, group.id, user.id)
    session.commit()
    session.refresh(membership)
    return membership


@router.delete("/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def remove_group_member(
    user_id: int,
    group: Group = Depends(require_group_admin),
    session: Session = Depends(get_session),
) -> Response:
    """SOLO admin: expulsa a un miembro del grupo (el admin no puede eliminarse a sí mismo)."""
    if user_id == group.admin_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "CANNOT_REMOVE_ADMIN", "message": "El administrador no puede ser eliminado del grupo."},
        )
    removed = repo.remove_member(session, group.id, user_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MEMBERSHIP_NOT_FOUND", "message": "El usuario no es miembro del grupo."},
        )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{group_id}/topics", response_model=TopicResponse, status_code=status.HTTP_201_CREATED)
def create_topic(
    payload: TopicCreate,
    group: Group = Depends(require_group_admin),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Topic:
    """SOLO admin: crea un nuevo tema/actividad asociando video y material tipo 'quiz' existentes."""
    video = None
    material = None

    if payload.video_id is not None:
        video = session.get(Video, payload.video_id)
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "VIDEO_NOT_FOUND", "message": "El video especificado no existe."},
            )

        if payload.material_id is not None:
            material = session.get(DidacticMaterial, payload.material_id)
            if not material or material.video_id != video.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "MATERIAL_NOT_FOUND", "message": "El material no existe o no corresponde a este video."},
                )
            if material.material_type != "quiz":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"code": "INVALID_MATERIAL_TYPE", "message": "El material asociado debe ser de tipo 'quiz'."},
                )
        else:
            # Buscar automáticamente si hay un quiz ya generado para este video
            material = (
                session.query(DidacticMaterial)
                .filter(DidacticMaterial.video_id == video.id, DidacticMaterial.material_type == "quiz")
                .order_by(DidacticMaterial.id.desc())
                .first()
            )

    topic = repo.create_topic(
        session,
        group_id=group.id,
        video_id=payload.video_id,
        material_id=material.id if material else payload.material_id,
        title=payload.title.strip(),
        description=payload.description or "",
        created_by=current_user.id,
        is_active=payload.is_active,
        is_published=payload.is_active,
    )
    session.commit()
    session.refresh(topic)
    return topic


@router.get("/{group_id}/topics", response_model=list[TopicResponse])
def list_topics(
    group: Group = Depends(require_group_member),
    session: Session = Depends(get_session),
) -> list[Topic]:
    """Cualquier miembro del grupo puede ver sus temas activos."""
    return repo.list_active_topics(session, group.id)


@router.patch("/{group_id}/topics/{topic_id}", response_model=TopicResponse)
def update_topic(
    topic_id: int,
    payload: TopicUpdate,
    group: Group = Depends(require_group_admin),
    session: Session = Depends(get_session),
) -> Topic:
    """SOLO admin: activa, pausa o renombra un tema existente."""
    topic = repo.get_topic(session, topic_id)
    if not topic or topic.group_id != group.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TOPIC_NOT_FOUND", "message": "El tema no existe en este grupo."},
        )

    if payload.title is not None:
        topic.title = payload.title.strip()
    if payload.is_active is not None:
        topic.is_active = payload.is_active

    session.commit()
    session.refresh(topic)
    return topic


@router.delete("/{group_id}/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_topic(
    topic_id: int,
    group: Group = Depends(require_group_admin),
    session: Session = Depends(get_session),
) -> Response:
    """SOLO admin: elimina un tema existente de su grupo."""
    topic = repo.get_topic(session, topic_id)
    if not topic or topic.group_id != group.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TOPIC_NOT_FOUND", "message": "El tema no existe en este grupo."},
        )
    session.delete(topic)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{group_id}/topics/{topic_id}/attempts",
    response_model=AttemptResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_attempt(
    topic_id: int,
    payload: AttemptSubmitRequest,
    group: Group = Depends(require_group_member),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Attempt:
    """Cualquier miembro envía sus respuestas; calcula raw_score, penalización por reintentos y guarda el Attempt."""
    topic = repo.get_topic(session, topic_id)
    if not topic or topic.group_id != group.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TOPIC_NOT_FOUND", "message": "El tema no existe en este grupo."},
        )
    if not topic.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "TOPIC_INACTIVE", "message": "Este tema se encuentra pausado."},
        )

    material = session.get(DidacticMaterial, topic.material_id)
    if not material:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "MATERIAL_MISSING", "message": "El cuestionario asociado no se encuentra disponible."},
        )

    settings = get_settings()
    grading_service = QuizAttemptGradingService(settings)
    eval_result = grading_service.grade_submission(session, topic.material_id, payload)
    raw_score = eval_result.raw_score

    previous_attempts_count = repo.count_user_attempts(session, topic.id, current_user.id)
    attempt_number = previous_attempts_count + 1

    final_score = compute_final_score(
        raw_score=raw_score,
        attempt_number=attempt_number,
        penalty_per_attempt=settings.penalty_per_attempt,
    )

    attempt = repo.save_attempt(
        session,
        topic_id=topic.id,
        user_id=current_user.id,
        attempt_number=attempt_number,
        raw_score=raw_score,
        final_score=final_score,
        answers_json=json.dumps(eval_result.answers_snapshot, ensure_ascii=False),
    )
    session.commit()
    session.refresh(attempt)
    return attempt


@router.get("/{group_id}/topics/{topic_id}/my-attempts", response_model=list[AttemptResponse])
def get_my_attempts(
    topic_id: int,
    group: Group = Depends(require_group_member),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[Attempt]:
    """El miembro consulta solo sus propios intentos en este tema."""
    topic = repo.get_topic(session, topic_id)
    if not topic or topic.group_id != group.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TOPIC_NOT_FOUND", "message": "El tema no existe en este grupo."},
        )
    return repo.list_user_attempts(session, topic.id, current_user.id)


@router.get("/{group_id}/topics/{topic_id}/attempts", response_model=list[AdminAttemptResponse])
def get_all_attempts(
    topic_id: int,
    group: Group = Depends(require_group_admin),
    session: Session = Depends(get_session),
) -> list[Attempt]:
    """SOLO admin: devuelve todos los intentos de todos los miembros para supervisar el desempeño."""
    topic = repo.get_topic(session, topic_id)
    if not topic or topic.group_id != group.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TOPIC_NOT_FOUND", "message": "El tema no existe en este grupo."},
        )
    return repo.list_all_topic_attempts(session, topic.id)


@router.get("/{group_id}/topics/{topic_id}/summary", response_model=TopicSummaryResponse)
def get_topic_summary(
    topic_id: int,
    group: Group = Depends(require_group_admin),
    session: Session = Depends(get_session),
) -> dict:
    """SOLO admin: muestra un resumen por miembro con su mejor intento, último intento y promedios."""
    topic = repo.get_topic(session, topic_id)
    if not topic or topic.group_id != group.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TOPIC_NOT_FOUND", "message": "El tema no existe en este grupo."},
        )

    members = repo.get_group_members(session, group.id)
    members_summary = []

    for member in members:
        attempts = repo.list_user_attempts(session, topic.id, member.id)
        summary = compute_member_topic_summary(
            user_id=member.id,
            user_name=member.nombre,
            user_email=member.email,
            attempts=attempts,
        )
        members_summary.append(summary)

    return {
        "topic_id": topic.id,
        "group_id": group.id,
        "title": topic.title,
        "members_summary": members_summary,
    }

