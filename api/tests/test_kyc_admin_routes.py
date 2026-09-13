"""/admin/kyc over HTTP: the queue's order and filter, what it masks, who may
read it, and the override route's gate."""

from datetime import UTC, datetime, timedelta

from remitx_api.extensions import db
from remitx_api.models.orm.kyc_lifecycle import KycStatus
from remitx_api.models.orm.kyc_risk_signal import KycRiskSignalRecord
from remitx_api.models.orm.permission import PermissionCode
from sqlalchemy import update
from tests.kyc_helpers import ID_NUMBER, insert_application, seed_kyc_reference_data
from tests.kyc_helpers import make_user as make_persisted_user
from tests.rbac_helpers import make_user, rbac_client

NOW = datetime.now(UTC)


def _queued(
    rating: str | None,
    *,
    minutes_ago: int,
    status=KycStatus.SUBMITTED,
    override: str | None = None,
):
    application = insert_application(
        make_persisted_user().id,
        status,
        with_pii=True,
        risk_rating=rating,
        risk_score={None: None, "low": 0, "medium": 25, "high": 60}[rating],
        submitted_at=NOW - timedelta(minutes=minutes_ago),
    )
    if override is not None:
        officer = make_persisted_user()
        application.risk_rating_override = override
        application.risk_rating_override_reason = "Reviewer judgement, see notes."
        application.risk_rating_overridden_by_user_id = officer.id
        application.risk_rating_overridden_at = NOW
        db.session.commit()
    return application


def test_the_queue_puts_the_highest_effective_risk_first_then_the_oldest():
    with rbac_client(make_user("queue"), roles=("compliance_analyst",)) as client:
        seed_kyc_reference_data()
        old_low = _queued("low", minutes_ago=90)
        new_high = _queued("high", minutes_ago=5)
        old_high = _queued("high", minutes_ago=60)
        medium = _queued("medium", minutes_ago=120)
        # Computed low, overridden to high: the override decides its place.
        overridden = _queued("low", minutes_ago=30, override="high")
        unscored = _queued(None, minutes_ago=200)
        _queued("high", minutes_ago=1, status=KycStatus.APPROVED)
        expected = [
            str(application.application_id)
            for application in (
                old_high,
                overridden,
                new_high,
                medium,
                old_low,
                unscored,
            )
        ]

        response = client.get("/admin/kyc/applications")

    assert response.status_code == 200
    assert [row["application_id"] for row in response.json()] == expected


def test_the_queue_filters_on_the_effective_rating():
    with rbac_client(make_user("filter"), roles=("compliance_analyst",)) as client:
        seed_kyc_reference_data()
        high = _queued("high", minutes_ago=10)
        overridden = _queued("medium", minutes_ago=20, override="high")
        _queued("low", minutes_ago=30, override="medium")
        _queued("medium", minutes_ago=40)
        expected = {str(high.application_id), str(overridden.application_id)}

        response = client.get("/admin/kyc/applications?risk_rating=high")

    assert response.status_code == 200
    assert {row["application_id"] for row in response.json()} == expected
    assert all(row["effective_risk_rating"] == "high" for row in response.json())


def test_the_queue_refuses_a_rating_that_is_not_in_the_catalogue():
    with rbac_client(make_user("badrating"), roles=("compliance_analyst",)) as client:
        seed_kyc_reference_data()

        response = client.get("/admin/kyc/applications?risk_rating=extreme")

    assert response.status_code == 400
    assert "extreme" in response.json()["detail"]


def test_the_queue_is_masked_and_shows_both_ratings():
    with rbac_client(make_user("masked"), roles=("compliance_officer",)) as client:
        seed_kyc_reference_data()
        _queued("low", minutes_ago=5, override="high")

        response = client.get("/admin/kyc/applications")

    (row,) = response.json()
    assert ID_NUMBER not in response.text
    assert row["risk_rating"] == "low"
    assert row["risk_rating_override"] == "high"
    assert row["effective_risk_rating"] == "high"


def test_the_queue_needs_kyc_application_read():
    with rbac_client(make_user("noread"), roles=("treasury_operator",)) as client:
        response = client.get("/admin/kyc/applications")

    assert response.status_code == 403


def test_the_rules_endpoint_reads_the_rows():
    """The admin page's explanation of the rating comes from the same rows the
    server scores against — change a row and the page changes."""
    with rbac_client(make_user("rules"), roles=("support_agent",)) as client:
        seed_kyc_reference_data()
        db.session.execute(
            update(KycRiskSignalRecord)
            .where(KycRiskSignalRecord.signal == "source_of_funds_other")
            .values(score_effect=40)
        )
        db.session.commit()

        response = client.get("/admin/kyc/risk-rules")

    assert response.status_code == 200
    body = response.json()
    effects = {signal["signal"]: signal["score_effect"] for signal in body["signals"]}
    assert effects["source_of_funds_other"] == 40
    assert [rating["rating"] for rating in body["ratings"]] == [
        "low",
        "medium",
        "high",
    ]
    assert {tier["tier"] for tier in body["tiers"]} == {0, 1, 2}
    assert {row["relationship"] for row in body["pep_relationships"]} == {
        "self",
        "immediate_family_member",
        "known_close_associate",
    }


def test_an_officer_can_override_and_the_audit_shows_it():
    officer = make_user("override")
    with rbac_client(officer, roles=("compliance_officer",)) as client:
        seed_kyc_reference_data()
        application = _queued("low", minutes_ago=5)

        response = client.post(
            f"/admin/kyc/applications/{application.application_id}"
            "/risk-rating-override",
            json={
                "rating": "high",
                "reason": "Declared employer could not be found.",
                "expected_version": application.version,
            },
        )
        audit = client.get(
            f"/admin/kyc/applications/{application.application_id}/assessment-audit"
        )

    assert response.status_code == 200
    assert response.json()["risk_rating"] == "low"
    assert response.json()["effective_risk_rating"] == "high"
    (entry,) = audit.json()
    assert entry["computed_risk_rating"] == "low"
    assert entry["final_risk_rating"] == "high"
    assert entry["reason"] == "Declared employer could not be found."
    assert entry["actor_user_id"] == str(officer.id)


def test_overriding_needs_kyc_risk_write():
    """An analyst can read the queue but not change what it says."""
    with rbac_client(make_user("analyst"), roles=("compliance_analyst",)) as client:
        seed_kyc_reference_data()
        application = _queued("low", minutes_ago=5)

        response = client.post(
            f"/admin/kyc/applications/{application.application_id}"
            "/risk-rating-override",
            json={
                "rating": "high",
                "reason": "Analysts cannot set ratings.",
                "expected_version": application.version,
            },
        )

    assert response.status_code == 403


def test_an_override_needs_a_real_reason():
    with rbac_client(
        make_user("blank"),
        permissions=(
            PermissionCode.KYC_APPLICATION_READ,
            PermissionCode.KYC_RISK_WRITE,
        ),
    ) as client:
        seed_kyc_reference_data()
        application = _queued("low", minutes_ago=5)

        response = client.post(
            f"/admin/kyc/applications/{application.application_id}"
            "/risk-rating-override",
            json={
                "rating": "high",
                "reason": "            ",
                "expected_version": application.version,
            },
        )

    assert response.status_code == 422
