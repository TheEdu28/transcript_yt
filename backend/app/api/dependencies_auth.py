"""Dependencias de autorización y control de acceso a nivel de grupo."""

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_session
from app.models.group import Group, GroupMember
from app.models.user import User
from app.services.auth_service import get_current_user


def require_group_admin(
    group_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Group:
    """Verifica que el grupo exista y que el usuario actual sea su administrador.

    Lanza:
        404 Not Found: si el grupo con group_id no existe.
        403 Forbidden: si el usuario no es el creador/admin del grupo.
    """
    group = session.get(Group, group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "GROUP_NOT_FOUND", "message": "El grupo especificado no existe."},
        )

    if group.admin_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN_NOT_GROUP_ADMIN",
                "message": "Acceso denegado: solo el administrador del grupo puede realizar esta acción.",
            },
        )

    return group


def require_group_member(
    group_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Group:
    """Verifica que el grupo exista y que el usuario sea miembro activo o su administrador.

    Lanza:
        404 Not Found: si el grupo no existe.
        403 Forbidden: si el usuario no pertenece al grupo.
    """
    group = session.get(Group, group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "GROUP_NOT_FOUND", "message": "El grupo especificado no existe."},
        )

    # El administrador del grupo siempre tiene acceso como miembro
    if group.admin_id == current_user.id:
        return group

    # Verificar si está registrado en la tabla de miembros
    membership = (
        session.query(GroupMember)
        .filter(GroupMember.group_id == group_id, GroupMember.user_id == current_user.id)
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN_NOT_GROUP_MEMBER",
                "message": "Acceso denegado: debes pertenecer al grupo para consultar sus recursos.",
            },
        )

    return group
