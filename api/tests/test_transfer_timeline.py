from datetime import UTC, datetime

from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSING,
)
from remitx_api.services.transfer_timeline import transfer_timeline


def test_pending_transfer_is_queued_on_the_timeline():
    created = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
    stages, step = transfer_timeline(STATUS_PENDING, created, None, None)
    assert step == 2
    assert [stage.title for stage in stages] == [
        "Quote accepted",
        "Queued",
        "Settling on XRPL Testnet",
        "Completed",
    ]
    assert stages[0].occurred_at == created
    assert stages[3].occurred_at is None


def test_failed_transfer_ends_on_failed():
    created = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
    processed = datetime(2026, 9, 22, 10, 1, tzinfo=UTC)
    stages, step = transfer_timeline(STATUS_FAILED, created, processed, None)
    assert step == 4
    assert stages[-1].title == "Failed"
    assert stages[-1].occurred_at is None


def test_confirmed_transfer_records_settled_at():
    created = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
    processed = datetime(2026, 9, 22, 10, 1, tzinfo=UTC)
    settled = datetime(2026, 9, 22, 10, 2, tzinfo=UTC)
    _stages, step = transfer_timeline(
        STATUS_CONFIRMED, created, processed, settled
    )
    assert step == 4


def test_processing_transfer_is_on_settling():
    created = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
    processed = datetime(2026, 9, 22, 10, 1, tzinfo=UTC)
    _stages, step = transfer_timeline(
        STATUS_PROCESSING, created, processed, None
    )
    assert step == 3
