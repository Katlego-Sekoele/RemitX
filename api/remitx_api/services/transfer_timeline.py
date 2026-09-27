"""Transfer status timeline — titles, descriptions, and timestamps for the UI."""

from dataclasses import dataclass
from datetime import datetime

from remitx_api.models.orm.transaction import (
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSING,
)


@dataclass(frozen=True)
class TimelineStage:
    step: int
    title: str
    description: str
    occurred_at: datetime | None


def transfer_timeline(
    status: str,
    created_at: datetime,
    processed_at: datetime | None,
    settled_at: datetime | None,
) -> tuple[list[TimelineStage], int]:
    """The four settlement stages and which step is active (1–4)."""
    failed = status == STATUS_FAILED
    stages = [
        TimelineStage(
            1,
            "Quote accepted",
            "The price was locked in and confirmed.",
            created_at,
        ),
        TimelineStage(
            2,
            "Queued",
            "Waiting for the settlement worker to pick it up.",
            created_at,
        ),
        TimelineStage(
            3,
            "Settling on XRPL Testnet",
            "UCTUSD is moving on the XRP Ledger Testnet.",
            processed_at,
        ),
        TimelineStage(
            4,
            "Failed" if failed else "Completed",
            "Settlement didn't complete." if failed else "The recipient has been paid.",
            None if failed else settled_at,
        ),
    ]
    if status == STATUS_PENDING:
        current = 2
    elif status == STATUS_PROCESSING:
        current = 3
    else:
        current = 4
    return stages, current
