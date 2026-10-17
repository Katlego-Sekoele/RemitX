"""Creating stokvels and listing the caller's (R2-07).

Every query names the caller: Postgres row-level security would scope them
anyway, but SQLite (tests) has none, and the two must return the same rows.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from remitx_api.config import Config
from remitx_api.db.transaction import db_transaction
from remitx_api.errors.stokvels import (
    KycNotApprovedToCreateStokvelError,
    StokvelCurrencyAccountMissingError,
)
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.models.orm.user import short_display_name
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.kyc_application_repository import KycApplicationRepository
from remitx_api.repositories.stokvel_invitation_repository import (
    StokvelInvitationRepository,
)
from remitx_api.repositories.stokvel_member_repository import StokvelMemberRepository
from remitx_api.repositories.stokvel_repository import StokvelRepository

# `stokvels.contribution_amount` is Numeric(20, 8). A new stokvel reports the
# amount the way the column stores it, so POST and GET print it alike.
AMOUNT_QUANTUM = Decimal("0.00000001")


def _amount(value: Decimal) -> Decimal:
    return value.quantize(AMOUNT_QUANTUM)


@dataclass(frozen=True)
class StokvelView:
    stokvel_id: uuid.UUID
    name: str
    currency: str
    # Fixed UCTUSD amount for the stokvel's life (D13)
    contribution_amount: Decimal
    is_organiser: bool
    member_count: int
    max_members: int
    created_at: datetime
    deactivated_at: datetime | None


@dataclass(frozen=True)
class StokvelInvitationView:
    invitation_id: uuid.UUID
    stokvel_id: uuid.UUID
    stokvel_name: str
    currency: str
    contribution_amount: Decimal
    # None when the inviter has no first name on file
    invited_by_name: str | None
    created_at: datetime


@dataclass(frozen=True)
class StokvelListView:
    stokvels: list[StokvelView]
    invitations: list[StokvelInvitationView]


def stokvel_view(
    stokvel: Stokvel, user_id: uuid.UUID, *, member_count: int
) -> StokvelView:
    """`stokvel` as `user_id` sees it. Shared with accepting an invitation,
    which answers with the stokvel just joined."""
    return StokvelView(
        stokvel_id=stokvel.id,
        name=stokvel.name,
        currency=stokvel.currency,
        contribution_amount=_amount(stokvel.contribution_amount),
        is_organiser=stokvel.organiser_user_id == user_id,
        member_count=member_count,
        max_members=Config().MAX_STOKVEL_MEMBERS,
        created_at=stokvel.created_at,
        deactivated_at=stokvel.deactivated_at,
    )


class StokvelController:
    def __init__(self) -> None:
        self._accounts = AccountRepository()
        self._applications = KycApplicationRepository()
        self._stokvels = StokvelRepository()
        self._members = StokvelMemberRepository()
        self._invitations = StokvelInvitationRepository()

    @db_transaction
    def create_stokvel(
        self,
        user_id: uuid.UUID,
        name: str,
        currency: str,
        contribution_amount: Decimal,
    ) -> StokvelView:
        """Create a stokvel with the caller as its Organiser and first Member.

        One transaction: the stokvel, its `STOKVEL` ledger account (D9) and
        the Organiser's membership, paid from their own fiat account in the
        Stokvel currency. Nothing goes on-chain yet: `createStokvel` is sent
        when the first cycle starts.
        """
        if not self._applications.get_standing(user_id).is_verified:
            raise KycNotApprovedToCreateStokvelError()
        account = self._accounts.get_user_account(user_id, currency)
        if account is None:
            raise StokvelCurrencyAccountMissingError(currency)

        stokvel = self._stokvels.add(
            Stokvel(
                organiser_user_id=user_id,
                name=name,
                currency=currency,
                contribution_amount=contribution_amount,
            )
        )
        self._accounts.create_stokvel_account(stokvel)
        self._members.add(
            StokvelMember(
                stokvel_id=stokvel.id,
                user_id=user_id,
                account_id=account.account_id,
                invitation_id=None,
            )
        )
        return stokvel_view(stokvel, user_id, member_count=1)

    def list_stokvels(self, user_id: uuid.UUID) -> StokvelListView:
        """The stokvels the caller is a current member of, and their pending
        invitations, each newest first."""
        return StokvelListView(
            stokvels=[
                stokvel_view(stokvel, user_id, member_count=member_count)
                for stokvel, member_count in self._stokvels.list_for_member(user_id)
            ],
            invitations=[
                StokvelInvitationView(
                    invitation_id=invitation.id,
                    stokvel_id=stokvel.id,
                    stokvel_name=stokvel.name,
                    currency=stokvel.currency,
                    contribution_amount=_amount(stokvel.contribution_amount),
                    invited_by_name=short_display_name(
                        inviter.first_name, inviter.last_name
                    ),
                    created_at=invitation.created_at,
                )
                for invitation, stokvel, inviter in (
                    self._invitations.list_pending_for_invitee(user_id)
                )
            ],
        )
