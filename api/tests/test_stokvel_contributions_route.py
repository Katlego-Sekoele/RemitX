"""`POST /stokvels/{id}/contributions` (R2-11, #233).

The SQLite lane covers the rules, the ledger legs and the limits. The Postgres
lane (`postgres` marker, TEST_DATABASE_URL) runs the route under row-level
security, which is what lets the contribution's token leg (Treasury Wallet ->
the stokvel's STOKVEL account) be recorded at all.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from remitx_api.app import create_app
from remitx_api.auth.dependencies import get_current_user
from remitx_api.config import TestConfig
from remitx_api.controllers import stokvel_contribution_controller
from remitx_api.controllers.stokvel_contribution_controller import (
    contribution_fee_share,
)
from remitx_api.controllers.user_controller import UserController
from remitx_api.db.rls import bound_row_security_context
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    CURRENCY_ZWL,
    TYPE_EVM_WALLET,
    TYPE_PLATFORM_FIAT,
    TYPE_PLATFORM_REVENUE,
    Account,
)
from remitx_api.models.orm.beneficiary import Beneficiary, BeneficiaryRelationship
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.models.orm.kyc_lifecycle import KYC_TIER_VERIFIED, KycStatus
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_contribution import (
    StokvelContribution,
    StokvelContributionStatus,
)
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.models.orm.stokvel_round import StokvelRound
from remitx_api.models.orm.transaction import (
    STATUS_PENDING,
    TYPE_FEE,
    TYPE_STOKVEL_CONTRIBUTION,
    Transaction,
)
from remitx_api.models.orm.user import User
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.kyc_application_repository import KycApplicationRepository
from remitx_api.repositories.stokvel_contribution_repository import (
    StokvelContributionRepository,
)
from remitx_api.repositories.user_repository import UserRepository
from remitx_api.services import exchange_rate_service, queue_service
from remitx_api.services.exchange_rate_provider import RateFetchError
from remitx_api.services.quote_service import TokenRates, token_to_fiat
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from tests.kyc_helpers import insert_application, seed_kyc_reference_data
from tests.platform_account_helpers import seed_platform_accounts

USD_ZAR = Decimal("18.50")
CONTRIBUTION = Decimal("100")  # UCTUSD
FIAT = Decimal("1850.00")  # CONTRIBUTION at USD_ZAR
# Round 0's payout fee on the 3,700.00 pool, paid to ZAR (no margin):
# 15 + 0.5% = 33.50, split between the two members.
FEE = Decimal("16.75")
TOTAL = FIAT + FEE  # what leaves the member's account
# A ZAR stokvel's rates at USD_ZAR, for pricing without the rate store.
ZAR_RATES = TokenRates(
    currency=CURRENCY_ZAR,
    units_per_token=USD_ZAR,
    token_per_unit=(Decimal("1") / USD_ZAR).quantize(Decimal("0.00000001")),
    zar_token_per_unit=(Decimal("1") / USD_ZAR).quantize(Decimal("0.00000001")),
)
_START = datetime(2026, 11, 1, tzinfo=UTC)


@dataclass
class Group:
    """A stokvel with an active two-member cycle of two rounds."""

    client: TestClient
    stokvel_id: uuid.UUID
    cycle_id: uuid.UUID
    caller: User
    caller_member_id: uuid.UUID
    other: User
    other_member_id: uuid.UUID
    enqueued: list[str]

    def contribute(self, stokvel_id: uuid.UUID | None = None):
        return self.client.post(
            f"/stokvels/{stokvel_id or self.stokvel_id}/contributions"
        )


def _in_session(fn):
    token = db.open_session()
    try:
        return fn()
    finally:
        db.close_session(token)


def _user(clerk_id: str, *, verified=True, zar_balance=Decimal("5000")) -> User:
    persisted = UserController().ensure_provisioned(
        clerk_id, lambda: f"{clerk_id}@example.com", lambda: clerk_id.title()
    )
    if verified:
        insert_application(
            persisted.id, status=KycStatus.APPROVED, tier_granted=KYC_TIER_VERIFIED
        )
    account = AccountRepository().get_user_account(persisted.id, CURRENCY_ZAR)
    account.account_balance = zar_balance
    db.session.flush()
    return persisted


def _build(app, monkeypatch, *, seed_platform: bool, caller_verified=True) -> Group:
    enqueued: list[str] = []
    monkeypatch.setattr(queue_service, "enqueue_submit_contribution", enqueued.append)
    token = db.open_session()
    try:
        seed_kyc_reference_data()
        if seed_platform:
            seed_platform_accounts()
        now = datetime.now(UTC)
        db.session.add(
            ExchangeRate(
                base_currency="USD",
                quote_currency="ZAR",
                rate=USD_ZAR,
                fetched_at=now,
                valid_until=now + timedelta(hours=1),
            )
        )
        suffix = uuid.uuid4().hex[:8]
        caller = _user(f"thandi_{suffix}", verified=caller_verified)
        other = _user(f"sipho_{suffix}")
        stokvel = Stokvel(
            organiser_user_id=caller.id,
            name="Savings club",
            currency=CURRENCY_ZAR,
            contribution_amount=CONTRIBUTION,
        )
        db.session.add(stokvel)
        db.session.flush()
        AccountRepository().create_stokvel_account(stokvel)
        members = []
        for user in (caller, other):
            member = StokvelMember(
                stokvel_id=stokvel.id,
                user_id=user.id,
                account_id=AccountRepository()
                .get_user_account(user.id, CURRENCY_ZAR)
                .account_id,
            )
            db.session.add(member)
            members.append(member)
        db.session.flush()
        cycle = StokvelCycle(
            stokvel_id=stokvel.id,
            cycle_number=1,
            status=StokvelCycleStatus.ACTIVE.value,
            total_rounds=2,
            current_round=0,
            started_at=now,
            # Open on-chain, so it takes contributions (R2-10)
            registered_at=now,
        )
        db.session.add(cycle)
        db.session.flush()
        # Round 0 pays the caller in ZAR (no FX margin), round 1 the other
        # member in ZWL (margin applies), so the fee share differs by round.
        pairs = ((caller, other, CURRENCY_ZAR), (other, caller, CURRENCY_ZWL))
        for position, (member, (user, linked, payout_currency)) in enumerate(
            zip(members, pairs, strict=True)
        ):
            beneficiary = Beneficiary(
                sender_user_id=user.id,
                linked_user_id=linked.id,
                payout_currency=payout_currency,
                relationship=BeneficiaryRelationship.PARENT.value,
            )
            db.session.add(beneficiary)
            db.session.flush()
            db.session.add(
                StokvelCycleMember(
                    cycle_id=cycle.id,
                    member_id=member.id,
                    payout_position=position,
                    payout_beneficiary_id=beneficiary.beneficiary_id,
                    payout_currency=payout_currency,
                    locked=True,
                )
            )
        for number in range(2):
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
        db.session.commit()
        ids = (stokvel.id, cycle.id, members[0].id, members[1].id)
        caller = User(id=caller.id, base_reference=caller.base_reference)
        other = User(id=other.id, base_reference=other.base_reference)
    finally:
        db.close_session(token)
    app.dependency_overrides[get_current_user] = lambda: caller
    return Group(
        client=None,  # set by the fixture
        stokvel_id=ids[0],
        cycle_id=ids[1],
        caller=caller,
        caller_member_id=ids[2],
        other=other,
        other_member_id=ids[3],
        enqueued=enqueued,
    )


@pytest.fixture
def group(monkeypatch):
    app = create_app(TestConfig)
    with TestClient(app) as client:
        built = _build(app, monkeypatch, seed_platform=True)
        built.client = client
        yield built


def _record(
    group: Group,
    member_id,
    round_,
    status=StokvelContributionStatus.PENDING,
    *,
    amount_zar=FIAT,
    created_at=None,
):
    """A contribution written directly, by default as if paid two days ago:
    before today, so it does not use up the caller's daily limit."""

    def write():
        db.session.add(
            StokvelContribution(
                cycle_id=group.cycle_id,
                round=round_,
                member_id=member_id,
                amount_token=CONTRIBUTION,
                amount_fiat=FIAT,
                amount_zar=amount_zar,
                status=status.value,
                created_at=created_at or datetime.now(UTC) - timedelta(days=2),
            )
        )
        db.session.commit()

    _in_session(write)


def _contributions(group: Group) -> list[StokvelContribution]:
    return _in_session(
        lambda: db.session.scalars(
            select(StokvelContribution)
            .where(StokvelContribution.cycle_id == group.cycle_id)
            .order_by(StokvelContribution.created_at)
        ).all()
    )


# --- Recording a contribution ------------------------------------------------


def test_a_contribution_is_a_pending_row_plus_its_pending_legs(group):
    response = group.contribute()

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["round"] == 0
    assert body["cycle_number"] == 1
    assert body["status"] == "pending"
    assert body["currency"] == "ZAR"
    assert Decimal(body["amount_token"]) == CONTRIBUTION
    assert Decimal(body["amount_fiat"]) == FIAT
    assert Decimal(body["fee_amount"]) == FEE
    assert Decimal(body["amount_zar"]) == TOTAL

    def check():
        row = db.session.get(StokvelContribution, uuid.UUID(body["contribution_id"]))
        assert row.member_id == group.caller_member_id
        assert row.amount_zar == TOTAL
        assert row.tx_id is None  # the deprecated column stays unused
        fiat = db.session.get(Transaction, row.fiat_tx_id)
        token = db.session.get(Transaction, row.token_tx_id)
        fee = db.session.get(Transaction, row.fee_tx_id)
        revenue = AccountRepository().get_platform_account(TYPE_PLATFORM_REVENUE, "ZAR")
        member_account = AccountRepository().get_user_account(
            group.caller.id, CURRENCY_ZAR
        )
        bank = AccountRepository().get_platform_account(TYPE_PLATFORM_FIAT, "ZAR")
        treasury = AccountRepository().get_platform_account(
            TYPE_EVM_WALLET, CURRENCY_TOKEN
        )
        stokvel = db.session.get(Stokvel, group.stokvel_id)
        assert (fiat.type, fiat.status) == (TYPE_STOKVEL_CONTRIBUTION, STATUS_PENDING)
        assert fiat.credit_account_id == member_account.account_id  # source
        assert fiat.debit_account_id == bank.account_id  # destination
        assert (fiat.amount, fiat.currency) == (FIAT, "ZAR")
        assert (token.type, token.status) == (TYPE_STOKVEL_CONTRIBUTION, STATUS_PENDING)
        assert token.credit_account_id == treasury.account_id
        assert token.debit_account_id == stokvel.account_id
        assert (token.amount, token.currency) == (CONTRIBUTION, CURRENCY_TOKEN)
        assert (fee.type, fee.status) == (TYPE_FEE, STATUS_PENDING)
        assert fee.credit_account_id == member_account.account_id
        assert fee.debit_account_id == revenue.account_id
        assert (fee.amount, fee.currency) == (FEE, "ZAR")
        # Nothing moves until the worker confirms: balances are untouched.
        assert member_account.account_balance == Decimal("5000")

    _in_session(check)


def test_contribution_refused_while_contract_paused(monkeypatch, group):
    monkeypatch.setattr(stokvel_contribution_controller, "is_paused", lambda: True)
    response = group.contribute()
    assert response.status_code == 503
    assert response.json()["code"] == "stokvel_paused"


def test_the_worker_task_is_queued_once_after_the_commit(group):
    response = group.contribute()

    assert group.enqueued == [response.json()["contribution_id"]]


def test_a_second_payment_to_the_open_round_is_refused(group):
    first = group.contribute()
    second = group.contribute()

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["code"] == "contribution_already_paid"
    assert len(_contributions(group)) == 1
    assert len(group.enqueued) == 1


def test_rounds_fill_in_order_like_the_contract(group):
    # Round 0 is full once both members have a contribution that has not
    # failed, so the caller's next payment goes into round 1.
    _record(group, group.caller_member_id, 0)
    _record(group, group.other_member_id, 0)

    response = group.contribute()

    assert response.status_code == 201, response.text
    assert response.json()["round"] == 1
    # Round 1 pays out in ZWL, so its fee adds the 1% margin on the pool:
    # (33.50 + 37.00) / 2.
    assert Decimal(response.json()["fee_amount"]) == Decimal("35.25")


def test_the_fee_share_rounds_up_to_the_cent():
    # Pool 3,702.00: 15 + 18.51 = 33.51, so each of two pays 16.755 -> 16.76.
    share = contribution_fee_share(
        Decimal("1851"), ZAR_RATES, member_count=2, payout_currency="ZAR"
    )

    assert share == Decimal("16.76")


def test_the_fiat_debit_uses_the_unrounded_rate():
    # A large rate, as for ZWL: its inverse rounded to 8 places
    # (0.00003846) would make 100 UCTUSD cost 2,600,104.00, not 2,600,050.00.
    rates = TokenRates(
        currency="ZWL",
        units_per_token=Decimal("26000.5"),
        token_per_unit=Decimal("0.00003846"),
        zar_token_per_unit=Decimal("0.05405405"),
    )

    assert token_to_fiat(Decimal("100"), rates) == Decimal("2600050.00")


def test_rates_are_looked_up_before_the_member_is_locked(group, monkeypatch):
    """A lookup that finds no valid rate fetches one live and commits, which
    would end the transaction and release the user lock. So every lookup
    must come before the lock, and the expired rate here forces the commit."""

    def expire():
        for rate in db.session.scalars(select(ExchangeRate)):
            rate.valid_until = datetime.now(UTC) - timedelta(minutes=1)
        db.session.commit()

    _in_session(expire)
    monkeypatch.setattr(
        "remitx_api.services.exchange_rate_provider.ExchangeRateApiProvider.get_rate",
        lambda self, base, quote: USD_ZAR,
    )
    events: list[str] = []
    real_lookup = exchange_rate_service.get_active_rate
    real_lock = UserRepository.lock

    def lookup(*args, **kwargs):
        events.append("rate")
        return real_lookup(*args, **kwargs)

    def lock(self, user_id):
        events.append("lock")
        return real_lock(self, user_id)

    monkeypatch.setattr(exchange_rate_service, "get_active_rate", lookup)
    monkeypatch.setattr(UserRepository, "lock", lock)

    response = group.contribute()

    assert response.status_code == 201, response.text
    assert events.count("lock") == 1
    assert "rate" in events
    assert "rate" not in events[events.index("lock") :]
    assert Decimal(response.json()["amount_fiat"]) == FIAT


def test_no_exchange_rate_is_unavailable_and_nothing_is_recorded(group, monkeypatch):
    def make_stale():
        for rate in db.session.scalars(select(ExchangeRate)):
            rate.fetched_at = datetime.now(UTC) - timedelta(days=30)
            rate.valid_until = datetime.now(UTC) - timedelta(days=29)
        db.session.commit()

    _in_session(make_stale)

    def fail(self, base, quote):
        raise RateFetchError("down")

    monkeypatch.setattr(
        "remitx_api.services.exchange_rate_provider.ExchangeRateApiProvider.get_rate",
        fail,
    )

    response = group.contribute()

    assert response.status_code == 503
    assert _contributions(group) == []
    assert group.enqueued == []


def test_a_lost_enqueue_is_logged_and_raised(group, monkeypatch, caplog):
    """The contribution is already committed pending; a broker failure must
    not pass quietly, as for a remittance's settlement."""

    def broker_down(contribution_id):
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(queue_service, "enqueue_submit_contribution", broker_down)

    with pytest.raises(ConnectionError):
        group.contribute()

    assert "failed to enqueue submit_contribution" in caplog.text
    [row] = _contributions(group)
    assert row.status == StokvelContributionStatus.PENDING.value


def test_a_failed_contribution_leaves_the_round_open_to_pay_again(group):
    _record(group, group.caller_member_id, 0, StokvelContributionStatus.FAILED)

    response = group.contribute()

    assert response.status_code == 201, response.text
    assert response.json()["round"] == 0


def test_with_every_round_paid_there_is_no_round_to_pay(group):
    for round_ in (0, 1):
        _record(group, group.caller_member_id, round_)
        _record(group, group.other_member_id, round_)

    response = group.contribute()

    assert response.status_code == 409
    assert response.json() == {
        "detail": "This round isn't open for contributions.",
        "code": "wrong_round",
    }


# --- Who may contribute ----------------------------------------------------


def test_an_unknown_stokvel_is_not_found(group):
    response = group.contribute(uuid.uuid4())

    assert response.status_code == 404
    assert "code" not in response.json()


def test_someone_who_is_not_a_member_gets_not_found(group):
    # As for an unknown id: on Postgres row-level security hides the stokvel
    # from them anyway (see the postgres test below).
    outsider = _in_session(lambda: _commit(_user(f"out_{uuid.uuid4().hex[:6]}")))
    group.client.app.dependency_overrides[get_current_user] = lambda: outsider

    response = group.contribute()

    assert response.status_code == 404
    assert _contributions(group) == []


def test_a_member_who_left_gets_not_found(group):
    def leave():
        db.session.get(StokvelMember, group.caller_member_id).left_at = datetime.now(
            UTC
        )
        db.session.commit()

    _in_session(leave)

    response = group.contribute()

    assert response.status_code == 404


def test_a_member_outside_the_current_cycle_is_refused(group):
    def join_late():
        user = _user(f"late_{uuid.uuid4().hex[:6]}")
        db.session.add(
            StokvelMember(
                stokvel_id=group.stokvel_id,
                user_id=user.id,
                account_id=AccountRepository()
                .get_user_account(user.id, CURRENCY_ZAR)
                .account_id,
            )
        )
        db.session.commit()
        return User(id=user.id, base_reference=user.base_reference)

    late = _in_session(join_late)
    group.client.app.dependency_overrides[get_current_user] = lambda: late

    response = group.contribute()

    assert response.status_code == 403
    assert response.json()["code"] == "not_a_member"


@pytest.mark.parametrize("status", ["forming", "closed"])
def test_without_an_active_cycle_there_is_nothing_to_pay(group, status):
    def change():
        cycle = db.session.get(StokvelCycle, group.cycle_id)
        cycle.status = status
        if status == "forming":
            cycle.started_at = None
            cycle.current_round = None
            cycle.total_rounds = None
            cycle.registered_at = None
        else:
            cycle.closed_at = datetime.now(UTC)
        db.session.commit()

    _in_session(change)

    response = group.contribute()

    assert response.status_code == 409
    assert response.json()["code"] == "cycle_not_open"


def test_a_cycle_not_yet_registered_on_chain_takes_no_contributions(group):
    """Started, but the worker's `startCycle` is not mined yet (R2-10): the
    contract has no open cycle, so the contribution would revert."""

    def unregister():
        db.session.get(StokvelCycle, group.cycle_id).registered_at = None
        db.session.commit()

    _in_session(unregister)

    response = group.contribute()

    assert response.status_code == 409
    assert response.json()["code"] == "cycle_starting"
    assert _contributions(group) == []
    assert group.enqueued == []


def test_a_former_members_unlocked_row_is_not_part_of_the_cycle(group):
    """A member who left before the cycle started keeps an unlocked row with
    no position (R2-09, R2-10). It must not count toward a full round, or
    round 0 could never fill."""

    def left_before_the_start():
        user = _user(f"left_{uuid.uuid4().hex[:6]}")
        member = StokvelMember(
            stokvel_id=group.stokvel_id,
            user_id=user.id,
            account_id=AccountRepository()
            .get_user_account(user.id, CURRENCY_ZAR)
            .account_id,
            left_at=datetime.now(UTC),
        )
        db.session.add(member)
        db.session.flush()
        db.session.add(StokvelCycleMember(cycle_id=group.cycle_id, member_id=member.id))
        db.session.commit()

    _in_session(left_before_the_start)
    _record(group, group.caller_member_id, 0)
    _record(group, group.other_member_id, 0)

    response = group.contribute()

    assert response.status_code == 201, response.text
    assert response.json()["round"] == 1


# --- Balance, standing and limits --------------------------------------------


def test_a_short_balance_is_refused_and_nothing_is_recorded(group):
    def drain():
        account = AccountRepository().get_user_account(group.caller.id, CURRENCY_ZAR)
        account.account_balance = TOTAL - Decimal("0.01")
        db.session.commit()

    _in_session(drain)

    response = group.contribute()

    assert response.status_code == 400
    assert "1,866.75" in response.json()["detail"]
    assert _contributions(group) == []
    assert group.enqueued == []


def test_a_balance_that_covers_the_contribution_but_not_the_fee_is_refused(group):
    def drain():
        account = AccountRepository().get_user_account(group.caller.id, CURRENCY_ZAR)
        account.account_balance = FIAT
        db.session.commit()

    _in_session(drain)

    response = group.contribute()

    assert response.status_code == 400
    assert _contributions(group) == []


def test_an_unverified_member_is_refused(monkeypatch):
    app = create_app(TestConfig)
    with TestClient(app) as client:
        built = _build(app, monkeypatch, seed_platform=True, caller_verified=False)
        built.client = client

        response = built.contribute()

        assert response.status_code == 403
        assert _contributions(built) == []


def test_contributions_count_toward_the_members_own_limits(group):
    first = group.contribute()
    standing = _in_session(
        lambda: KycApplicationRepository().get_standing(group.caller.id)
    )

    assert first.status_code == 201
    # The fee counts too: it leaves the member's account with the contribution.
    assert standing.daily_used_zar == TOTAL
    assert standing.monthly_used_zar == TOTAL


def test_a_contribution_over_the_daily_limit_is_refused(group):
    # The verified tier allows R3,000 a day. Round 0 (R1,850) fits; paying
    # round 1 the same day as well (another R1,850) would not.
    _record(group, group.other_member_id, 0)
    assert group.contribute().status_code == 201

    response = group.contribute()

    assert response.status_code == 400
    assert "today" in response.json()["detail"]
    assert len(_contributions(group)) == 2  # the caller's round 0 and Sipho's


def test_a_contribution_over_the_monthly_limit_is_refused(group, monkeypatch):
    # The verified tier allows R25,000 a month. The clock is fixed mid-month so
    # the earlier contribution is this month but not today, on any run date.
    now = datetime(2026, 11, 16, 10, tzinfo=UTC)
    monkeypatch.setattr(
        "remitx_api.repositories.kyc_application_repository.utcnow", lambda: now
    )
    earlier = now - timedelta(days=6)
    _record(
        group,
        group.caller_member_id,
        0,
        amount_zar=Decimal("23500"),
        created_at=earlier,
    )
    _record(group, group.other_member_id, 0, created_at=earlier)

    # Round 1 costs 1,885.25 (1,850 + a 35.25 fee share): 25,385.25 in all.
    response = group.contribute()

    assert response.status_code == 400
    assert "monthly limit" in response.json()["detail"]
    assert len(_contributions(group)) == 2  # only the two recorded above
    assert group.enqueued == []


def test_a_payment_that_slips_past_the_paid_check_is_still_refused(group, monkeypatch):
    """If two payments for the same round both pass the "already paid" read
    (the user lock prevents this; see the Postgres test below), the unique
    index stops the second, and it is refused as already paid with nothing
    left behind."""
    _record(group, group.caller_member_id, 0)
    monkeypatch.setattr(
        StokvelContributionRepository,
        "get_member_contribution",
        lambda self, cycle_id, round_, member_id: None,
    )

    response = group.contribute()

    assert response.status_code == 409
    assert response.json()["code"] == "contribution_already_paid"
    assert len(_contributions(group)) == 1
    assert group.enqueued == []

    def legs():
        return db.session.scalars(
            select(Transaction).where(Transaction.type == TYPE_STOKVEL_CONTRIBUTION)
        ).all()

    assert _in_session(legs) == []  # the pending legs rolled back too


def test_another_integrity_error_is_not_reported_as_already_paid(group, monkeypatch):
    """Only the once-per-round index means "already paid": any other
    constraint is a fault and is raised as is, not answered with a 409."""

    def broken_add(self, entity):
        raise IntegrityError("INSERT", {}, Exception("FOREIGN KEY constraint failed"))

    monkeypatch.setattr(StokvelContributionRepository, "add", broken_add)

    with pytest.raises(IntegrityError):
        group.contribute()
    assert group.enqueued == []


def test_a_round_without_a_locked_recipient_is_a_fault(group):
    # The fee depends on the recipient's payout currency, which is fixed
    # only once their row is locked: never priced on a currency that might
    # still change. Round 0's recipient row is unlocked, so the cycle (its
    # locked rows, R2-10) has nobody at position 0; the other, locked member
    # pays.
    def unlock():
        row = db.session.scalars(
            select(StokvelCycleMember).where(
                StokvelCycleMember.cycle_id == group.cycle_id,
                StokvelCycleMember.payout_position == 0,
            )
        ).one()
        row.locked = False
        db.session.commit()

    _in_session(unlock)
    group.client.app.dependency_overrides[get_current_user] = lambda: group.other

    with pytest.raises(RuntimeError, match="locked recipient"):
        group.contribute()
    assert _contributions(group) == []


def test_failed_contributions_do_not_count_toward_limits(group):
    _record(group, group.caller_member_id, 0, StokvelContributionStatus.FAILED)

    standing = _in_session(
        lambda: KycApplicationRepository().get_standing(group.caller.id)
    )

    assert standing.daily_used_zar == 0


def _commit(user: User) -> User:
    db.session.commit()
    return User(id=user.id, base_reference=user.base_reference)


# --- Row-level security (Postgres) -------------------------------------------


@pytest.mark.postgres
def test_under_row_security_the_route_records_the_token_leg(postgres_app, monkeypatch):
    """The token leg moves money between two non-USER accounts. The ledger
    policy lets a customer route record it only because the debit side is the
    STOKVEL account of a stokvel the caller belongs to."""
    with TestClient(postgres_app) as client:
        built = _build(postgres_app, monkeypatch, seed_platform=False)
        built.client = client

        response = built.contribute()

        assert response.status_code == 201, response.text
        assert len(built.enqueued) == 1


@pytest.mark.postgres
def test_two_payments_at_once_record_one_contribution(postgres_app, monkeypatch):
    """Two requests for the same round at the same moment: the user lock
    makes the second wait, then it reads the first one's row and is refused."""
    with TestClient(postgres_app) as client:
        built = _build(postgres_app, monkeypatch, seed_platform=False)
        built.client = client

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: built.contribute(), range(2)))

        assert sorted(r.status_code for r in responses) == [201, 409]
        refused = next(r for r in responses if r.status_code == 409)
        assert refused.json()["code"] == "contribution_already_paid"
        assert len(_contributions(built)) == 1
        assert len(built.enqueued) == 1


@pytest.mark.postgres
def test_under_row_security_an_outsider_gets_not_found(postgres_app, monkeypatch):
    """Row-level security hides the stokvel from someone outside it, so they
    get the same 404 as for an unknown id, as on SQLite."""
    with TestClient(postgres_app) as client:
        built = _build(postgres_app, monkeypatch, seed_platform=False)
        built.client = client
        outsider = _in_session(lambda: _commit(_user(f"out_{uuid.uuid4().hex[:6]}")))
        postgres_app.dependency_overrides[get_current_user] = lambda: outsider

        response = built.contribute()

        assert response.status_code == 404
        assert _contributions(built) == []


@pytest.mark.postgres
def test_under_row_security_a_slipped_duplicate_is_refused_as_paid(
    postgres_app, monkeypatch
):
    """Postgres names the violated constraint, so the once-per-round index
    is told apart from any other and answered as already paid."""
    with TestClient(postgres_app) as client:
        built = _build(postgres_app, monkeypatch, seed_platform=False)
        built.client = client
        _record(built, built.caller_member_id, 0)
        monkeypatch.setattr(
            StokvelContributionRepository,
            "get_member_contribution",
            lambda self, cycle_id, round_, member_id: None,
        )

        response = built.contribute()

        assert response.status_code == 409
        assert response.json()["code"] == "contribution_already_paid"


@pytest.mark.postgres
def test_row_security_lets_no_member_change_or_remove_a_stokvel_leg(
    postgres_app, monkeypatch
):
    """Members may read and record legs on their stokvel's account, but no
    member's session may update or delete one: not another member's, and not
    their own."""
    with TestClient(postgres_app) as client:
        built = _build(postgres_app, monkeypatch, seed_platform=False)
        built.client = client
        contribution_id = uuid.UUID(built.contribute().json()["contribution_id"])
        leg_id = _in_session(
            lambda: db.session.get(StokvelContribution, contribution_id).token_tx_id
        )

        def rows_changed(user: User, statement) -> int:
            def run():
                with bound_row_security_context(user.id, is_admin_route=False):
                    changed = db.session.execute(statement).rowcount
                db.session.rollback()
                return changed

            return _in_session(run)

        where = Transaction.tx_id == leg_id
        for user in (built.caller, built.other):
            assert (
                rows_changed(
                    user, update(Transaction).where(where).values(amount=Decimal("1"))
                )
                == 0
            )
            assert rows_changed(user, delete(Transaction).where(where)) == 0

        def amount():
            return db.session.get(Transaction, leg_id).amount

        assert _in_session(amount) == CONTRIBUTION


@pytest.mark.postgres
def test_row_security_refuses_a_stokvel_leg_from_a_former_member(
    postgres_app, monkeypatch
):
    """A member who has left may still read the stokvel's legs, but may
    record none."""
    with TestClient(postgres_app) as client:
        built = _build(postgres_app, monkeypatch, seed_platform=False)
        built.client = client
        contribution_id = uuid.UUID(built.contribute().json()["contribution_id"])

        def leave():
            db.session.get(StokvelMember, built.other_member_id).left_at = datetime.now(
                UTC
            )
            db.session.commit()
            contribution = db.session.get(StokvelContribution, contribution_id)
            token = db.session.get(Transaction, contribution.token_tx_id)
            return token.tx_id, token.credit_account_id, token.debit_account_id

        leg_id, treasury_id, stokvel_account_id = _in_session(leave)

        def read_then_record():
            with bound_row_security_context(built.other.id, is_admin_route=False):
                seen = (
                    db.session.scalars(
                        select(Transaction).where(Transaction.tx_id == leg_id)
                    ).first()
                    is not None
                )
                db.session.add(
                    Transaction(
                        type=TYPE_STOKVEL_CONTRIBUTION,
                        credit_account_id=treasury_id,
                        debit_account_id=stokvel_account_id,
                        amount=CONTRIBUTION,
                        currency=CURRENCY_TOKEN,
                        status=STATUS_PENDING,
                    )
                )
                with pytest.raises(Exception, match="row-level security"):
                    db.session.flush()
            db.session.rollback()
            return seen

        assert _in_session(read_then_record)


@pytest.mark.postgres
def test_row_security_lets_a_member_record_only_the_token_leg(
    postgres_app, monkeypatch
):
    """The insert policy pins both sides: a member may add only a
    stokvel_contribution leg from the Treasury Wallet into their stokvel's
    account. Any other source, or any other type, is refused."""
    with TestClient(postgres_app) as client:
        built = _build(postgres_app, monkeypatch, seed_platform=False)
        built.client = client

        def accounts():
            stokvel = db.session.get(Stokvel, built.stokvel_id)
            repo = AccountRepository()
            return (
                stokvel.account_id,
                repo.get_platform_account(TYPE_EVM_WALLET, CURRENCY_TOKEN).account_id,
                repo.get_platform_account(TYPE_PLATFORM_FIAT, "ZAR").account_id,
            )

        stokvel_account_id, treasury_id, bank_id = _in_session(accounts)

        def refused(credit_account_id, type_) -> bool:
            def run():
                with bound_row_security_context(built.caller.id, is_admin_route=False):
                    db.session.add(
                        Transaction(
                            type=type_,
                            credit_account_id=credit_account_id,
                            debit_account_id=stokvel_account_id,
                            amount=CONTRIBUTION,
                            currency=CURRENCY_TOKEN,
                            status=STATUS_PENDING,
                        )
                    )
                    try:
                        db.session.flush()
                    except Exception as exc:
                        return "row-level security" in str(exc)
                    finally:
                        db.session.rollback()
                    return False

            return _in_session(run)

        assert not refused(treasury_id, TYPE_STOKVEL_CONTRIBUTION)
        assert refused(bank_id, TYPE_STOKVEL_CONTRIBUTION)  # not the Treasury
        assert refused(treasury_id, TYPE_FEE)  # not a contribution leg


@pytest.mark.postgres
def test_row_security_shows_stokvel_legs_to_members_only(postgres_app, monkeypatch):
    with TestClient(postgres_app) as client:
        built = _build(postgres_app, monkeypatch, seed_platform=False)
        built.client = client
        contribution_id = uuid.UUID(built.contribute().json()["contribution_id"])

        def token_leg_id():
            return db.session.get(StokvelContribution, contribution_id).token_tx_id

        leg_id = _in_session(token_leg_id)
        outsider = _in_session(lambda: _commit(_user(f"out_{uuid.uuid4().hex[:6]}")))

        def visible(user: User) -> bool:
            def read():
                with bound_row_security_context(user.id, is_admin_route=False):
                    return (
                        db.session.scalars(
                            select(Transaction).where(Transaction.tx_id == leg_id)
                        ).first()
                        is not None
                    )

            return _in_session(read)

        assert visible(built.caller)
        assert visible(built.other)  # a fellow member
        assert not visible(outsider)


@pytest.mark.postgres
def test_row_security_refuses_a_stokvel_leg_from_a_non_member(postgres_app):
    """Recording a leg on a STOKVEL account still needs membership."""
    token = db.open_session()
    try:
        owner = _user(f"own_{uuid.uuid4().hex[:6]}")
        outsider = _user(f"out_{uuid.uuid4().hex[:6]}")
        stokvel = Stokvel(
            organiser_user_id=owner.id,
            name="Club",
            currency=CURRENCY_ZAR,
            contribution_amount=CONTRIBUTION,
        )
        db.session.add(stokvel)
        db.session.flush()
        stokvel_account = AccountRepository().create_stokvel_account(stokvel)
        treasury = db.session.scalars(
            select(Account).where(Account.type == TYPE_EVM_WALLET)
        ).first()
        db.session.commit()
        leg = {
            "credit_account_id": treasury.account_id,
            "debit_account_id": stokvel_account.account_id,
        }
        with bound_row_security_context(outsider.id, is_admin_route=False):
            db.session.add(
                Transaction(
                    type=TYPE_STOKVEL_CONTRIBUTION,
                    amount=CONTRIBUTION,
                    currency=CURRENCY_TOKEN,
                    status=STATUS_PENDING,
                    **leg,
                )
            )
            with pytest.raises(Exception, match="row-level security"):
                db.session.flush()
        db.session.rollback()
    finally:
        db.close_session(token)
