"""Request/response schemas for the customer remittance-confirmation endpoint."""

import uuid
from decimal import Decimal

from pydantic import ConfigDict

from remitx_api.models.schemas.base import Schema, UtcDateTime


class RemittanceConfirmRequest(Schema):
    quote_id: uuid.UUID

    """A request to confirm a remittance."""


class RemittanceRead(Schema):
    """A read-only representation of a remittance."""

    model_config = ConfigDict(from_attributes=True)

    remittance_id: uuid.UUID
    quote_id: uuid.UUID
    tx_id: uuid.UUID
    status: str
    sender_amount: Decimal
    sender_currency: str
    token_amount: Decimal
    token_name: str
    receiver_amount: Decimal
    receiver_currency: str
    created_at: UtcDateTime
