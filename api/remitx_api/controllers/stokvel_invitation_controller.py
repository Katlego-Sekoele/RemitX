"""Inviting users to a stokvel, and answering an invitation (R2-08).

Nobody becomes a Member without accepting. The database holds the same line:
a customer may insert their own member row only with their accepted
invitation (`V20261017_1820`), so accepting sets the invitation to
`accepted` before inserting the member, in one transaction.

Row-level security hides the invitee's KYC applications from the Organiser
and the member rows from an invitee who has not joined yet; those two checks
go through the lookups in `KycApplicationRepository.is_other_user_verified`
and `StokvelMemberRepository.count_active`.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from remitx_api.clock import utcnow
from remitx_api.config import Config
from remitx_api.controllers.stokvel_controller import StokvelView, stokvel_view
from remitx_api.db.transaction import db_transaction
from remitx_api.errors.stokvels import (
    AlreadyStokvelMemberError,
    CannotInviteYourselfError,
    InvitationAlreadyPendingError,
    InvitationNotFoundError,
    InvitationNotPendingError,
    InviteeAccountNotFoundError,
    InviteeCurrencyMismatchError,
    InviteeNotKycVerifiedError,
    KycNotApprovedToJoinStokvelError,
    NotInviteeError,
    NotStokvelOrganiserError,
    StokvelCurrencyAccountMissingError,
    StokvelDeactivatedError,
    StokvelNotFoundError,
    TooManyMembersError,
)
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_invitation import (
    StokvelInvitation,
    StokvelInvitationStatus,
)
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.models.orm.user import short_display_name
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.kyc_application_repository import KycApplicationRepository
from remitx_api.repositories.stokvel_invitation_repository import (
    StokvelInvitationRepository,
)
from remitx_api.repositories.stokvel_member_repository import StokvelMemberRepository
from remitx_api.repositories.stokvel_repository import StokvelRepository
from remitx_api.repositories.user_repository import UserRepository

_PENDING_CONSTRAINT = "uq_stokvel_invitations_pending"
# SQLite names no index in its error, only the columns of a unique one.
_PENDING_SQLITE_MESSAGE = (
    "UNIQUE constraint failed: stokvel_invitations.stokvel_id, "
    "stokvel_invitations.invitee_user_id"
)


def _is_invited_twice(exc: IntegrityError) -> bool:
    """Whether `exc` is a violation of `uq_stokvel_invitations_pending`.
    Postgres (psycopg2) names the index in the error's diagnostics; SQLite
    gives only the unique columns in its message."""
    diag = getattr(exc.orig, "diag", None)
    if diag is not None:
        return diag.constraint_name == _PENDING_CONSTRAINT
    return _PENDING_SQLITE_MESSAGE in str(exc.orig)


@dataclass(frozen=True)
class SentStokvelInvitationView:
    invitation_id: uuid.UUID
    stokvel_id: uuid.UUID
    # "Thandi M."; None when the invitee has no first name on file
    invitee_name: str | None
    account_reference: str
    status: str
    created_at: datetime


class StokvelInvitationController:
    def __init__(self) -> None:
        self._accounts = AccountRepository()
        self._applications = KycApplicationRepository()
        self._invitations = StokvelInvitationRepository()
        self._members = StokvelMemberRepository()
        self._stokvels = StokvelRepository()
        self._users = UserRepository()

    @db_transaction
    def invite(
        self, organiser_id: uuid.UUID, stokvel_id: uuid.UUID, account_reference: str
    ) -> SentStokvelInvitationView:
        """Invite the owner of `account_reference` to the stokvel.

        The member cap is checked here only to refuse early: invitations may
        outnumber free places, and accepting is where the cap holds.
        """
        stokvel = self._stokvels.get_by_id(stokvel_id)
        # Not visible to the caller: the same 404 as an unknown id. On
        # Postgres row-level security hides it; this keeps SQLite the same.
        if stokvel is None or not self._can_see(stokvel, organiser_id):
            raise StokvelNotFoundError()
        if stokvel.organiser_user_id != organiser_id:
            raise NotStokvelOrganiserError()
        if stokvel.deactivated_at is not None:
            raise StokvelDeactivatedError()

        account = self._accounts.get_user_account_by_reference(account_reference)
        if account is None or account.user_id is None:
            raise InviteeAccountNotFoundError(account_reference)
        invitee_id = account.user_id
        if invitee_id == organiser_id:
            raise CannotInviteYourselfError()
        if account.account_currency != stokvel.currency:
            raise InviteeCurrencyMismatchError(stokvel.currency)
        if not self._applications.is_other_user_verified(invitee_id):
            raise InviteeNotKycVerifiedError()
        if self._members.get_active_member(stokvel.id, invitee_id) is not None:
            raise AlreadyStokvelMemberError()
        max_members = Config().MAX_STOKVEL_MEMBERS
        if self._members.count_active(stokvel.id) >= max_members:
            raise TooManyMembersError(max_members)

        try:
            invitation = self._invitations.add(
                StokvelInvitation(
                    stokvel_id=stokvel.id,
                    invitee_user_id=invitee_id,
                    invited_by_user_id=organiser_id,
                )
            )
        except IntegrityError as exc:
            # Only the one-pending-invitation index means a concurrent invite
            # got there first. Any other constraint is a fault, raised as is.
            if _is_invited_twice(exc):
                raise InvitationAlreadyPendingError() from exc
            raise

        invitee = self._users.get_by_id(invitee_id)
        return SentStokvelInvitationView(
            invitation_id=invitation.id,
            stokvel_id=stokvel.id,
            invitee_name=short_display_name(invitee.first_name, invitee.last_name),
            account_reference=account.reference,
            status=invitation.status,
            created_at=invitation.created_at,
        )

    @db_transaction
    def accept(self, user_id: uuid.UUID, invitation_id: uuid.UUID) -> StokvelView:
        """Accept the caller's invitation: they become a Member, paying from
        their own account in the Stokvel currency. Answers with the stokvel
        they joined."""
        invitation = self._own_invitation(user_id, invitation_id)
        # Held until the commit, so two accepts cannot both pass the cap.
        # Nothing below may commit before the member is inserted.
        stokvel = self._stokvels.lock(invitation.stokvel_id)
        if stokvel is None:
            raise InvitationNotFoundError()
        if stokvel.deactivated_at is not None:
            raise StokvelDeactivatedError()
        if not self._applications.get_standing(user_id).is_verified:
            raise KycNotApprovedToJoinStokvelError()
        account = self._accounts.get_user_account(user_id, stokvel.currency)
        if account is None:
            raise StokvelCurrencyAccountMissingError(stokvel.currency)
        max_members = Config().MAX_STOKVEL_MEMBERS
        member_count = self._members.count_active(stokvel.id)
        if member_count >= max_members:
            raise TooManyMembersError(max_members)

        self._answer(invitation, user_id, StokvelInvitationStatus.ACCEPTED)
        self._members.add(
            StokvelMember(
                stokvel_id=stokvel.id,
                user_id=user_id,
                account_id=account.account_id,
                invitation_id=invitation.id,
            )
        )
        return stokvel_view(stokvel, user_id, member_count=member_count + 1)

    @db_transaction
    def decline(self, user_id: uuid.UUID, invitation_id: uuid.UUID) -> None:
        """Decline the caller's invitation. They do not become a Member."""
        invitation = self._own_invitation(user_id, invitation_id)
        self._answer(invitation, user_id, StokvelInvitationStatus.DECLINED)

    def _own_invitation(
        self, user_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> StokvelInvitation:
        """The invitation, if `user_id` is its invitee and it is still
        pending. A fellow member of the stokvel can see it but not answer it;
        anyone else gets the same 404 as an unknown id. Checked again by the
        guarded update, for a concurrent answer."""
        invitation = self._invitations.get_by_id(invitation_id)
        if invitation is None:
            raise InvitationNotFoundError()
        if invitation.invitee_user_id != user_id:
            if self._members.get_active_member(invitation.stokvel_id, user_id):
                raise NotInviteeError()
            raise InvitationNotFoundError()
        if invitation.status != StokvelInvitationStatus.PENDING.value:
            raise InvitationNotPendingError()
        return invitation

    def _answer(
        self,
        invitation: StokvelInvitation,
        user_id: uuid.UUID,
        status: StokvelInvitationStatus,
    ) -> None:
        if not self._invitations.set_status_if_pending(
            invitation.id, status, by_user_id=user_id, at=utcnow()
        ):
            raise InvitationNotPendingError()

    def _can_see(self, stokvel: Stokvel, user_id: uuid.UUID) -> bool:
        """The Organiser or a current member, as the invite refusals need
        it: anyone else gets 404, as row-level security answers on
        Postgres for an outsider."""
        return (
            stokvel.organiser_user_id == user_id
            or self._members.get_active_member(stokvel.id, user_id) is not None
        )
