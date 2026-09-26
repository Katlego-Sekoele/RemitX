"""GET and PATCH /me — the caller's profile."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from remitx_api.extensions import db
from remitx_api.models.orm.kyc_lifecycle import KycStatus
from remitx_api.models.orm.user import User
from tests.kyc_helpers import (
    insert_application,
    make_user as persist_user,
    seed_kyc_reference_data,
)
from tests.rbac_helpers import make_user, rbac_client
from tests.send_helpers import record_transfer

PROFILE = "/me"


def test_unverified_profile_has_no_limits():
    user = make_user("fresh")
    with rbac_client(user) as client:
        seed_kyc_reference_data()
        response = client.get(PROFILE)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "fresh@example.com"
    assert body["mobile_number"] is None
    assert body["kyc"]["status"] == "not_started"
    assert body["kyc"]["tier"] == 0
    assert body["kyc"]["daily_limit_zar"] == "0.00"
    assert body["kyc"]["monthly_limit_zar"] == "0.00"
    assert body["kyc"]["daily_remaining_zar"] == "0.00"
    assert body["kyc"]["monthly_remaining_zar"] == "0.00"


def test_approved_profile_carries_the_tier_limits():
    user = make_user("verified")
    with rbac_client(user) as client:
        insert_application(
            user.id,
            KycStatus.APPROVED,
            with_pii=True,
            tier_granted=1,
            next_review_at=datetime.now(UTC) + timedelta(days=300),
        )
        body = client.get(PROFILE).json()

    assert body["kyc"]["status"] == "approved"
    assert body["kyc"]["tier"] == 1
    assert body["kyc"]["daily_limit_zar"] == "3000.00"
    assert body["kyc"]["monthly_limit_zar"] == "25000.00"


def test_the_profile_says_what_is_used_and_what_is_left():
    """What the Verification page and the send form show: "R 1,800.00 of
    R 3,000.00 left today"."""
    user = make_user("sender")
    with rbac_client(user) as client:
        insert_application(
            user.id,
            KycStatus.APPROVED,
            with_pii=True,
            tier_granted=1,
            next_review_at=datetime.now(UTC) + timedelta(days=300),
        )
        record_transfer(user, persist_user("recipient"), sender_amount=Decimal("1200"))
        db.session.commit()
        kyc = client.get(PROFILE).json()["kyc"]

    assert kyc["daily_used_zar"] == "1200.00"
    assert kyc["daily_remaining_zar"] == "1800.00"
    assert kyc["monthly_used_zar"] == "1200.00"
    assert kyc["monthly_remaining_zar"] == "23800.00"


def test_patch_sets_the_mobile():
    user = make_user("editor")
    with rbac_client(user) as client:
        seed_kyc_reference_data()
        response = client.patch(PROFILE, json={"mobile_number": " +27821234567 "})
        stored = db.session.get(User, user.id)
        db.session.refresh(stored)

    assert response.status_code == 200
    assert response.json()["mobile_number"] == "+27821234567"
    assert stored.mobile_number == "+27821234567"


def test_null_clears_the_mobile():
    user = make_user("clearer")
    user.mobile_number = "+27821234567"
    with rbac_client(user) as client:
        seed_kyc_reference_data()
        body = client.patch(PROFILE, json={"mobile_number": None}).json()

    assert body["mobile_number"] is None


def test_patch_refuses_a_mobile_not_in_e164():
    user = make_user("badmobile")
    with rbac_client(user) as client:
        seed_kyc_reference_data()
        response = client.patch(PROFILE, json={"mobile_number": "082 123 4567"})

    assert response.status_code == 422


def test_patch_refuses_fields_it_does_not_own():
    user = make_user("sneaky")
    with rbac_client(user) as client:
        seed_kyc_reference_data()
        response = client.patch(
            PROFILE,
            json={"mobile_number": None, "email": "other@example.com"},
        )

    assert response.status_code == 422


def test_profile_requires_a_session(anonymous_client):
    assert anonymous_client.get(PROFILE).status_code == 401
