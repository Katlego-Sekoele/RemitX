"""Admin stokvel vault emergency stop and manual release (R3-07, #244; R3-10, #247)."""

import uuid
from typing import Annotated, Literal

from pydantic import ConfigDict, StringConstraints

from remitx_api.models.schemas.base import LedgerDecimal, Schema, UtcDateTime

PauseReason = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=10, max_length=500)
]


class StokvelContractPauseRequest(Schema):
    """Why the administrator is pausing; recorded in the audit log."""

    model_config = ConfigDict(extra="forbid")

    reason: PauseReason


class StokvelContractActionResponse(Schema):
    """On-chain pause or unpause completed."""

    tx_hash: str


class StokvelContractRead(Schema):
    """The shared vault as the admin contract page shows it."""

    address: str
    network: str
    paused: bool
    paused_at: UtcDateTime | None
    paused_reason: str | None
    treasury_token_balance: LedgerDecimal


ReleaseStatusRead = Literal["pending", "processing", "released", "failed"]


class AdminStokvelRoundRead(Schema):
    """One round of one stokvel's open cycle, for the admin rounds list."""

    stokvel_id: uuid.UUID
    stokvel_name: str
    round: int
    total_rounds: int
    recipient_name: str | None
    paid_count: int
    member_count: int
    payout_time: UtcDateTime
    release_status: ReleaseStatusRead | None
    release_tx_hash: str | None


class StokvelRoundFinaliseResponse(Schema):
    """The round's release was queued. The worker sends `finalise`; the
    transaction hash is not known until that send."""

    stokvel_id: uuid.UUID
    cycle_id: uuid.UUID
    cycle_number: int
    round: int
