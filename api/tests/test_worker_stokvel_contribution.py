"""The contribution worker tasks (R2-12, #234): `stokvel.submit_contribution`
and `stokvel.confirm_contribution`.

Same conventions as test_worker_burn_treasury_tokens.py: the tasks are called
directly against a scratch SQLite file, with no broker. The chain is faked
(`stokvel_contract.ensure_allowance` and `contribute`, and
`evm_service.wait_for_receipt`), and the `confirm_contribution` enqueue is
captured, so `submit_contribution`'s tests assert on what it claims, the hash
it stores and what it hands on; `confirm_contribution` is then called with
that, as a worker would.

The ticket's two "done when" cases are here: a reverted transaction never
shows as paid, and a replayed message does not pay twice.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from remitx_api.extensions import Base, build_engine
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    TYPE_EVM_WALLET,
    TYPE_PLATFORM_FIAT,
    TYPE_PLATFORM_REVENUE,
    TYPE_STOKVEL,
    TYPE_USER,
    Account,
)
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_contribution import StokvelContribution
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.models.orm.stokvel_round import StokvelRound
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    TYPE_FEE,
    TYPE_STOKVEL_CONTRIBUTION,
    Transaction,
)
from remitx_api.models.orm.user import User
from remitx_api.services import queue_service
from remitx_worker import db as worker_db, evm_service, stokvel_contract, stokvel_tasks
from remitx_worker.celery_app import celery
from remitx_worker.stokvel_tasks import confirm_contribution, submit_contribution
from sqlalchemy.orm import sessionmaker
from web3.exceptions import ContractCustomError, TimeExhausted

TX_HASH = "0x" + "c0" * 32
BLOCK = 77
CONTRIBUTION = Decimal("100")  # UCTUSD
FIAT = Decimal("1850.00")
FEE = Decimal("16.75")
W3 = object()  # what the tasks pass around as their web3 client


@pytest.fixture
def session_factory(tmp_path, monkeypatch):
    engine = build_engine(f"sqlite:///{tmp_path / 'worker.db'}")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    worker_db.configure(factory)
    # The tasks ask for a client once and hand it to the faked calls; nothing
    # here may reach a real RPC.
    monkeypatch.setattr(evm_service, "get_web3", lambda: W3)
    yield factory
    worker_db.configure(None)


@pytest.fixture
def enqueued(monkeypatch):
    calls = []
    monkeypatch.setattr(
        stokvel_tasks.queue_service,
        "enqueue_confirm_contribution",
        lambda *args: calls.append(args),
    )
    return calls


class FakeChain:
    """`stokvel_contract.ensure_allowance` / `contribute` and
    `evm_service.wait_for_receipt`, without a chain.

    `contribute` behaves like the real one: the hash goes to `on_signed`
    before the "send", and nothing is sent if that raises. `before_signing` is
    a list of exceptions raised by successive calls before signing (then they
    sign normally); `after_signing` an exception raised after `on_signed`;
    `receipt` an exception every wait raises."""

    def __init__(self):
        self.allowances = []
        self.contributes = []
        self.sent = []
        self.waits = []
        self.before_signing: list[BaseException] = []
        self.before_on_signed = None
        self.after_signing: list[BaseException] = []
        self.receipt = None

    def ensure_allowance(self, amount, w3=None):
        assert w3 is W3
        self.allowances.append(amount)

    def contribute(self, stokvel_id, round_, member_id, *, on_signed=None, w3=None):
        assert w3 is W3
        self.contributes.append((stokvel_id, round_, member_id))
        if self.before_signing:
            raise self.before_signing.pop(0)
        if self.before_on_signed is not None:
            self.before_on_signed()
        if on_signed is not None:
            on_signed(TX_HASH)
        if self.after_signing:
            raise self.after_signing.pop(0)
        self.sent.append(TX_HASH)
        return TX_HASH

    def wait_for_receipt(self, tx_hash, timeout=120, w3=None):
        self.waits.append(tx_hash)
        if isinstance(self.receipt, BaseException):
            raise self.receipt
        return {"transactionHash": tx_hash, "status": 1, "blockNumber": BLOCK}


@pytest.fixture
def chain(monkeypatch):
    fake = FakeChain()
    monkeypatch.setattr(stokvel_contract, "ensure_allowance", fake.ensure_allowance)
    monkeypatch.setattr(stokvel_contract, "contribute", fake.contribute)
    monkeypatch.setattr(evm_service, "wait_for_receipt", fake.wait_for_receipt)
    return fake


def _user(session) -> uuid.UUID:
    user = User(id=uuid.uuid4(), clerk_user_id=f"user_{uuid.uuid4()}")
    user.base_reference = f"wrk{user.id.int}"
    session.add(user)
    session.flush()
    return user.id


def _account(session, *, type_, currency, balance="0", user_id=None) -> uuid.UUID:
    account = Account(
        account_id=uuid.uuid4(),
        user_id=user_id,
        type=type_,
        reference=f"{uuid.uuid4()}-{currency}" if type_ == TYPE_USER else None,
        account_currency=currency,
        account_balance=Decimal(balance),
        label=f"{type_} {currency} {uuid.uuid4().hex[:6]}",
    )
    session.add(account)
    session.flush()
    return account.account_id


def _leg(session, *, type_, source, destination, amount, currency) -> uuid.UUID:
    leg = Transaction(
        tx_id=uuid.uuid4(),
        type=type_,
        credit_account_id=source,
        debit_account_id=destination,
        amount=amount,
        currency=currency,
        status=STATUS_PENDING,
    )
    session.add(leg)
    session.flush()
    return leg.tx_id


@pytest.fixture
def pending(session_factory):
    """A pending round-0 contribution with its three pending legs, as
    `POST /stokvels/{id}/contributions` writes it."""
    now = datetime.now(UTC)
    with session_factory() as session:
        user_id = _user(session)
        member_account = _account(
            session,
            type_=TYPE_USER,
            currency=CURRENCY_ZAR,
            balance="5000",
            user_id=user_id,
        )
        bank = _account(session, type_=TYPE_PLATFORM_FIAT, currency=CURRENCY_ZAR)
        revenue = _account(session, type_=TYPE_PLATFORM_REVENUE, currency=CURRENCY_ZAR)
        treasury = _account(
            session, type_=TYPE_EVM_WALLET, currency=CURRENCY_TOKEN, balance="1000"
        )
        stokvel_account = _account(session, type_=TYPE_STOKVEL, currency=CURRENCY_TOKEN)
        stokvel = Stokvel(
            organiser_user_id=user_id,
            name="Savings club",
            currency=CURRENCY_ZAR,
            contribution_amount=CONTRIBUTION,
            account_id=stokvel_account,
        )
        session.add(stokvel)
        session.flush()
        member = StokvelMember(
            stokvel_id=stokvel.id, user_id=user_id, account_id=member_account
        )
        session.add(member)
        session.flush()
        cycle = StokvelCycle(
            stokvel_id=stokvel.id,
            cycle_number=1,
            status=StokvelCycleStatus.ACTIVE.value,
            total_rounds=2,
            current_round=0,
            started_at=now,
        )
        session.add(cycle)
        session.flush()
        other_user = _user(session)
        other = StokvelMember(
            stokvel_id=stokvel.id,
            user_id=other_user,
            account_id=_account(
                session, type_=TYPE_USER, currency=CURRENCY_ZAR, user_id=other_user
            ),
        )
        session.add(other)
        session.flush()
        for position, row in enumerate((member, other)):
            session.add(
                StokvelCycleMember(
                    cycle_id=cycle.id, member_id=row.id, payout_position=position
                )
            )
            session.add(
                StokvelRound(
                    cycle_id=cycle.id,
                    round=position,
                    start_time=now,
                    deadline=now + timedelta(days=1),
                    payout_time=now + timedelta(days=2),
                )
            )
        session.flush()
        contribution = StokvelContribution(
            cycle_id=cycle.id,
            round=0,
            member_id=member.id,
            amount_token=CONTRIBUTION,
            amount_fiat=FIAT,
            amount_zar=FIAT + FEE,
            fiat_tx_id=_leg(
                session,
                type_=TYPE_STOKVEL_CONTRIBUTION,
                source=member_account,
                destination=bank,
                amount=FIAT,
                currency=CURRENCY_ZAR,
            ),
            token_tx_id=_leg(
                session,
                type_=TYPE_STOKVEL_CONTRIBUTION,
                source=treasury,
                destination=stokvel_account,
                amount=CONTRIBUTION,
                currency=CURRENCY_TOKEN,
            ),
            fee_tx_id=_leg(
                session,
                type_=TYPE_FEE,
                source=member_account,
                destination=revenue,
                amount=FEE,
                currency=CURRENCY_ZAR,
            ),
        )
        session.add(contribution)
        session.commit()
        return {
            "id": str(contribution.id),
            "stokvel_id": stokvel.id,
            "member_id": member.id,
            "legs": [
                contribution.fiat_tx_id,
                contribution.token_tx_id,
                contribution.fee_tx_id,
            ],
            "accounts": {
                "member": member_account,
                "bank": bank,
                "revenue": revenue,
                "treasury": treasury,
                "stokvel": stokvel_account,
            },
        }


def _row(factory, contribution_id) -> StokvelContribution:
    with factory() as session:
        row = session.get(StokvelContribution, uuid.UUID(contribution_id))
        session.expunge(row)
        return row


def _leg_statuses(factory, leg_ids) -> set[str]:
    with factory() as session:
        return {session.get(Transaction, tx_id).status for tx_id in leg_ids}


def _balances(factory, accounts) -> dict[str, Decimal]:
    with factory() as session:
        return {
            name: session.get(Account, account_id).account_balance
            for name, account_id in accounts.items()
        }


STARTING = {
    "member": Decimal("5000"),
    "bank": Decimal("0"),
    "revenue": Decimal("0"),
    "treasury": Decimal("1000"),
    "stokvel": Decimal("0"),
}


# --- Submitting --------------------------------------------------------------


def test_a_contribution_is_claimed_sent_and_handed_on_once_mined(
    session_factory, pending, enqueued, chain
):
    result = submit_contribution(pending["id"])

    assert result == "mined"
    assert chain.allowances == [CONTRIBUTION]
    assert chain.contributes == [(pending["stokvel_id"], 0, pending["member_id"])]
    assert chain.waits == [TX_HASH]
    assert enqueued == [(pending["id"], TX_HASH, BLOCK)]
    row = _row(session_factory, pending["id"])
    assert (row.status, row.evm_tx_hash, row.block_number) == (
        "processing",
        TX_HASH,
        None,
    )
    assert _leg_statuses(session_factory, pending["legs"]) == {STATUS_PROCESSING}
    # Nothing moves until confirm_contribution.
    assert _balances(session_factory, pending["accounts"]) == STARTING


def test_confirming_marks_it_paid_and_moves_every_leg_once(
    session_factory, pending, enqueued, chain
):
    submit_contribution(pending["id"])

    assert confirm_contribution(*enqueued[0]) == "confirmed"

    row = _row(session_factory, pending["id"])
    assert (row.status, row.evm_tx_hash, row.block_number) == (
        "confirmed",
        TX_HASH,
        BLOCK,
    )
    assert row.confirmed_at is not None
    assert _leg_statuses(session_factory, pending["legs"]) == {STATUS_CONFIRMED}
    assert _balances(session_factory, pending["accounts"]) == {
        "member": Decimal("5000") - FIAT - FEE,
        "bank": FIAT,
        "revenue": FEE,
        "treasury": Decimal("1000") - CONTRIBUTION,
        "stokvel": CONTRIBUTION,
    }


# --- Duplicate messages ------------------------------------------------------


def test_a_redelivered_submit_waits_on_the_stored_hash_and_never_pays_twice(
    session_factory, pending, enqueued, chain
):
    submit_contribution(pending["id"])

    assert submit_contribution(pending["id"]) == "mined"

    assert len(chain.contributes) == 1  # one contribute, ever
    assert chain.waits == [TX_HASH, TX_HASH]
    assert enqueued == [(pending["id"], TX_HASH, BLOCK)] * 2


def test_a_replayed_confirm_credits_nothing_twice(
    session_factory, pending, enqueued, chain
):
    submit_contribution(pending["id"])
    confirm_contribution(*enqueued[0])
    after_first = _balances(session_factory, pending["accounts"])

    assert confirm_contribution(*enqueued[0]) == "skipped"
    assert submit_contribution(pending["id"]) == "skipped"

    assert _balances(session_factory, pending["accounts"]) == after_first
    assert len(chain.contributes) == 1


def test_a_redelivery_while_unsigned_sends_nothing(
    session_factory, pending, enqueued, chain, caplog
):
    """Claimed but no hash yet: another delivery may be signing right now,
    so a redelivery leaves it alone."""

    def redeliver():
        assert submit_contribution(pending["id"]) == "skipped"

    chain.before_on_signed = redeliver

    with caplog.at_level(logging.WARNING, logger="remitx_worker.stokvel_tasks"):
        assert submit_contribution(pending["id"]) == "mined"

    assert len(chain.contributes) == 1
    assert "event=stokvel.contribution_unsigned" in caplog.text


def test_a_signed_contribute_is_not_sent_if_its_hash_cannot_be_stored(
    session_factory, pending, enqueued, chain
):
    def someone_else_failed_it():
        confirm_contribution(pending["id"], None, None, "failed elsewhere")

    chain.before_on_signed = someone_else_failed_it

    assert submit_contribution(pending["id"]) == "skipped"

    assert chain.sent == []
    assert _row(session_factory, pending["id"]).status == "failed"


# --- Reverts and refusals ----------------------------------------------------


def test_a_reverted_contribution_never_shows_as_paid(
    session_factory, pending, enqueued, chain
):
    chain.receipt = evm_service.TransactionReverted(
        f"EVM transaction {TX_HASH} reverted"
    )

    assert submit_contribution(pending["id"]) == "failed"
    assert enqueued == [
        (pending["id"], None, None, f"EVM transaction {TX_HASH} reverted")
    ]

    assert confirm_contribution(*enqueued[0]) == "failed"
    row = _row(session_factory, pending["id"])
    assert row.status == "failed"
    assert row.confirmed_at is None
    assert row.evm_tx_hash == TX_HASH  # kept for investigation
    assert _leg_statuses(session_factory, pending["legs"]) == {STATUS_FAILED}
    # Failed legs no longer hold the member's balance, and nothing moved.
    assert _balances(session_factory, pending["accounts"]) == STARTING


def test_a_rule_refusal_fails_it_without_sending(
    session_factory, pending, enqueued, chain, caplog
):
    chain.before_signing = [
        stokvel_contract.ContractRefused("NotMember", "execution reverted")
    ]

    with caplog.at_level(logging.ERROR, logger="remitx_worker.stokvel_tasks"):
        assert submit_contribution(pending["id"]) == "failed"

    assert chain.sent == []
    assert "event=stokvel.contribution_refused" in caplog.text
    assert "error=NotMember" in caplog.text
    confirm_contribution(*enqueued[0])
    assert _row(session_factory, pending["id"]).status == "failed"
    assert _leg_statuses(session_factory, pending["legs"]) == {STATUS_FAILED}


@pytest.mark.parametrize(
    "error",
    [
        "EnforcedPause",
        "ERC20InsufficientBalance",
        "ERC20InsufficientAllowance",
        "AccessControlUnauthorizedAccount",
        "SafeERC20FailedOperation",
    ],
)
def test_a_platform_refusal_is_retried_then_succeeds(
    session_factory, pending, enqueued, chain, error
):
    """Paused, or the Treasury short: the platform's to fix, so the claim is
    handed back and the task retries instead of failing the member."""
    chain.before_signing = [stokvel_contract.ContractRefused(error, "reverted")]

    result = submit_contribution.apply(args=[pending["id"]]).get()

    assert result == "mined"
    assert len(chain.contributes) == 2
    assert chain.sent == [TX_HASH]


def test_a_platform_refusal_fails_once_the_retries_are_spent(
    session_factory, pending, enqueued, chain, caplog
):
    chain.before_signing = [
        stokvel_contract.ContractRefused("EnforcedPause", "reverted")
    ] * (stokvel_tasks.MAX_RETRIES + 1)

    with caplog.at_level(logging.WARNING, logger="remitx_worker.stokvel_tasks"):
        result = submit_contribution.apply(args=[pending["id"]]).get()

    assert result == "failed"
    assert chain.sent == []
    assert len(chain.contributes) == stokvel_tasks.MAX_RETRIES + 1
    assert caplog.text.count("event=stokvel.contribution_retry") == (
        stokvel_tasks.MAX_RETRIES
    )
    assert "event=stokvel.contribution_unsent" in caplog.text
    assert len(enqueued) == 1 and enqueued[0][1] is None


# --- RPC trouble -------------------------------------------------------------


def test_an_rpc_error_before_signing_hands_the_claim_back_and_retries(
    session_factory, pending, enqueued, chain
):
    chain.before_signing = [ConnectionError("RPC down")]

    with pytest.raises(ConnectionError):
        submit_contribution(pending["id"])  # direct call: the retry re-raises

    row = _row(session_factory, pending["id"])
    assert (row.status, row.evm_tx_hash) == ("pending", None)
    assert _leg_statuses(session_factory, pending["legs"]) == {STATUS_PENDING}
    assert chain.sent == []
    assert enqueued == []


def test_a_refused_send_drops_its_hash_and_retries(
    session_factory, pending, enqueued, chain
):
    """The RPC refused the signed transaction (for example, too little XRP
    for gas): it can never be mined, so its hash is cleared with the claim."""
    chain.after_signing = [
        evm_service.TransactionRejected(TX_HASH, Exception("insufficient funds"))
    ]

    result = submit_contribution.apply(args=[pending["id"]]).get()

    assert result == "mined"
    assert len(chain.contributes) == 2
    assert enqueued == [(pending["id"], TX_HASH, BLOCK)]


def _second_attempt(factory, pending) -> str:
    """A new pending contribution for the same member and round, as the API
    writes after a failed one: the member paying again."""
    with factory() as session:
        first = session.get(StokvelContribution, uuid.UUID(pending["id"]))
        legs = []
        for tx_id in pending["legs"]:
            old = session.get(Transaction, tx_id)
            legs.append(
                _leg(
                    session,
                    type_=old.type,
                    source=old.credit_account_id,
                    destination=old.debit_account_id,
                    amount=old.amount,
                    currency=old.currency,
                )
            )
        retry = StokvelContribution(
            cycle_id=first.cycle_id,
            round=first.round,
            member_id=first.member_id,
            amount_token=first.amount_token,
            amount_fiat=first.amount_fiat,
            amount_zar=first.amount_zar,
            fiat_tx_id=legs[0],
            token_tx_id=legs[1],
            fee_tx_id=legs[2],
        )
        session.add(retry)
        session.commit()
        return str(retry.id)


def test_a_refused_send_that_fails_leaves_no_hash_to_block_a_retry(
    session_factory, pending, enqueued, chain
):
    """The RPC refuses every send (the Treasury out of XRP for gas) until the
    retries run out. The refused transaction never existed, so the failed row
    keeps no hash: after a top-up, the member's second attempt signs the
    identical transaction (same calldata and nonce, so the same hash) and
    must not hit the unique index on `evm_tx_hash`."""
    chain.after_signing = [
        evm_service.TransactionRejected(TX_HASH, Exception("insufficient funds"))
    ] * (stokvel_tasks.MAX_RETRIES + 1)

    assert submit_contribution.apply(args=[pending["id"]]).get() == "failed"
    assert confirm_contribution(*enqueued[0]) == "failed"
    failed = _row(session_factory, pending["id"])
    assert (failed.status, failed.evm_tx_hash) == ("failed", None)

    retry_id = _second_attempt(session_factory, pending)
    assert submit_contribution(retry_id) == "mined"
    assert confirm_contribution(*enqueued[-1]) == "confirmed"
    retry = _row(session_factory, retry_id)
    assert (retry.status, retry.evm_tx_hash) == ("confirmed", TX_HASH)


def test_a_send_that_raises_after_its_hash_is_stored_is_waited_on(
    session_factory, pending, enqueued, chain, caplog
):
    chain.after_signing = [TimeoutError("send timed out")]

    with caplog.at_level(logging.WARNING, logger="remitx_worker.stokvel_tasks"):
        assert submit_contribution(pending["id"]) == "mined"

    assert len(chain.contributes) == 1
    assert chain.waits == [TX_HASH]
    assert "event=stokvel.contribution_send_uncertain" in caplog.text


def test_no_receipt_retries_the_same_hash_then_leaves_it_for_a_person(
    session_factory, pending, enqueued, chain, caplog
):
    chain.receipt = TimeExhausted("not mined in 120s")

    with caplog.at_level(logging.WARNING, logger="remitx_worker.stokvel_tasks"):
        result = submit_contribution.apply(args=[pending["id"]]).get()

    assert result == "awaiting_receipt"
    assert len(chain.contributes) == 1
    assert chain.waits == [TX_HASH] * (stokvel_tasks.MAX_RETRIES + 1)
    assert enqueued == []
    assert "event=stokvel.contribution_unconfirmed" in caplog.text
    row = _row(session_factory, pending["id"])
    assert (row.status, row.evm_tx_hash) == ("processing", TX_HASH)


def test_unknown_and_invalid_ids_are_skipped(session_factory, enqueued, chain):
    assert submit_contribution("not-a-uuid") == "skipped"
    assert submit_contribution(str(uuid.uuid4())) == "skipped"
    assert confirm_contribution(str(uuid.uuid4()), TX_HASH, BLOCK) == "skipped"
    assert chain.contributes == []


def test_a_confirmation_needs_its_block_number(session_factory, pending, chain):
    with pytest.raises(ValueError):
        confirm_contribution(pending["id"], TX_HASH, None)
    assert _row(session_factory, pending["id"]).status == "pending"


# --- Wiring ------------------------------------------------------------------


def test_the_api_and_the_worker_agree_on_the_task_names():
    assert queue_service.SUBMIT_CONTRIBUTION == submit_contribution.name
    assert queue_service.CONFIRM_CONTRIBUTION == confirm_contribution.name
    assert submit_contribution.name in celery.tasks
    assert confirm_contribution.name in celery.tasks


# --- The contract wrapper ----------------------------------------------------


def test_the_worker_abi_is_the_contracts_abi():
    exported = Path(__file__).resolve().parents[2] / "contracts/abi/StokvelVault.json"
    if not exported.exists():
        pytest.skip("contracts/ is not in this checkout")
    assert stokvel_contract._ABI_PATH.read_text() == exported.read_text()


@pytest.mark.parametrize(
    ("data", "name"),
    [
        # Selectors from doc section 1 ("Treasury allowance").
        ("0xfb8f41b2" + "00" * 96, "ERC20InsufficientAllowance"),
        ("0xe450d38c" + "00" * 96, "ERC20InsufficientBalance"),
        ("0x" + "12345678", None),
        (None, None),
    ],
)
def test_revert_data_is_decoded_against_the_vault_and_the_token(data, name):
    assert stokvel_contract.error_name(data) == name


def test_vault_errors_are_decoded_by_name():
    for entry in stokvel_contract.VAULT_ABI:
        if entry["type"] == "error":
            selector = stokvel_contract._selector(stokvel_contract._signature(entry))
            assert stokvel_contract.error_name("0x" + selector) == entry["name"]


class _FakeCall:
    def __init__(self, value):
        self.value = value

    def call(self):
        return self.value


class _FakeContract:
    def __init__(self, address, allowance=0):
        self.address = address
        self.encoded = []
        self._allowance = allowance
        self.functions = self

    def allowance(self, owner, spender):
        return _FakeCall(self._allowance)

    def encode_abi(self, name, args):
        self.encoded.append((name, args))
        return f"data:{name}"


@pytest.fixture
def wrapper(monkeypatch):
    token = _FakeContract("0xToken")
    vault = _FakeContract("0xVault")
    sent, waited = [], []

    def submit(tx, w3=None, *, on_signed=None):
        sent.append(tx)
        if on_signed is not None:
            on_signed(TX_HASH)
        return TX_HASH

    monkeypatch.setattr(evm_service, "token_contract", lambda w3: token)
    monkeypatch.setattr(stokvel_contract, "vault", lambda w3: vault)
    monkeypatch.setattr(evm_service, "treasury_address", lambda: "0xTreasury")
    monkeypatch.setattr(evm_service, "submit_transaction", submit)
    monkeypatch.setattr(
        evm_service, "wait_for_receipt", lambda h, w3=None: waited.append(h)
    )
    return {"token": token, "vault": vault, "sent": sent, "waited": waited}


def test_enough_allowance_sends_no_approval(wrapper):
    wrapper["token"]._allowance = 10**30

    assert stokvel_contract.ensure_allowance(CONTRIBUTION, w3=W3) is None
    assert wrapper["sent"] == []


def test_a_short_allowance_approves_the_vault_for_the_maximum_and_waits(wrapper):
    wrapper["token"]._allowance = 10**20 - 1  # 1 base unit under 100 UCTUSD

    assert stokvel_contract.ensure_allowance(CONTRIBUTION, w3=W3) == TX_HASH
    assert wrapper["token"].encoded == [
        ("approve", ["0xVault", stokvel_contract.MAX_UINT256])
    ]
    assert wrapper["sent"] == [{"to": "0xToken", "data": "data:approve"}]
    assert wrapper["waited"] == [TX_HASH]


def test_contribute_sends_packed_ids_to_the_vault(wrapper):
    stokvel_id, member_id = uuid.uuid4(), uuid.uuid4()
    signed = []

    assert (
        stokvel_contract.contribute(
            stokvel_id, 2, member_id, on_signed=signed.append, w3=W3
        )
        == TX_HASH
    )
    assert wrapper["vault"].encoded == [
        (
            "contribute",
            [stokvel_id.bytes + bytes(16), 2, member_id.bytes + bytes(16)],
        )
    ]
    assert wrapper["sent"] == [{"to": "0xVault", "data": "data:contribute"}]
    assert signed == [TX_HASH]


def test_a_revert_at_the_gas_estimate_is_refused_with_its_name(wrapper, monkeypatch):
    not_member = next(
        entry
        for entry in stokvel_contract.VAULT_ABI
        if entry["type"] == "error" and entry["name"] == "NotMember"
    )
    data = "0x" + stokvel_contract._selector(stokvel_contract._signature(not_member))

    def reverts(tx, w3=None, *, on_signed=None):
        raise ContractCustomError(data, data=data)

    monkeypatch.setattr(evm_service, "submit_transaction", reverts)

    with pytest.raises(stokvel_contract.ContractRefused) as refused:
        stokvel_contract.contribute(uuid.uuid4(), 0, uuid.uuid4(), w3=W3)
    assert refused.value.error == "NotMember"
