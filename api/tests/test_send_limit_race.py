"""Two confirms racing one allowance (KYC-3, #25), on Postgres.

Each confirm reads what the sender has already sent, then inserts. Two
running at once could both read the same total and both pass. SQLite ignores
row locks, so only a real Postgres can show `confirm_remittance`'s lock on the
sender closing that window. Runs in the `postgres` lane (TEST_DATABASE_URL).
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.controllers.beneficiary_controller import BeneficiaryController
from remitx_api.controllers.user_controller import UserController
from remitx_api.errors.remittances import LimitExceededError
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR, CURRENCY_ZWL
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.models.orm.kyc_lifecycle import KYC_TIER_VERIFIED, KycStatus
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.kyc_application_repository import (
    KycApplicationRepository,
)
from remitx_api.repositories.remittance_repository import RemittanceRepository
from remitx_api.services import quote_service, remittance_service
from tests.kyc_helpers import insert_application

pytestmark = pytest.mark.postgres


def _sender_with_two_quotes(amount: Decimal) -> tuple:
    """A tier-1 sender (R3,000 a day), well funded, holding two quotes for
    `amount` each. Platform accounts and KYC reference data come from the
    migrations."""
    now = datetime.now(UTC)
    for base, quote, rate in (("USD", "ZAR", "18.50"), ("ZAR", "ZWL", "16.22")):
        db.session.add(
            ExchangeRate(
                base_currency=base,
                quote_currency=quote,
                rate=Decimal(rate),
                fetched_at=now,
                valid_until=now + timedelta(hours=1),
            )
        )
    db.session.commit()

    users = UserController()
    sender = users.ensure_provisioned(
        "user_race_sender", lambda: "race-sender@example.com", lambda: "Sender"
    )
    insert_application(
        sender.id, KycStatus.APPROVED, tier_granted=KYC_TIER_VERIFIED, with_pii=True
    )
    recipient = users.ensure_provisioned(
        "user_race_recipient", lambda: "race-recipient@example.com", lambda: "Recip"
    )
    accounts = AccountRepository()
    accounts.get_or_create_user_account(
        recipient.id, recipient.base_reference, CURRENCY_ZWL
    )
    zar = accounts.get_user_account(sender.id, CURRENCY_ZAR)
    accounts.increase_balance(zar.account_id, Decimal("10000"))
    db.session.commit()
    beneficiary = (
        BeneficiaryController()
        .create(
            sender_user_id=sender.id,
            linked_user_id=recipient.id,
            payout_currency=CURRENCY_ZWL,
            relationship="sibling",
        )
        .beneficiary
    )
    quote_ids = [
        quote_service.create_quote(
            sender.id,
            beneficiary.beneficiary_id,
            amount,
            sender_currency=CURRENCY_ZAR,
            receiver_payout_currency=CURRENCY_ZWL,
        ).quote_id
        for _ in range(2)
    ]
    return sender.id, quote_ids


def test_concurrent_confirms_cannot_jointly_exceed_the_daily_limit(
    postgres_app, monkeypatch
):
    token = db.open_session()
    try:
        sender_id, quote_ids = _sender_with_two_quotes(Decimal("2000"))
    finally:
        db.close_session(token)
    monkeypatch.setattr(
        remittance_service.queue_service, "enqueue_settle_remittance", lambda *_: None
    )

    # Makes the bad interleaving certain rather than lucky: each confirm, once
    # it has read what was sent, waits for the other to have read it too.
    # Without the lock both read R0 and both pass. With it, the second can't
    # read until the first commits, so the first stops waiting after a second.
    barrier = threading.Barrier(2, timeout=1)
    sent_zar = RemittanceRepository.sent_zar

    def sent_zar_then_wait(self, *args, **kwargs):
        totals = sent_zar(self, *args, **kwargs)
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        return totals

    monkeypatch.setattr(RemittanceRepository, "sent_zar", sent_zar_then_wait)

    def confirm(quote_id) -> str:
        token = db.open_session()
        try:
            remittance_service.confirm_remittance(sender_id, quote_id)
            return "sent"
        except LimitExceededError:
            return "refused"
        finally:
            db.close_session(token)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(confirm, quote_ids))

    monkeypatch.undo()
    token = db.open_session()
    try:
        standing = KycApplicationRepository().get_standing(sender_id)
    finally:
        db.close_session(token)
    assert outcomes == ["refused", "sent"]
    assert standing.daily_used_zar == Decimal("2000.00")
