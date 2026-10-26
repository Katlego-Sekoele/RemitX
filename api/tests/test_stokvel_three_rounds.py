"""The brief's scenario end to end (R6-04, #269; brief §2): three members
contribute across three rounds, and each round's pool reaches the scheduled
member's beneficiary as a burnt, credited remittance. The cycle then closes.

Each piece has its own tests; this one checks they fit together. Everything a
person does goes through the API: the Organiser creates the stokvel, invites
two users, sets the payout order and starts the cycle; each member accepts,
chooses a beneficiary and contributes. Everything after that is the worker's
own tasks, run in the order the broker would deliver them: registering the
cycle, each contribution's `contribute` and its confirmation, the event sync,
the payout and its settlement (`settle_remittance` -> `burn_treasury_tokens`
-> `confirm_treasury_burn`).

Only the chain is faked. `FakeVault` keeps the contract's state as the real
one does: a round releases once it and the next round are fully paid and its
payout time has passed (D5, D12), and the last round once it is fully paid,
followed by `CycleClosed`. The schedule is already due, so each release
happens in the `contribute` that completes the next round, as on-chain. The
API and the worker share one scratch SQLite file. Beneficiaries are written
directly, as in the R2-09 tests, rather than through `POST /beneficiaries`.
"""

import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from remitx_api.app import create_app
from remitx_api.config import TestConfig
from remitx_api.controllers import (
    stokvel_admin_controller,
    stokvel_contribution_controller,
)
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    TYPE_EVM_WALLET,
    TYPE_PLATFORM_FIAT,
    Account,
)
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.models.orm.quote import Quote
from remitx_api.models.orm.remittance import Remittance
from remitx_api.models.orm.stokvel_payout import StokvelPayout
from remitx_api.models.orm.transaction import TYPE_BENEFICIARY_PAYOUT, Transaction
from remitx_api.services import queue_service
from remitx_api.services.exchange_rate_provider import use_rate_provider
from remitx_api.services.stokvel_contract_read import classify_finalise
from remitx_worker import db as worker_db, evm_service, stokvel_contract
from remitx_worker.stokvel_contract import ContractEvent, OnChainStokvel
from remitx_worker.stokvel_payouts import settle_payout
from remitx_worker.stokvel_release import release_pool
from remitx_worker.stokvel_tasks import (
    confirm_contribution,
    start_cycle,
    submit_contribution,
    sync_events,
)
from remitx_worker.tasks import (
    burn_treasury_tokens,
    confirm_treasury_burn,
    settle_remittance,
)
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from tests.platform_account_helpers import seed_platform_accounts
from tests.test_stokvel_setup_route import (
    USER_HEADER,
    Api,
    Person,
    _beneficiary,
    _person,
)
from tests.test_worker_stokvel_settle_payout import USD_ZAR, FakeRates

CONTRACT = "0x2f240705314BB79780522635eA47d20072CB8Fe1"
START_BLOCK = 100
CONTRIBUTION = Decimal("10")  # UCTUSD, small enough for three rounds' limits
MEMBERS = 3
POOL = CONTRIBUTION * MEMBERS  # UCTUSD
PAID_OUT = POOL * USD_ZAR  # each beneficiary's ZAR credit
OPENING_ZAR = Decimal("2000")  # each member's simulated cash-in
TREASURY_UCTUSD = Decimal("1000")  # test tokens in the Treasury Wallet


def _hash(prefix: str, n: int) -> str:
    return "0x" + prefix + f"{n:062x}"


class FakeVault:
    """The StokvelVault contract and its chain, as the worker sees them.

    Transactions are mined at once, one block each, and their events are
    kept for the sync to read back. `contribute` refuses a duplicate or an
    unknown member, and `finalise` a round that is not ready, as the
    contract does. `now` is the chain's clock, which a test may move on.
    `burn_tokens` is the Treasury Wallet's UCTUSD burn, which this chain
    also mines."""

    def __init__(self):
        self.now = time.time
        self.contributes: list[tuple[int, uuid.UUID]] = []
        self.block = START_BLOCK
        self.events: list[ContractEvent] = []
        self.blocks: dict[str, int] = {}
        self.contribution: int | None = None
        self.cycle = 0
        self.cycle_open = False
        self.members: list[uuid.UUID] = []
        self.payout_times: list[int] = []
        self.paid: dict[int, set[uuid.UUID]] = {}
        self.released = 0  # rounds released so far, in order
        self.burns: list[Decimal] = []
        self._sent = 0

    def _mine(self, prefix: str) -> str:
        self._sent += 1
        self.block += 1
        tx_hash = _hash(prefix, self._sent)
        self.blocks[tx_hash] = self.block
        return tx_hash

    def _emit(self, name: str, tx_hash: str, stokvel_id, **args) -> None:
        self.events.append(
            ContractEvent(
                name=name,
                args={
                    "id": evm_service.uuid_to_bytes32(stokvel_id),
                    "cycle": self.cycle,
                    **args,
                },
                tx_hash=tx_hash,
                block_number=self.blocks[tx_hash],
                log_index=sum(1 for e in self.events if e.tx_hash == tx_hash),
            )
        )

    # --- registering the stokvel and its cycle (stokvel.start_cycle) ---

    def get_stokvel(self, stokvel_id, w3=None):
        if self.contribution is None:
            return None
        return OnChainStokvel(self.contribution, self.cycle, self.cycle_open)

    def create_stokvel(self, stokvel_id, contribution, *, on_signed=None, w3=None):
        tx_hash = self._mine("c1")
        if on_signed is not None:
            on_signed(tx_hash)
        self.contribution = evm_service.to_base_units(contribution)
        return tx_hash

    def start_cycle(self, stokvel_id, member_ids, starts, deadlines, payouts, **kw):
        assert not self.cycle_open
        tx_hash = self._mine("c2")
        kw["on_signed"](tx_hash)
        self.cycle += 1
        self.cycle_open = True
        self.members = [uuid.UUID(str(member_id)) for member_id in member_ids]
        self.payout_times = list(payouts)
        self.paid = {round_: set() for round_ in range(len(self.members))}
        self.released = 0
        return tx_hash

    # --- contributions (stokvel.submit_contribution) ---

    def ensure_allowance(self, amount, w3=None):
        return None

    def contribute(self, stokvel_id, round_, member_id, *, on_signed=None, w3=None):
        member_id = uuid.UUID(str(member_id))
        self.contributes.append((round_, member_id))
        if not self.cycle_open:
            raise stokvel_contract.ContractRefused("CycleNotOpen", "")
        if member_id not in self.members:
            raise stokvel_contract.ContractRefused("NotMember", "")
        if member_id in self.paid[round_]:
            raise stokvel_contract.ContractRefused("AlreadyContributed", "")
        tx_hash = self._mine("c3")
        if on_signed is not None:
            on_signed(tx_hash)
        self.paid[round_].add(member_id)
        self._emit(
            "ContributionMade",
            tx_hash,
            stokvel_id,
            round=round_,
            memberId=evm_service.uuid_to_bytes32(member_id),
            amount=self.contribution,
        )
        # Automatic finalisation (D5, D12): every round now due, in order
        while self.cycle_open and self._finalisable(self.released):
            self._release(stokvel_id, tx_hash)
        return tx_hash

    def _finalisable(self, round_: int) -> bool:
        """`isFinalisable`: the round is fully paid, so is the next one (or
        it is the last), and its payout time has passed (D5, D12)."""
        everyone = set(self.members)
        last = round_ == len(self.members) - 1
        return (
            self.paid[round_] == everyone
            and (last or self.paid[round_ + 1] == everyone)
            and self.now() >= self.payout_times[round_]
        )

    def _release(self, stokvel_id, tx_hash: str) -> None:
        """Release the next round's pool, and close the cycle after the
        last."""
        round_ = self.released
        self._emit(
            "RoundFinalised",
            tx_hash,
            stokvel_id,
            round=round_,
            memberId=evm_service.uuid_to_bytes32(self.members[round_]),
            pool=self.contribution * len(self.members),
        )
        self.released += 1
        if self.released == len(self.members):
            self._emit("CycleClosed", tx_hash, stokvel_id)
            self.cycle_open = False

    # --- a release by hand (the admin's finalise, stokvel.release_pool) ---

    def finalise(self, stokvel_id, round_, *, on_signed=None, w3=None):
        if round_ < self.released:
            raise stokvel_contract.ContractRefused("AlreadyFinalised", "")
        if round_ > self.released or not self._finalisable(round_):
            raise stokvel_contract.ContractRefused("NotYetFinalisable", "")
        tx_hash = self._mine("f0")
        if on_signed is not None:
            on_signed(tx_hash)
        self._release(stokvel_id, tx_hash)
        return tx_hash

    def round_finalised(self, receipt, w3):
        return [
            e
            for e in self.events
            if e.tx_hash == receipt["transactionHash"] and e.name == "RoundFinalised"
        ]

    def finalise_readiness(self, stokvel_id, cycle_number, round_):
        """The API's read of `getStokvel`, `isFinalisable` and `getCycle`,
        classified by the real `classify_finalise`."""
        return classify_finalise(
            round_,
            current_cycle=self.cycle,
            cycle_open=self.cycle_open,
            asked_cycle=cycle_number,
            is_finalisable=self.cycle_open
            and round_ == self.released
            and self._finalisable(round_),
            next_to_finalise=self.released if self.cycle else None,
        )

    # --- the payout's burn (burn_treasury_tokens) ---

    def burn_tokens(self, amount, *, on_signed=None, w3=None):
        tx_hash = self._mine("b0")
        if on_signed is not None:
            on_signed(tx_hash)
        self.burns.append(amount)
        return tx_hash

    def transaction_status(self, tx_hash, w3=None):
        return evm_service.TX_PENDING

    # --- shared ---

    def wait_for_receipt(self, tx_hash, timeout=120, w3=None):
        return {
            "transactionHash": tx_hash,
            "status": 1,
            "blockNumber": self.blocks[tx_hash],
        }

    def fetch_logs(self, from_block, to_block, w3):
        return [e for e in self.events if from_block <= e.block_number <= to_block]

    def decode_log(self, log, w3):
        return log


class Broker:
    """The queue, as a list: every task the API or the worker enqueues lands
    in `messages`, and `deliver` runs them in order until none are left,
    including the ones they queue."""

    TASKS = {
        "start_cycle": start_cycle,
        "release_pool": release_pool,
        "submit_contribution": submit_contribution,
        "confirm_contribution": confirm_contribution,
        "settle_payout": settle_payout,
        "settle_remittance": settle_remittance,
        "burn_treasury_tokens": burn_treasury_tokens,
        "confirm_treasury_burn": confirm_treasury_burn,
    }

    def __init__(self, monkeypatch):
        self.messages: list[tuple[str, tuple]] = []
        for name in self.TASKS:
            monkeypatch.setattr(queue_service, f"enqueue_{name}", self._enqueuer(name))

    def _enqueuer(self, name):
        return lambda *args: self.messages.append((name, args))

    def deliver(self) -> list[tuple[str, str]]:
        outcomes = []
        while self.messages:
            name, args = self.messages.pop(0)
            outcomes.append((name, self.TASKS[name](*args)))
        return outcomes


class StokvelApi(Api):
    """The routes a member or Organiser calls, as a chosen user."""

    def _post(self, as_: Person, path: str, body=None):
        return self.client.post(path, json=body, headers={USER_HEADER: str(as_.id)})

    def create(self, as_: Person):
        return self._post(
            as_,
            "/stokvels",
            {
                "name": "Family",
                "currency": CURRENCY_ZAR,
                "contribution_amount": str(CONTRIBUTION),
            },
        )

    def invite(self, as_: Person, stokvel_id, reference: str):
        return self._post(
            as_,
            f"/stokvels/{stokvel_id}/invitations",
            {"account_reference": reference},
        )

    def accept(self, as_: Person, invitation_id):
        return self._post(as_, f"/invitations/{invitation_id}/accept")

    def start(self, as_: Person, stokvel_id, rounds):
        return self._post(as_, f"/stokvels/{stokvel_id}/cycles", {"rounds": rounds})

    def contribute(self, as_: Person, stokvel_id):
        return self._post(as_, f"/stokvels/{stokvel_id}/contributions")

    def finalise(self, as_: Person, stokvel_id, round_: int):
        """The admin's Release payout button (P5)."""
        return self._post(as_, f"/admin/stokvels/{stokvel_id}/rounds/{round_}/finalise")

    def stokvel(self, as_: Person, stokvel_id):
        return self.client.get(
            f"/stokvels/{stokvel_id}", headers={USER_HEADER: str(as_.id)}
        )


@pytest.fixture
def vault(monkeypatch):
    fake = FakeVault()
    for name in (
        "get_stokvel",
        "create_stokvel",
        "start_cycle",
        "ensure_allowance",
        "contribute",
        "fetch_logs",
        "decode_log",
        "finalise",
        "round_finalised",
    ):
        monkeypatch.setattr(stokvel_contract, name, getattr(fake, name))
    for name in ("burn_tokens", "transaction_status", "wait_for_receipt"):
        monkeypatch.setattr(evm_service, name, getattr(fake, name))
    # The sync reads the head from the client; the faked calls ignore it.
    monkeypatch.setattr(
        evm_service,
        "get_web3",
        lambda: SimpleNamespace(eth=SimpleNamespace(block_number=fake.block)),
    )
    # The API's own reads of the vault: whether it is paused, before taking
    # a contribution or a manual finalise, and whether a round is ready.
    for controller in (stokvel_contribution_controller, stokvel_admin_controller):
        monkeypatch.setattr(controller, "is_paused", lambda: False)
    monkeypatch.setattr(
        stokvel_admin_controller, "finalise_readiness", fake.finalise_readiness
    )
    monkeypatch.setenv("STOKVEL_CONTRACT_ADDRESS", CONTRACT)
    monkeypatch.setenv("STOKVEL_SYNC_START_BLOCK", str(START_BLOCK))
    monkeypatch.setenv("STOKVEL_SYNC_CONFIRMATIONS", "0")
    monkeypatch.setenv("STOKVEL_SYNC_BLOCK_RANGE", "1000")
    return fake


@pytest.fixture
def broker(monkeypatch):
    return Broker(monkeypatch)


@pytest.fixture
def rates():
    use_rate_provider(FakeRates())
    yield
    use_rate_provider(None)


@pytest.fixture
def platform(tmp_path, rates):
    """The app and the worker on one scratch database, with RemitX's platform
    accounts, test UCTUSD in the Treasury Wallet and a live USD/ZAR rate."""

    class SharedFileConfig(TestConfig):
        DATABASE_URL = f"sqlite:///{tmp_path / 'stokvel.db'}"

    with TestClient(create_app(SharedFileConfig)) as client:
        factory = sessionmaker(bind=db.engine, autoflush=False, autocommit=False)
        worker_db.configure(factory)
        token = db.open_session()
        try:
            seed_platform_accounts()
            _treasury(db.session).account_balance = TREASURY_UCTUSD
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
            db.session.commit()
        finally:
            db.close_session(token)
        try:
            yield SimpleNamespace(api=StokvelApi(client), session=factory)
        finally:
            client.app.dependency_overrides.clear()
            worker_db.configure(None)


def _treasury(session) -> Account:
    return session.scalars(
        select(Account).where(
            Account.type == TYPE_EVM_WALLET, Account.account_currency == CURRENCY_TOKEN
        )
    ).one()


def _bank_zar(session) -> Account:
    return session.scalars(
        select(Account).where(
            Account.type == TYPE_PLATFORM_FIAT, Account.account_currency == CURRENCY_ZAR
        )
    ).one()


def _zar_account(session, person: Person) -> Account:
    return session.scalars(
        select(Account).where(
            Account.user_id == person.id, Account.account_currency == CURRENCY_ZAR
        )
    ).one()


def _fund(session_factory, person: Person) -> None:
    """The member's simulated ZAR cash-in, confirmed."""
    with session_factory() as session:
        _zar_account(session, person).account_balance = OPENING_ZAR
        session.commit()


def _zar_balance(session_factory, person: Person) -> Decimal:
    with session_factory() as session:
        return _zar_account(session, person).account_balance


def _schedule(rounds: int, *, due=True) -> list[dict]:
    """Rounds a few minutes apart (brief §7.5). If `due`, every payout time
    has already passed, so each round releases as soon as the payment rule
    allows; otherwise the first is an hour away."""
    first = datetime.now(UTC) + timedelta(hours=-1 if due else 1)
    schedule = []
    for number in range(rounds):
        start = first + timedelta(minutes=5 * number)
        schedule.append(
            {
                "start_time": start.isoformat(),
                "deadline": (start + timedelta(minutes=3)).isoformat(),
                "payout_time": (start + timedelta(minutes=4)).isoformat(),
            }
        )
    return schedule


def _payouts(session_factory) -> dict[int, StokvelPayout]:
    with session_factory() as session:
        rows = session.scalars(select(StokvelPayout)).all()
        session.expunge_all()
        return {row.round: row for row in rows}


def _set_up(platform, vault, broker, *, due=True):
    """Brief §2 steps 1-2, through the API: the Organiser (Sipho) creates a
    ZAR stokvel and invites Thandi and Lerato, who accept; the payout order
    is Thandi, Sipho, Lerato, so it differs from the order they joined in;
    each member chooses a beneficiary of their own; the cycle starts on
    `_schedule(due=due)` and the worker opens it on-chain."""
    api = platform.api
    sipho, thandi, lerato = _person("sipho"), _person("thandi"), _person("lerato")
    for member in (sipho, thandi, lerato):
        _fund(platform.session, member)

    created = api.create(sipho)
    assert created.status_code == 201, created.text
    stokvel_id = created.json()["stokvel_id"]
    for invitee in (thandi, lerato):
        with platform.session() as session:
            reference = _zar_account(session, invitee).reference
        invited = api.invite(sipho, stokvel_id, reference)
        assert invited.status_code == 201, invited.text
        accepted = api.accept(invitee, invited.json()["invitation_id"])
        assert accepted.status_code == 200, accepted.text

    members = {
        uuid.UUID(m["user_id"]): uuid.UUID(m["member_id"])
        for m in api.stokvel(sipho, stokvel_id).json()["members"]
    }
    order = [thandi, sipho, lerato]
    ordered = api.payout_order(sipho, stokvel_id, [members[p.id] for p in order])
    assert ordered.status_code == 200, ordered.text

    recipients = {}
    for member in order:
        recipient = _person("gogo")
        chosen = api.beneficiary(member, stokvel_id, _beneficiary(member, recipient))
        assert chosen.status_code == 200, chosen.text
        recipients[member] = recipient

    started = api.start(sipho, stokvel_id, _schedule(MEMBERS, due=due))
    assert started.status_code in (200, 201), started.text
    assert broker.deliver() == [("start_cycle", "registered")]
    assert vault.members == [members[p.id] for p in order]

    return SimpleNamespace(
        stokvel_id=stokvel_id,
        order=order,
        member_ids={p: members[p.id] for p in order},
        recipients=recipients,
    )


def _pay_round(
    platform, broker, group, round_: int, members=None
) -> dict[Person, Decimal]:
    """Brief §2 step 3: each member (or only `members`) contributes through
    the API, and the worker sends it to the contract and confirms it. Returns
    what each was debited: the contribution in ZAR and their fee share."""
    debited = {}
    for member in group.order if members is None else members:
        response = platform.api.contribute(member, group.stokvel_id)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["round"] == round_
        debited[member] = Decimal(body["amount_fiat"]) + Decimal(body["fee_amount"])
        assert [outcome for _, outcome in broker.deliver()] == ["mined", "confirmed"]
    return debited


def _sync_and_settle(broker) -> list[tuple[str, str]]:
    """The scheduled event sync, then the payouts it queues, settled."""
    sync_events()
    return broker.deliver()


def test_three_members_three_rounds_each_payout_reaches_its_beneficiary(
    platform, vault, broker
):
    group = _set_up(platform, vault, broker)
    debited = []

    # Round 0 fully paid: nothing is released until round 1 is paid too (D5)
    debited.append(_pay_round(platform, broker, group, 0))
    assert _sync_and_settle(broker) == []
    assert _payouts(platform.session) == {}

    # Round 1 fully paid: its last contribution releases round 0 to Thandi
    debited.append(_pay_round(platform, broker, group, 1))
    settled = _sync_and_settle(broker)
    assert [name for name, _ in settled] == [
        "settle_payout",
        "settle_remittance",
        "burn_treasury_tokens",
        "confirm_treasury_burn",
    ]
    assert sorted(_payouts(platform.session)) == [0]

    # Round 2 fully paid: rounds 1 and 2 release together and the cycle closes
    debited.append(_pay_round(platform, broker, group, 2))
    settled = _sync_and_settle(broker)
    assert [name for name, _ in settled].count("confirm_treasury_burn") == 2
    payouts = _payouts(platform.session)
    assert sorted(payouts) == [0, 1, 2]
    assert not vault.cycle_open

    # Each round paid the scheduled member's own beneficiary, exactly once,
    # with the burn hash, the credit and the remittance reference together
    # (brief §7.2)
    assert vault.burns == [POOL] * MEMBERS
    with platform.session() as session:
        for round_, member in enumerate(group.order):
            payout = payouts[round_]
            assert payout.member_id == group.member_ids[member]
            assert payout.release_status == "released"
            assert payout.remittance_status == "confirmed"
            assert payout.burn_tx_hash in vault.blocks
            remittance = session.get(Remittance, payout.remittance_id)
            assert remittance.quote_id == payout.quote_id
            quote = session.get(Quote, payout.quote_id)
            recipient = group.recipients[member]
            assert quote.beneficiary_user_id == recipient.id
            credits = session.scalars(
                select(Transaction).where(
                    Transaction.quote_id == payout.quote_id,
                    Transaction.type == TYPE_BENEFICIARY_PAYOUT,
                )
            ).all()
            assert [(c.amount, c.status) for c in credits] == [(PAID_OUT, "confirmed")]
            assert _zar_balance(platform.session, recipient) == PAID_OUT
        assert session.scalar(select(func.count()).select_from(Remittance)) == MEMBERS

        # The pool left the stokvel's account and was burnt from the Treasury
        # Wallet; RemitX's bank took in the fiat and paid it out again.
        assert _treasury(session).account_balance == TREASURY_UCTUSD - POOL * MEMBERS
        assert _bank_zar(session).account_balance == 0

    # Each member was debited their three contributions and fee shares, once
    for member in group.order:
        spent = sum(round_[member] for round_ in debited)
        assert _zar_balance(platform.session, member) == OPENING_ZAR - spent

    # Brief §2 step 6: the member screen shows each round's payout status,
    # hashes and remittance reference. The worker opened cycle 2 as cycle 1
    # closed (R2-15, #237), so the closed cycle is `previous_cycle`.
    screen = platform.api.stokvel(group.order[0], group.stokvel_id).json()
    assert (screen["cycle"]["cycle_number"], screen["cycle"]["status"]) == (
        2,
        "forming",
    )
    closed = screen["previous_cycle"]
    assert (closed["cycle_number"], closed["status"]) == (1, "closed")
    rounds = closed["rounds"]
    assert [r["recipient_member_id"] for r in rounds] == [
        str(group.member_ids[member]) for member in group.order
    ]
    for shown in rounds:
        payout = payouts[shown["round"]]
        assert shown["release_status"] == "released"
        assert shown["remittance_status"] == "confirmed"
        assert shown["remittance_id"] == str(payout.remittance_id)
        assert shown["burn_tx_hash"] == payout.burn_tx_hash
        assert shown["release_tx_hash"] == payout.release_tx_hash
