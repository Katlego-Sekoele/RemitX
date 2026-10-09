"""Stokvel group tables (R2-04): constraints on SQLite, row-level security on
Postgres (the `postgres` lane, TEST_DATABASE_URL)."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from remitx_api.db.rls import bound_row_security_context
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_invitation import (
    StokvelInvitation,
    StokvelInvitationStatus,
)
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.repositories.account_repository import AccountRepository
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from tests.kyc_helpers import make_user


def _stokvel(organiser) -> Stokvel:
    stokvel = Stokvel(
        organiser_user_id=organiser.id,
        name="Savings club",
        currency=CURRENCY_ZAR,
        contribution_amount=Decimal("500"),
    )
    db.session.add(stokvel)
    db.session.flush()
    _member(stokvel, organiser)
    return stokvel


def _member(stokvel, user, **columns) -> StokvelMember:
    account = AccountRepository().get_or_create_user_account(
        user.id, user.base_reference, stokvel.currency
    )
    member = StokvelMember(
        stokvel_id=stokvel.id, user_id=user.id, account_id=account.account_id, **columns
    )
    db.session.add(member)
    db.session.flush()
    return member


def _invite(stokvel, invitee, status=StokvelInvitationStatus.PENDING, by=None):
    answered = status != StokvelInvitationStatus.PENDING
    invitation = StokvelInvitation(
        stokvel_id=stokvel.id,
        invitee_user_id=invitee.id,
        invited_by_user_id=stokvel.organiser_user_id,
        status=status.value,
        status_changed_at=datetime.now(UTC) if answered else None,
        status_changed_by_user_id=(by or invitee).id if answered else None,
    )
    db.session.add(invitation)
    db.session.flush()
    return invitation


def _rejected(write) -> None:
    with pytest.raises(IntegrityError):
        write()
    db.session.rollback()


def test_a_stokvel_with_an_accepted_invitation_and_member(app_context):
    stokvel = _stokvel(make_user())
    invitee = make_user()
    invitation = _invite(stokvel, invitee, StokvelInvitationStatus.ACCEPTED)
    _member(stokvel, invitee, invitation_id=invitation.id)
    db.session.commit()

    members = db.session.scalars(
        select(StokvelMember).where(StokvelMember.stokvel_id == stokvel.id)
    ).all()
    assert len(members) == 2


def test_only_one_pending_invitation_per_invitee(app_context):
    stokvel = _stokvel(make_user())
    invitee = make_user()
    _invite(stokvel, invitee, StokvelInvitationStatus.DECLINED)
    _invite(stokvel, invitee)

    _rejected(lambda: _invite(stokvel, invitee))


def test_an_organiser_cannot_invite_themselves(app_context):
    organiser = make_user()
    stokvel = _stokvel(organiser)

    _rejected(lambda: _invite(stokvel, organiser))


def test_only_the_invitee_accepts(app_context):
    organiser = make_user()
    stokvel = _stokvel(organiser)

    _rejected(
        lambda: _invite(
            stokvel, make_user(), StokvelInvitationStatus.ACCEPTED, by=organiser
        )
    )


def test_a_final_status_needs_its_change_time(app_context):
    stokvel = _stokvel(make_user())
    invitation = _invite(stokvel, make_user())
    invitation.status = StokvelInvitationStatus.REVOKED.value

    _rejected(db.session.flush)


def test_one_active_membership_but_a_former_member_can_rejoin(app_context):
    organiser = make_user()
    stokvel = _stokvel(organiser)
    db.session.commit()

    _rejected(lambda: _member(stokvel, organiser))

    stokvel = db.session.get(Stokvel, stokvel.id)
    first = db.session.scalars(select(StokvelMember)).one()
    first.left_at = datetime.now(UTC)
    rejoined = _member(stokvel, organiser)
    assert rejoined.id != first.id


@pytest.mark.postgres
def test_row_security_scopes_each_customer(postgres_app):
    token = db.open_session()
    try:
        organiser, member, pending, declined, former, outsider = (
            make_user() for _ in range(6)
        )
        stokvel = _stokvel(organiser)
        accepted = _invite(stokvel, member, StokvelInvitationStatus.ACCEPTED)
        _member(stokvel, member, invitation_id=accepted.id)
        _invite(stokvel, pending)
        _invite(stokvel, declined, StokvelInvitationStatus.DECLINED)
        _member(stokvel, former, left_at=datetime.now(UTC))
        other = _stokvel(outsider)
        db.session.commit()
        ours = (stokvel.id, other.id)

        def visible(user, model, column, *, admin=False):
            with bound_row_security_context(user.id, is_admin_route=admin):
                return len(
                    db.session.scalars(select(model).where(column.in_(ours))).all()
                )

        # (stokvels, members, invitations) each customer sees
        expected = {
            "organiser": (organiser, 1, 3, 3),
            "member": (member, 1, 3, 3),
            "pending invitee": (pending, 1, 0, 3),
            "declined invitee": (declined, 0, 0, 1),
            "former member": (former, 1, 3, 3),
            "outsider": (outsider, 1, 1, 0),
        }
        for who, (user, stokvels, members, invitations) in expected.items():
            seen = (
                visible(user, Stokvel, Stokvel.id),
                visible(user, StokvelMember, StokvelMember.stokvel_id),
                visible(user, StokvelInvitation, StokvelInvitation.stokvel_id),
            )
            assert seen == (stokvels, members, invitations), who

        assert visible(outsider, Stokvel, Stokvel.id, admin=True) == 2

        # A member can read the stokvel but only the Organiser may change it
        with bound_row_security_context(member.id, is_admin_route=False):
            with pytest.raises(ProgrammingError, match="row-level security"):
                db.session.execute(
                    text("UPDATE stokvels SET name = 'taken' WHERE id = :id"),
                    {"id": stokvel.id},
                )
        db.session.rollback()
    finally:
        db.close_session(token)
