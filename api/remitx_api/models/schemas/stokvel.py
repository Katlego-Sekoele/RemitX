"""Request/response schemas for creating and listing stokvels (R2-07),
inviting members (R2-08), setting up a cycle (R2-09) and contributing
(R2-11)."""

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
from remitx_api.controllers.stokvel_invitation_controller import (
    SentStokvelInvitationView,
)
from remitx_api.controllers.stokvel_setup_controller import (
    PayoutBeneficiaryView,
    PayoutOrderView,
    PayoutPlaceView,
)
from remitx_api.models.orm.account import PayoutCurrency
from remitx_api.models.orm.stokvel_invitation import StokvelInvitationStatus
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


class StokvelInvitationCreateRequest(Schema):
    """Invite the owner of an account to the stokvel."""

    model_config = ConfigDict(extra="forbid")

    account_reference: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
    ] = Field(
        description=(
            "The invitee's account reference, e.g. `thandi2-zar`. The account "
            "must be in the Stokvel currency: the invitee's contributions are "
            "paid from it."
        )
    )


class SentStokvelInvitationRead(Schema):
    """An invitation the Organiser has sent."""

    invitation_id: uuid.UUID
    stokvel_id: uuid.UUID
    # "Thandi M."; null when the invitee has no name on file.
    invitee_name: str | None
    account_reference: str
    status: StokvelInvitationStatus
    created_at: UtcDateTime

    @classmethod
    def from_view(cls, view: SentStokvelInvitationView) -> "SentStokvelInvitationRead":
        return cls(
            invitation_id=view.invitation_id,
            stokvel_id=view.stokvel_id,
            invitee_name=view.invitee_name,
            account_reference=view.account_reference,
            status=view.status,
            created_at=view.created_at,
        )


class StokvelPayoutOrderRequest(Schema):
    """The payout order the members agreed off the platform (D3)."""

    model_config = ConfigDict(extra="forbid")

    member_ids: list[uuid.UUID] = Field(
        min_length=1,
        description=(
            "Every current member's `member_id`, each once, in the order they "
            "are paid: the first is paid in round 0. Replaces any earlier "
            "order."
        ),
    )


class StokvelPayoutPlaceRead(Schema):
    """One member's place in the payout order."""

    member_id: uuid.UUID
    # 0-based, as on the contract: the round that pays this member.
    payout_position: int
    # "Thandi M."; null when the member has no name on file.
    name: str | None

    @classmethod
    def from_view(cls, view: PayoutPlaceView) -> "StokvelPayoutPlaceRead":
        return cls(
            member_id=view.member_id,
            payout_position=view.payout_position,
            name=view.name,
        )


class StokvelPayoutOrderRead(Schema):
    """The payout order of the stokvel's forming cycle, first paid first."""

    stokvel_id: uuid.UUID
    # 1 for the stokvel's first cycle.
    cycle_number: int
    order: list[StokvelPayoutPlaceRead]

    @classmethod
    def from_view(cls, view: PayoutOrderView) -> "StokvelPayoutOrderRead":
        return cls(
            stokvel_id=view.stokvel_id,
            cycle_number=view.cycle_number,
            order=[StokvelPayoutPlaceRead.from_view(place) for place in view.order],
        )


class StokvelBeneficiaryRequest(Schema):
    """The beneficiary the stokvel pays the caller's pool to."""

    model_config = ConfigDict(extra="forbid")

    beneficiary_id: uuid.UUID = Field(
        description=(
            "One of the caller's own beneficiaries (`GET /beneficiaries`). "
            "They are paid in the beneficiary's payout currency."
        )
    )


class StokvelBeneficiaryRead(Schema):
    """The caller's payout beneficiary for the stokvel's forming cycle."""

    stokvel_id: uuid.UUID
    # 1 for the stokvel's first cycle.
    cycle_number: int
    member_id: uuid.UUID
    beneficiary_id: uuid.UUID
    payout_currency: PayoutCurrency = Field(
        description=(
            "The beneficiary's payout currency when chosen. Fixed for the "
            "cycle once it starts."
        )
    )

    @classmethod
    def from_view(cls, view: PayoutBeneficiaryView) -> "StokvelBeneficiaryRead":
        return cls(
            stokvel_id=view.stokvel_id,
            cycle_number=view.cycle_number,
            member_id=view.member_id,
            beneficiary_id=view.beneficiary_id,
            payout_currency=view.payout_currency,
        )
