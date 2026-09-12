"""Fixtures for KYC tests: users and applications written straight to the
database.

Applications are inserted rather than transitioned into place on purpose. The
transition table is the thing under test, so building a `rejected` application
by walking the machine would mean trusting the machine to test itself — and
states the machine cannot reach would be untestable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from remitx_api.extensions import db
from remitx_api.models.orm.kyc_application import KycApplication
from remitx_api.models.orm.kyc_lifecycle import KycStatus
from remitx_api.models.orm.user import User

# A full South African ID number, 13 digits — the value masking has to hide.
ID_NUMBER = "9001015800085"


def make_user(suffix: str | None = None) -> User:
    """Persist a user with unique-by-construction identifiers."""
    suffix = suffix or uuid.uuid4().hex[:10]
    user = User(
        clerk_user_id=f"user_{suffix}",
        email=f"{suffix}@example.com",
        first_name="Test",
        base_reference=suffix,
    )
    db.session.add(user)
    db.session.flush()
    return user


def insert_application(
    user_id: uuid.UUID,
    status: KycStatus = KycStatus.IN_PROGRESS,
    *,
    created_at: datetime | None = None,
    tier_granted: int | None = None,
    with_pii: bool = False,
) -> KycApplication:
    application = KycApplication(
        user_id=user_id,
        status=status.value,
        created_at=created_at or datetime.now(UTC),
        tier_granted=tier_granted,
    )
    if with_pii:
        application.full_name = "Thandiwe Mokoena"
        application.date_of_birth = datetime(1990, 1, 1, tzinfo=UTC).date()
        application.nationality = "ZA"
        application.id_type = "national_id"
        application.issuing_country = "ZA"
        application.id_number = ID_NUMBER
        application.mobile_number = "+27821234567"
        application.email = "thandiwe.mokoena@example.com"
        application.source_of_funds = "salary"
        application.residential_line1 = "12 Kloof Street"
        application.residential_line2 = "Unit 4B"
        application.residential_city = "Cape Town"
        application.residential_postal_code = "8001"
        application.residential_country = "ZA"
    db.session.add(application)
    db.session.commit()
    return application
