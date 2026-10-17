import uuid

from sqlalchemy import select

from remitx_api.extensions import db
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.repositories.repository import Repository


class StokvelMemberRepository(Repository[StokvelMember, uuid.UUID]):
    """Repository for stokvel memberships. Queries here run under row-level security on
    Postgres; SQLite (tests) does not filter, so callers scope by user."""

    def __init__(self) -> None:
        super().__init__(StokvelMember)

    def get_active_member(
        self, stokvel_id: uuid.UUID, user_id: uuid.UUID
    ) -> StokvelMember | None:
        """The user's current membership of the stokvel (not left), if any.
        There is at most one (uq_stokvel_members_active)."""
        return db.session.scalars(
            select(StokvelMember).where(
                StokvelMember.stokvel_id == stokvel_id,
                StokvelMember.user_id == user_id,
                StokvelMember.left_at.is_(None),
            )
        ).one_or_none()
