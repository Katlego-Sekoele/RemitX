"""Applicant-facing KYC onboarding read/write schemas.

The applicant is looking at what they typed, so this view is unmasked. Staff
routes keep using `KycApplicationRead`, which masks during validation.

`KycApplicantApplicationRead` lists what it includes rather than inheriting the
staff `_ApplicationBase`: risk scores, overrides and reviewer ids are internal,
and a field added to the staff base later must not reach the applicant by
default.

`next_step` is a `step` key from `kyc_onboarding_steps`, not a closed Python
literal — the catalogue is the vocabulary.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import AliasChoices, ConfigDict, Field

from remitx_api.models.orm.kyc_lifecycle import KycStatus
from remitx_api.models.schemas.base import LedgerDecimal, Schema, UtcDateTime
from remitx_api.models.schemas.kyc import (
    KycPepRelationshipRead,
    KycStandingRead,
)


class KycOnboardingStepRead(Schema):
    step: str
    position: int
    role: str
    description: str


class KycApplicationPatch(Schema):
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
    expected_monthly_volume_zar: LedgerDecimal | None = None
    is_domestic_prominent_influential_person: bool | None = None
    is_foreign_prominent_public_official: bool | None = None
    is_pep_family_or_close_associate: bool | None = None
    pep_relationship: str | None = None
    pep_position: str | None = None
    pep_country: str | None = None
    pep_details: str | None = None
    source_of_wealth: str | None = None


class KycStartRequest(Schema):
    """Optional. Welcome sends the residence so a country RemitX does not
    operate in is refused before a draft exists; resume sends nothing."""

    model_config = ConfigDict(extra="forbid")

    residential_country: str | None = None


class KycSubmitRequest(Schema):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    consent: bool


class KycApplicantApplicationRead(Schema):
    """One of the caller's own applications, unmasked, without internal
    assessment data."""

    model_config = ConfigDict(from_attributes=True)

    application_id: uuid.UUID
    # Effective: an approval past its review date reports `review_due`.
    status: KycStatus = Field(
        validation_alias=AliasChoices("effective_status", "status")
    )
    version: int
    tier_granted: int | None = None
    created_at: UtcDateTime
    submitted_at: UtcDateTime | None = None
    processing_consented_at: UtcDateTime | None = None
    next_review_at: UtcDateTime | None = None

    full_name: str | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    id_type: str | None = None
    issuing_country: str | None = None
    id_number: str | None = None
    id_expiry_date: date | None = None
    mobile_number: str | None = None
    email: str | None = None
    residential_line1: str | None = None
    residential_line2: str | None = None
    residential_city: str | None = None
    residential_postal_code: str | None = None
    residential_country: str | None = None
    source_of_funds: str | None = None
    source_of_funds_detail: str | None = None
    expected_monthly_volume_zar: LedgerDecimal | None = None
    is_domestic_prominent_influential_person: bool | None = None
    is_foreign_prominent_public_official: bool | None = None
    is_pep_family_or_close_associate: bool | None = None
    declares_pep: bool = False
    pep_relationship: str | None = None
    pep_position: str | None = None
    pep_country: str | None = None
    pep_details: str | None = None
    source_of_wealth: str | None = None


class KycOnboardingRead(Schema):
    """Standing and the application the applicant is on now."""

    standing: KycStandingRead
    application: KycApplicantApplicationRead | None = None
    next_step: str
    stored_document_types: list[str]
    pep_relationships: list[KycPepRelationshipRead]
    steps: list[KycOnboardingStepRead]


class KycApplicationSummaryRead(Schema):
    application_id: uuid.UUID
    status: KycStatus
    created_at: UtcDateTime
    submitted_at: UtcDateTime | None = None
    decided_at: UtcDateTime | None = None
    tier_granted: int | None = None
    next_review_at: UtcDateTime | None = None
    editable: bool


class KycStatusEventRead(Schema):
    model_config = ConfigDict(from_attributes=True)

    status: KycStatus
    changed_at: UtcDateTime


class KycApplicationDetailRead(Schema):
    application: KycApplicantApplicationRead
    editable: bool
    applicant_message: str | None = None
    timeline: list[KycStatusEventRead]
    next_step: str
    stored_document_types: list[str]
    pep_relationships: list[KycPepRelationshipRead]
    steps: list[KycOnboardingStepRead]


class KycCountryRead(Schema):
    code: str
    name: str
    operates_in: bool


class KycIdentitySchemeRead(Schema):
    scheme: str
    country: str | None
    id_type: str
    label: str
    requires_expiry: bool
    input_mode: Literal["numeric", "text"]
    number_hint: str
    document_hint: str


class KycReferenceRead(Schema):
    """Countries and identity schemes. Static between migrations and free of
    PII, so the client fetches it once rather than with every draft save."""

    countries: list[KycCountryRead]
    identity_schemes: list[KycIdentitySchemeRead]
