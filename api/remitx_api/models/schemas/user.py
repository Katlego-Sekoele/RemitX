"""Request/response schemas for user-facing and admin user endpoints."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from remitx_api.models.orm.user import KYC_APPROVED, KYC_UNVERIFIED


class KycStatusUpdate(BaseModel):
    kyc_status: Annotated[
        Literal["UNVERIFIED", "APPROVED"],
        Field(examples=[KYC_APPROVED, KYC_UNVERIFIED]),
    ]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kyc_status: str
    created_at: datetime

    @field_serializer("created_at")
    def _as_utc(self, value: datetime) -> str:
        # See models/schemas/integration_message.py for why this is needed:
        # SQLite drops the tz offset Postgres preserves.
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
