"""Admin stokvel vault emergency stop and manual release (R3-07, #244; R3-10, #247)."""

import uuid
from typing import Annotated

from pydantic import ConfigDict, StringConstraints

from remitx_api.models.schemas.base import Schema

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


class StokvelRoundFinaliseResponse(Schema):
    """The round's release was queued. The worker sends `finalise`; the
    transaction hash is not known until that send."""

    stokvel_id: uuid.UUID
    cycle_id: uuid.UUID
    cycle_number: int
    round: int
