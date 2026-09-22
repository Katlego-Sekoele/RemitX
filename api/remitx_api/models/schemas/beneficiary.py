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
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from remitx_api.models.orm.account import PAYOUT_CURRENCIES
from remitx_api.models.orm.beneficiary import RELATIONSHIPS
from remitx_api.models.schemas.base import Schema, UtcDateTime
from remitx_api.repositories.beneficiary_repository import BeneficiaryRow
from remitx_api.services.contact_masking import mask_email, mask_mobile


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


class BeneficiaryRead(Schema):
    """A sender's beneficiary, with the linked person's details read live from
    their profile.

    Build with `from_row`: the name, contact and country aren't columns on
    `beneficiaries` (see models/orm/beneficiary.py). Contact details are
    masked here and never leave the API in full — account references are
    guessable, so the list must not become a way to read a stranger's email
    or mobile.
    """

    beneficiary_id: uuid.UUID
    linked_user_id: uuid.UUID
    full_name: str | None = Field(
        description=(
            "The verified name from their approved KYC application, or the "
            "first name they signed up with until they are verified."
        )
    )
    country: str | None = Field(
        description="Verified country of residence, ISO 3166-1 alpha-2."
    )
    country_name: str | None = Field(description="That country's name.")
    masked_email: str | None = Field(examples=["t•••@gmail.com"])
    masked_mobile_number: str | None = Field(examples=["+2637••••••23"])
    payout_currency: str
    relationship: str
    created_at: UtcDateTime

    @classmethod
    def from_row(cls, row: BeneficiaryRow) -> "BeneficiaryRead":
        beneficiary, user, country = row
        return cls(
            beneficiary_id=beneficiary.beneficiary_id,
            linked_user_id=beneficiary.linked_user_id,
            full_name=user.full_name or user.first_name,
            country=user.country,
            country_name=None if country is None else country.name,
            masked_email=mask_email(user.email),
            masked_mobile_number=mask_mobile(user.mobile_number),
            payout_currency=beneficiary.payout_currency,
            relationship=beneficiary.relationship,
            created_at=beneficiary.created_at,
        )


class BeneficiaryLookupResponse(BaseModel):
    """The preview shown after a sender pastes in a beneficiary's fiat
    account reference (e.g. "sian1-zar"), before they confirm adding it as a
    beneficiary. Deliberately minimal — no email, no kyc_status, nothing
    private beyond a name to confirm "is this the right person"."""

    model_config = ConfigDict(from_attributes=True)

    linked_user_id: uuid.UUID = Field(validation_alias="id")
    first_name: str | None
