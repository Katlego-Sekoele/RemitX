"""`StokvelController` (R2-07) under Postgres row-level security (the
`postgres` lane, TEST_DATABASE_URL). Each call runs bound to the caller on a
customer route, as a request would; set-up and checks run unbound and see
every row. The same behaviour on SQLite is in `test_stokvels_route.py`."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from remitx_api.controllers.stokvel_controller import StokvelController
from remitx_api.db.rls import bound_row_security_context
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    TYPE_STOKVEL,
    Account,
)
from remitx_api.models.orm.kyc_lifecycle import KYC_TIER_VERIFIED, KycStatus
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_invitation import (
    StokvelInvitation,
    StokvelInvitationStatus,
)
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.repositories.account_repository import AccountRepository
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from tests.kyc_helpers import insert_application, make_user


def _zar_account(user) -> Account:
    return AccountRepository().get_or_create_user_account(
        user.id, user.base_reference, CURRENCY_ZAR
    )


def _customer(*, verified: bool = False):
    """A user with a ZAR account, committed; KYC-verified if `verified`."""
    user = make_user()
    _zar_account(user)
    if verified:
        insert_application(
            user.id, KycStatus.APPROVED, tier_granted=KYC_TIER_VERIFIED, with_pii=True
        )
    db.session.commit()
    return user


def _stokvel(organiser, name: str) -> Stokvel:
    stokvel = Stokvel(
        organiser_user_id=organiser.id,
        name=name,
        currency=CURRENCY_ZAR,
        contribution_amount=Decimal("10"),
    )
    db.session.add(stokvel)
    db.session.flush()
    _member(stokvel, organiser)
    return stokvel


def _member(stokvel, user, **columns) -> StokvelMember:
    member = StokvelMember(
        stokvel_id=stokvel.id,
        user_id=user.id,
        account_id=_zar_account(user).account_id,
        **columns,
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
        status_changed_by_user_id=invitee.id if answered else None,
    )
    db.session.add(invitation)
    db.session.flush()
    return invitation


@pytest.mark.postgres
def test_an_organiser_creates_a_stokvel_under_row_security(postgres_app):
    """The stokvel insert, its `account_id` update, the Organiser's member
    insert and the membership trigger all pass as the Organiser."""
    token = db.open_session()
    try:
        organiser = _customer(verified=True)
        organiser_id = organiser.id
        zar_account_id = _zar_account(organiser).account_id

        with bound_row_security_context(organiser_id, is_admin_route=False):
            view = StokvelController().create_stokvel(
                organiser_id,
                name="Family",
                currency="ZAR",
                contribution_amount=Decimal("25"),
            )

        stokvel = db.session.get(Stokvel, view.stokvel_id)
        assert stokvel is not None
        assert stokvel.organiser_user_id == organiser_id
        assert stokvel.account_id is not None

        ledger = db.session.get(Account, stokvel.account_id)
        assert ledger.type == TYPE_STOKVEL
        assert ledger.account_currency == CURRENCY_TOKEN
        assert ledger.user_id is None

        members = db.session.scalars(
            select(StokvelMember).where(StokvelMember.stokvel_id == stokvel.id)
        ).all()
        assert [(m.user_id, m.account_id) for m in members] == [
            (organiser_id, zar_account_id)
        ]
    finally:
        db.close_session(token)


@pytest.mark.postgres
def test_list_stokvels_under_row_security(postgres_app):
    token = db.open_session()
    try:
        organiser, member, pending, declined, outsider = (_customer() for _ in range(5))
        ours = _stokvel(organiser, "Ours")
        accepted = _invite(ours, member, StokvelInvitationStatus.ACCEPTED)
        _member(ours, member, invitation_id=accepted.id)
        _invite(ours, pending)
        _invite(ours, declined, StokvelInvitationStatus.DECLINED)
        theirs = _stokvel(outsider, "Theirs")
        db.session.commit()

        def listed(user):
            with bound_row_security_context(user.id, is_admin_route=False):
                view = StokvelController().list_stokvels(user.id)
            return (
                [(s.stokvel_id, s.member_count) for s in view.stokvels],
                [(i.stokvel_id, i.stokvel_name) for i in view.invitations],
            )

        expected = {
            "organiser": (organiser, [(ours.id, 2)], []),
            "member": (member, [(ours.id, 2)], []),
            "pending invitee": (pending, [], [(ours.id, "Ours")]),
            "declined invitee": (declined, [], []),
            "outsider": (outsider, [(theirs.id, 1)], []),
        }
        for who, (user, stokvels, invitations) in expected.items():
            assert listed(user) == (stokvels, invitations), who
    finally:
        db.close_session(token)


@pytest.mark.postgres
def test_a_member_row_with_another_users_account_is_refused(postgres_app):
    """Row-level security lets a customer insert their own member row, so the
    trigger is what stops it naming someone else's account."""
    token = db.open_session()
    try:
        organiser, joiner = _customer(), _customer()
        stokvel = _stokvel(organiser, "Guarded")
        db.session.commit()
        stokvel_id, joiner_id = stokvel.id, joiner.id
        organiser_account_id = _zar_account(organiser).account_id
        joiner_account_id = _zar_account(joiner).account_id

        def join_with(account_id):
            with bound_row_security_context(joiner_id, is_admin_route=False):
                db.session.add(
                    StokvelMember(
                        stokvel_id=stokvel_id,
                        user_id=joiner_id,
                        account_id=account_id,
                    )
                )
                db.session.flush()

        with pytest.raises(IntegrityError, match="stokvel currency"):
            join_with(organiser_account_id)
        db.session.rollback()

        # The same insert with the joiner's own account passes, so the
        # refusal above was the trigger, not row-level security.
        join_with(joiner_account_id)
        db.session.commit()
    finally:
        db.close_session(token)
