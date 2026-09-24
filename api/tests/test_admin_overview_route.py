"""Staff overview: queues, settlement volume, pipeline, treasury coverage."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    TYPE_PLATFORM_FIAT,
    TYPE_XRPL_WALLET,
    Account,
)
from remitx_api.models.orm.bank_account import BankAccount
from remitx_api.models.orm.deposit import PAYMENT_METHOD_BANK_TRANSFER, Deposit
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.quote import Quote
from remitx_api.models.orm.remittance import Remittance
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_FAILED,
    STATUS_PENDING,
    TYPE_DEPOSIT,
    TYPE_REMITTANCE,
    Transaction,
)
from remitx_api.repositories.account_repository import AccountRepository
from tests.kyc_helpers import make_user as persist_user
from tests.rbac_helpers import make_user, rbac_client

OPERATIONS = "/admin/operations"
DEPOSITS = "/admin/deposits/pending-count"
BANKS = "/admin/bank-accounts/pending-count"
COVERAGE = "/admin/platform-accounts/coverage"


def test_operations_requires_transaction_read_any():
    with rbac_client(make_user("ops-denied")) as client:
        assert client.get(OPERATIONS).status_code == 403


def test_queue_counts_stay_on_their_own_permissions():
    with rbac_client(
        make_user("ops-tx-only"),
        permissions=(PermissionCode.TRANSACTION_READ_ANY,),
    ) as client:
        assert client.get(OPERATIONS).status_code == 200
        assert client.get(DEPOSITS).status_code == 403
        assert client.get(BANKS).status_code == 403
        assert client.get(COVERAGE).status_code == 403


def test_overview_reports_queues_volume_pipeline_and_coverage():
    with rbac_client(
        make_user("ops-reader"),
        permissions=(
            PermissionCode.TRANSACTION_READ_ANY,
            PermissionCode.CASHIN_READ,
            PermissionCode.CASHOUT_READ,
            PermissionCode.PLATFORM_ACCOUNT_READ,
        ),
    ) as client:
        _seed_overview()
        db.session.commit()

        operations = client.get(OPERATIONS)
        deposits = client.get(DEPOSITS)
        banks = client.get(BANKS)
        coverage = client.get(COVERAGE)

    assert operations.status_code == 200
    body = operations.json()
    today = datetime.now(UTC).date().isoformat()
    volume = next(row for row in body["volume"] if row["day"] == today)
    pipeline = next(row for row in body["pipeline"] if row["day"] == today)

    assert body["failed_settlements"] == 1
    assert volume["zar_cash_in"] == "400.00"
    assert volume["token_settled"] == "50.00"
    assert pipeline["settled"] == 1
    assert pipeline["failed"] == 1
    assert pipeline["queued"] == 0
    assert deposits.json() == {"count": 1}
    assert banks.json() == {"count": 1}
    assert coverage.json() == {
        "token_available": "80.00",
        "customer_token_balances": "50.00",
    }


def _seed_overview() -> None:
    now = datetime.now(UTC)
    sender = persist_user("ops-sender")
    beneficiary = persist_user("ops-beneficiary")
    accounts = AccountRepository()
    sender_zar = accounts.get_or_create_user_account(
        sender.id, sender.base_reference, CURRENCY_ZAR
    )
    sender_token = accounts.get_or_create_user_account(
        sender.id, sender.base_reference, CURRENCY_TOKEN
    )
    beneficiary_token = accounts.get_or_create_user_account(
        beneficiary.id, beneficiary.base_reference, CURRENCY_TOKEN
    )
    beneficiary_token.account_balance = Decimal("50.00")
    bank = Account(
        user_id=None,
        type=TYPE_PLATFORM_FIAT,
        account_currency=CURRENCY_ZAR,
        label="overview bank",
        account_balance=Decimal("0"),
    )
    wallet = Account(
        user_id=None,
        type=TYPE_XRPL_WALLET,
        account_currency=CURRENCY_TOKEN,
        label="overview treasury",
        account_balance=Decimal("80.00"),
    )
    db.session.add_all([bank, wallet])
    db.session.flush()

    _remittance(
        now,
        sender.id,
        beneficiary.id,
        sender_token.account_id,
        beneficiary_token.account_id,
        Decimal("1000"),
        Decimal("50"),
        STATUS_CONFIRMED,
    )
    _remittance(
        now,
        sender.id,
        beneficiary.id,
        sender_token.account_id,
        beneficiary_token.account_id,
        Decimal("20"),
        Decimal("1"),
        STATUS_FAILED,
    )
    pending = Transaction(
        type=TYPE_DEPOSIT,
        credit_account_id=bank.account_id,
        debit_account_id=None,
        amount=Decimal("200"),
        currency=CURRENCY_ZAR,
        status=STATUS_PENDING,
    )
    confirmed = Transaction(
        type=TYPE_DEPOSIT,
        credit_account_id=bank.account_id,
        debit_account_id=sender_zar.account_id,
        amount=Decimal("400"),
        currency=CURRENCY_ZAR,
        status=STATUS_CONFIRMED,
        confirmed_at=now,
    )
    db.session.add_all([pending, confirmed])
    db.session.flush()
    db.session.add(
        Deposit(
            statement_fingerprint="overview-pending",
            tx_id=pending.tx_id,
            payment_method=PAYMENT_METHOD_BANK_TRANSFER,
        )
    )
    db.session.add(
        BankAccount(
            user_id=sender.id,
            account_holder_name="Ops Sender",
            bank_name="FNB",
            account_number="1234567890",
            currency=CURRENCY_ZAR,
        )
    )


def _remittance(
    now,
    sender_id,
    beneficiary_id,
    source_id,
    destination_id,
    sender_amount,
    token_amount,
    status,
):
    rate = ExchangeRate(
        base_currency=CURRENCY_ZAR,
        quote_currency=CURRENCY_ZAR,
        rate=Decimal("1"),
        fetched_at=now,
        valid_until=now + timedelta(hours=1),
    )
    db.session.add(rate)
    db.session.flush()
    quote = Quote(
        sender_user_id=sender_id,
        beneficiary_user_id=beneficiary_id,
        sender_amount=sender_amount,
        sender_currency=CURRENCY_ZAR,
        sender_transaction_fee=Decimal("0"),
        token_amount=token_amount,
        token_name=CURRENCY_TOKEN,
        fiat_to_token_exchange_rate=Decimal("0.05"),
        fiat_exchange_rate_id=rate.id,
        fiat_exchange_rate=Decimal("1"),
        exchange_rate_margin=Decimal("0"),
        receiver_amount=sender_amount,
        receiver_currency=CURRENCY_ZAR,
        receiver_payout_fee=Decimal("0"),
        receiver_payout_estimate=sender_amount,
        expires_at=now + timedelta(minutes=15),
    )
    db.session.add(quote)
    db.session.flush()
    leg = Transaction(
        type=TYPE_REMITTANCE,
        credit_account_id=source_id,
        debit_account_id=destination_id,
        amount=token_amount,
        currency=CURRENCY_TOKEN,
        status=status,
        quote_id=quote.quote_id,
        confirmed_at=now if status == STATUS_CONFIRMED else None,
    )
    db.session.add(leg)
    db.session.flush()
    db.session.add(Remittance(quote_id=quote.quote_id, tx_id=leg.tx_id))
    db.session.flush()
