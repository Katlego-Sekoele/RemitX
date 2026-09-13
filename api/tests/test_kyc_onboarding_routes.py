"""Applicant history, start, PATCH and submit for the KYC wizard."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from remitx_api.extensions import db
from remitx_api.models.orm.kyc_decision import KycDecision
from remitx_api.models.orm.kyc_document import KycDocument
from remitx_api.models.orm.kyc_lifecycle import KycDocumentStatus, KycStatus
from tests.kyc_helpers import insert_application, seed_kyc_reference_data
from tests.kyc_helpers import make_user as make_persisted_user
from tests.rbac_helpers import make_user, rbac_client

# Check digit and 1990-01-01 match — the with_pii helper's number is 13 digits
# for masking tests and is not a well-formed SA ID.
VALID_SA_ID = "9001015000085"
STANDING = "/kyc/application"
APPLICATIONS = "/kyc/applications"


def _url(application_id) -> str:
    return f"{APPLICATIONS}/{application_id}"


def _submit(client, application_id, version, *, consent=True):
    return client.post(
        f"{_url(application_id)}/submit",
        json={"expected_version": version, "consent": consent},
    )


def _client():
    return rbac_client(make_user("onboard"))


def _store_document(application, user_id, document_type: str) -> None:
    db.session.add(
        KycDocument(
            application_id=application.application_id,
            document_type=document_type,
            status=KycDocumentStatus.STORED.value,
            storage_path=f"kyc/{application.application_id}/{uuid.uuid4()}",
            content_type="application/pdf",
            size_bytes=128,
            sha256=uuid.uuid4().hex + uuid.uuid4().hex[:32],
            uploaded_by_user_id=user_id,
            stored_at=datetime.now(UTC),
        )
    )
    db.session.commit()


def _complete_draft(user):
    application = insert_application(
        user.id,
        with_pii=True,
        id_number=VALID_SA_ID,
        expected_monthly_volume_zar=Decimal("5000.00"),
        is_domestic_prominent_influential_person=False,
        is_foreign_prominent_public_official=False,
        is_pep_family_or_close_associate=False,
    )
    _store_document(application, user.id, "id_document")
    _store_document(application, user.id, "proof_of_address")
    return application


def test_get_without_an_application_points_at_welcome():
    user = make_user("welcome")
    with rbac_client(user) as client:
        seed_kyc_reference_data()

        response = client.get(STANDING)
        history = client.get(APPLICATIONS)

    assert response.status_code == 200
    body = response.json()
    assert body["application"] is None
    assert body["standing"]["status"] == "not_started"
    assert body["next_step"] == "welcome"
    assert history.json() == []
    assert [step["step"] for step in body["steps"]][0] == "welcome"


def test_start_opens_a_draft_and_is_idempotent():
    user = make_user("start")
    with rbac_client(user) as client:
        seed_kyc_reference_data()

        first = client.post(APPLICATIONS)
        second = client.post(APPLICATIONS)

    assert first.status_code == 200
    assert second.status_code == 200
    assert (
        first.json()["application"]["application_id"]
        == second.json()["application"]["application_id"]
    )
    assert first.json()["next_step"] == "identity"
    assert first.json()["editable"] is True


def test_patch_saves_only_what_was_sent_and_returns_unmasked_pii():
    user = make_user("patch")
    with rbac_client(user) as client:
        seed_kyc_reference_data()
        started = client.post(APPLICATIONS).json()["application"]

        response = client.patch(
            _url(started["application_id"]),
            json={
                "expected_version": started["version"],
                "full_name": "Thandiwe Mokoena",
                "date_of_birth": "1990-01-01",
                "nationality": "za",
            },
        )

    assert response.status_code == 200
    application = response.json()["application"]
    assert application["full_name"] == "Thandiwe Mokoena"
    assert application["date_of_birth"] == "1990-01-01"
    assert application["nationality"] == "ZA"
    assert application["id_number"] is None
    assert response.json()["next_step"] == "id-document"


def test_saving_steps_adds_no_status_history():
    user = make_user("nohistory")
    with rbac_client(user) as client:
        seed_kyc_reference_data()
        started = client.post(APPLICATIONS).json()["application"]
        url = _url(started["application_id"])

        first = client.patch(
            url,
            json={"expected_version": started["version"], "full_name": "Thandiwe"},
        ).json()
        client.patch(
            url,
            json={
                "expected_version": first["application"]["version"],
                "nationality": "ZA",
            },
        )
        detail = client.get(url).json()

    assert [event["status"] for event in detail["timeline"]] == ["in_progress"]


def test_sa_id_format_failure_does_not_claim_the_identity_is_invalid():
    user = make_user("said")
    with rbac_client(user) as client:
        seed_kyc_reference_data()
        started = client.post(APPLICATIONS).json()["application"]

        response = client.patch(
            _url(started["application_id"]),
            json={
                "expected_version": started["version"],
                "id_type": "national_id",
                "issuing_country": "ZA",
                "id_number": "1234567890123",
            },
        )

    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "format" in detail
    assert "identity" not in detail


def test_submit_refuses_an_incomplete_draft():
    user = make_user("incomplete")
    with rbac_client(user) as client:
        seed_kyc_reference_data()
        started = client.post(APPLICATIONS).json()["application"]

        response = _submit(client, started["application_id"], started["version"])

    assert response.status_code == 400
    assert "full_name" in response.json()["detail"]


def test_submit_refuses_without_consent():
    user = make_user("noconsent")
    with rbac_client(user) as client:
        application = _complete_draft(user)

        omitted = client.post(
            f"{_url(application.application_id)}/submit",
            json={"expected_version": application.version},
        )
        refused = _submit(
            client, application.application_id, application.version, consent=False
        )

    assert omitted.status_code == 422
    assert refused.status_code == 400
    assert "consent" in refused.json()["detail"].lower()


def test_submit_moves_a_complete_draft_and_a_retry_does_not_open_another():
    user = make_user("submit")
    with rbac_client(user) as client:
        application = _complete_draft(user)

        application_id = application.application_id
        first = _submit(client, application_id, application.version)
        second = _submit(client, application_id, first.json()["application"]["version"])

    assert first.status_code == 200
    assert first.json()["application"]["status"] == "submitted"
    assert first.json()["application"]["processing_consented_at"] is not None
    assert first.json()["next_step"] == "status"
    assert first.json()["editable"] is False
    assert second.status_code == 200
    assert (
        first.json()["application"]["application_id"]
        == second.json()["application"]["application_id"]
    )


def _decide(application, status: KycStatus, **decision) -> None:
    db.session.add(
        KycDecision(
            application_id=application.application_id,
            decision=status.value,
            from_status=KycStatus.UNDER_REVIEW.value,
            decided_at=datetime.now(UTC),
            **decision,
        )
    )
    db.session.commit()


def test_rejected_resubmission_prefills_and_the_reason_stays_on_the_rejection():
    user = make_user("reject")
    with rbac_client(user) as client:
        rejected = insert_application(
            user.id, KycStatus.REJECTED, with_pii=True, id_number=VALID_SA_ID
        )
        _decide(
            rejected,
            KycStatus.REJECTED,
            reason_text="The name on the ID does not match what you declared.",
        )
        rejected_id = str(rejected.application_id)

        response = client.post(APPLICATIONS)
        old = client.get(_url(rejected_id))

    body = response.json()
    assert body["application"]["full_name"] == "Thandiwe Mokoena"
    assert body["application"]["application_id"] != rejected_id
    assert body["applicant_message"] is None
    assert "does not match" in old.json()["applicant_message"]


def test_a_later_approval_carries_no_message_from_an_earlier_rejection():
    user = make_user("rejthenok")
    with rbac_client(user) as client:
        earlier = datetime.now(UTC) - timedelta(days=10)
        rejected = insert_application(
            user.id, KycStatus.REJECTED, with_pii=True, created_at=earlier
        )
        _decide(rejected, KycStatus.REJECTED, reason_code="details_mismatch")
        approved = insert_application(
            user.id,
            KycStatus.APPROVED,
            with_pii=True,
            tier_granted=1,
            next_review_at=datetime.now(UTC) + timedelta(days=300),
        )

        detail = client.get(_url(approved.application_id)).json()
        standing = client.get(STANDING).json()
        history = client.get(APPLICATIONS).json()

    assert detail["applicant_message"] is None
    assert standing["standing"]["status"] == "approved"
    assert [item["status"] for item in history] == ["approved", "rejected"]


def test_more_info_required_shows_what_the_reviewer_named():
    user = make_user("moreinfo")
    with rbac_client(user) as client:
        application = insert_application(
            user.id, KycStatus.MORE_INFO_REQUIRED, with_pii=True
        )
        _decide(
            application,
            KycStatus.MORE_INFO_REQUIRED,
            reason_text="Upload a clearer photo of your ID.",
        )

        detail = client.get(_url(application.application_id)).json()

    assert detail["applicant_message"] == "Upload a clearer photo of your ID."
    assert detail["editable"] is True


def test_start_is_refused_while_an_approval_is_in_force():
    user = make_user("approved")
    with rbac_client(user) as client:
        insert_application(
            user.id,
            KycStatus.APPROVED,
            with_pii=True,
            tier_granted=1,
            next_review_at=datetime.now(UTC) + timedelta(days=30),
        )

        response = client.post(APPLICATIONS)
        history = client.get(APPLICATIONS).json()

    assert response.status_code == 409
    assert len(history) == 1


def test_an_expired_approval_reports_review_due_and_may_start_again():
    user = make_user("expired")
    with rbac_client(user) as client:
        approved = insert_application(
            user.id,
            KycStatus.APPROVED,
            with_pii=True,
            tier_granted=1,
            created_at=datetime.now(UTC) - timedelta(days=400),
            next_review_at=datetime.now(UTC) - timedelta(minutes=1),
        )

        standing = client.get(STANDING).json()["standing"]
        detail = client.get(_url(approved.application_id)).json()
        started = client.post(APPLICATIONS)

    assert standing["status"] == "review_due"
    assert standing["tier"] == 1
    assert detail["application"]["status"] == "review_due"
    assert started.status_code == 200
    assert started.json()["application"]["application_id"] != str(
        approved.application_id
    )
    assert started.json()["application"]["full_name"] == "Thandiwe Mokoena"


def test_another_users_application_is_not_found():
    with rbac_client(make_user("intruder")) as client:
        owner = make_persisted_user()
        application = insert_application(owner.id, with_pii=True)
        url = _url(application.application_id)

        read = client.get(url)
        patch = client.patch(url, json={"expected_version": 1, "full_name": "X"})
        submit = _submit(client, application.application_id, 1)

    assert read.status_code == 404
    assert patch.status_code == 404
    assert submit.status_code == 404


def test_a_decided_application_cannot_be_patched_or_submitted():
    user = make_user("decided")
    with rbac_client(user) as client:
        application = insert_application(user.id, KycStatus.REJECTED, with_pii=True)
        url = _url(application.application_id)

        patch = client.patch(url, json={"expected_version": 1, "full_name": "X"})
        submit = _submit(client, application.application_id, 1)

    assert patch.status_code == 409
    assert submit.status_code == 409


_INTERNAL_FIELDS = {
    "risk_score",
    "risk_rating",
    "risk_rating_override",
    "risk_rating_override_reason",
    "risk_rating_overridden_by_user_id",
    "risk_rating_overridden_at",
    "effective_risk_rating",
    "reviewer_user_id",
    "user_id",
}


def test_applicant_responses_carry_no_internal_assessment_data():
    user = make_user("internal")
    with rbac_client(user) as client:
        reviewer = make_persisted_user()
        application = insert_application(
            user.id,
            KycStatus.UNDER_REVIEW,
            with_pii=True,
            risk_score=40,
            risk_rating="medium",
            risk_rating_override="high",
            risk_rating_override_reason="Adverse media.",
            risk_rating_overridden_by_user_id=reviewer.id,
            risk_rating_overridden_at=datetime.now(UTC),
            submitted_at=datetime.now(UTC),
        )
        _decide(application, KycStatus.UNDER_REVIEW, decided_by_user_id=reviewer.id)

        standing = client.get(STANDING).json()
        history = client.get(APPLICATIONS).json()
        detail = client.get(_url(application.application_id)).json()

    assert "risk_rating" not in standing["standing"]
    assert _INTERNAL_FIELDS.isdisjoint(standing["application"])
    assert _INTERNAL_FIELDS.isdisjoint(history[0])
    assert _INTERNAL_FIELDS.isdisjoint(detail["application"])
    assert "Adverse" not in str(detail)


# --- jurisdictions and identity schemes ---------------------------------------------


def _patch(client, **fields):
    current = client.get(STANDING).json()["application"]
    return client.patch(
        _url(current["application_id"]),
        json={"expected_version": current["version"], **fields},
    )


def _future(days: int = 365) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def test_start_refuses_a_residence_we_do_not_operate_in_and_opens_nothing():
    user = make_user("startfr")
    with rbac_client(user) as client:
        seed_kyc_reference_data()

        refused = client.post(APPLICATIONS, json={"residential_country": "FR"})
        after = client.get(STANDING)

    assert refused.status_code == 400
    detail = refused.json()["detail"]
    assert "France" in detail
    assert "South Africa and United States" in detail
    assert after.json()["application"] is None


def test_start_records_a_supported_residence():
    user = make_user("startus")
    with rbac_client(user) as client:
        seed_kyc_reference_data()

        response = client.post(APPLICATIONS, json={"residential_country": "us"})
        resumed = client.post(APPLICATIONS, json={"residential_country": "ZA"})

    assert response.status_code == 200
    assert response.json()["application"]["residential_country"] == "US"
    # Resuming with a different answer on welcome updates the same draft.
    assert resumed.json()["application"]["residential_country"] == "ZA"
    assert (
        resumed.json()["application"]["application_id"]
        == response.json()["application"]["application_id"]
    )


def test_patch_refuses_an_unsupported_residence_and_an_unknown_country():
    with _client() as client:
        seed_kyc_reference_data()
        client.post(APPLICATIONS)

        residence = _patch(client, residential_country="GB")
        unknown = _patch(client, nationality="XX")
        abroad = _patch(client, nationality="GB")

    assert residence.status_code == 400
    assert "United Kingdom" in residence.json()["detail"]
    assert unknown.status_code == 400
    assert "recognise" in unknown.json()["detail"]
    # Nationality is not gated.
    assert abroad.status_code == 200


def test_a_us_ssn_is_checked_as_an_ssn_and_stored_without_hyphens():
    with _client() as client:
        seed_kyc_reference_data()
        client.post(APPLICATIONS)

        response = _patch(
            client,
            date_of_birth="1990-01-01",
            id_type="national_id",
            issuing_country="US",
            id_number="123-45-6789",
        )

    assert response.status_code == 200
    assert response.json()["application"]["id_number"] == "123456789"


def test_a_national_id_from_a_country_without_a_scheme_is_refused():
    with _client() as client:
        seed_kyc_reference_data()
        client.post(APPLICATIONS)

        response = _patch(
            client,
            id_type="national_id",
            issuing_country="FR",
            id_number="123456789012",
        )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "France" in detail
    assert "passport" in detail


def test_a_passport_from_any_country_is_accepted_with_a_future_expiry():
    with _client() as client:
        seed_kyc_reference_data()
        client.post(APPLICATIONS)

        response = _patch(
            client,
            id_type="passport",
            issuing_country="ZW",
            id_number="fn 123456",
            id_expiry_date=_future(),
        )

    assert response.status_code == 200
    application = response.json()["application"]
    assert application["id_number"] == "FN123456"
    assert application["id_expiry_date"] == _future()


def test_an_expired_passport_is_refused_on_save():
    with _client() as client:
        seed_kyc_reference_data()
        client.post(APPLICATIONS)

        response = _patch(
            client,
            id_type="passport",
            issuing_country="ZW",
            id_number="FN123456",
            id_expiry_date=(date.today() - timedelta(days=1)).isoformat(),
        )

    assert response.status_code == 400
    assert "expired" in response.json()["detail"]


def test_a_passport_without_an_expiry_keeps_the_id_step_incomplete():
    user = make_user("noexpiry")
    with rbac_client(user) as client:
        application = _complete_draft(user)
        application.id_type = "passport"
        application.id_number = "A12345678"
        db.session.commit()

        view = client.get(STANDING).json()
        submit = _submit(client, application.application_id, application.version)

    assert view["next_step"] == "id-document"
    assert submit.status_code == 400
    assert "id_expiry_date" in submit.json()["detail"]


def test_submit_refuses_a_passport_that_expired_after_it_was_saved():
    user = make_user("expiredlater")
    with rbac_client(user) as client:
        application = _complete_draft(user)
        application.id_type = "passport"
        application.id_number = "A12345678"
        application.id_expiry_date = date.today()
        db.session.commit()

        response = _submit(client, application.application_id, application.version)

    assert response.status_code == 400
    assert "expired" in response.json()["detail"]


def test_submit_refuses_a_draft_saved_before_the_residence_gate():
    user = make_user("legacygb")
    with rbac_client(user) as client:
        application = _complete_draft(user)
        application.residential_country = "GB"
        db.session.commit()

        response = _submit(client, application.application_id, application.version)

    assert response.status_code == 400
    assert "United Kingdom" in response.json()["detail"]


def test_swapping_a_passport_for_an_sa_id_clears_the_stale_expiry():
    with _client() as client:
        seed_kyc_reference_data()
        client.post(APPLICATIONS)
        _patch(
            client,
            id_type="passport",
            issuing_country="ZA",
            id_number="A12345678",
            id_expiry_date=_future(),
        )

        response = _patch(
            client,
            date_of_birth="1990-01-01",
            id_type="national_id",
            id_number=VALID_SA_ID,
        )

    assert response.status_code == 200
    application = response.json()["application"]
    assert application["id_type"] == "national_id"
    assert application["id_expiry_date"] is None
