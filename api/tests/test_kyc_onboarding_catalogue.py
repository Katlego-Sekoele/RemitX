"""The wizard order and completeness come from catalogue rows, not tuples."""

from remitx_api.models.orm.kyc_lifecycle import KycStatus
from remitx_api.repositories.jurisdiction_repository import JurisdictionRepository
from remitx_api.repositories.kyc_onboarding_repository import KycOnboardingRepository
from remitx_api.services.kyc_onboarding import missing_for_submit, next_step
from tests.kyc_helpers import insert_application, make_user


def test_the_catalogue_is_the_wizard_order(app_context):
    insert_application(make_user().id)  # seeds reference data
    catalogue = KycOnboardingRepository().load()

    assert [step.step for step in catalogue.steps] == [
        "welcome",
        "identity",
        "id-document",
        "address",
        "contact",
        "financial",
        "declarations",
        "review",
        "status",
    ]
    assert catalogue.editable_statuses == frozenset(
        {"in_progress", "more_info_required"}
    )
    assert "full_name" in catalogue.copy_fields
    assert "id_document" not in catalogue.copy_fields


def test_next_step_walks_the_catalogue(app_context):
    application = insert_application(make_user().id, with_pii=True)
    catalogue = KycOnboardingRepository().load()
    jurisdictions = JurisdictionRepository().load()

    assert next_step(None, (), catalogue, jurisdictions) == "welcome"
    assert next_step(application, (), catalogue, jurisdictions) == "id-document"
    assert (
        next_step(application, ("id_document",), catalogue, jurisdictions) == "address"
    )
    application.status = KycStatus.SUBMITTED.value
    assert (
        next_step(
            application, ("id_document", "proof_of_address"), catalogue, jurisdictions
        )
        == "status"
    )


def test_submit_names_missing_catalogue_fields(app_context):
    application = insert_application(make_user().id)
    catalogue = KycOnboardingRepository().load()

    missing = missing_for_submit(
        application, (), catalogue, JurisdictionRepository().load()
    )

    assert "full_name" in missing
    assert "id_document" in missing
    assert "proof_of_address" in missing


def test_pep_follow_ups_come_from_required_when(app_context):
    application = insert_application(
        make_user().id,
        with_pii=True,
        is_domestic_prominent_influential_person=True,
        is_foreign_prominent_public_official=False,
        is_pep_family_or_close_associate=False,
    )
    catalogue = KycOnboardingRepository().load()

    missing = missing_for_submit(
        application,
        ("id_document", "proof_of_address"),
        catalogue,
        JurisdictionRepository().load(),
    )

    assert "pep_relationship" in missing
    assert "source_of_wealth" in missing
