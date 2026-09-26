"""Fully-pending remittance groups are re-enqueued; processing groups are not."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.extensions import db
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_PROCESSING,
    Transaction,
)
from remitx_api.repositories.remittance_repository import RemittanceRepository
from remitx_api.services import queue_service, remittance_service
from remitx_worker import db as worker_db
from remitx_worker.reclaim import (
    SETTLE_REMITTANCE,
    log_stale_processing_settlements,
    reclaim_pending_settlements,
)
from sqlalchemy import update
from sqlalchemy.orm import sessionmaker
from tests.platform_account_helpers import seed_platform_accounts
from tests.test_remittance_service import (
    _fund_and_quote,
    _make_sender_and_beneficiary,
    _store_rate,
)


@pytest.fixture
def settle_enqueue_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        queue_service,
        "enqueue_settle_remittance",
        calls.append,
    )
    return calls


@pytest.fixture
def worker_on_app_db(app_context):
    worker_db.configure(sessionmaker(bind=db.engine, autoflush=False, autocommit=False))
    yield
    worker_db.configure(None)


def _confirm_quote(enqueue_calls):
    _store_rate("18.50")
    _store_rate("16.22", base_currency="ZAR", quote_currency="ZWL")
    seed_platform_accounts()
    sender, _recipient, beneficiary = _make_sender_and_beneficiary()
    quote = _fund_and_quote(sender, beneficiary, Decimal("1000"))
    remittance_service.confirm_remittance(sender.id, quote.quote_id)
    assert enqueue_calls == [str(quote.quote_id)]
    enqueue_calls.clear()
    return quote.quote_id


def test_reclaim_enqueues_fully_pending_group(
    app_context, worker_on_app_db, settle_enqueue_calls, monkeypatch
):
    quote_id = _confirm_quote(settle_enqueue_calls)

    sent = []
    monkeypatch.setattr(
        "remitx_worker.reclaim.celery.send_task",
        lambda name, args, queue: sent.append((name, args[0], queue)),
    )

    assert reclaim_pending_settlements(min_age_seconds=0) == 1
    assert sent == [(SETTLE_REMITTANCE, str(quote_id), "settlement")]


def test_reclaim_skips_processing_group(
    app_context, worker_on_app_db, settle_enqueue_calls, monkeypatch
):
    quote_id = _confirm_quote(settle_enqueue_calls)
    now = datetime.now(UTC)
    db.session.execute(
        update(Transaction)
        .where(Transaction.quote_id == quote_id)
        .values(status=STATUS_PROCESSING, processed_at=now)
    )
    db.session.commit()

    sent = []
    monkeypatch.setattr(
        "remitx_worker.reclaim.celery.send_task",
        lambda *a, **k: sent.append(1),
    )

    assert reclaim_pending_settlements(min_age_seconds=0) == 0
    assert sent == []


def test_reclaim_skips_confirmed_group(
    app_context, worker_on_app_db, settle_enqueue_calls, monkeypatch
):
    quote_id = _confirm_quote(settle_enqueue_calls)
    db.session.execute(
        update(Transaction)
        .where(Transaction.quote_id == quote_id)
        .values(status=STATUS_CONFIRMED)
    )
    db.session.commit()

    sent = []
    monkeypatch.setattr(
        "remitx_worker.reclaim.celery.send_task",
        lambda *a, **k: sent.append(1),
    )

    assert reclaim_pending_settlements(min_age_seconds=0) == 0
    assert sent == []


def test_reclaim_respects_min_age(
    app_context, worker_on_app_db, settle_enqueue_calls, monkeypatch
):
    _store_rate("18.50")
    _store_rate("16.22", base_currency="ZAR", quote_currency="ZWL")
    seed_platform_accounts()
    sender, _recipient, beneficiary = _make_sender_and_beneficiary()
    old_quote = _fund_and_quote(sender, beneficiary, Decimal("1000")).quote_id
    remittance_service.confirm_remittance(sender.id, old_quote)
    settle_enqueue_calls.clear()

    old_when = datetime.now(UTC) - timedelta(minutes=10)
    remittance = RemittanceRepository().get_by_quote_id(old_quote)
    remittance.created_at = old_when
    db.session.commit()

    young_quote = _fund_and_quote(sender, beneficiary, Decimal("500")).quote_id
    remittance_service.confirm_remittance(sender.id, young_quote)

    sent = []
    monkeypatch.setattr(
        "remitx_worker.reclaim.celery.send_task",
        lambda name, args, queue: sent.append(args[0]),
    )

    assert reclaim_pending_settlements(min_age_seconds=180) == 1
    assert sent == [str(old_quote)]


def test_stale_processing_is_logged_not_enqueued(
    app_context, worker_on_app_db, settle_enqueue_calls, monkeypatch, caplog
):
    quote_id = _confirm_quote(settle_enqueue_calls)
    stale = datetime.now(UTC) - timedelta(minutes=30)
    db.session.execute(
        update(Transaction)
        .where(Transaction.quote_id == quote_id)
        .values(status=STATUS_PROCESSING, processed_at=stale)
    )
    remittance = RemittanceRepository().get_by_quote_id(quote_id)
    remittance.created_at = stale
    db.session.commit()

    sent = []
    monkeypatch.setattr(
        "remitx_worker.reclaim.celery.send_task",
        lambda *a, **k: sent.append(1),
    )

    with caplog.at_level("WARNING"):
        count = log_stale_processing_settlements(min_age_seconds=60)

    assert count == 1
    assert sent == []
    assert str(quote_id) in caplog.text
