"""Transitions as transactions: what lands, what rolls back, and what a second
reviewer sees."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from remitx_api.app import create_app
from remitx_api.config import TestConfig
from remitx_api.controllers.kyc_controller import KycController
from remitx_api.errors.kyc import (
    KycVersionConflictError,
    OpenApplicationExistsError,
    UnknownKycApplicationError,
)
from remitx_api.errors.users import UnknownUserError
from remitx_api.extensions import db
from remitx_api.models.orm.kyc_application import KycApplication
from remitx_api.models.orm.kyc_decision import KycDecision
from remitx_api.models.orm.kyc_lifecycle import (
    KYC_TIER_NONE,
    KYC_TIER_VERIFIED,
    REVIEW_INTERVAL_DAYS,
    KycReasonCode,
    KycStatus,
)
from remitx_api.models.orm.user import User
from remitx_api.repositories import kyc_application_repository as kyc_repo_module
from remitx_api.repositories.kyc_application_repository import (
    KycApplicationRepository,
)
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from tests.kyc_helpers import insert_application, make_user, seed_kyc_reference_data


@pytest.fixture(autouse=True)
def _seed_kyc_reference(app_context):
    seed_kyc_reference_data()


def _decisions(application_id: uuid.UUID) -> list[KycDecision]:
    return list(
        db.session.scalars(
            select(KycDecision).where(KycDecision.application_id == application_id)
        ).all()
    )


# --- starting an application -------------------------------------------------


def test_start_application_opens_a_draft(app_context):
    user = make_user()
    application = KycController().start_application(user.id)

    assert application.status == KycStatus.IN_PROGRESS.value
    assert application.version == 1
    assert application.submitted_at is None


def test_start_application_rejects_an_unknown_user(app_context):
    with pytest.raises(UnknownUserError):
        KycController().start_application(uuid.uuid4())


def test_a_user_cannot_hold_two_open_applications(app_context):
    user = make_user()
    controller = KycController()
    controller.start_application(user.id)

    with pytest.raises(OpenApplicationExistsError):
        controller.start_application(user.id)


def test_the_database_refuses_a_second_open_application(app_context):
    """The partial unique index, not the Python check above.

    Written as "the second insert raises" rather than "the first succeeds": if
    `uq_kyc_applications_one_open_per_user` silently did not exist — the failure
    mode when a partial index is declared with only `postgresql_where` and the
    test database is SQLite — this test fails instead of passing vacuously.
    """
    user = make_user()
    insert_application(user.id, KycStatus.SUBMITTED)

    db.session.add(KycApplication(user_id=user.id, status=KycStatus.IN_PROGRESS.value))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_a_decided_application_does_not_block_the_next_attempt(app_context):
    """The index is partial. A plain unique index on `user_id` would pass the
    test above and fail here, which is why both exist."""
    user = make_user()
    insert_application(user.id, KycStatus.REJECTED)

    application = KycController().start_application(user.id)

    assert application.status == KycStatus.IN_PROGRESS.value
    assert len(KycApplicationRepository().list_for_user(user.id)) == 2


def test_an_approved_user_may_open_a_refresh_application(app_context):
    """`review_due` is not an open status, so the refresh it prompts is
    possible."""
    user = make_user()
    insert_application(user.id, KycStatus.REVIEW_DUE, tier_granted=KYC_TIER_VERIFIED)

    assert KycController().start_application(user.id) is not None


# --- what a transition writes ------------------------------------------------


def test_approving_writes_the_decision_tier_and_review_date(app_context):
    reviewer = make_user()
    applicant = make_user()
    application = insert_application(applicant.id, KycStatus.UNDER_REVIEW)

    approved = KycController().transition(
        application.application_id,
        KycStatus.APPROVED,
        expected_version=1,
        actor_user_id=reviewer.id,
        reason_code=KycReasonCode.IDENTITY_VERIFIED,
        reason_text="ID and proof of address match the declaration.",
    )

    assert approved.status == KycStatus.APPROVED.value
    assert approved.tier_granted == KYC_TIER_VERIFIED
    assert approved.next_review_at is not None
    assert (approved.next_review_at - approved.updated_at).days == REVIEW_INTERVAL_DAYS

    (decision,) = _decisions(application.application_id)
    assert decision.decision == KycStatus.APPROVED.value
    assert decision.from_status == KycStatus.UNDER_REVIEW.value
    assert decision.decided_by_user_id == reviewer.id
    assert decision.reason_code == KycReasonCode.IDENTITY_VERIFIED.value


def test_submitting_stamps_submitted_at_once(app_context):
    """A more_info_required round trip keeps the original submission time — it
    is what turnaround reporting measures from."""
    reviewer = make_user()
    applicant = make_user()
    application = insert_application(applicant.id, KycStatus.IN_PROGRESS)
    controller = KycController()

    submitted = controller.transition(
        application.application_id, KycStatus.SUBMITTED, expected_version=1
    )
    first_submitted_at = submitted.submitted_at
    assert first_submitted_at is not None
    assert submitted.processing_consented_at is None

    controller.transition(
        application.application_id,
        KycStatus.UNDER_REVIEW,
        expected_version=2,
        actor_user_id=reviewer.id,
    )
    controller.transition(
        application.application_id,
        KycStatus.MORE_INFO_REQUIRED,
        expected_version=3,
        actor_user_id=reviewer.id,
        reason_code=KycReasonCode.DOCUMENT_ILLEGIBLE,
    )
    controller.transition(
        application.application_id, KycStatus.IN_PROGRESS, expected_version=4
    )
    resubmitted = controller.transition(
        application.application_id, KycStatus.SUBMITTED, expected_version=5
    )

    assert resubmitted.submitted_at == first_submitted_at


def test_an_applicant_action_writes_no_decision_row(app_context):
    """`kyc_decisions` records reviewer decisions. Submitting is not one."""
    application = insert_application(make_user().id, KycStatus.IN_PROGRESS)

    KycController().transition(
        application.application_id, KycStatus.SUBMITTED, expected_version=1
    )

    assert _decisions(application.application_id) == []


def test_transition_rejects_an_unknown_application(app_context):
    with pytest.raises(UnknownKycApplicationError):
        KycController().transition(
            uuid.uuid4(), KycStatus.SUBMITTED, expected_version=1
        )


# --- one transaction ---------------------------------------------------------


def test_a_failure_part_way_leaves_none_of_the_approval_applied(
    app_context, monkeypatch
):
    """The status change and the decision row land together or not at all.

    The decision row is made to blow up *after* the conditional UPDATE has run,
    which is precisely the window a controller that committed the status change
    first would leave open: an approved applicant with no record of who
    approved them.
    """
    reviewer = make_user()
    applicant = make_user()
    application = insert_application(applicant.id, KycStatus.UNDER_REVIEW)

    def explode(**_kwargs):
        raise RuntimeError("writing the decision failed")

    monkeypatch.setattr(kyc_repo_module, "KycDecision", explode)

    with pytest.raises(RuntimeError, match="writing the decision failed"):
        KycController().transition(
            application.application_id,
            KycStatus.APPROVED,
            expected_version=1,
            actor_user_id=reviewer.id,
        )

    monkeypatch.undo()
    reloaded = db.session.get(KycApplication, application.application_id)
    assert reloaded.status == KycStatus.UNDER_REVIEW.value
    assert reloaded.version == 1
    assert reloaded.tier_granted is None
    assert reloaded.next_review_at is None
    assert _decisions(application.application_id) == []


# --- optimistic concurrency --------------------------------------------------


def test_a_stale_version_loses_to_whoever_wrote_first(app_context):
    reviewer = make_user()
    application = insert_application(make_user().id, KycStatus.UNDER_REVIEW)

    # Stand in for a concurrent writer having moved the row on.
    db.session.execute(
        update(KycApplication)
        .where(KycApplication.application_id == application.application_id)
        .values(version=7)
    )
    db.session.commit()

    with pytest.raises(KycVersionConflictError):
        KycController().transition(
            application.application_id,
            KycStatus.APPROVED,
            expected_version=1,
            actor_user_id=reviewer.id,
        )

    reloaded = db.session.get(KycApplication, application.application_id)
    assert reloaded.status == KycStatus.UNDER_REVIEW.value
    assert _decisions(application.application_id) == []


def test_two_reviewers_with_the_page_open_cannot_both_decide(app_context):
    """The case the status alone cannot catch.

    Both reviewers are looking at the same `under_review` application. The first
    sends it back for more information, the applicant fixes it and resubmits,
    and a colleague claims it again — so it is `under_review` once more, and
    "approve" is still a legal move from where it now stands. Only the version
    says the row is not the one the second reviewer read.
    """
    first_reviewer = make_user()
    second_reviewer = make_user()
    applicant = make_user()
    application = insert_application(applicant.id, KycStatus.UNDER_REVIEW)
    controller = KycController()

    # What the second reviewer's open page is showing.
    version_on_screen = application.version

    controller.transition(
        application.application_id,
        KycStatus.MORE_INFO_REQUIRED,
        expected_version=1,
        actor_user_id=first_reviewer.id,
        reason_code=KycReasonCode.DOCUMENT_ILLEGIBLE,
    )
    controller.transition(
        application.application_id, KycStatus.IN_PROGRESS, expected_version=2
    )
    controller.transition(
        application.application_id, KycStatus.SUBMITTED, expected_version=3
    )
    controller.transition(
        application.application_id,
        KycStatus.UNDER_REVIEW,
        expected_version=4,
        actor_user_id=first_reviewer.id,
    )

    with pytest.raises(KycVersionConflictError):
        controller.transition(
            application.application_id,
            KycStatus.APPROVED,
            expected_version=version_on_screen,
            actor_user_id=second_reviewer.id,
        )

    reloaded = db.session.get(KycApplication, application.application_id)
    assert reloaded.status == KycStatus.UNDER_REVIEW.value
    assert reloaded.tier_granted is None


def test_a_conflict_is_answered_with_409(current_user):
    """A KYC `ConflictError` is a `DomainError`, so the shared handler in
    app.py answers 409. No KYC route has to translate it.

    The route is mounted for the test only: the review endpoints belong to the
    review ticket, and this is about the mapping, not about them.
    """
    app = create_app(TestConfig)

    @app.get("/_test/conflict")
    def raise_conflict():
        raise KycVersionConflictError("application is no longer at version 1")

    with TestClient(app) as client:
        response = client.get("/_test/conflict")

    assert response.status_code == 409
    assert response.json() == {"detail": "application is no longer at version 1"}


# --- derived standing --------------------------------------------------------


def test_application_history_records_create_and_transitions(app_context):
    reviewer = make_user()
    applicant = make_user()
    controller = KycController()
    repo = KycApplicationRepository()

    application = controller.start_application(applicant.id)
    history = repo.list_application_history(application.application_id)
    assert len(history) == 1
    assert history[0].status == KycStatus.IN_PROGRESS.value
    assert history[0].version_after == 1

    controller.transition(
        application.application_id,
        KycStatus.SUBMITTED,
        expected_version=1,
    )
    controller.transition(
        application.application_id,
        KycStatus.UNDER_REVIEW,
        expected_version=2,
        actor_user_id=reviewer.id,
    )

    history = repo.list_application_history(application.application_id)
    assert len(history) == 3
    assert history[-1].status == KycStatus.UNDER_REVIEW.value
    assert history[-1].version_after == 3
    assert history[-1].changed_by_user_id == reviewer.id


def test_every_transition_writes_history(app_context):
    reviewer = make_user()
    applicant = make_user()
    application = insert_application(applicant.id, KycStatus.IN_PROGRESS)
    controller = KycController()

    controller.transition(
        application.application_id,
        KycStatus.SUBMITTED,
        expected_version=1,
    )

    history = KycApplicationRepository().list_history(application.application_id)
    assert len(history) == 1
    assert history[0].status == KycStatus.SUBMITTED.value
    assert history[0].made_by_user_id is None

    controller.transition(
        application.application_id,
        KycStatus.UNDER_REVIEW,
        expected_version=2,
        actor_user_id=reviewer.id,
    )

    history = KycApplicationRepository().list_history(application.application_id)
    assert len(history) == 2
    assert history[1].made_by_user_id == reviewer.id


def test_standing_for_a_user_with_no_application(app_context):
    standing = KycController().get_standing(make_user().id)

    assert standing.status is KycStatus.NOT_STARTED
    assert standing.tier == KYC_TIER_NONE
    assert standing.application_id is None
    assert standing.is_verified is False


def test_standing_follows_the_latest_application(app_context):
    user = make_user()
    application = insert_application(user.id, KycStatus.SUBMITTED)

    standing = KycController().get_standing(user.id)

    assert standing.status is KycStatus.SUBMITTED
    assert standing.tier == KYC_TIER_NONE
    assert standing.application_id == application.application_id


def test_approval_grants_the_tier_without_a_column_on_users(app_context):
    reviewer = make_user()
    user = make_user()
    application = insert_application(user.id, KycStatus.UNDER_REVIEW)

    KycController().transition(
        application.application_id,
        KycStatus.APPROVED,
        expected_version=1,
        actor_user_id=reviewer.id,
    )

    standing = KycController().get_standing(user.id)
    assert standing.status is KycStatus.APPROVED
    assert standing.tier == KYC_TIER_VERIFIED
    assert standing.is_verified is True


def test_a_refresh_in_flight_keeps_the_earned_tier(app_context):
    """An approved user re-verifying should not drop to a zero allowance for as
    long as the refresh takes."""
    user = make_user()
    earlier = datetime.now(UTC) - timedelta(days=400)
    insert_application(
        user.id,
        KycStatus.REVIEW_DUE,
        created_at=earlier,
        tier_granted=KYC_TIER_VERIFIED,
    )
    insert_application(user.id, KycStatus.IN_PROGRESS)

    standing = KycController().get_standing(user.id)

    assert standing.status is KycStatus.IN_PROGRESS
    assert standing.tier == KYC_TIER_VERIFIED


def test_approval_copies_the_verified_name_and_country_onto_the_user(app_context):
    """A sender's beneficiary list reads these from `users`, since RLS keeps a
    customer route out of anyone else's application."""
    reviewer = make_user()
    user = make_user()
    application = insert_application(
        user.id,
        KycStatus.UNDER_REVIEW,
        full_name="  Tendai Moyo ",
        residential_country="ZW",
    )

    KycController().transition(
        application.application_id,
        KycStatus.APPROVED,
        expected_version=1,
        actor_user_id=reviewer.id,
    )

    db.session.expire_all()
    stored = db.session.get(User, user.id)
    assert stored.full_name == "Tendai Moyo"
    assert stored.country == "ZW"


def test_approval_copies_the_verified_mobile_number_onto_the_user(app_context):
    """The profile contact page reads `users.mobile_number`, so an approval
    seeds it from the application instead of leaving the user to re-enter
    what they already gave during verification."""
    reviewer = make_user()
    user = make_user()
    application = insert_application(
        user.id,
        KycStatus.UNDER_REVIEW,
        full_name="Tendai Moyo",
        residential_country="ZW",
        mobile_number=" +27821234567 ",
    )

    KycController().transition(
        application.application_id,
        KycStatus.APPROVED,
        expected_version=1,
        actor_user_id=reviewer.id,
    )

    db.session.expire_all()
    stored = db.session.get(User, user.id)
    assert stored.mobile_number == "+27821234567"


def test_only_an_approval_copies_the_name_onto_the_user(app_context):
    reviewer = make_user()
    user = make_user()
    application = insert_application(
        user.id,
        KycStatus.UNDER_REVIEW,
        full_name="Tendai Moyo",
        residential_country="ZW",
    )

    KycController().transition(
        application.application_id,
        KycStatus.REJECTED,
        expected_version=1,
        actor_user_id=reviewer.id,
        reason_code=KycReasonCode.DOCUMENT_ILLEGIBLE,
    )

    db.session.expire_all()
    stored = db.session.get(User, user.id)
    assert stored.full_name is None
    assert stored.country is None
