"""`stokvel_members` write rules and the invitation lookups under Postgres
row-level security (R2-08, `V20261017_1820`; the `postgres` lane,
TEST_DATABASE_URL).

Each write runs bound to a customer, as a request would; set-up and checks run
unbound and see every row. A policy refuses with SQLSTATE 42501, the triggers
with 23514, so each refusal is told apart by its code.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.db.rls import bound_row_security_context
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR, Account
from remitx_api.models.orm.kyc_lifecycle import KycStatus
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_invitation import (
    StokvelInvitation,
    StokvelInvitationStatus,
)
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.repositories.account_repository import AccountRepository
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import DBAPIError
from tests.kyc_helpers import insert_application, make_user

POLICY_REFUSED = "42501"
TRIGGER_REFUSED = "23514"


@pytest.fixture
def session(postgres_app):
    token = db.open_session()
    try:
        yield db.session
    finally:
        db.close_session(token)


def _zar_account(user) -> Account:
    return AccountRepository().get_or_create_user_account(
        user.id, user.base_reference, CURRENCY_ZAR
    )


def _customer():
    user = make_user()
    _zar_account(user)
    db.session.commit()
    return user


def _stokvel(organiser, name: str = "Family") -> Stokvel:
    """A committed stokvel with its Organiser as first member."""
    stokvel = Stokvel(
        organiser_user_id=organiser.id,
        name=name,
        currency=CURRENCY_ZAR,
        contribution_amount=Decimal("10"),
    )
    db.session.add(stokvel)
    db.session.flush()
    _add_member(stokvel.id, organiser)
    db.session.commit()
    return stokvel


def _add_member(stokvel_id, user, invitation_id=None) -> StokvelMember:
    """A member row written unbound, as set-up."""
    member = StokvelMember(
        stokvel_id=stokvel_id,
        user_id=user.id,
        account_id=_zar_account(user).account_id,
        invitation_id=invitation_id,
    )
    db.session.add(member)
    db.session.flush()
    return member


def _invite(stokvel, invitee, status=StokvelInvitationStatus.PENDING):
    answered = status != StokvelInvitationStatus.PENDING
    invitation = StokvelInvitation(
        stokvel_id=stokvel.id,
        invitee_user_id=invitee.id,
        invited_by_user_id=stokvel.organiser_user_id,
        status=status.value,
        status_changed_at=datetime.now(UTC) if answered else None,
        status_changed_by_user_id=(
            None
            if not answered
            else stokvel.organiser_user_id
            if status == StokvelInvitationStatus.REVOKED
            else invitee.id
        ),
    )
    db.session.add(invitation)
    db.session.commit()
    return invitation


def _join_as(user, stokvel_id, invitation_id) -> None:
    """Insert `user`'s own member row on a customer route."""
    account_id = _zar_account(user).account_id
    with bound_row_security_context(user.id, is_admin_route=False):
        db.session.add(
            StokvelMember(
                stokvel_id=stokvel_id,
                user_id=user.id,
                account_id=account_id,
                invitation_id=invitation_id,
            )
        )
        db.session.flush()


def _refused_code(fn) -> str:
    with pytest.raises(DBAPIError) as refused:
        fn()
    db.session.rollback()
    return refused.value.orig.pgcode


def _members(stokvel_id) -> set[uuid.UUID]:
    return set(
        db.session.scalars(
            select(StokvelMember.user_id).where(StokvelMember.stokvel_id == stokvel_id)
        )
    )


@pytest.mark.postgres
def test_joining_needs_your_own_accepted_invitation_to_that_stokvel(session):
    organiser, joiner, other = _customer(), _customer(), _customer()
    stokvel = _stokvel(organiser)
    elsewhere = _stokvel(_customer(), "Elsewhere")
    statuses = {
        status: _invite(stokvel, joiner, status).id
        for status in (
            StokvelInvitationStatus.DECLINED,
            StokvelInvitationStatus.REVOKED,
            StokvelInvitationStatus.LAPSED,
        )
    }
    pending = _invite(stokvel, joiner).id
    to_elsewhere = _invite(elsewhere, joiner, StokvelInvitationStatus.ACCEPTED).id
    for_other = _invite(stokvel, other, StokvelInvitationStatus.ACCEPTED).id

    refused = {
        "no invitation": None,
        "pending": pending,
        **{status.value: invitation for status, invitation in statuses.items()},
        "accepted, to another stokvel": to_elsewhere,
        "accepted, for another user": for_other,
    }
    codes = {
        who: _refused_code(lambda inv=invitation: _join_as(joiner, stokvel.id, inv))
        for who, invitation in refused.items()
    }

    assert codes == {who: POLICY_REFUSED for who in refused}
    assert _members(stokvel.id) == {organiser.id}


@pytest.mark.postgres
def test_an_accepted_invitation_lets_the_invitee_join(session):
    organiser, joiner = _customer(), _customer()
    stokvel = _stokvel(organiser)
    accepted = _invite(stokvel, joiner, StokvelInvitationStatus.ACCEPTED)

    _join_as(joiner, stokvel.id, accepted.id)
    db.session.commit()

    assert _members(stokvel.id) == {organiser.id, joiner.id}


@pytest.mark.postgres
def test_an_accepted_invitation_is_used_once(session):
    """`invitation_id` is unique, so leaving does not let the old invitation
    readmit you."""
    organiser, joiner = _customer(), _customer()
    stokvel = _stokvel(organiser)
    accepted = _invite(stokvel, joiner, StokvelInvitationStatus.ACCEPTED)
    member = _add_member(stokvel.id, joiner, accepted.id)
    member.left_at = datetime.now(UTC)
    db.session.commit()

    assert _refused_code(lambda: _join_as(joiner, stokvel.id, accepted.id)) == "23505"


@pytest.mark.postgres
def test_only_the_organiser_joins_without_an_invitation(session):
    """The Organiser's own row when creating a stokvel (R2-07) has no
    invitation; nobody else's may."""
    organiser, member = _customer(), _customer()
    stokvel = Stokvel(
        organiser_user_id=organiser.id,
        name="Fresh",
        currency=CURRENCY_ZAR,
        contribution_amount=Decimal("10"),
    )
    db.session.add(stokvel)
    db.session.commit()

    assert _refused_code(lambda: _join_as(member, stokvel.id, None)) == POLICY_REFUSED
    _join_as(organiser, stokvel.id, None)
    db.session.commit()

    assert _members(stokvel.id) == {organiser.id}


@pytest.mark.postgres
def test_a_member_may_update_their_own_row(session):
    organiser, member = _customer(), _customer()
    stokvel = _stokvel(organiser)
    accepted = _invite(stokvel, member, StokvelInvitationStatus.ACCEPTED)
    row = _add_member(stokvel.id, member, accepted.id)
    db.session.commit()
    row_id = row.id
    left_at = datetime.now(UTC)

    with bound_row_security_context(member.id, is_admin_route=False):
        updated = db.session.execute(
            update(StokvelMember)
            .where(StokvelMember.id == row_id)
            .values(left_at=left_at, account_id=_zar_account(member).account_id)
        ).rowcount
    db.session.commit()

    assert updated == 1
    assert db.session.get(StokvelMember, row_id).left_at == left_at


@pytest.mark.postgres
def test_a_member_cannot_update_or_delete_someone_elses_row(session):
    organiser, member = _customer(), _customer()
    stokvel = _stokvel(organiser)
    accepted = _invite(stokvel, member, StokvelInvitationStatus.ACCEPTED)
    _add_member(stokvel.id, member, accepted.id)
    db.session.commit()
    organisers_row = StokvelMember.user_id == organiser.id

    with bound_row_security_context(member.id, is_admin_route=False):
        updated = db.session.execute(
            update(StokvelMember)
            .where(organisers_row)
            .values(left_at=datetime.now(UTC))
        ).rowcount
    assert updated == 0
    db.session.rollback()


@pytest.mark.postgres
def test_no_customer_can_delete_a_membership_their_own_included(session):
    organiser = _customer()
    stokvel = _stokvel(organiser)

    with bound_row_security_context(organiser.id, is_admin_route=False):
        deleted = db.session.execute(
            delete(StokvelMember).where(StokvelMember.stokvel_id == stokvel.id)
        ).rowcount
    db.session.rollback()

    assert deleted == 0
    assert _members(stokvel.id) == {organiser.id}


@pytest.mark.postgres
@pytest.mark.parametrize("bound", [True, False], ids=["customer", "unbound"])
@pytest.mark.parametrize(
    "column", ["stokvel_id", "user_id", "invitation_id", "joined_at", "left_at"]
)
def test_a_memberships_identity_cannot_change(session, column, bound):
    """For every role, workers included: leaving and rejoining makes a new
    row, so a former membership is never reopened. Moving to another ZAR
    stokvel keeps the account valid, so the refusal is this trigger's, not the
    account trigger's."""
    organiser = _customer()
    stokvel = _stokvel(organiser)
    other = _stokvel(organiser, "Other")
    stranger = _customer()
    invitation = _invite(other, stranger)
    row = db.session.scalars(
        select(StokvelMember).where(
            StokvelMember.stokvel_id == stokvel.id,
            StokvelMember.user_id == organiser.id,
        )
    ).one()
    row_id = row.id
    # A new user moves the account with it, so the account trigger passes.
    changes = {
        "stokvel_id": {"stokvel_id": other.id},
        "user_id": {
            "user_id": stranger.id,
            "account_id": _zar_account(stranger).account_id,
        },
        "invitation_id": {"invitation_id": invitation.id},
        "joined_at": {"joined_at": row.joined_at - timedelta(days=1)},
        "left_at": {"left_at": None},
    }[column]
    db.session.commit()
    if column == "left_at":
        # Leaving is allowed; coming back on the same row is not.
        with bound_row_security_context(organiser.id, is_admin_route=False):
            left = db.session.execute(
                update(StokvelMember)
                .where(StokvelMember.id == row_id)
                .values(left_at=datetime.now(UTC))
            ).rowcount
        db.session.commit()
        assert left == 1

    def change():
        statement = (
            update(StokvelMember).where(StokvelMember.id == row_id).values(changes)
        )
        if bound:
            with bound_row_security_context(organiser.id, is_admin_route=False):
                db.session.execute(statement)
        else:
            db.session.execute(statement)

    with pytest.raises(DBAPIError, match="cannot change") as refused:
        change()
    db.session.rollback()

    assert refused.value.orig.pgcode == TRIGGER_REFUSED


@pytest.mark.postgres
def test_kyc_latest_status_reads_another_users_latest_application(session):
    """Bound as someone who cannot read the applications, the lookup still
    answers, and with the latest one, as `get_standing` reads it."""
    asker, approved, reapplied, none = (_customer() for _ in range(4))
    now = datetime.now(UTC)
    insert_application(approved.id, KycStatus.APPROVED, created_at=now)
    insert_application(
        reapplied.id, KycStatus.APPROVED, created_at=now - timedelta(days=2)
    )
    insert_application(reapplied.id, KycStatus.REJECTED, created_at=now)

    def status_of(user):
        with bound_row_security_context(asker.id, is_admin_route=False):
            return db.session.scalar(select(func.kyc_latest_status(user.id)))

    assert status_of(approved) == "approved"
    assert status_of(reapplied) == "rejected"
    assert status_of(none) is None


@pytest.mark.postgres
def test_active_member_count_answers_an_invitee(session):
    """An invitee cannot read the member rows, but can count them."""
    organiser, member, former, invitee = (_customer() for _ in range(4))
    stokvel = _stokvel(organiser)
    for user in (member, former):
        accepted = _invite(stokvel, user, StokvelInvitationStatus.ACCEPTED)
        row = _add_member(stokvel.id, user, accepted.id)
    row.left_at = datetime.now(UTC)
    _invite(stokvel, invitee)
    db.session.commit()

    with bound_row_security_context(invitee.id, is_admin_route=False):
        visible = db.session.scalars(
            select(StokvelMember.id).where(StokvelMember.stokvel_id == stokvel.id)
        ).all()
        count = db.session.scalar(select(func.stokvel_active_member_count(stokvel.id)))

    assert visible == []
    assert count == 2
