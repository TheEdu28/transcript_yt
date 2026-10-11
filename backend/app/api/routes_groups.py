"""Rutas de API para la gestión de grupos, temas, miembros y libro de calificaciones."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies_auth import require_group_admin, require_group_member
from app.core.errors import PipelineError
from app.db.database import get_session
from app.models.group import Attempt, Group, GroupMembership, Topic
from app.models.user import User
from app.repositories.group_repository import GroupRepository
from app.schemas.contracts import (
    AdminAttemptResponse,
    AttemptGradeUpdate,
    AttemptResponse,
    AttemptSubmitRequest,
    GroupCreate,
    GroupGradesResponse,
    GroupJoinRequest,
    GroupMemberAdd,
    GroupMemberDetail,
    GroupMemberResponse,
    GroupResponse,
    MyGroupsResponse,
    TopicCreate,
    TopicMaterialsResponse,
    TopicResponse,
    TopicSummaryResponse,
    TopicUpdate,
)
from app.services.auth_service import get_current_user
from app.services.group_service import GroupService

router = APIRouter(prefix="/api/v1/groups", tags=["groups"])
repo = GroupRepository()
group_service = GroupService(repo)


def raise_http(error: PipelineError) -> None:
    """Eleva errores funcionales estables hacia el cliente HTTP."""
    raise HTTPException(status_code=error.status_code, detail={"code": error.code, "message": str(error)})


# =============================================================================
# Grupos y Membresías
# =============================================================================
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
    """Permite al usuario autenticado unirse a un grupo mediante su código alfanumérico."""
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
    """Lista todos los grupos donde el usuario es admin o miembro."""
    admin_groups, member_groups = repo.get_user_groups(session, current_user.id)
    return admin_groups + member_groups


@router.get("/mine", response_model=MyGroupsResponse)
def get_my_groups(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, list[Group]]:
    """Devuelve los grupos divididos en admin_groups y member_groups."""
    admin_groups, member_groups = repo.get_user_groups(session, current_user.id)
    return {"admin_groups": admin_groups, "member_groups": member_groups}


@router.get("/{group_id}", response_model=GroupResponse)
def get_group(
    group: Group = Depends(require_group_member),
) -> Group:
    """Obtiene los detalles del grupo para cualquier miembro autorizado."""
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
    """Lista los integrantes del grupo con detalles de usuario y rol."""
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
    """SOLO admin: expulsa a un miembro del grupo."""
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


# =============================================================================
# Temas y Actividades Académicas
# =============================================================================
@router.post("/{group_id}/topics", response_model=TopicResponse, status_code=status.HTTP_201_CREATED)
def create_topic(
    payload: TopicCreate,
    group: Group = Depends(require_group_admin),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Topic:
    """SOLO admin: crea un nuevo tema/actividad asociando video y cuestionario."""
    try:
        return group_service.create_topic(session, group, current_user, payload)
    except PipelineError as error:
        raise_http(error)


@router.get("/{group_id}/topics", response_model=list[TopicResponse])
def list_topics(
    group: Group = Depends(require_group_member),
    session: Session = Depends(get_session),
) -> list[TopicResponse]:
    """Cualquier miembro del grupo puede ver sus temas activos con materiales vinculados."""
    return group_service.list_topics_with_materials(session, group)


@router.patch("/{group_id}/topics/{topic_id}", response_model=TopicResponse)
def update_topic(
    topic_id: int,
    payload: TopicUpdate,
    group: Group = Depends(require_group_admin),
    session: Session = Depends(get_session),
) -> Topic:
    """SOLO admin: activa, pausa o renombra un tema existente."""
    try:
        return group_service.update_topic(session, group, topic_id, payload)
    except PipelineError as error:
        raise_http(error)


@router.delete("/{group_id}/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_topic(
    topic_id: int,
    group: Group = Depends(require_group_admin),
    session: Session = Depends(get_session),
) -> Response:
    """SOLO admin: elimina un tema existente de su grupo."""
    try:
        group_service.delete_topic(session, group, topic_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PipelineError as error:
        raise_http(error)


@router.get("/{group_id}/topics/{topic_id}/materials", response_model=TopicMaterialsResponse)
def get_topic_materials(
    topic_id: int,
    group: Group = Depends(require_group_member),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TopicMaterialsResponse:
    """Devuelve los materiales compartidos del tema (del docente) y los personales del estudiante."""
    try:
        return group_service.get_topic_materials(session, group, topic_id, current_user)
    except PipelineError as error:
        raise_http(error)


# =============================================================================
# Intentos y Libro de Calificaciones
# =============================================================================
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
    """Envía respuestas a evaluación determinista + RAG, penaliza reintentos y guarda el Attempt."""
    try:
        return group_service.submit_topic_attempt(session, group, topic_id, current_user, payload)
    except PipelineError as error:
        raise_http(error)


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
    """SOLO admin: devuelve todos los intentos de todos los miembros del tema."""
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
) -> TopicSummaryResponse:
    """SOLO admin: muestra un resumen por miembro con mejor intento, último intento y promedios."""
    try:
        return group_service.get_topic_summary(session, group, topic_id)
    except PipelineError as error:
        raise_http(error)


@router.get("/{group_id}/grades", response_model=GroupGradesResponse)
def get_group_grades(
    group: Group = Depends(require_group_member),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> GroupGradesResponse:
    """Libro de calificaciones: el admin consulta todos los miembros; un miembro solo ve lo propio."""
    try:
        return group_service.get_group_grades(session, group, current_user)
    except PipelineError as error:
        raise_http(error)


@router.patch("/{group_id}/topics/{topic_id}/attempts/{attempt_id}", response_model=AdminAttemptResponse)
def update_attempt_grade(
    topic_id: int,
    attempt_id: int,
    payload: AttemptGradeUpdate,
    group: Group = Depends(require_group_admin),
    session: Session = Depends(get_session),
) -> Attempt:
    """SOLO admin: revisa y ajusta la calificación final de un intento manualmente."""
    try:
        return group_service.update_attempt_grade(session, group, topic_id, attempt_id, payload)
    except PipelineError as error:
        raise_http(error)
