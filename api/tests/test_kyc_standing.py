"""KYC standing reads its status from the latest application and its tier and
rating from the latest stored-verified one; those can be different rows."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.controllers.kyc_controller import KycController
from remitx_api.models.orm.kyc_lifecycle import KYC_TIER_VERIFIED, KycStatus
from tests.kyc_helpers import insert_application, make_user, seed_kyc_reference_data


@pytest.fixture(autouse=True)
def _seed(app_context):
    seed_kyc_reference_data()


def test_newer_draft_keeps_the_approved_tier(app_context):
    user = make_user()
    insert_application(
        user.id,
        KycStatus.APPROVED,
        created_at=datetime.now(UTC) - timedelta(days=10),
        tier_granted=KYC_TIER_VERIFIED,
        risk_rating="medium",
    )
    newer = insert_application(user.id, KycStatus.SUBMITTED)

    standing = KycController().get_standing(user.id)

    assert standing.status is KycStatus.SUBMITTED
    assert standing.application_id == newer.application_id
    assert standing.tier == KYC_TIER_VERIFIED
    assert standing.risk_rating == "medium"
    assert standing.daily_limit_zar == Decimal("2250.00")
    assert standing.monthly_limit_zar == Decimal("18750.00")
