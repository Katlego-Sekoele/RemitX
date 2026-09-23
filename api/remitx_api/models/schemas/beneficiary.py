"""
Request/response schemas for the customer beneficiary endpoints.
Validates input before it ever reaches the database layer, and shapes the
output for the API response.

Name, email, mobile number and country are NOT request fields on
BeneficiaryCreateRequest — a beneficiary must already be a registered User
(see models/orm/beneficiary.py), so all of those come from that User, not
from the sender. "mobile_number or email required" (brief) is therefore
enforced in BeneficiaryController.create, not here — it's a precondition on
the resolved User's own profile, not anything in this request.
"""

import uuid

from pydantic import ConfigDict, Field, model_validator

from remitx_api.controllers.beneficiary_controller import ReferenceLookup
from remitx_api.models.orm.account import PayoutCurrency
from remitx_api.models.orm.beneficiary import BeneficiaryRelationship
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.base import Schema, UtcDateTime
from remitx_api.repositories.beneficiary_repository import BeneficiaryRow
from remitx_api.services.contact_masking import mask_email, mask_mobile


def short_display_name(user: User) -> str | None:
    """First name and last initial, e.g. "Tendai M.", from the verified name
    when there is one; the Clerk first name alone until then."""
    words = (user.full_name or "").split()
    if len(words) >= 2:
        return f"{words[0]} {words[-1][0].upper()}."
    if words:
        return words[0]
    return user.first_name


class BeneficiaryCreateRequest(Schema):
    """Schema for creating a new beneficiary."""

    model_config = ConfigDict(extra="forbid")

    linked_user_id: uuid.UUID
    payout_currency: PayoutCurrency
    relationship: BeneficiaryRelationship


class BeneficiaryUpdateRequest(Schema):
    """Change how a beneficiary is paid, or how the sender knows them. The
    person can't change: a different person is a different beneficiary."""

    model_config = ConfigDict(extra="forbid")

    payout_currency: PayoutCurrency | None = None
    relationship: BeneficiaryRelationship | None = None

    @model_validator(mode="after")
    def _changes_something(self) -> "BeneficiaryUpdateRequest":
        if self.payout_currency is None and self.relationship is None:
            raise ValueError("Give a payout_currency, a relationship, or both")
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
    payout_currency: PayoutCurrency
    payout_currencies: list[PayoutCurrency] = Field(
        description=(
            "Payout currencies this person already holds an account for, "
            "in ZAR, USD, ZWL, NAD order. The edit form offers only these."
        )
    )
    relationship: BeneficiaryRelationship
    created_at: UtcDateTime

    @classmethod
    def from_row(cls, row: BeneficiaryRow) -> "BeneficiaryRead":
        beneficiary, user, country = row.beneficiary, row.user, row.country
        return cls(
            beneficiary_id=beneficiary.beneficiary_id,
            linked_user_id=beneficiary.linked_user_id,
            full_name=user.full_name or user.first_name,
            country=user.country,
            country_name=None if country is None else country.name,
            masked_email=mask_email(user.email),
            masked_mobile_number=mask_mobile(user.mobile_number),
            payout_currency=beneficiary.payout_currency,
            payout_currencies=list(row.payout_currencies),
            relationship=beneficiary.relationship,
            created_at=beneficiary.created_at,
        )


class BeneficiaryLookupResponse(Schema):
    """The preview shown after a sender types in a beneficiary's fiat account
    reference (e.g. "sian1-zar"), before they confirm adding them.

    Deliberately never the email or mobile, masked or not: references are
    guessable (`sipho1`, `sipho2`, ...), so the lookup must not become a
    directory. A name and country are enough to confirm "is this the right
    person".
    """

    linked_user_id: uuid.UUID
    first_name: str | None
    display_name: str | None = Field(
        description="First name and last initial, e.g. Tendai M.",
        examples=["Tendai M."],
    )
    country: str | None = Field(
        description="Verified country of residence, ISO 3166-1 alpha-2."
    )
    country_name: str | None = Field(description="That country's name.")
    account_currency: str = Field(
        description=(
            "The looked-up account's currency. Pre-fills the payout "
            "currency when it is one they already hold."
        ),
        examples=["ZWL"],
    )
    payout_currencies: list[PayoutCurrency] = Field(
        description=(
            "Payout currencies this person already holds an account for, "
            "in ZAR, USD, ZWL, NAD order. The add form offers only these."
        )
    )

    @classmethod
    def from_lookup(cls, lookup: ReferenceLookup) -> "BeneficiaryLookupResponse":
        user = lookup.user
        return cls(
            linked_user_id=user.id,
            first_name=user.first_name,
            display_name=short_display_name(user),
            country=user.country,
            country_name=None if lookup.country is None else lookup.country.name,
            account_currency=lookup.account_currency,
            payout_currencies=list(lookup.payout_currencies),
        )
