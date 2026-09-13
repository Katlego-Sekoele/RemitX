"""The status machine: every legal move, every illegal one, and the database's
agreement with the Python enum."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from remitx_api.controllers.kyc_controller import KycController
from remitx_api.errors.kyc import IllegalKycTransitionError
from remitx_api.extensions import db
from remitx_api.models.orm.kyc_application import KycApplication
from remitx_api.models.orm.kyc_lifecycle import (
    APPLICATION_STATUSES,
    DECISION_STATUSES,
    LEGAL_TRANSITIONS,
    OPEN_STATUSES,
    KycStatus,
    effective_status,
    sql_value_list,
)
from remitx_api.models.schemas.kyc import KycApplicationRead, KycApplicationReadPII
from sqlalchemy.exc import IntegrityError
from tests.kyc_helpers import insert_application, make_user, seed_kyc_reference_data

# Every ordered pair of statuses a row can actually hold. `not_started` is
# excluded because no row holds it — it is the derived answer for a user with
# no application at all.
ALL_PAIRS = [
    (from_status, to_status)
    for from_status in APPLICATION_STATUSES
    for to_status in APPLICATION_STATUSES
]


@pytest.fixture(autouse=True)
def _seed_kyc_reference(app_context):
    seed_kyc_reference_data()


def test_every_status_has_a_transition_rule():
    """A new `KycStatus` member with no entry in LEGAL_TRANSITIONS would make
    `transition` raise KeyError at runtime instead of rejecting the move."""
    assert set(LEGAL_TRANSITIONS) == set(KycStatus)


def test_no_status_transitions_to_itself():
    for status, targets in LEGAL_TRANSITIONS.items():
        assert status not in targets, f"{status.value} loops to itself"


def test_not_started_is_never_a_target():
    """Nothing walks a user back to "no application": `start_application`
    creates a new row instead, so the rejected attempt survives."""
    for targets in LEGAL_TRANSITIONS.values():
        assert KycStatus.NOT_STARTED not in targets


def test_rejected_and_review_due_are_terminal_on_the_row():
    """Both are left by opening a *new* application, never by editing this one
    — see models/orm/kyc_lifecycle.py."""
    assert LEGAL_TRANSITIONS[KycStatus.REJECTED] == frozenset()
    assert LEGAL_TRANSITIONS[KycStatus.REVIEW_DUE] == frozenset()


def test_review_due_is_not_an_open_status():
    """If it were, the partial unique index would stop an approved user ever
    opening the refresh application `review_due` exists to prompt."""
    assert KycStatus.REVIEW_DUE not in OPEN_STATUSES
    assert KycStatus.APPROVED not in OPEN_STATUSES


def test_sql_value_list_is_stable_and_in_declaration_order():
    """The CHECK constraints and the partial index predicate are built from
    these, and a predicate whose text shuffles between runs is phantom drift."""
    assert sql_value_list(OPEN_STATUSES) == (
        "'in_progress', 'submitted', 'under_review', 'more_info_required'"
    )
    assert sql_value_list(OPEN_STATUSES) == sql_value_list(set(OPEN_STATUSES))


def test_sql_value_list_rejects_an_empty_set():
    with pytest.raises(ValueError, match="cannot be empty"):
        sql_value_list([])


@pytest.mark.parametrize(("from_status", "to_status"), ALL_PAIRS)
def test_every_transition_pair_is_allowed_or_raises(
    app_context, from_status, to_status
):
    """The whole machine, exhaustively: each of the 49 ordered pairs either
    moves the application or raises, and which one is decided by
    LEGAL_TRANSITIONS rather than by this test restating it."""
    reviewer = make_user()
    applicant = make_user()
    application = insert_application(applicant.id, from_status)
    controller = KycController()

    if to_status in LEGAL_TRANSITIONS[from_status]:
        updated = controller.transition(
            application.application_id,
            to_status,
            expected_version=1,
            actor_user_id=reviewer.id,
        )
        assert updated.status == to_status.value
        assert updated.version == 2
    else:
        with pytest.raises(IllegalKycTransitionError):
            controller.transition(
                application.application_id,
                to_status,
                expected_version=1,
                actor_user_id=reviewer.id,
            )
        # Illegal moves raise *before* touching the row, so nothing to roll back.
        assert application.status == from_status.value
        assert application.version == 1


def test_an_unknown_status_is_rejected_rather_than_written(app_context):
    application = insert_application(make_user().id)
    with pytest.raises(IllegalKycTransitionError, match="Unknown KYC status"):
        KycController().transition(
            application.application_id,
            "pending",  # the backlog's old ambiguous value
            expected_version=1,
        )


@pytest.mark.parametrize("status", list(DECISION_STATUSES))
def test_a_reviewer_decision_without_an_actor_is_refused(app_context, status):
    """`decided_by_user_id` NULL because the caller forgot reads as "the system
    did this", which is worse than no log at all."""
    applicant = make_user()
    # Set the row up in a status the decision is legal from.
    from_status = next(
        candidate
        for candidate, targets in LEGAL_TRANSITIONS.items()
        if status in targets
    )
    application = insert_application(applicant.id, from_status)

    with pytest.raises(ValueError, match="requires actor_user_id"):
        KycController().transition(
            application.application_id,
            status,
            expected_version=1,
        )


def test_the_database_rejects_a_status_outside_the_enum(app_context):
    """Statuses are foreign keys to `kyc_application_statuses`, seeded from
    `KycStatus`, so an unknown value fails at the database."""
    user = make_user()
    db.session.add(KycApplication(user_id=user.id, status="pending"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_the_database_rejects_not_started_on_an_application(app_context):
    """`not_started` is not in the status catalogue, so a row holding it
    violates the foreign key."""
    user = make_user()
    db.session.add(KycApplication(user_id=user.id, status=KycStatus.NOT_STARTED.value))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


# --- expiry ---------------------------------------------------------------------


def test_an_approval_expires_on_its_review_date_and_not_before():
    now = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
    approved = KycStatus.APPROVED.value

    assert effective_status(approved, now + timedelta(seconds=1), now) == (
        KycStatus.APPROVED
    )
    assert effective_status(approved, now, now) == KycStatus.REVIEW_DUE
    assert effective_status(approved, now - timedelta(days=1), now) == (
        KycStatus.REVIEW_DUE
    )
    # Naive values come back from SQLite and are read as UTC.
    assert effective_status(approved, now.replace(tzinfo=None), now) == (
        KycStatus.REVIEW_DUE
    )
    assert effective_status(approved, None, now) == KycStatus.APPROVED
    assert effective_status(KycStatus.REJECTED.value, now, now) == KycStatus.REJECTED


def test_staff_schemas_report_an_expired_approval_as_review_due():
    now = datetime.now(UTC)
    application = KycApplication(
        application_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        status=KycStatus.APPROVED.value,
        next_review_at=now - timedelta(minutes=1),
        version=1,
        created_at=now,
        updated_at=now,
    )

    assert KycApplicationRead.model_validate(application).status == "review_due"
    assert KycApplicationReadPII.model_validate(application).status == "review_due"
