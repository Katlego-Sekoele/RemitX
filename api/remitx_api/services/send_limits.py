"""Sending limits as running daily and monthly totals (KYC-3, #25).

A sender's allowance is their KYC standing's limits: the tier's daily and
monthly ZAR limits, scaled by the risk rating. What they have used is the sum
of their own sends over the current day and calendar month, read from the
ledger rather than kept as a counter, so it cannot drift from the transfers
it describes. Everything they have committed counts, settled or not; a
transfer whose settlement leg failed gives its amount back.

The day and the month are South African. Both reset at midnight SAST, not
midnight UTC, which would reset the daily limit at 02:00 local time.

Everything is pinned to rand, as the fees are. Any fiat account can send, and
a send counts against the limits at its value in rand, worked out at its
quote's rates and locked on the quote (`Quote.sender_amount_zar`).

`KycApplicationRepository.get_standing` reports the usage alongside the
limits, and `require_can_send` is the one rule `create_quote` (early, so the
sender hears it before committing) and `confirm_remittance` (the real gate,
since two quotes can be issued against one allowance) both apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING

from remitx_api.errors.remittances import (
    LIMIT_DAILY,
    LIMIT_MONTHLY,
    KycNotApprovedError,
    LimitExceededError,
)
from remitx_api.models.orm.account import CURRENCY_ZAR

if TYPE_CHECKING:
    from remitx_api.repositories.kyc_application_repository import KycStanding

CENTS = Decimal("0.01")

# South Africa Standard Time. There is no daylight saving, so a fixed offset
# is exact; tools/seeder/remitx_seeder/stories/timing.py uses the same one.
SAST = timezone(timedelta(hours=2), "SAST")


@dataclass(frozen=True)
class LimitWindows:
    """The SAST day and calendar month containing a moment, each from its
    first instant up to, not including, the next one's."""

    day_start: datetime
    day_end: datetime
    month_start: datetime
    month_end: datetime


def limit_windows(now: datetime) -> LimitWindows:
    """The SAST day and month `now` falls in, as UTC instants: SQLite drops
    an offset when it binds a datetime, so bounds compared with stored
    timestamps must already be UTC. `now` must be aware."""
    local = now.astimezone(SAST)
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)
    # Day 28 plus four days is always in the next month, whatever its length.
    month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return LimitWindows(
        day_start=day_start.astimezone(UTC),
        day_end=(day_start + timedelta(days=1)).astimezone(UTC),
        month_start=month_start.astimezone(UTC),
        month_end=month_end.astimezone(UTC),
    )


def require_verified(standing: KycStanding) -> None:
    """Brief: only approved users may send. Refused outright, never limited."""
    if not standing.is_verified:
        raise KycNotApprovedError()


def require_within_limits(
    standing: KycStanding, amount_zar: Decimal, *, amount: Decimal, currency: str
) -> None:
    """Refuse a send worth `amount_zar` in rand that doesn't fit what is left
    of both the day and the month.

    The refusal names whichever leaves less, and the month on a tie, since a
    new day wouldn't help. For a send of `amount` in another `currency`, it
    also estimates what is left in that currency at the send's own rate.
    """
    daily = standing.daily_remaining_zar
    monthly = standing.monthly_remaining_zar
    if amount_zar <= min(daily, monthly):
        return
    limit, remaining = (
        (LIMIT_MONTHLY, monthly) if monthly <= daily else (LIMIT_DAILY, daily)
    )
    estimate = None
    if currency != CURRENCY_ZAR:
        # Rounded down, so sending the estimate itself would fit.
        estimate = (
            (remaining * amount / amount_zar).quantize(CENTS, rounding=ROUND_DOWN),
            currency,
        )
    raise LimitExceededError(limit, remaining, estimate=estimate)


def require_can_send(
    standing: KycStanding, amount_zar: Decimal, *, amount: Decimal, currency: str
) -> None:
    """Both of the above: the check confirming a quote repeats in full."""
    require_verified(standing)
    require_within_limits(standing, amount_zar, amount=amount, currency=currency)
