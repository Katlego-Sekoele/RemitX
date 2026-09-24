"""Staff overview: cash-in and settlement over the last 30 UTC days."""

from datetime import date
from decimal import Decimal

from remitx_api.models.schemas.base import Schema


class VolumeDayRead(Schema):
    """Confirmed ZAR cash-in and confirmed token settlement on one UTC day."""

    day: date
    zar_cash_in: Decimal
    token_settled: Decimal


class PipelineDayRead(Schema):
    """Transfers created that UTC day, by the settlement leg's current status."""

    day: date
    queued: int
    settling: int
    settled: int
    failed: int


class OperationsRead(Schema):
    """Volume and pipeline for the staff overview, plus the failed count."""

    # Settlement legs whose status is failed now, not only inside the window.
    failed_settlements: int
    volume: list[VolumeDayRead]
    pipeline: list[PipelineDayRead]
