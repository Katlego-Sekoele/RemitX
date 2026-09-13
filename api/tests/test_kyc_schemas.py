"""PII leaves masked unless something explicitly asks for it unmasked."""

import json

import pytest
from remitx_api.models.orm.kyc_application import KycApplication
from remitx_api.models.orm.kyc_assessment_audit import KycAssessmentAudit
from remitx_api.models.orm.kyc_assessment_audit_signal import (
    KycAssessmentAuditSignal,
)
from remitx_api.models.orm.kyc_decision import KycDecision
from remitx_api.models.orm.kyc_decision_history import KycDecisionHistory
from remitx_api.models.orm.kyc_document import KycDocument
from remitx_api.models.orm.kyc_reason_code import KycReasonCodeRecord
from remitx_api.models.orm.kyc_status_progression import KycApplicationStatusProgression
from remitx_api.models.schemas.kyc import (
    FREE_TEXT_MASK,
    KycApplicationRead,
    KycApplicationReadPII,
    mask_email,
    mask_free_text,
    mask_name,
    mask_tail,
    mask_year_only,
)
from tests.kyc_helpers import ID_NUMBER, insert_application, make_user

# Everything the applicant declared that must not appear in a default read.
SECRETS = (
    ID_NUMBER,
    "Thandiwe Mokoena",
    "+27821234567",
    "thandiwe.mokoena@example.com",
    "12 Kloof Street",
    "Unit 4B",
    "1990-01-01",
)


# The PEP and wealth narratives: any part of one can identify a person, so
# none of it may survive a default read.
PEP_SECRETS = {
    "pep_position": "Deputy Minister of Mineral Resources",
    "pep_details": "Brother-in-law of the applicant since 2014",
    "source_of_wealth": "Sale of a Constantia wine farm in 2019",
    "source_of_funds_detail": "Proceeds of a Bitcoin sale",
}


@pytest.fixture
def application(app_context):
    return insert_application(
        make_user().id,
        with_pii=True,
        is_pep_family_or_close_associate=True,
        pep_relationship="immediate_family_member",
        pep_country="ZA",
        **PEP_SECRETS,
    )


def test_the_default_read_contains_no_full_id_number(application):
    read = KycApplicationRead.model_validate(application)

    assert ID_NUMBER not in json.dumps(read.model_dump(mode="json"))
    assert read.id_number == "•••••••••0085"


def test_the_default_read_leaks_no_declared_value_anywhere(application):
    """Field by field is not enough — a value copied into some other field, or a
    field added later and left unmasked, would pass that and fail this."""
    serialized = json.dumps(
        KycApplicationRead.model_validate(application).model_dump(mode="json")
    )

    for secret in (*SECRETS, *PEP_SECRETS.values()):
        assert secret not in serialized, f"{secret!r} survived masking"


def test_declared_narratives_mask_to_a_fixed_length(application):
    """Only whether something was declared survives — not how long it was."""
    read = KycApplicationRead.model_validate(application)

    for field in PEP_SECRETS:
        assert getattr(read, field) == FREE_TEXT_MASK
    assert mask_free_text(None) is None


def test_the_masked_read_shows_the_pep_answers_that_route_the_application(
    application,
):
    read = KycApplicationRead.model_validate(application)

    assert read.declares_pep is True
    assert read.is_pep_family_or_close_associate is True
    assert read.pep_relationship == "immediate_family_member"
    assert read.pep_country == "ZA"


def test_the_masked_model_does_not_hold_the_raw_value(application):
    """Masking happens during validation, not on the way out, so there is no
    unmasked value on the instance for a stray dump or log line to find."""
    read = KycApplicationRead.model_validate(application)

    assert ID_NUMBER not in str(read.__dict__.values())
    assert ID_NUMBER not in repr(read)


def test_the_masked_read_keeps_what_a_reviewer_needs(application):
    read = KycApplicationRead.model_validate(application)

    # Jurisdiction and status are not PII, and a queue is unusable without them.
    assert read.nationality == "ZA"
    assert read.residential_city == "Cape Town"
    assert read.residential_country == "ZA"
    assert read.status == application.status
    # The value a caller has to echo back to decide the application.
    assert read.version == application.version


def test_the_pii_read_reveals_the_declared_values(application):
    read = KycApplicationReadPII.model_validate(application)

    assert read.id_number == ID_NUMBER
    assert read.full_name == "Thandiwe Mokoena"
    assert read.residential_line1 == "12 Kloof Street"
    assert read.date_of_birth == application.date_of_birth
    for field, value in PEP_SECRETS.items():
        assert getattr(read, field) == value


def test_a_draft_application_masks_without_tripping_over_nulls(app_context):
    """`in_progress` is a real state: most fields are still NULL."""
    read = KycApplicationRead.model_validate(
        insert_application(make_user().id, with_pii=False)
    )

    assert read.id_number is None
    assert read.full_name is None
    assert read.date_of_birth is None


def test_no_route_returns_a_kyc_orm_model(client):
    """The ORM rows carry PII and must never be a response model. Nothing
    returns them today; this is here so nothing starts to."""
    forbidden = {
        KycApplication,
        KycDocument,
        KycDecision,
        KycDecisionHistory,
        KycReasonCodeRecord,
        KycApplicationStatusProgression,
        KycAssessmentAudit,
        KycAssessmentAuditSignal,
    }

    for route in client.app.routes:
        assert getattr(route, "response_model", None) not in forbidden, route.path


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (ID_NUMBER, "•••••••••0085"),
        ("8001", "••••"),  # too short to reveal any of
        ("123", "•••"),
        ("", ""),
        (None, None),
    ],
)
def test_mask_tail(value, expected):
    assert mask_tail(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Thandiwe Mokoena", "T. Mokoena"),
        ("Thandiwe Naledi Mokoena", "T. N. Mokoena"),
        ("Thandiwe", "••••••••"),  # one name reveals nothing
        (None, None),
    ],
)
def test_mask_name(value, expected):
    assert mask_name(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("thandiwe.mokoena@example.com", "t•••••••••••••••@example.com"),
        ("a@example.com", "•@example.com"),
        # No "@" at all: fall back to keeping the tail rather than
        # revealing the first character of something that is not a local part.
        ("not-an-email", "••••••••mail"),
        (None, None),
    ],
)
def test_mask_email(value, expected):
    assert mask_email(value) == expected


def test_mask_year_only_keeps_the_year_an_age_check_needs(application):
    assert mask_year_only(application.date_of_birth) == "1990-••-••"
    assert mask_year_only(None) is None
