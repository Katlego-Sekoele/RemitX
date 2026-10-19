import uuid
from datetime import datetime

from sqlalchemy import select, update

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
        stokvel and the user who sent it. An invitation to a deactivated
        stokvel is left out: it can no longer be accepted.

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
                Stokvel.deactivated_at.is_(None),
            )
            .order_by(StokvelInvitation.created_at.desc(), StokvelInvitation.id)
        ).all()
        return [(invitation, stokvel, inviter) for invitation, stokvel, inviter in rows]

    def set_status_if_pending(
        self,
        invitation_id: uuid.UUID,
        status: StokvelInvitationStatus,
        *,
        by_user_id: uuid.UUID,
        at: datetime,
    ) -> bool:
        """Move a pending invitation to its final `status`, recording who
        changed it and when. Guarded by `status = 'pending'`, so of two
        requests answering the same invitation exactly one changes it.
        Whether this one did. Flushes only: the caller commits."""
        result = db.session.execute(
            update(StokvelInvitation)
            .where(
                StokvelInvitation.id == invitation_id,
                StokvelInvitation.status == StokvelInvitationStatus.PENDING.value,
            )
            .values(
                status=status.value,
                status_changed_at=at,
                status_changed_by_user_id=by_user_id,
            )
            .execution_options(synchronize_session="fetch")
        )
        return result.rowcount == 1

    def lapse_pending(
        self, stokvel_id: uuid.UUID, *, by_user_id: uuid.UUID, at: datetime
    ) -> int:
        """Lapse every invitation to the stokvel that is still pending, as
        when its Organiser starts a cycle (CONTEXT.md, Invitation): the
        invitee is not a member of that cycle. Recorded as the Organiser's
        answer (`V20261019_1052`). The number lapsed. Flushes only: the
        caller commits."""
        result = db.session.execute(
            update(StokvelInvitation)
            .where(
                StokvelInvitation.stokvel_id == stokvel_id,
                StokvelInvitation.status == StokvelInvitationStatus.PENDING.value,
            )
            .values(
                status=StokvelInvitationStatus.LAPSED.value,
                status_changed_at=at,
                status_changed_by_user_id=by_user_id,
            )
            # "evaluate" updates any loaded invitation in Python; "fetch"
            # would SELECT the rows first, and only the count is used.
            .execution_options(synchronize_session="evaluate")
        )
        return result.rowcount
