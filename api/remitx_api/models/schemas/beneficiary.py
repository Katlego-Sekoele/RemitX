"""
Request/response schemas for the customer beneficiary endpoints.
Validates input before it ever reaches the database layer, and shapes the
output for the API response.

first_name/last_name/email/mobile_number/country are NOT request fields on
BeneficiaryCreateRequest — a beneficiary must already be a registered User
(see models/orm/beneficiary.py), so all of those come from that User, not
from the sender. "mobile_number or email required" (brief) is therefore
enforced in BeneficiaryController.create, not here — it's a precondition on
the resolved User's own profile, not anything in this request.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from remitx_api.models.orm.account import PAYOUT_CURRENCIES
from remitx_api.models.orm.beneficiary import RELATIONSHIPS, Beneficiary
from remitx_api.models.orm.user import User


class BeneficiaryCreateRequest(BaseModel):
    """Schema for creating a new beneficiary."""

    # Parameters the user provides in the request body
    linked_user_id: uuid.UUID
    payout_currency: Annotated[str, Field(examples=list(PAYOUT_CURRENCIES))]
    relationship: Annotated[str, Field(examples=list(RELATIONSHIPS))]

    @model_validator(mode="after")
    def _payout_currency_is_valid(self) -> "BeneficiaryCreateRequest":
        """Validate that the payout_currency is one of the allowed values.
        If not, raise a ValueError which will be caught and returned as a 422."""
        if self.payout_currency not in PAYOUT_CURRENCIES:
            raise ValueError(f"payout_currency must be one of {PAYOUT_CURRENCIES}")
        return self

    @model_validator(mode="after")
    def _relationship_is_valid(self) -> "BeneficiaryCreateRequest":
        """Validate that the relationship is one of the allowed values.
        If not, raise a ValueError which will be caught and returned as a 422."""
        if self.relationship not in RELATIONSHIPS:
            raise ValueError(f"relationship must be one of {RELATIONSHIPS}")
        return self


class BeneficiaryRead(BaseModel):
    """Schema for reading a beneficiary.

    Can't be built with plain `from_attributes=True` off a bare `Beneficiary`
    — first_name/last_name/email/mobile_number/country aren't columns on
    that table (see models/orm/beneficiary.py). Always construct via
    `from_beneficiary_and_user`.
    """

    beneficiary_id: uuid.UUID
    linked_user_id: uuid.UUID
    first_name: str | None
    last_name: str | None
    mobile_number: str | None
    email: str | None
    country: str | None
    payout_currency: str
    relationship: str
    created_at: datetime

    @classmethod
    def from_beneficiary_and_user(
        cls, beneficiary: Beneficiary, user: User
    ) -> "BeneficiaryRead":
        return cls(
            beneficiary_id=beneficiary.beneficiary_id,
            linked_user_id=beneficiary.linked_user_id,
            first_name=user.first_name,
            last_name=user.last_name,
            mobile_number=user.mobile_number,
            email=user.email,
            country=user.country,
            payout_currency=beneficiary.payout_currency,
            relationship=beneficiary.relationship,
            created_at=beneficiary.created_at,
        )

    @field_serializer("created_at")
    def _as_utc(self, value: datetime) -> str:
        """Serialize the created_at field as an ISO 8601 string in UTC."""
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()


class BeneficiaryLookupResponse(BaseModel):
    """The preview shown after a sender pastes in a beneficiary's fiat
    account reference (e.g. "sian1-zar"), before they confirm adding it as a
    beneficiary. Deliberately minimal — no email, no kyc_status, nothing
    private beyond a name to confirm "is this the right person"."""

    model_config = ConfigDict(from_attributes=True)

    linked_user_id: uuid.UUID = Field(validation_alias="id")
    first_name: str | None
