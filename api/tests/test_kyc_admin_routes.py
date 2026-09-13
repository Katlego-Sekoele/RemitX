"""/admin/kyc over HTTP: the queue's order and filter, what it masks, who may
read it, the override route's gate, and the review decisions (#20)."""

from datetime import UTC, datetime, timedelta

from remitx_api.extensions import db
from remitx_api.models.orm.audit_log import AuditAction, AuditLog
from remitx_api.models.orm.kyc_application import KycApplication
from remitx_api.models.orm.kyc_decision import KycDecision
from remitx_api.models.orm.kyc_lifecycle import KycReasonCode, KycStatus
from remitx_api.models.orm.kyc_risk_signal import KycRiskSignalRecord
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.repositories.kyc_application_repository import (
    KycApplicationRepository,
)
from sqlalchemy import select, update
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


# --- review: open, decide, request info --------------------------------------


def _audit(action: AuditAction) -> list[AuditLog]:
    return list(
        db.session.scalars(
            select(AuditLog).where(AuditLog.action == action.value)
        ).all()
    )


def _decisions(application_id) -> list[KycDecision]:
    return list(
        db.session.scalars(
            select(KycDecision)
            .where(KycDecision.application_id == application_id)
            .order_by(KycDecision.decided_at)
        ).all()
    )


def test_the_detail_view_is_masked_and_needs_read():
    officer = make_user("detail")
    with rbac_client(officer, roles=("compliance_officer",)) as client:
        seed_kyc_reference_data()
        application = _queued("low", minutes_ago=5)

        response = client.get(f"/admin/kyc/applications/{application.application_id}")

    assert response.status_code == 200
    body = response.json()
    assert ID_NUMBER not in response.text
    assert body["application_id"] == str(application.application_id)
    assert body["full_name"] != "Thandiwe Mokoena"


def test_the_detail_view_refuses_an_unknown_application():
    with rbac_client(make_user("missing"), roles=("compliance_officer",)) as client:
        seed_kyc_reference_data()
        missing = "00000000-0000-0000-0000-000000000001"

        response = client.get(f"/admin/kyc/applications/{missing}")

    assert response.status_code == 404


def test_revealing_pii_is_audited_and_needs_read_pii():
    officer = make_user("pii")
    with rbac_client(officer, roles=("compliance_officer",)) as client:
        seed_kyc_reference_data()
        application = _queued("low", minutes_ago=5)

        response = client.post(
            f"/admin/kyc/applications/{application.application_id}/reveal-pii"
        )
        (entry,) = _audit(AuditAction.KYC_PII_VIEWED)
        actor_id, subject_id, after = (
            entry.actor_user_id,
            entry.subject_id,
            entry.after,
        )

    assert response.status_code == 200
    assert response.json()["id_number"] == ID_NUMBER
    assert response.json()["full_name"] == "Thandiwe Mokoena"
    assert actor_id == officer.id
    assert str(subject_id) == response.json()["application_id"]
    assert ID_NUMBER not in str(after)


def test_revealing_pii_needs_read_pii():
    """`kyc:application:read` is the queue, not somebody's ID number."""
    with rbac_client(make_user("support"), roles=("support_agent",)) as client:
        seed_kyc_reference_data()
        application = _queued("low", minutes_ago=5)

        response = client.post(
            f"/admin/kyc/applications/{application.application_id}/reveal-pii"
        )

    assert response.status_code == 403


def test_starting_review_moves_submitted_to_under_review():
    officer = make_user("claim")
    with rbac_client(officer, roles=("compliance_officer",)) as client:
        seed_kyc_reference_data()
        application = _queued("low", minutes_ago=5)

        response = client.post(
            f"/admin/kyc/applications/{application.application_id}/start-review",
            json={"expected_version": application.version},
        )
        (decision,) = _decisions(application.application_id)
        decision_status, decided_by = decision.decision, decision.decided_by_user_id

    assert response.status_code == 200
    assert response.json()["status"] == "under_review"
    assert response.json()["reviewer_user_id"] == str(officer.id)
    assert decision_status == "under_review"
    assert decided_by == officer.id


def test_a_second_reviewer_sees_who_already_has_the_application():
    with rbac_client(make_user("second"), roles=("compliance_officer",)) as client:
        seed_kyc_reference_data()
        first = make_persisted_user()
        application = _queued("low", minutes_ago=5)
        application.status = KycStatus.UNDER_REVIEW.value
        db.session.add(
            KycDecision(
                application_id=application.application_id,
                decision=KycStatus.UNDER_REVIEW.value,
                from_status=KycStatus.SUBMITTED.value,
                decided_by_user_id=first.id,
                decided_at=NOW,
            )
        )
        db.session.commit()

        response = client.post(
            f"/admin/kyc/applications/{application.application_id}/start-review",
            json={"expected_version": application.version},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "under_review"
        assert response.json()["reviewer_user_id"] == str(first.id)


def test_an_officer_can_approve_in_one_transaction():
    officer = make_user("approve")
    with rbac_client(officer, roles=("compliance_officer",)) as client:
        seed_kyc_reference_data()
        application = _queued("low", minutes_ago=5, status=KycStatus.UNDER_REVIEW)

        response = client.post(
            f"/admin/kyc/applications/{application.application_id}/approve",
            json={"expected_version": application.version},
        )
        (decision,) = _decisions(application.application_id)
        (entry,) = _audit(AuditAction.KYC_APPLICATION_DECIDED)
        decided_by, reason_code, actor_id, after_status = (
            decision.decided_by_user_id,
            decision.reason_code,
            entry.actor_user_id,
            entry.after["status"],
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["tier_granted"] == 1
    assert decided_by == officer.id
    assert reason_code == KycReasonCode.IDENTITY_VERIFIED.value
    assert actor_id == officer.id
    assert after_status == "approved"


def test_reject_needs_a_reason_code_and_hides_the_internal_note_from_the_applicant():
    officer = make_user("reject")
    with rbac_client(officer, roles=("compliance_officer",)) as client:
        seed_kyc_reference_data()
        applicant = make_persisted_user()
        application = insert_application(
            applicant.id,
            KycStatus.UNDER_REVIEW,
            with_pii=True,
            risk_rating="low",
            risk_score=0,
            submitted_at=NOW,
        )

        response = client.post(
            f"/admin/kyc/applications/{application.application_id}/reject",
            json={
                "expected_version": application.version,
                "reason_code": "suspected_fraud",
                "internal_note": "Name on the ID looks forged.",
            },
        )
        (decision,) = _decisions(application.application_id)
        reason = KycApplicationRepository().latest_rejection_reason(applicant.id)
        code, note = decision.reason_code, decision.reason_text

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert code == "suspected_fraud"
    assert note == "Name on the ID looks forged."
    assert reason is not None
    assert "fraud" not in reason.lower()
    assert "forged" not in reason.lower()


def test_request_info_names_what_the_applicant_must_fix():
    analyst = make_user("info")
    with rbac_client(analyst, roles=("compliance_analyst",)) as client:
        seed_kyc_reference_data()
        applicant = make_persisted_user()
        application = insert_application(
            applicant.id,
            KycStatus.UNDER_REVIEW,
            with_pii=True,
            risk_rating="low",
            risk_score=0,
            submitted_at=NOW,
        )

        response = client.post(
            f"/admin/kyc/applications/{application.application_id}/request-info",
            json={
                "expected_version": application.version,
                "reason_code": "document_illegible",
                "reason_text": "Please re-upload a clearer photo of your ID.",
            },
        )
        reason = KycApplicationRepository().latest_rejection_reason(applicant.id)

    assert response.status_code == 200
    assert response.json()["status"] == "more_info_required"
    assert "clearer photo of your ID" in reason


def test_an_analyst_cannot_decide():
    with rbac_client(make_user("analyst"), roles=("compliance_analyst",)) as client:
        seed_kyc_reference_data()
        application = _queued("low", minutes_ago=5, status=KycStatus.UNDER_REVIEW)

        approve = client.post(
            f"/admin/kyc/applications/{application.application_id}/approve",
            json={"expected_version": application.version},
        )
        reject = client.post(
            f"/admin/kyc/applications/{application.application_id}/reject",
            json={
                "expected_version": application.version,
                "reason_code": "other",
                "internal_note": "Analysts cannot reject.",
            },
        )

    assert approve.status_code == 403
    assert reject.status_code == 403


def test_a_reviewer_cannot_decide_on_their_own_application():
    officer = make_user("self")
    with rbac_client(officer, roles=("compliance_officer",)) as client:
        seed_kyc_reference_data()
        application = insert_application(
            officer.id,
            KycStatus.UNDER_REVIEW,
            with_pii=True,
            risk_rating="low",
            risk_score=0,
            submitted_at=NOW,
        )

        response = client.post(
            f"/admin/kyc/applications/{application.application_id}/approve",
            json={"expected_version": application.version},
        )

    assert response.status_code == 403


def test_a_stale_decision_is_409_and_names_who_decided():
    with rbac_client(make_user("stale"), roles=("compliance_officer",)) as client:
        seed_kyc_reference_data()
        first = make_persisted_user()
        application = _queued("low", minutes_ago=5, status=KycStatus.UNDER_REVIEW)
        db.session.add(
            KycDecision(
                application_id=application.application_id,
                decision=KycStatus.UNDER_REVIEW.value,
                from_status=KycStatus.SUBMITTED.value,
                decided_by_user_id=first.id,
                decided_at=NOW,
            )
        )
        db.session.execute(
            update(KycApplication)
            .where(KycApplication.application_id == application.application_id)
            .values(version=7)
        )
        db.session.commit()

        response = client.post(
            f"/admin/kyc/applications/{application.application_id}/approve",
            json={"expected_version": 1},
        )

        assert response.status_code == 409
        assert str(first.id) in response.json()["detail"]


def test_the_queue_count_is_the_waiting_applications():
    with rbac_client(make_user("count"), roles=("compliance_analyst",)) as client:
        seed_kyc_reference_data()
        _queued("low", minutes_ago=5)
        _queued("high", minutes_ago=1, status=KycStatus.UNDER_REVIEW)
        _queued("low", minutes_ago=2, status=KycStatus.APPROVED)

        response = client.get("/admin/kyc/queue-count")

    assert response.status_code == 200
    assert response.json() == {"count": 2}


def test_the_queue_filters_by_minimum_age():
    with rbac_client(make_user("age"), roles=("compliance_analyst",)) as client:
        seed_kyc_reference_data()
        old = _queued("low", minutes_ago=60 * 24 * 4)
        _queued("low", minutes_ago=30)
        expected = str(old.application_id)

        response = client.get("/admin/kyc/applications?min_age_days=3")

    assert response.status_code == 200
    assert [row["application_id"] for row in response.json()] == [expected]


def test_reason_codes_are_the_controlled_list():
    with rbac_client(make_user("codes"), roles=("compliance_officer",)) as client:
        seed_kyc_reference_data()

        response = client.get("/admin/kyc/reason-codes")

    assert response.status_code == 200
    codes = {row["reason_code"] for row in response.json()}
    assert "suspected_fraud" in codes
    assert "document_illegible" in codes
    fraud = next(
        row for row in response.json() if row["reason_code"] == "suspected_fraud"
    )
    assert fraud["visible_to_applicant"] is False
