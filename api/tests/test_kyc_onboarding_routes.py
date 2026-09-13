"""Applicant GET/PATCH/submit for the KYC wizard (issue #60)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from remitx_api.extensions import db
from remitx_api.models.orm.kyc_decision import KycDecision
from remitx_api.models.orm.kyc_document import KycDocument
from remitx_api.models.orm.kyc_lifecycle import KycDocumentStatus, KycStatus
from tests.kyc_helpers import insert_application, seed_kyc_reference_data
from tests.rbac_helpers import make_user, rbac_client

# Check digit and 1990-01-01 match — the with_pii helper's number is 13 digits
# for masking tests and is not a well-formed SA ID.
VALID_SA_ID = "9001015000085"
PATH = "/kyc/application"
SUBMIT = "/kyc/submit"


def _submit(client, version, *, consent=True):
    return client.post(SUBMIT, json={"expected_version": version, "consent": consent})


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

        response = client.get(PATH)

    assert response.status_code == 200
    body = response.json()
    assert body["application"] is None
    assert body["next_step"] == "welcome"
    assert [step["step"] for step in body["steps"]][0] == "welcome"


def test_start_opens_a_draft_and_is_idempotent():
    user = make_user("start")
    with rbac_client(user) as client:
        seed_kyc_reference_data()

        first = client.post(PATH)
        second = client.post(PATH)

    assert first.status_code == 200
    assert second.status_code == 200
    assert (
        first.json()["application"]["application_id"]
        == second.json()["application"]["application_id"]
    )
    assert first.json()["next_step"] == "identity"


def test_patch_saves_only_what_was_sent_and_returns_unmasked_pii():
    user = make_user("patch")
    with rbac_client(user) as client:
        seed_kyc_reference_data()
        started = client.post(PATH).json()
        version = started["application"]["version"]

        response = client.patch(
            PATH,
            json={
                "expected_version": version,
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


def test_sa_id_format_failure_does_not_claim_the_identity_is_invalid():
    user = make_user("said")
    with rbac_client(user) as client:
        seed_kyc_reference_data()
        version = client.post(PATH).json()["application"]["version"]

        response = client.patch(
            PATH,
            json={
                "expected_version": version,
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
        version = client.post(PATH).json()["application"]["version"]

        response = _submit(client, version)

    assert response.status_code == 400
    assert "full_name" in response.json()["detail"]


def test_submit_refuses_without_consent():
    user = make_user("noconsent")
    with rbac_client(user) as client:
        application = _complete_draft(user)

        omitted = client.post(SUBMIT, json={"expected_version": application.version})
        refused = _submit(client, application.version, consent=False)

    assert omitted.status_code == 422
    assert refused.status_code == 400
    assert "consent" in refused.json()["detail"].lower()


def test_submit_moves_a_complete_draft_and_a_retry_does_not_open_another():
    user = make_user("submit")
    with rbac_client(user) as client:
        application = _complete_draft(user)

        first = _submit(client, application.version)
        second = _submit(client, first.json()["application"]["version"])

    assert first.status_code == 200
    assert first.json()["application"]["status"] == "submitted"
    assert first.json()["application"]["processing_consented_at"] is not None
    assert first.json()["next_step"] == "status"
    assert second.status_code == 200
    assert (
        first.json()["application"]["application_id"]
        == second.json()["application"]["application_id"]
    )


def test_rejected_resubmission_prefills_and_shows_the_reason():
    user = make_user("reject")
    with rbac_client(user) as client:
        rejected = insert_application(
            user.id, KycStatus.REJECTED, with_pii=True, id_number=VALID_SA_ID
        )
        db.session.add(
            KycDecision(
                application_id=rejected.application_id,
                decision=KycStatus.REJECTED.value,
                from_status=KycStatus.UNDER_REVIEW.value,
                reason_text="The name on the ID does not match what you declared.",
                decided_at=datetime.now(UTC),
            )
        )
        db.session.commit()
        rejected_id = str(rejected.application_id)

        response = client.post(PATH)

    body = response.json()
    assert body["application"]["full_name"] == "Thandiwe Mokoena"
    assert body["application"]["application_id"] != rejected_id
    assert "does not match" in body["rejection_reason"]


# --- jurisdictions and identity schemes ---------------------------------------------


def _patch(client, **fields):
    version = client.get(PATH).json()["application"]["version"]
    return client.patch(PATH, json={"expected_version": version, **fields})


def _future(days: int = 365) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def test_start_refuses_a_residence_we_do_not_operate_in_and_opens_nothing():
    user = make_user("startfr")
    with rbac_client(user) as client:
        seed_kyc_reference_data()

        refused = client.post(PATH, json={"residential_country": "FR"})
        after = client.get(PATH)

    assert refused.status_code == 400
    detail = refused.json()["detail"]
    assert "France" in detail
    assert "South Africa and United States" in detail
    assert after.json()["application"] is None


def test_start_records_a_supported_residence():
    user = make_user("startus")
    with rbac_client(user) as client:
        seed_kyc_reference_data()

        response = client.post(PATH, json={"residential_country": "us"})
        resumed = client.post(PATH, json={"residential_country": "ZA"})

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
        client.post(PATH)

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
        client.post(PATH)

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
        client.post(PATH)

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
        client.post(PATH)

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
        client.post(PATH)

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

        view = client.get(PATH).json()
        submit = _submit(client, application.version)

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

        response = _submit(client, application.version)

    assert response.status_code == 400
    assert "expired" in response.json()["detail"]


def test_submit_refuses_a_draft_saved_before_the_residence_gate():
    user = make_user("legacygb")
    with rbac_client(user) as client:
        application = _complete_draft(user)
        application.residential_country = "GB"
        db.session.commit()

        response = _submit(client, application.version)

    assert response.status_code == 400
    assert "United Kingdom" in response.json()["detail"]


def test_swapping_a_passport_for_an_sa_id_clears_the_stale_expiry():
    with _client() as client:
        seed_kyc_reference_data()
        client.post(PATH)
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
