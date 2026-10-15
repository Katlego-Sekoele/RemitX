import uuid

from sqlalchemy import select

from remitx_api.extensions import db
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_invitation import (
    StokvelInvitation,
    StokvelInvitationStatus,
)
from remitx_api.models.orm.user import User
from remitx_api.repositories.repository import Repository


class StokvelInvitationRepository(Repository[StokvelInvitation, uuid.UUID]):
    """Repository for stokvel invitations. Queries here run under row-level security on
    Postgres; SQLite (tests) does not filter, so callers scope by user."""

    def __init__(self) -> None:
        super().__init__(StokvelInvitation)

    def list_pending_for_invitee(
        self, user_id: uuid.UUID
    ) -> list[tuple[StokvelInvitation, Stokvel, User]]:
        """`user_id`'s unanswered invitations, newest first, each with its
        stokvel and the user who sent it.

        Scoped by `user_id` here, not only by row-level security, so SQLite
        returns the same rows as Postgres.
        """
        rows = db.session.execute(
            select(StokvelInvitation, Stokvel, User)
            .join(Stokvel, Stokvel.id == StokvelInvitation.stokvel_id)
            .join(User, User.id == StokvelInvitation.invited_by_user_id)
            .where(
                StokvelInvitation.invitee_user_id == user_id,
                StokvelInvitation.status == StokvelInvitationStatus.PENDING.value,
            )
            .order_by(StokvelInvitation.created_at.desc(), StokvelInvitation.id)
        ).all()
        return [(invitation, stokvel, inviter) for invitation, stokvel, inviter in rows]
