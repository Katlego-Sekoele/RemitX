"""Stokvel contributions table (R2-06): constraints on SQLite, row-level
security on Postgres (the `postgres` lane, TEST_DATABASE_URL)."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.db.rls import bound_row_security_context
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_contribution import (
    StokvelContribution,
    StokvelContributionStatus,
)
from remitx_api.models.orm.stokvel_cycle import StokvelCycle
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.models.orm.stokvel_round import StokvelRound
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.stokvel_contribution_repository import (
    StokvelContributionRepository,
)
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from tests.kyc_helpers import make_user

_START = datetime(2026, 11, 1, tzinfo=UTC)
_PENDING = StokvelContributionStatus.PENDING.value
_PROCESSING = StokvelContributionStatus.PROCESSING.value
_CONFIRMED = StokvelContributionStatus.CONFIRMED.value
_FAILED = StokvelContributionStatus.FAILED.value


def _stokvel(organiser) -> tuple[Stokvel, StokvelMember]:
    stokvel = Stokvel(
        organiser_user_id=organiser.id,
        name="Savings club",
        currency=CURRENCY_ZAR,
        contribution_amount=Decimal("25"),
    )
    db.session.add(stokvel)
    db.session.flush()
    return stokvel, _member(stokvel, organiser)


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


def _cycle(stokvel, members, rounds=2) -> StokvelCycle:
    """A cycle of `stokvel` with `members` in it and `rounds` rounds."""
    cycle = StokvelCycle(stokvel_id=stokvel.id, cycle_number=1)
    db.session.add(cycle)
    db.session.flush()
    for position, member in enumerate(members):
        db.session.add(
            StokvelCycleMember(
                cycle_id=cycle.id, member_id=member.id, payout_position=position
            )
        )
    for number in range(rounds):
        start = _START + timedelta(weeks=number)
        db.session.add(
            StokvelRound(
                cycle_id=cycle.id,
                round=number,
                start_time=start,
                deadline=start + timedelta(days=1),
                payout_time=start + timedelta(days=2),
            )
        )
    db.session.flush()
    return cycle


def _group(*, rounds=2):
    """A stokvel whose Organiser and one other member are in its cycle."""
    stokvel, organiser = _stokvel(make_user())
    member = _member(stokvel, make_user())
    return stokvel, organiser, member, _cycle(stokvel, [organiser, member], rounds)


def _confirmed(block=1) -> dict:
    return {
        "status": _CONFIRMED,
        "evm_tx_hash": "0x" + uuid.uuid4().hex * 2,
        "block_number": block,
        "confirmed_at": datetime.now(UTC),
    }


def _contribute(cycle, member, round_=0, **columns) -> StokvelContribution:
    row = StokvelContribution(
        cycle_id=cycle.id,
        round=round_,
        member_id=member.id,
        amount_token=columns.pop("amount_token", Decimal("25")),
        amount_fiat=columns.pop("amount_fiat", Decimal("462.50")),
        **columns,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _rejected(write) -> None:
    with pytest.raises(IntegrityError):
        write()
    db.session.rollback()


def test_contributions_record_who_has_paid_a_round(app_context):
    _, organiser, member, cycle = _group()
    _contribute(cycle, organiser, **_confirmed())
    pending = _contribute(cycle, member)
    db.session.commit()

    repo = StokvelContributionRepository()
    assert pending.status == _PENDING
    assert pending.created_at is not None
    assert repo.get_member_contribution(cycle.id, 0, member.id).id == pending.id
    assert repo.get_member_contribution(cycle.id, 1, member.id) is None
    assert repo.get_paid_member_ids(cycle.id, 0) == {organiser.id}
    assert repo.get_paid_member_ids(cycle.id, 1) == set()
    assert len(repo.get_round_contributions(cycle.id, 0)) == 2


@pytest.mark.parametrize(
    "first",
    [
        pytest.param({}, id="pending"),
        pytest.param({"status": _PROCESSING}, id="processing"),
        pytest.param(_confirmed(), id="confirmed"),
    ],
)
def test_a_member_cannot_pay_a_round_twice(app_context, first):
    _, _, member, cycle = _group()
    _contribute(cycle, member, **first)

    _rejected(lambda: _contribute(cycle, member))


def test_a_failed_contribution_can_be_paid_again(app_context):
    _, _, member, cycle = _group()
    failed = _contribute(
        cycle,
        member,
        status=_FAILED,
        created_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    retry = _contribute(cycle, member)

    repo = StokvelContributionRepository()
    assert repo.get_member_contribution(cycle.id, 0, member.id).id == retry.id
    assert [row.id for row in repo.get_round_contributions(cycle.id, 0)] == [
        failed.id,
        retry.id,
    ]
    _rejected(lambda: _contribute(cycle, member))


def test_members_pay_every_round_and_each_other_round(app_context):
    _, organiser, member, cycle = _group()
    for round_ in (0, 1):
        _contribute(cycle, organiser, round_)
        _contribute(cycle, member, round_)

    assert db.session.scalar(select(func.count(StokvelContribution.id))) == 4


def test_a_contribution_stays_inside_its_cycle(app_context):
    stokvel, _, member, cycle = _group()
    not_in_cycle = _member(stokvel, make_user())
    other_stokvel, outsider = _stokvel(make_user())
    _cycle(other_stokvel, [outsider, _member(other_stokvel, make_user())])
    db.session.commit()

    refused = {
        "a stokvel member not in the cycle": lambda: _contribute(cycle, not_in_cycle),
        "a member of another stokvel": lambda: _contribute(cycle, outsider),
        "a round the cycle does not have": lambda: _contribute(cycle, member, 2),
    }
    for what, insert in refused.items():
        with pytest.raises(IntegrityError):
            insert()
            pytest.fail(f"{what}: accepted")
        db.session.rollback()


@pytest.mark.parametrize(
    "columns",
    [
        pytest.param({"status": "paid"}, id="unknown status"),
        pytest.param({"amount_token": Decimal("0")}, id="no tokens"),
        pytest.param({"amount_fiat": Decimal("-1")}, id="negative fiat"),
        pytest.param({"evm_tx_hash": "0xabc"}, id="pending with a hash"),
        pytest.param(
            {"status": _PROCESSING, "block_number": 7}, id="block without a hash"
        ),
        pytest.param(
            {**_confirmed(), "block_number": None}, id="confirmed without a block"
        ),
        pytest.param(
            {**_confirmed(), "confirmed_at": None}, id="confirmed without a time"
        ),
        pytest.param({"confirmed_at": datetime.now(UTC)}, id="pending with a time"),
        pytest.param({**_confirmed(block=-1)}, id="negative block"),
    ],
)
def test_a_contributions_status_matches_its_columns(app_context, columns):
    _, _, member, cycle = _group()

    _rejected(lambda: _contribute(cycle, member, **columns))


def test_a_processing_contribution_may_hold_its_hash(app_context):
    """The worker stores the hash before it sends `contribute` (as for the
    burn, #278), so a processing or failed row may have one."""
    _, organiser, member, cycle = _group()
    _contribute(cycle, organiser, status=_PROCESSING, evm_tx_hash="0x01")
    _contribute(cycle, member, status=_FAILED, evm_tx_hash="0x02")


def test_a_transaction_hash_belongs_to_one_contribution(app_context):
    _, organiser, member, cycle = _group()
    _contribute(cycle, organiser, status=_PROCESSING, evm_tx_hash="0xsame")

    _rejected(
        lambda: _contribute(cycle, member, status=_PROCESSING, evm_tx_hash="0xsame")
    )


_SET_STATUS = (
    "UPDATE stokvel_contributions SET status = 'processing' WHERE cycle_id = :cycle"
)
_DELETE = "DELETE FROM stokvel_contributions WHERE cycle_id = :cycle"


def _as(user, sql, **params) -> int:
    """Run `sql` as `user` on a customer route; the number of rows it hit."""
    with bound_row_security_context(user.id, is_admin_route=False):
        return db.session.execute(text(sql), params).rowcount


@pytest.mark.postgres
def test_row_security_scopes_contributions_to_members(postgres_app):
    token = db.open_session()
    try:
        organiser, member, former, outsider = (make_user() for _ in range(4))
        stokvel, organiser_row = _stokvel(organiser)
        member_row = _member(stokvel, member)
        _member(stokvel, former, left_at=datetime.now(UTC))
        cycle = _cycle(stokvel, [organiser_row, member_row])
        _contribute(cycle, organiser_row)
        _contribute(cycle, member_row)
        other, outsider_row = _stokvel(outsider)
        other_cycle = _cycle(other, [outsider_row, _member(other, make_user())])
        _contribute(other_cycle, outsider_row)
        db.session.commit()
        ours = (cycle.id, other_cycle.id)

        def visible(user, *, admin=False) -> int:
            with bound_row_security_context(user.id, is_admin_route=admin):
                return len(
                    db.session.scalars(
                        select(StokvelContribution).where(
                            StokvelContribution.cycle_id.in_(ours)
                        )
                    ).all()
                )

        seen = {
            "organiser": (organiser, 2),
            "member": (member, 2),
            "former member": (former, 2),
            "outsider": (outsider, 1),
        }
        for who, (user, count) in seen.items():
            assert visible(user) == count, who
        assert visible(outsider, admin=True) == 3
    finally:
        db.close_session(token)


@pytest.mark.postgres
def test_row_security_lets_a_member_record_only_their_own(postgres_app):
    token = db.open_session()
    try:
        organiser, member, outsider = (make_user() for _ in range(3))
        stokvel, organiser_row = _stokvel(organiser)
        member_row = _member(stokvel, member)
        cycle = _cycle(stokvel, [organiser_row, member_row])
        db.session.commit()
        cycle_id, organiser_id, member_id = cycle.id, organiser_row.id, member_row.id

        def contribute_as(user, member_row_id):
            # By id: an outsider cannot read the cycle or member rows, so it
            # is the insert policy, not a failed read, that must refuse them
            with bound_row_security_context(user.id, is_admin_route=False):
                db.session.add(
                    StokvelContribution(
                        cycle_id=cycle_id,
                        round=0,
                        member_id=member_row_id,
                        amount_token=Decimal("25"),
                        amount_fiat=Decimal("462.50"),
                    )
                )
                db.session.flush()

        contribute_as(member, member_id)
        db.session.commit()

        refused = {
            "the Organiser, for a member": (organiser, member_id),
            "a member, for the Organiser": (member, organiser_id),
            "an outsider, for the Organiser": (outsider, organiser_id),
        }
        for what, (user, row_id) in refused.items():
            with pytest.raises(ProgrammingError, match="row-level security"):
                contribute_as(user, row_id)
                pytest.fail(f"{what}: accepted")
            db.session.rollback()

        count = select(func.count()).where(StokvelContribution.cycle_id == cycle_id)
        assert db.session.scalar(count) == 1
    finally:
        db.close_session(token)


@pytest.mark.postgres
def test_only_workers_change_contributions_and_nobody_deletes(postgres_app):
    token = db.open_session()
    try:
        organiser, member = make_user(), make_user()
        stokvel, organiser_row = _stokvel(organiser)
        member_row = _member(stokvel, member)
        cycle = _cycle(stokvel, [organiser_row, member_row])
        _contribute(cycle, organiser_row)
        _contribute(cycle, member_row)
        db.session.commit()
        cycle_id = cycle.id

        for who, user in {"member": member, "Organiser": organiser}.items():
            assert _as(user, _SET_STATUS, cycle=cycle_id) == 0, f"{who} updated"
            assert _as(user, _DELETE, cycle=cycle_id) == 0, f"{who} deleted"
        db.session.commit()

        # A worker (no user bound) claims them
        assert db.session.execute(text(_SET_STATUS), {"cycle": cycle_id}).rowcount == 2
        db.session.commit()
        statuses = db.session.scalars(
            select(StokvelContribution.status).where(
                StokvelContribution.cycle_id == cycle_id
            )
        ).all()
        assert statuses == [_PROCESSING, _PROCESSING]
    finally:
        db.close_session(token)
