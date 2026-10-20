"""Stokvel payout model tests: constraints on SQLite; the scheduled-member
trigger, row-level security and the migration on Postgres (the `postgres`
lane, TEST_DATABASE_URL)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.db.rls import bound_row_security_context
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    TYPE_EVM_WALLET,
    Account,
)
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_cycle import StokvelCycle
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.models.orm.stokvel_payout import (
    StokvelPayout,
    StokvelPayoutReleaseStatus,
)
from remitx_api.models.orm.stokvel_round import StokvelRound
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    TYPE_STOKVEL_POOL_RELEASE,
    Transaction,
    TransactionStatus,
)
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.stokvel_payout_repository import (
    StokvelPayoutRepository,
)
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from tests.kyc_helpers import make_user
from tests.postgres_helpers import downgrade, migrate
from tests.send_helpers import record_transfer

_START = datetime(2026, 11, 1, tzinfo=UTC)
_RELEASED = StokvelPayoutReleaseStatus.RELEASED.value
_PROCESSING = StokvelPayoutReleaseStatus.PROCESSING.value
_FAILED = StokvelPayoutReleaseStatus.FAILED.value
# The migration before this one
_BEFORE_PAYOUTS = "e09d8fb367b5"


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


def _cycle(*users) -> tuple[Stokvel, StokvelCycle, list[StokvelMember]]:
    """A forming cycle of a new stokvel organised by the first user. Each user
    is a member, paid in their own round: the i-th by round i."""
    stokvel = Stokvel(
        organiser_user_id=users[0].id,
        name="Savings club",
        currency=CURRENCY_ZAR,
        contribution_amount=Decimal("500"),
    )
    db.session.add(stokvel)
    db.session.flush()
    cycle = StokvelCycle(stokvel_id=stokvel.id, cycle_number=1)
    db.session.add(cycle)
    db.session.flush()
    members = []
    for position, user in enumerate(users):
        member = _member(stokvel, user)
        start = _START + timedelta(weeks=position)
        db.session.add_all(
            [
                StokvelCycleMember(
                    cycle_id=cycle.id, member_id=member.id, payout_position=position
                ),
                StokvelRound(
                    cycle_id=cycle.id,
                    round=position,
                    start_time=start,
                    deadline=start + timedelta(days=1),
                    payout_time=start + timedelta(days=2),
                ),
            ]
        )
        members.append(member)
    db.session.flush()
    return stokvel, cycle, members


def _payout(cycle, round_, member, **columns) -> StokvelPayout:
    payout = StokvelPayout(
        cycle_id=cycle.id, round=round_, member_id=member.id, **columns
    )
    db.session.add(payout)
    db.session.flush()
    return payout


def _release_leg(stokvel) -> Transaction:
    """The pool release's ledger leg: `STOKVEL` → Treasury Wallet (R2-11)."""
    accounts = AccountRepository()
    stokvel_account = accounts.get_stokvel_account(
        stokvel.id
    ) or accounts.create_stokvel_account(stokvel)
    treasury = accounts.get_platform_account(TYPE_EVM_WALLET, CURRENCY_TOKEN)
    if treasury is None:
        # Seeded by migration on Postgres; SQLite's schema has no seed rows.
        treasury = Account(
            user_id=None,
            type=TYPE_EVM_WALLET,
            account_currency=CURRENCY_TOKEN,
            label="payout-test treasury",
        )
        db.session.add(treasury)
        db.session.flush()
    leg = Transaction(
        type=TYPE_STOKVEL_POOL_RELEASE,
        credit_account_id=stokvel_account.account_id,
        debit_account_id=treasury.account_id,
        amount=Decimal("1000"),
        currency=CURRENCY_TOKEN,
        status=STATUS_CONFIRMED,
    )
    db.session.add(leg)
    db.session.flush()
    return leg


def _rejected(write) -> None:
    with pytest.raises(IntegrityError):
        write()
    db.session.rollback()


def _released(leg, **columns) -> dict:
    """A released payout's columns, booked by `leg`."""
    return {
        "release_status": _RELEASED,
        "release_tx_hash": "0xrelease",
        "release_block_number": 9072949,
        "release_tx_id": leg.tx_id,
        "released_at": datetime.now(UTC),
        **columns,
    }


def _without(columns: dict, name: str) -> dict:
    return {key: value for key, value in columns.items() if key != name}


_TOUCH = (
    "UPDATE stokvel_payouts SET release_status = 'processing' WHERE cycle_id = :cycle"
)
_DELETE = "DELETE FROM stokvel_payouts WHERE cycle_id = :cycle"


def _as(user, sql, **params) -> int:
    """Run `sql` as `user` on a customer route; the number of rows it hit."""
    with bound_row_security_context(user.id, is_admin_route=False):
        return db.session.execute(text(sql), params).rowcount


def _count(cycle_id) -> int:
    """The cycle's payouts, as a worker sees them."""
    return db.session.scalar(
        select(func.count())
        .select_from(StokvelPayout)
        .where(StokvelPayout.cycle_id == cycle_id)
    )


def test_a_new_payout_is_pending_on_both_steps(app_context):
    _, cycle, [first, _] = _cycle(make_user(), make_user())

    payout = _payout(cycle, 0, first)
    db.session.commit()

    assert payout.release_status == StokvelPayoutReleaseStatus.PENDING.value
    assert payout.remittance_status == TransactionStatus.PENDING.value
    assert payout.quote_id is payout.remittance_id is payout.burn_tx_hash is None
    assert payout.release_tx_id is payout.release_block_number is None
    assert payout.released_at is None


def test_a_round_is_paid_out_once(app_context):
    _, cycle, [first, _] = _cycle(make_user(), make_user())
    _payout(cycle, 0, first)
    db.session.commit()

    _rejected(lambda: _payout(cycle, 0, first))

    assert _count(cycle.id) == 1


def test_a_payout_is_released_then_remitted(app_context):
    stokvel, cycle, [first, second] = _cycle(make_user(), make_user())
    later = _payout(cycle, 1, second)
    payout = _payout(cycle, 0, first)
    db.session.commit()
    created = payout.updated_at

    # The release (R3-04), then the stokvel's remittance (R3-05, R3-06)
    leg = _release_leg(stokvel)
    for name, value in _released(leg).items():
        setattr(payout, name, value)
    payout.remittance_status = TransactionStatus.PROCESSING.value
    remittance = record_transfer(stokvel, make_user(), sender_amount=Decimal("1000"))
    payout.quote_id = remittance.quote_id
    payout.remittance_id = remittance.remittance_id
    payout.burn_tx_hash = "0xburn"
    payout.remittance_status = TransactionStatus.CONFIRMED.value
    db.session.commit()

    repo = StokvelPayoutRepository()
    assert repo.get_round_payout(cycle.id, 0).remittance_id == remittance.remittance_id
    assert repo.get_round_payout(cycle.id, 0).release_tx_id == leg.tx_id
    assert repo.get_round_payout(cycle.id, 2) is None
    assert [row.id for row in repo.get_cycle_payouts(cycle.id)] == [
        payout.id,
        later.id,
    ]
    assert payout.updated_at > created


@pytest.mark.parametrize(
    "columns",
    [
        pytest.param(
            lambda leg: {"release_status": "paid"}, id="unknown release status"
        ),
        pytest.param(
            lambda leg: _released(leg, remittance_status="credited"),
            id="unknown remittance status",
        ),
        pytest.param(
            lambda leg: _without(_released(leg), "release_tx_hash"),
            id="released without a hash",
        ),
        pytest.param(
            lambda leg: _without(_released(leg), "release_block_number"),
            id="released without a block",
        ),
        pytest.param(
            lambda leg: _without(_released(leg), "release_tx_id"),
            id="released without its ledger leg",
        ),
        pytest.param(
            lambda leg: _without(_released(leg), "released_at"),
            id="released without released_at",
        ),
        pytest.param(
            lambda leg: {"release_status": _PROCESSING, "released_at": _START},
            id="released_at before the release",
        ),
        pytest.param(
            lambda leg: {"release_status": _FAILED, "released_at": _START},
            id="released_at on a failed release",
        ),
        pytest.param(
            lambda leg: {"release_tx_hash": "0xrelease"},
            id="pending with a release hash",
        ),
        pytest.param(
            lambda leg: {"release_block_number": 1},
            id="pending with a release block",
        ),
        pytest.param(
            lambda leg: {"release_status": _PROCESSING, "release_block_number": 1},
            id="a block without a hash",
        ),
        pytest.param(
            lambda leg: _released(leg, release_block_number=-1),
            id="negative block",
        ),
        pytest.param(
            lambda leg: {"remittance_status": "processing"},
            id="remittance before the release",
        ),
        pytest.param(
            lambda leg: {"release_status": _FAILED, "remittance_status": "failed"},
            id="remittance failed before the release",
        ),
        pytest.param(
            lambda leg: _released(leg, remittance_status="confirmed"),
            id="confirmed without a burn hash",
        ),
    ],
)
def test_a_payouts_statuses_match_its_columns(app_context, columns):
    stokvel, cycle, [first, _] = _cycle(make_user(), make_user())
    leg = _release_leg(stokvel)
    db.session.commit()

    _rejected(lambda: _payout(cycle, 0, first, **columns(leg)))


def test_a_failed_release_is_retried_on_the_same_row(app_context):
    stokvel, cycle, [first, _] = _cycle(make_user(), make_user())
    payout = _payout(cycle, 0, first)
    db.session.commit()

    # The hash is stored before the send, so a claimed or failed release may
    # have one; the retry replaces it
    payout.release_status = _PROCESSING
    payout.release_tx_hash = "0xfirst"
    db.session.commit()
    payout.release_status = _FAILED
    db.session.commit()
    payout.release_status = _PROCESSING
    payout.release_tx_hash = "0xsecond"
    db.session.commit()
    for name, value in _released(
        _release_leg(stokvel), release_tx_hash="0xsecond"
    ).items():
        setattr(payout, name, value)
    db.session.commit()

    assert _count(cycle.id) == 1
    assert payout.release_tx_hash == "0xsecond"


def test_two_payouts_never_share_a_leg_burn_quote_or_remittance(app_context):
    stokvel, cycle, [first, second] = _cycle(make_user(), make_user())
    leg = _release_leg(stokvel)
    remittance = record_transfer(stokvel, make_user(), sender_amount=Decimal("1000"))
    taken = _released(
        leg,
        remittance_status=TransactionStatus.CONFIRMED.value,
        quote_id=remittance.quote_id,
        remittance_id=remittance.remittance_id,
        burn_tx_hash="0xburn",
    )
    _payout(cycle, 0, first, **taken)
    db.session.commit()

    # Round 1's payout, valid except that it reuses one of round 0's values
    other_leg = _release_leg(stokvel)
    other = record_transfer(stokvel, make_user(), sender_amount=Decimal("1000"))
    fresh = _released(
        other_leg,
        release_tx_hash="0xrelease-1",
        remittance_status=TransactionStatus.CONFIRMED.value,
        quote_id=other.quote_id,
        remittance_id=other.remittance_id,
        burn_tx_hash="0xburn-1",
    )
    db.session.commit()
    for name in (
        "release_tx_id",
        "quote_id",
        "remittance_id",
        "burn_tx_hash",
    ):
        with pytest.raises(IntegrityError):
            _payout(cycle, 1, second, **{**fresh, name: taken[name]})
            pytest.fail(f"{name}: shared")
        db.session.rollback()

    _payout(cycle, 1, second, **fresh)
    db.session.commit()
    assert _count(cycle.id) == 2


def test_rounds_released_in_one_transaction_share_its_hash(app_context):
    """One `contribute` releases every round that has become due (the
    contract's `_releaseDue`): with rounds left unfinalised after their
    payout time, a late final payment releases them all in one transaction,
    and every payout carries its hash (R3-04)."""
    stokvel, cycle, members = _cycle(make_user(), make_user(), make_user())
    for round_, member in enumerate(members):
        _payout(
            cycle,
            round_,
            member,
            **_released(_release_leg(stokvel), release_tx_hash="0xall"),
        )
    db.session.commit()

    assert _count(cycle.id) == 3


def test_a_payouts_references_follow_its_steps(app_context):
    stokvel, cycle, [first, _] = _cycle(make_user(), make_user())
    remittance = record_transfer(stokvel, make_user(), sender_amount=Decimal("1000"))
    leg = _release_leg(stokvel)
    db.session.commit()
    quote_id, remittance_id = remittance.quote_id, remittance.remittance_id

    refused = {
        "a quote before the release": {"quote_id": quote_id},
        "a remittance without its quote": _released(leg, remittance_id=remittance_id),
        "a burn hash without a remittance": _released(
            leg, quote_id=quote_id, burn_tx_hash="0xburn"
        ),
    }
    for what, columns in refused.items():
        with pytest.raises(IntegrityError):
            _payout(cycle, 0, first, **columns)
            pytest.fail(f"{what}: accepted")
        db.session.rollback()
    assert _count(cycle.id) == 0


def test_a_payout_needs_its_round_and_a_member_of_the_cycle(app_context):
    _, cycle, [first, _] = _cycle(make_user(), make_user())
    _, _, [outsider] = _cycle(make_user())
    db.session.commit()

    _rejected(lambda: _payout(cycle, 2, first))
    _rejected(lambda: _payout(cycle, 0, outsider))
    assert _count(cycle.id) == 0


@pytest.mark.postgres
@pytest.mark.parametrize(
    "function",
    ["stokvel_payout_member_is_scheduled", "stokvel_cycle_member_position_is_paid"],
)
def test_the_trigger_functions_are_security_definer(postgres_app, function):
    token = db.open_session()
    try:
        security_definer, settings = db.session.execute(
            text("SELECT prosecdef, proconfig FROM pg_proc WHERE proname = :name"),
            {"name": function},
        ).one()

        assert security_definer
        assert settings == ["search_path=pg_catalog, public, pg_temp"]
    finally:
        db.close_session(token)


@pytest.mark.postgres
def test_a_payout_pays_the_member_the_round_is_for(postgres_app):
    token = db.open_session()
    try:
        stokvel, cycle, [first, second] = _cycle(make_user(), make_user())
        unplaced = _member(stokvel, make_user())
        db.session.add(StokvelCycleMember(cycle_id=cycle.id, member_id=unplaced.id))
        payout = _payout(cycle, 0, first)
        db.session.commit()
        params = {
            "id": payout.id,
            "cycle": cycle.id,
            "first": first.id,
            "second": second.id,
            "unplaced": unplaced.id,
        }

        refused = {
            "round 1 to the first member": (
                "INSERT INTO stokvel_payouts (id, cycle_id, round, member_id,"
                " created_at, updated_at) VALUES (gen_random_uuid(), :cycle, 1,"
                " :first, now(), now())"
            ),
            "round 0 moved to the second member": (
                "UPDATE stokvel_payouts SET member_id = :second WHERE id = :id"
            ),
            "the first member's payout moved to round 1": (
                "UPDATE stokvel_payouts SET round = 1 WHERE id = :id"
            ),
            "round 1 to a member with no place in the order": (
                "INSERT INTO stokvel_payouts (id, cycle_id, round, member_id,"
                " created_at, updated_at) VALUES (gen_random_uuid(), :cycle, 1,"
                " :unplaced, now(), now())"
            ),
        }
        for what, sql in refused.items():
            with pytest.raises(IntegrityError, match="not the one this round pays"):
                db.session.execute(text(sql), params)
                pytest.fail(f"{what}: accepted")
            db.session.rollback()

        assert [
            (row.round, row.member_id)
            for row in StokvelPayoutRepository().get_cycle_payouts(params["cycle"])
        ] == [(0, params["first"])]
    finally:
        db.close_session(token)


@pytest.mark.postgres
def test_a_paid_members_position_cannot_move(postgres_app):
    token = db.open_session()
    try:
        _, cycle, [first, second] = _cycle(make_user(), make_user())
        _payout(cycle, 0, first)
        db.session.commit()
        params = {"cycle": cycle.id, "first": first.id, "second": second.id}
        move = (
            "UPDATE stokvel_cycle_members SET payout_position = :position"
            " WHERE cycle_id = :cycle AND member_id = :member"
        )

        for position in (2, None):
            with pytest.raises(
                IntegrityError, match="already has a payout for their round"
            ):
                db.session.execute(
                    text(move), {**params, "position": position, "member": first.id}
                )
                pytest.fail(f"moving the paid member to {position}: accepted")
            db.session.rollback()

        # A member with no payout yet can still move.
        db.session.execute(text(move), {**params, "position": 2, "member": second.id})
        db.session.commit()

        positions = dict(
            db.session.execute(
                text(
                    "SELECT member_id, payout_position FROM stokvel_cycle_members"
                    " WHERE cycle_id = :cycle"
                ),
                params,
            ).all()
        )
        assert positions == {first.id: 0, second.id: 2}
    finally:
        db.close_session(token)


@pytest.mark.postgres
def test_row_security_lets_members_read_and_only_workers_write(postgres_app):
    token = db.open_session()
    try:
        organiser, member, former, outsider = (make_user() for _ in range(4))
        stokvel, cycle, [organiser_row, member_row] = _cycle(organiser, member)
        _member(stokvel, former, left_at=datetime.now(UTC))
        _, other_cycle, [outsider_row] = _cycle(outsider)
        _payout(cycle, 0, organiser_row)
        _payout(other_cycle, 0, outsider_row)
        db.session.commit()
        ours = (cycle.id, other_cycle.id)
        cycle_id, member_row_id = cycle.id, member_row.id

        def visible(user, *, admin=False) -> int:
            with bound_row_security_context(user.id, is_admin_route=admin):
                return len(
                    db.session.scalars(
                        select(StokvelPayout).where(StokvelPayout.cycle_id.in_(ours))
                    ).all()
                )

        # Each customer sees their own stokvel's payout, not the other's
        customers = {
            "organiser": organiser,
            "member": member,
            "former member": former,
            "outsider": outsider,
        }
        for who, user in customers.items():
            assert visible(user) == 1, who
        assert visible(outsider, admin=True) == 2

        # Not even the Organiser or the member being paid writes a payout
        for who, user in {"Organiser": organiser, "member": member}.items():
            with bound_row_security_context(user.id, is_admin_route=False):
                with pytest.raises(ProgrammingError, match="row-level security"):
                    _payout(
                        db.session.get(StokvelCycle, cycle_id),
                        1,
                        db.session.get(StokvelMember, member_row_id),
                    )
                    pytest.fail(f"{who} inserted a payout")
            db.session.rollback()
            assert _as(user, _TOUCH, cycle=cycle_id) == 0, f"{who} updated"
            assert _as(user, _DELETE, cycle=cycle_id) == 0, f"{who} deleted"
            db.session.commit()

        # The release task (a worker: no user id) writes it
        _payout(
            db.session.get(StokvelCycle, cycle_id),
            1,
            db.session.get(StokvelMember, member_row_id),
            release_status=StokvelPayoutReleaseStatus.PROCESSING.value,
        )
        db.session.commit()

        # So does an admin route (the staff fallback), but it deletes nothing
        with bound_row_security_context(outsider.id, is_admin_route=True):
            touched = db.session.execute(
                text(
                    "UPDATE stokvel_payouts SET release_status = 'failed'"
                    " WHERE cycle_id = :cycle AND round = 1"
                ),
                {"cycle": cycle_id},
            ).rowcount
            deleted = db.session.execute(text(_DELETE), {"cycle": cycle_id}).rowcount
        db.session.commit()
        assert (touched, deleted) == (1, 0)

        assert [
            row.release_status
            for row in StokvelPayoutRepository().get_cycle_payouts(cycle_id)
        ] == ["pending", "failed"]
    finally:
        db.close_session(token)


@pytest.mark.postgres
def test_the_payouts_migration_rolls_back_and_reapplies(empty_postgres_url):
    migrate(empty_postgres_url)
    downgrade(empty_postgres_url, _BEFORE_PAYOUTS)
    engine = create_engine(empty_postgres_url)
    try:
        with engine.connect() as connection:
            table = connection.scalar(text("SELECT to_regclass('stokvel_payouts')"))
            trigger = connection.scalar(
                text(
                    "SELECT count(*) FROM pg_proc WHERE proname IN"
                    " ('stokvel_payout_member_is_scheduled',"
                    " 'stokvel_cycle_member_position_is_paid')"
                )
            )
    finally:
        engine.dispose()

    assert table is None
    assert trigger == 0
    migrate(empty_postgres_url)
