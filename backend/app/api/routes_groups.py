"""Endpoints para administración de grupos, temas y control de accesos."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies_auth import require_group_admin, require_group_member
from app.db.database import get_session
from app.models.group import ActivityAttempt, Group, GroupMember, Topic
from app.models.user import User
from app.schemas.contracts import (
    AttemptCreate,
    AttemptResponse,
    GroupCreate,
    GroupMemberAdd,
    GroupMemberResponse,
    GroupResponse,
    GroupUpdate,
    TopicCreate,
    TopicResponse,
    TopicUpdate,
)
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/api/v1/groups", tags=["groups"])


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: GroupCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Group:
    """Crea un grupo registrando al usuario autenticado como su admin_id."""
    group = Group(name=payload.name.strip(), admin_id=current_user.id)
    session.add(group)
    session.flush()

    # Añadir al creador como miembro del grupo automáticamente
    membership = GroupMember(group_id=group.id, user_id=current_user.id)
    session.add(membership)
    session.commit()
    session.refresh(group)
    return group


@router.get("", response_model=list[GroupResponse])
def list_my_groups(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[Group]:
    """Lista todos los grupos donde el usuario autenticado es admin o miembro."""
    member_group_ids = select(GroupMember.group_id).where(GroupMember.user_id == current_user.id)
    groups = (
        session.query(Group)
        .filter(
            (Group.admin_id == current_user.id) | (Group.id.in_(member_group_ids))
        )
        .order_by(Group.created_at.desc())
        .all()
    )
    return groups


@router.get("/{group_id}", response_model=GroupResponse)
def get_group(
    group: Group = Depends(require_group_member),
) -> Group:
    """Obtiene los detalles del grupo. Accesible para cualquier miembro o admin."""
    return group


@router.patch("/{group_id}", response_model=GroupResponse)
def update_group(
    payload: GroupUpdate,
    group: Group = Depends(require_group_admin),
    session: Session = Depends(get_session),
) -> Group:
    """Edita el nombre del grupo. Solo permitido para el admin del grupo."""
    group.name = payload.name.strip()
    session.commit()
    session.refresh(group)
    return group


@router.post("/{group_id}/members", response_model=GroupMemberResponse, status_code=status.HTTP_201_CREATED)
def add_member(
    payload: GroupMemberAdd,
    group: Group = Depends(require_group_admin),
    session: Session = Depends(get_session),
) -> GroupMember:
    """Agrega un usuario como miembro del grupo. Solo el admin puede añadir miembros."""
    target_user = session.get(User, payload.user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "El usuario a incorporar no existe."},
        )

    existing = (
        session.query(GroupMember)
        .filter(GroupMember.group_id == group.id, GroupMember.user_id == payload.user_id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "MEMBER_ALREADY_EXISTS", "message": "El usuario ya es miembro de este grupo."},
        )

    member = GroupMember(group_id=group.id, user_id=payload.user_id)
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


@router.delete("/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    user_id: int,
    group: Group = Depends(require_group_admin),
    session: Session = Depends(get_session),
) -> None:
    """Remueve a un miembro del grupo. Solo permitido para el admin."""
    if user_id == group.admin_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "CANNOT_REMOVE_ADMIN", "message": "No se puede remover al administrador del grupo."},
        )

    membership = (
        session.query(GroupMember)
        .filter(GroupMember.group_id == group.id, GroupMember.user_id == user_id)
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MEMBER_NOT_FOUND", "message": "El miembro no fue encontrado en este grupo."},
        )

    session.delete(membership)
    session.commit()


@router.post("/{group_id}/topics", response_model=TopicResponse, status_code=status.HTTP_201_CREATED)
def create_topic(
    payload: TopicCreate,
    group: Group = Depends(require_group_admin),
    session: Session = Depends(get_session),
) -> Topic:
    """Crea una nueva actividad o tema. Solo permitido para el admin del grupo."""
    topic = Topic(
        group_id=group.id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        is_published=payload.is_published,
        video_id=payload.video_id,
    )
    session.add(topic)
    session.commit()
    session.refresh(topic)
    return topic


@router.get("/{group_id}/topics", response_model=list[TopicResponse])
def list_topics(
    group: Group = Depends(require_group_member),
    session: Session = Depends(get_session),
) -> list[Topic]:
    """Lista los temas del grupo. Accesible para cualquier miembro y para el admin."""
    topics = (
        session.query(Topic)
        .filter(Topic.group_id == group.id)
        .order_by(Topic.created_at.asc())
        .all()
    )
    return topics


@router.patch("/{group_id}/topics/{topic_id}", response_model=TopicResponse)
def update_topic(
    topic_id: int,
    payload: TopicUpdate,
    group: Group = Depends(require_group_admin),
    session: Session = Depends(get_session),
) -> Topic:
    """Modifica un tema existente. Solo permitido para el admin del grupo."""
    topic = session.get(Topic, topic_id)
    if not topic or topic.group_id != group.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TOPIC_NOT_FOUND", "message": "El tema no existe en este grupo."},
        )

    if payload.title is not None:
        topic.title = payload.title.strip()
    if payload.description is not None:
        topic.description = payload.description.strip()
    if payload.is_published is not None:
        topic.is_published = payload.is_published
    if payload.video_id is not None:
        topic.video_id = payload.video_id

    session.commit()
    session.refresh(topic)
    return topic


@router.delete("/{group_id}/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_topic(
    topic_id: int,
    group: Group = Depends(require_group_admin),
    session: Session = Depends(get_session),
) -> None:
    """Elimina un tema del grupo. Solo permitido para el admin del grupo."""
    topic = session.get(Topic, topic_id)
    if not topic or topic.group_id != group.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TOPIC_NOT_FOUND", "message": "El tema no existe en este grupo."},
        )

    session.delete(topic)
    session.commit()


@router.get("/{group_id}/attempts", response_model=list[AttemptResponse])
def list_all_group_attempts(
    group: Group = Depends(require_group_admin),
    session: Session = Depends(get_session),
) -> list[ActivityAttempt]:
    """Lista todos los intentos de todos los miembros del grupo. Solo para el admin."""
    topic_ids = select(Topic.id).where(Topic.group_id == group.id)
    attempts = (
        session.query(ActivityAttempt)
        .filter(ActivityAttempt.topic_id.in_(topic_ids))
        .order_by(ActivityAttempt.created_at.desc())
        .all()
    )
    return attempts


@router.get("/{group_id}/my-attempts", response_model=list[AttemptResponse])
def list_my_attempts(
    group: Group = Depends(require_group_member),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ActivityAttempt]:
    """Lista SOLO los intentos del usuario autenticado dentro del grupo."""
    topic_ids = select(Topic.id).where(Topic.group_id == group.id)
    attempts = (
        session.query(ActivityAttempt)
        .filter(
            ActivityAttempt.topic_id.in_(topic_ids),
            ActivityAttempt.user_id == current_user.id,
        )
        .order_by(ActivityAttempt.created_at.desc())
        .all()
    )
    return attempts


@router.post(
    "/{group_id}/topics/{topic_id}/attempts",
    response_model=AttemptResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_attempt(
    topic_id: int,
    payload: AttemptCreate,
    group: Group = Depends(require_group_member),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ActivityAttempt:
    """Registra la realización de una actividad. Cualquier miembro del grupo puede realizarla."""
    topic = session.get(Topic, topic_id)
    if not topic or topic.group_id != group.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TOPIC_NOT_FOUND", "message": "El tema no existe en este grupo."},
        )

    attempt = ActivityAttempt(
        topic_id=topic.id,
        user_id=current_user.id,
        score=payload.score,
        details=payload.details.strip(),
    )
    session.add(attempt)
    session.commit()
    session.refresh(attempt)
    return attempt
