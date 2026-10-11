"""Persistencia y consultas de grupos, membresías, temas e intentos."""

from __future__ import annotations

import secrets
import string
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.group import Attempt, Group, GroupMembership, Topic
from app.models.user import User


class GroupRepository:
    """Encapsula las operaciones de acceso a datos para la gestión grupal."""

    @staticmethod
    def generate_unique_code(session: Session, length: int = 6) -> str:
        chars = string.ascii_uppercase + string.digits
        for _ in range(30):
            code = "".join(secrets.choice(chars) for _ in range(length))
            exists = session.scalar(select(Group.id).where(Group.code == code))
            if not exists:
                return code
        raise RuntimeError("No se pudo generar un código único de grupo tras múltiples intentos.")

    def create_group(self, session: Session, *, name: str, admin_id: int) -> Group:
        code = self.generate_unique_code(session)
        group = Group(name=name, admin_id=admin_id, code=code)
        session.add(group)
        session.flush()

        # El creador queda registrado como miembro al crear el grupo
        membership = GroupMembership(group_id=group.id, user_id=admin_id)
        session.add(membership)
        session.flush()
        return group

    def get_group(self, session: Session, group_id: int) -> Group | None:
        return session.get(Group, group_id)

    def get_group_by_code(self, session: Session, code: str) -> Group | None:
        return session.scalar(select(Group).where(Group.code == code.upper()))

    def get_membership(self, session: Session, group_id: int, user_id: int) -> GroupMembership | None:
        return session.scalar(
            select(GroupMembership).where(
                GroupMembership.group_id == group_id, GroupMembership.user_id == user_id
            )
        )

    def add_member(self, session: Session, group_id: int, user_id: int) -> GroupMembership:
        membership = GroupMembership(group_id=group_id, user_id=user_id)
        session.add(membership)
        session.flush()
        return membership

    def get_user_groups(self, session: Session, user_id: int) -> tuple[list[Group], list[Group]]:
        """Devuelve (admin_groups, member_groups)."""
        admin_groups = list(
            session.scalars(
                select(Group).where(Group.admin_id == user_id).order_by(Group.created_at.desc())
            )
        )

        member_groups = list(
            session.scalars(
                select(Group)
                .join(GroupMembership, Group.id == GroupMembership.group_id)
                .where(GroupMembership.user_id == user_id, Group.admin_id != user_id)
                .order_by(Group.created_at.desc())
            )
        )
        return admin_groups, member_groups

    def get_group_members(self, session: Session, group_id: int) -> list[User]:
        """Obtiene la lista de usuarios que forman parte del grupo."""
        return list(
            session.scalars(
                select(User)
                .join(GroupMembership, User.id == GroupMembership.user_id)
                .where(GroupMembership.group_id == group_id)
                .order_by(User.nombre.asc())
            )
        )

    def get_group_members_detail(self, session: Session, group_id: int) -> list[dict[str, Any]]:
        """Obtiene la lista de miembros con metadatos de usuario y rol."""
        results = session.execute(
            select(GroupMembership, User)
            .join(User, GroupMembership.user_id == User.id)
            .where(GroupMembership.group_id == group_id)
            .order_by(GroupMembership.joined_at.asc())
        ).all()
        group = session.get(Group, group_id)
        admin_id = group.admin_id if group else None

        items: list[dict[str, Any]] = []
        for membership, user in results:
            items.append({
                "id": membership.id,
                "user_id": user.id,
                "nombre": user.nombre,
                "email": user.email,
                "is_admin": user.id == admin_id,
                "joined_at": membership.joined_at,
            })
        return items

    def remove_member(self, session: Session, group_id: int, user_id: int) -> bool:
        """Elimina la membresía de un usuario en un grupo."""
        membership = self.get_membership(session, group_id, user_id)
        if membership:
            session.delete(membership)
            session.flush()
            return True
        return False

    def regenerate_code(self, session: Session, group_id: int) -> Group | None:
        """Genera un nuevo código único de 6 caracteres para el grupo."""
        group = session.get(Group, group_id)
        if not group:
            return None
        group.code = self.generate_unique_code(session)
        session.flush()
        return group

    def create_topic(
        self,
        session: Session,
        *,
        group_id: int,
        video_id: int | None = None,
        material_id: int | None = None,
        title: str,
        description: str = "",
        created_by: int | None = None,
        is_active: bool = True,
        is_published: bool = True,
    ) -> Topic:
        topic = Topic(
            group_id=group_id,
            video_id=video_id,
            material_id=material_id,
            title=title,
            description=description or "",
            is_published=is_published,
            created_by=created_by,
            is_active=is_active,
        )
        session.add(topic)
        session.flush()
        return topic

    def list_active_topics(self, session: Session, group_id: int) -> list[Topic]:
        return list(
            session.scalars(
                select(Topic)
                .where(Topic.group_id == group_id, Topic.is_active.is_(True))
                .order_by(Topic.created_at.desc())
            )
        )

    def get_topic(self, session: Session, topic_id: int) -> Topic | None:
        return session.get(Topic, topic_id)

    def count_user_attempts(self, session: Session, topic_id: int, user_id: int) -> int:
        return (
            session.scalar(
                select(func.count(Attempt.id)).where(
                    Attempt.topic_id == topic_id, Attempt.user_id == user_id
                )
            )
            or 0
        )

    def save_attempt(
        self,
        session: Session,
        *,
        topic_id: int,
        user_id: int,
        attempt_number: int,
        raw_score: float,
        final_score: float,
        answers_json: str,
    ) -> Attempt:
        attempt = Attempt(
            topic_id=topic_id,
            user_id=user_id,
            attempt_number=attempt_number,
            raw_score=raw_score,
            final_score=final_score,
            answers_json=answers_json,
        )
        session.add(attempt)
        session.flush()
        return attempt

    def list_user_attempts(self, session: Session, topic_id: int, user_id: int) -> list[Attempt]:
        return list(
            session.scalars(
                select(Attempt)
                .where(Attempt.topic_id == topic_id, Attempt.user_id == user_id)
                .order_by(Attempt.attempt_number.asc())
            )
        )

    def list_all_topic_attempts(self, session: Session, topic_id: int) -> list[Attempt]:
        return list(
            session.scalars(
                select(Attempt)
                .where(Attempt.topic_id == topic_id)
                .order_by(Attempt.submitted_at.desc())
            )
        )

    def get_attempt(self, session: Session, attempt_id: int) -> Attempt | None:
        return session.get(Attempt, attempt_id)

    def update_attempt_score(
        self, session: Session, attempt: Attempt, final_score: float, review_notes: str | None = None
    ) -> Attempt:
        attempt.final_score = round(final_score, 2)
        if review_notes is not None:
            try:
                data = json.loads(attempt.answers_json) if attempt.answers_json else {}
                if isinstance(data, dict):
                    data["review_notes"] = review_notes
                    attempt.answers_json = json.dumps(data, ensure_ascii=False)
            except Exception:
                pass
        session.commit()
        session.refresh(attempt)
        return attempt

