"""Volume and pipeline for the staff overview."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSING,
)
from remitx_api.models.schemas.operations import (
    OperationsRead,
    PipelineDayRead,
    VolumeDayRead,
)
from remitx_api.repositories.overview_repository import OverviewRepository

WINDOW_DAYS = 30
AMOUNT_QUANTUM = Decimal("0.01")

_PIPELINE = {
    STATUS_PENDING: "queued",
    STATUS_PROCESSING: "settling",
    STATUS_CONFIRMED: "settled",
    STATUS_FAILED: "failed",
}


def _money(value: Decimal) -> Decimal:
    return value.quantize(AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)


def _midnight(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


class OperationsController:
    def __init__(self) -> None:
        self._overview = OverviewRepository()

    def get_operations(self) -> OperationsRead:
        now = datetime.now(UTC)
        today = _midnight(now)
        window_start = today - timedelta(days=WINDOW_DAYS - 1)
        days = [
            window_start.date() + timedelta(days=offset)
            for offset in range(WINDOW_DAYS)
        ]

        cash_in: dict = defaultdict(lambda: Decimal("0"))
        for deposit in self._overview.confirmed_zar_cash_in_since(window_start):
            if deposit.at >= window_start:
                cash_in[deposit.at.date()] += deposit.amount

        settled: dict = defaultdict(lambda: Decimal("0"))
        pipeline: dict[object, dict[str, int]] = defaultdict(
            lambda: {"queued": 0, "settling": 0, "settled": 0, "failed": 0}
        )
        for fact in self._overview.transfers_since(window_start):
            if fact.created_at >= window_start:
                bucket = _PIPELINE.get(fact.status)
                if bucket is not None:
                    pipeline[fact.created_at.date()][bucket] += 1
            confirmed_at = fact.confirmed_at
            if (
                fact.status == STATUS_CONFIRMED
                and confirmed_at is not None
                and confirmed_at >= window_start
            ):
                settled[confirmed_at.date()] += fact.token_amount

        return OperationsRead(
            failed_settlements=self._overview.failed_settlement_count(),
            volume=[
                VolumeDayRead(
                    day=day,
                    zar_cash_in=_money(cash_in[day]),
                    token_settled=_money(settled[day]),
                )
                for day in days
            ],
            pipeline=[PipelineDayRead(day=day, **pipeline[day]) for day in days],
        )
