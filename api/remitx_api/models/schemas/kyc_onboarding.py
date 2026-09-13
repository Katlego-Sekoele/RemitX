"""Applicant-facing KYC onboarding read/write schemas.

The applicant is looking at what they typed, so this view is unmasked. Staff
routes keep using `KycApplicationRead`, which masks during validation.

`next_step` is a `step` key from `kyc_onboarding_steps`, not a closed Python
literal — the catalogue is the vocabulary.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from remitx_api.models.schemas.kyc import (
    KycApplicationReadPII,
    KycPepRelationshipRead,
    KycStandingRead,
)


class KycOnboardingStepRead(BaseModel):
    step: str
    position: int
    role: str
    description: str


class KycApplicationPatch(BaseModel):
    """Partial save. Absent fields are left alone; sent fields are validated."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    full_name: str | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    id_type: str | None = None
    issuing_country: str | None = None
    id_number: str | None = None
    id_expiry_date: date | None = None
    mobile_number: str | None = None
    email: str | None = None
    source_of_funds: str | None = None
    source_of_funds_detail: str | None = None
    residential_line1: str | None = None
    residential_line2: str | None = None
    residential_city: str | None = None
    residential_postal_code: str | None = None
    residential_country: str | None = None
    expected_monthly_volume_zar: Decimal | None = None
    is_domestic_prominent_influential_person: bool | None = None
    is_foreign_prominent_public_official: bool | None = None
    is_pep_family_or_close_associate: bool | None = None
    pep_relationship: str | None = None
    pep_position: str | None = None
    pep_country: str | None = None
    pep_details: str | None = None
    source_of_wealth: str | None = None


class KycStartRequest(BaseModel):
    """Optional. Welcome sends the residence so a country RemitX does not
    operate in is refused before a draft exists; resume sends nothing."""

    model_config = ConfigDict(extra="forbid")

    residential_country: str | None = None


class KycSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    consent: bool


class KycOnboardingRead(BaseModel):
    standing: KycStandingRead
    application: KycApplicationReadPII | None = None
    next_step: str
    rejection_reason: str | None = None
    stored_document_types: list[str]
    pep_relationships: list[KycPepRelationshipRead]
    steps: list[KycOnboardingStepRead]


class KycCountryRead(BaseModel):
    code: str
    name: str
    operates_in: bool


class KycIdentitySchemeRead(BaseModel):
    scheme: str
    country: str | None
    id_type: str
    label: str
    requires_expiry: bool
    input_mode: str
    number_hint: str
    document_hint: str


class KycReferenceRead(BaseModel):
    """Countries and identity schemes. Static between migrations and free of
    PII, so the client fetches it once rather than with every draft save."""

    countries: list[KycCountryRead]
    identity_schemes: list[KycIdentitySchemeRead]
