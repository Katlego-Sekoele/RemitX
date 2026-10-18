import uuid

from sqlalchemy import func, select

from remitx_api.extensions import db
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.repositories.repository import Repository


class StokvelRepository(Repository[Stokvel, uuid.UUID]):
    """Repository for stokvels. Queries here run under row-level security on
    Postgres; SQLite (tests) does not filter, so callers scope by user."""

    def __init__(self) -> None:
        super().__init__(Stokvel)

    def lock(self, stokvel_id: uuid.UUID) -> Stokvel | None:
        """The stokvel, locked until the transaction ends, or None if the
        caller cannot see it. Accepting an invitation holds it so two accepts
        cannot both pass `MAX_STOKVEL_MEMBERS`. A pending invitee may take
        the lock: the read rule, which they pass, is also the update rule's
        `USING`."""
        return db.session.scalars(
            select(Stokvel).where(Stokvel.id == stokvel_id).with_for_update()
        ).one_or_none()

    def list_for_member(self, user_id: uuid.UUID) -> list[tuple[Stokvel, int]]:
        """Stokvels `user_id` is a current member of, newest first, each with
        its number of current members. Former memberships are left out.

        Scoped by `user_id` here, not only by row-level security, so SQLite
        returns the same rows as Postgres.
        """
        mine = (
            select(StokvelMember.stokvel_id)
            .where(StokvelMember.user_id == user_id, StokvelMember.left_at.is_(None))
            .subquery()
        )
        counts = (
            select(
                StokvelMember.stokvel_id,
                func.count().label("member_count"),
            )
            .where(StokvelMember.left_at.is_(None))
            .group_by(StokvelMember.stokvel_id)
            .subquery()
        )
        rows = db.session.execute(
            select(Stokvel, counts.c.member_count)
            .join(mine, mine.c.stokvel_id == Stokvel.id)
            .join(counts, counts.c.stokvel_id == Stokvel.id)
            .order_by(Stokvel.created_at.desc(), Stokvel.id)
        ).all()
        return [(stokvel, member_count) for stokvel, member_count in rows]
