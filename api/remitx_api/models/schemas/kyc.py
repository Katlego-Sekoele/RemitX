"""KYC read schemas. The default one masks; the unmasked one is gated.

`KycApplication` carries every field of PII the applicant declared and must
never be returned by a route. Two schemas stand between it and the wire:

- `KycApplicationRead` — the default. Masking happens during validation, so an
  instance never *holds* a full ID number. That matters more than it sounds:
  a masking `field_serializer` would leave the real value on the model, one
  stray `model_dump(exclude=...)` or log line away from leaking.
- `KycApplicationReadPII` — the full values, for a reviewer who has to compare
  what was declared against the documents. Routes returning it must gate on
  `PermissionCode.KYC_APPLICATION_READ_PII`.

Masks keep the last few characters rather than blanking the field: a reviewer
skimming a queue needs to tell two applications apart, and "the one ending
0085" does that without showing anyone's identity number.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    model_validator,
)

MASK_CHARACTER = "•"
# Enough to disambiguate two rows, not enough to identify anyone. A South
# African ID number is 13 digits, so four leaves nine hidden.
VISIBLE_SUFFIX_LENGTH = 4
# Free text is masked to a fixed length, so the mask says "something was
# declared" without leaking how long it was.
FREE_TEXT_MASK = MASK_CHARACTER * 8

MIN_REASON_LENGTH = 10
MAX_REASON_LENGTH = 500


def mask_tail(value: str | None, visible: int = VISIBLE_SUFFIX_LENGTH) -> str | None:
    """Replace all but the last `visible` characters.

    Short values are masked entirely rather than mostly-revealed — a 4-digit
    value with 4 visible characters is not masked at all.
    """
    if value is None:
        return None
    if len(value) <= visible:
        return MASK_CHARACTER * len(value)
    return MASK_CHARACTER * (len(value) - visible) + value[-visible:]


def mask_name(value: str | None) -> str | None:
    """ "Thandiwe Mokoena" -> "T. Mokoena": enough to recognise the record you
    were already looking at, not enough to be a directory of applicants."""
    if value is None:
        return None
    parts = value.split()
    if len(parts) < 2:
        return MASK_CHARACTER * len(value)
    return " ".join([f"{part[0]}." for part in parts[:-1]] + [parts[-1]])


def mask_email(value: str | None) -> str | None:
    """Keep the first character of the local part and the whole domain:
    "t•••@example.com". The leading letter is what makes a masked address
    recognisable to the person it belongs to, and a domain is not identifying.

    The tail is the wrong half to keep here — unlike an ID number, an email's
    last characters are often the recipient's surname.
    """
    if value is None:
        return None
    local, separator, domain = value.partition("@")
    if not separator:
        return mask_tail(value)
    if len(local) <= 1:
        return f"{MASK_CHARACTER * len(local)}@{domain}"
    return f"{local[0]}{MASK_CHARACTER * (len(local) - 1)}@{domain}"


def mask_free_text(value: str | None) -> str | None:
    """A declared narrative — a PEP's position, a source of wealth. Any part
    of it can identify someone, so none of it survives; only whether it was
    given does, which is what a reviewer skimming the queue needs to know."""
    if value is None:
        return None
    return FREE_TEXT_MASK


def mask_year_only(value: date | None) -> str | None:
    """Keep the year: it is what an age check needs, and a year alone is not
    the birth date an identity thief needs."""
    if value is None:
        return None
    return f"{value.year}-{MASK_CHARACTER * 2}-{MASK_CHARACTER * 2}"


class _ApplicationBase(BaseModel):
    """Fields that carry no PII, shared by both views."""

    model_config = ConfigDict(from_attributes=True)

    application_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    nationality: str | None = None
    id_type: str | None = None
    issuing_country: str | None = None
    # An expiry date identifies nobody on its own, and a reviewer needs it
    # unmasked to see that the passport was valid.
    id_expiry_date: date | None = None
    source_of_funds: str | None = None
    # City and country are not masked in either view: a reviewer has to be able
    # to see the jurisdiction to judge the application at all, and a city is
    # not identifying on its own.
    residential_city: str | None = None
    residential_country: str | None = None
    expected_monthly_volume_zar: Decimal | None = None
    # The PEP answers and the country are not masked: whether someone declared
    # themselves politically exposed is what routes the application, and a
    # country is not identifying. The position and details are, and are masked.
    is_domestic_prominent_influential_person: bool | None = None
    is_foreign_prominent_public_official: bool | None = None
    is_pep_family_or_close_associate: bool | None = None
    declares_pep: bool = False
    pep_relationship: str | None = None
    pep_country: str | None = None
    # Computed at submission, and the reviewer's override beside it — both are
    # shown, never merged. Not PII.
    risk_score: int | None = None
    risk_rating: str | None = None
    risk_rating_override: str | None = None
    risk_rating_override_reason: str | None = None
    risk_rating_overridden_by_user_id: uuid.UUID | None = None
    risk_rating_overridden_at: datetime | None = None
    effective_risk_rating: str | None = None
    tier_granted: int | None = None
    submitted_at: datetime | None = None
    processing_consented_at: datetime | None = None
    next_review_at: datetime | None = None
    # The value a caller must echo back to decide this application — see
    # KycController.transition.
    version: int
    created_at: datetime
    updated_at: datetime

    @field_serializer(
        "submitted_at",
        "processing_consented_at",
        "next_review_at",
        "risk_rating_overridden_at",
        "created_at",
        "updated_at",
        when_used="unless-none",
    )
    def _as_utc(self, value: datetime) -> str:
        # See models/schemas/integration_message.py for why this is needed:
        # SQLite drops the tz offset Postgres preserves.
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()


class KycApplicationRead(_ApplicationBase):
    """The default view. Masked during validation, so the instance itself never
    holds a full value — there is no serializer to forget to apply."""

    full_name: str | None = None
    date_of_birth: str | None = None
    id_number: str | None = None
    mobile_number: str | None = None
    email: str | None = None
    residential_line1: str | None = None
    residential_line2: str | None = None
    residential_postal_code: str | None = None
    source_of_funds_detail: str | None = None
    pep_position: str | None = None
    pep_details: str | None = None
    source_of_wealth: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _mask(cls, data):
        """Mask on the way in, whether the source is an ORM row or a dict.

        `mode="before"` rather than `"after"`: the unmasked string is never
        assigned to the model at all, so nothing downstream — a subclass, a
        `model_dump`, a debugger — can reach it.
        """

        def read(name: str):
            if isinstance(data, dict):
                return data.get(name)
            return getattr(data, name, None)

        masked = {
            field: read(field)
            for field in _ApplicationBase.model_fields
            if read(field) is not None
        }
        masked.update(
            full_name=mask_name(read("full_name")),
            date_of_birth=mask_year_only(read("date_of_birth")),
            id_number=mask_tail(read("id_number")),
            mobile_number=mask_tail(read("mobile_number"), visible=3),
            email=mask_email(read("email")),
            residential_line1=mask_tail(read("residential_line1")),
            residential_line2=mask_tail(read("residential_line2")),
            residential_postal_code=mask_tail(read("residential_postal_code")),
            source_of_funds_detail=mask_free_text(read("source_of_funds_detail")),
            pep_position=mask_free_text(read("pep_position")),
            pep_details=mask_free_text(read("pep_details")),
            source_of_wealth=mask_free_text(read("source_of_wealth")),
        )
        return masked


class KycApplicationReadPII(_ApplicationBase):
    """Unmasked. A route returning this must depend on
    `RequirePermission(PermissionCode.KYC_APPLICATION_READ_PII)`."""

    full_name: str | None = None
    date_of_birth: date | None = None
    id_number: str | None = None
    mobile_number: str | None = None
    email: str | None = None
    residential_line1: str | None = None
    residential_line2: str | None = None
    residential_postal_code: str | None = None
    source_of_funds_detail: str | None = None
    pep_position: str | None = None
    pep_details: str | None = None
    source_of_wealth: str | None = None


class KycDecisionRead(BaseModel):
    """A reviewer's decision. No applicant PII, so there is one view of it —
    but `reason_text` is written by a reviewer for an applicant, so it goes to
    the applicant and to staff, and nowhere else."""

    model_config = ConfigDict(from_attributes=True)

    decision_id: uuid.UUID
    application_id: uuid.UUID
    decision: str
    from_status: str
    reason_code: str | None = None
    reason_text: str | None = None
    decided_by_user_id: uuid.UUID | None = None
    decided_at: datetime

    @field_serializer("decided_at")
    def _as_utc(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()


class KycStandingRead(BaseModel):
    """A user's KYC status, tier and limits, derived rather than stored — see
    `KycApplicationRepository.get_standing`."""

    model_config = ConfigDict(from_attributes=True)

    status: str
    tier: int
    application_id: uuid.UUID | None = None
    risk_rating: str | None = None
    limit_percent: int
    daily_limit_zar: Decimal
    monthly_limit_zar: Decimal


# --- Risk rule set ---------------------------------------------------------------


class KycRiskSignalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    signal: str
    description: str
    score_effect: int
    is_active: bool


class KycRiskRatingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rating: str
    description: str
    min_score: int
    max_score: int
    severity: int
    max_tier: int
    limit_percent: int
    review_interval_days: int
    requires_senior_approval: bool


class KycTierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tier: int
    name: str
    description: str
    daily_limit_zar: Decimal
    monthly_limit_zar: Decimal
    requires_source_of_wealth: bool


class KycPepRelationshipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    relationship: str
    description: str


class KycRiskRulesRead(BaseModel):
    """The rule set exactly as the server scores against it — read from the
    same rows, so a page showing it cannot drift from what is enforced."""

    signals: list[KycRiskSignalRead]
    ratings: list[KycRiskRatingRead]
    tiers: list[KycTierRead]
    pep_relationships: list[KycPepRelationshipRead]


class KycMatchedSignalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    signal: str
    score_effect: int


class KycAssessmentAuditRead(BaseModel):
    """One rating or tier change: computed, final, and why they differ."""

    model_config = ConfigDict(from_attributes=True)

    audit_id: uuid.UUID
    application_id: uuid.UUID
    computed_risk_rating: str | None = None
    final_risk_rating: str | None = None
    risk_score: int | None = None
    matched_signals: list[KycMatchedSignalRead] = []
    computed_tier: int | None = None
    final_tier: int | None = None
    reason: str | None = None
    actor_user_id: uuid.UUID | None = None
    recorded_at: datetime

    @field_serializer("recorded_at")
    def _as_utc(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()


class KycRiskOverrideRequest(BaseModel):
    # Stripped before the length check, so ten spaces is not a reason.
    model_config = ConfigDict(str_strip_whitespace=True)

    rating: str = Field(description="A rating from kyc_risk_ratings, e.g. high.")
    reason: str = Field(
        min_length=MIN_REASON_LENGTH,
        max_length=MAX_REASON_LENGTH,
        description="Why the computed rating is wrong. Recorded with the override.",
    )
    expected_version: int = Field(
        ge=1,
        description="The application version the reviewer was looking at.",
    )


class KycDocumentRead(BaseModel):
    """Document metadata. `storage_path` is deliberately absent: a caller who
    knows the object key is one misconfigured bucket away from the file, and
    handing out access is the upload ticket's job, through a signed URL."""

    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    application_id: uuid.UUID
    document_type: str
    content_type: str
    size_bytes: int
    sha256: str
    uploaded_by_user_id: uuid.UUID
    uploaded_at: datetime

    @field_serializer("uploaded_at")
    def _as_utc(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
