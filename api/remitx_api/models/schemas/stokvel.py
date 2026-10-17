"""Request/response schemas for creating and listing stokvels (R2-07) and
contributing to one (R2-11)."""

import uuid
from typing import Annotated

from pydantic import ConfigDict, Field, StringConstraints

from remitx_api.controllers.stokvel_contribution_controller import (
    StokvelContributionView,
)
from remitx_api.controllers.stokvel_controller import (
    StokvelInvitationView,
    StokvelListView,
    StokvelView,
)
from remitx_api.models.orm.account import PayoutCurrency
from remitx_api.models.schemas.base import Amount, LedgerDecimal, Schema, UtcDateTime

# A Stokvel currency is any fiat currency a customer can hold an account in.
StokvelCurrency = PayoutCurrency

STOKVEL_NAME_MAX_LENGTH = 80

_CONTRIBUTION_DESCRIPTION = (
    "Fixed UCTUSD (token) amount each member contributes per round, for the "
    "stokvel's life (D13). Members pay it from their account in the Stokvel "
    "currency at the live rate when they contribute."
)


class StokvelCreateRequest(Schema):
    """A new stokvel. The caller becomes its Organiser and first Member."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=STOKVEL_NAME_MAX_LENGTH
        ),
    ]
    currency: StokvelCurrency = Field(
        description=(
            "The Stokvel currency. The caller must already hold a fiat "
            "account in it: contributions are paid from that account."
        )
    )
    contribution_amount: Amount = Field(description=_CONTRIBUTION_DESCRIPTION)


class StokvelRead(Schema):
    """A stokvel the caller is a current member of."""

    stokvel_id: uuid.UUID
    name: str
    currency: StokvelCurrency
    contribution_amount: LedgerDecimal = Field(description=_CONTRIBUTION_DESCRIPTION)
    is_organiser: bool
    # Current members, the Organiser included.
    member_count: int
    # The platform-wide member cap (MAX_STOKVEL_MEMBERS).
    max_members: int
    created_at: UtcDateTime
    # Null while the stokvel is in service.
    deactivated_at: UtcDateTime | None

    @classmethod
    def from_view(cls, view: StokvelView) -> "StokvelRead":
        return cls(
            stokvel_id=view.stokvel_id,
            name=view.name,
            currency=view.currency,
            contribution_amount=view.contribution_amount,
            is_organiser=view.is_organiser,
            member_count=view.member_count,
            max_members=view.max_members,
            created_at=view.created_at,
            deactivated_at=view.deactivated_at,
        )


class StokvelInvitationRead(Schema):
    """An invitation to join a stokvel that the caller has not answered."""

    invitation_id: uuid.UUID
    stokvel_id: uuid.UUID
    stokvel_name: str
    currency: StokvelCurrency
    contribution_amount: LedgerDecimal = Field(description=_CONTRIBUTION_DESCRIPTION)
    # "Tendai M."; null when the inviter has no name on file.
    invited_by_name: str | None
    created_at: UtcDateTime

    @classmethod
    def from_view(cls, view: StokvelInvitationView) -> "StokvelInvitationRead":
        return cls(
            invitation_id=view.invitation_id,
            stokvel_id=view.stokvel_id,
            stokvel_name=view.stokvel_name,
            currency=view.currency,
            contribution_amount=view.contribution_amount,
            invited_by_name=view.invited_by_name,
            created_at=view.created_at,
        )


class StokvelListRead(Schema):
    """The caller's stokvels and pending invitations, each newest first."""

    stokvels: list[StokvelRead]
    invitations: list[StokvelInvitationRead]

    @classmethod
    def from_view(cls, view: StokvelListView) -> "StokvelListRead":
        return cls(
            stokvels=[StokvelRead.from_view(item) for item in view.stokvels],
            invitations=[
                StokvelInvitationRead.from_view(item) for item in view.invitations
            ],
        )


class StokvelContributionRead(Schema):
    """A contribution just recorded. It is `pending` until the worker has
    sent `contribute` on-chain and it is mined; then `confirmed`, or `failed`
    if nothing landed (the member may then pay the round again)."""

    contribution_id: uuid.UUID
    stokvel_id: uuid.UUID
    # 1 for the stokvel's first cycle.
    cycle_number: int
    # 0-based, as on the contract.
    round: int
    status: str
    # The Stokvel currency the member paid in.
    currency: StokvelCurrency
    amount_token: LedgerDecimal = Field(
        description="UCTUSD sent to the contract: the stokvel's fixed contribution."
    )
    amount_fiat: LedgerDecimal = Field(
        description="Debited from the member's account: amount_token at the live rate."
    )
    fee_amount: LedgerDecimal = Field(
        description=(
            "The member's equal share of the round's payout fee (FSE's fee "
            "and FX margin on the pool), rounded up to the cent and debited "
            "on top of amount_fiat."
        )
    )
    amount_zar: LedgerDecimal = Field(
        description="amount_fiat plus the fee in rand: what counts against the limits."
    )
    created_at: UtcDateTime

    @classmethod
    def from_view(cls, view: StokvelContributionView) -> "StokvelContributionRead":
        return cls(
            contribution_id=view.contribution_id,
            stokvel_id=view.stokvel_id,
            cycle_number=view.cycle_number,
            round=view.round,
            status=view.status,
            currency=view.currency,
            amount_token=view.amount_token,
            amount_fiat=view.amount_fiat,
            fee_amount=view.fee_amount,
            amount_zar=view.amount_zar,
            created_at=view.created_at,
        )
