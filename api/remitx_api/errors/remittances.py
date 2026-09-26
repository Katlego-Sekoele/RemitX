"""Errors raised by the remittance domain."""

from __future__ import annotations

import uuid
from decimal import Decimal

from remitx_api.errors.base import DomainError, ForbiddenError, NotFoundError


class UnknownRemittanceError(NotFoundError):
    """No such remittance, or the caller is neither its sender nor its
    recipient — one answer for both, so an id can't be probed for."""

    def __init__(self, remittance_id: uuid.UUID | str) -> None:
        super().__init__("Transfer not found")
        self.remittance_id = str(remittance_id)


class KycNotApprovedError(ForbiddenError):
    """Brief: "Only approved users may send remittances." A sender who never
    verified, or whose verification was rejected, is turned away outright,
    never just limited. Checked when a quote is issued and again when it is
    confirmed, since standing can change in between."""

    def __init__(self) -> None:
        super().__init__(
            "Only verified customers can send money. Finish verification to "
            "start sending."
        )


LIMIT_DAILY = "daily"
LIMIT_MONTHLY = "monthly"

# What's left is spent "today" and comes back "tomorrow", and so on.
_PERIOD_WORDS = {
    LIMIT_DAILY: ("today", "tomorrow"),
    LIMIT_MONTHLY: ("this month", "next month"),
}


def _format_money(amount: Decimal, currency: str) -> str:
    """`R 1,800.00` or `USD 97.29`, as the customer UI writes them."""
    prefix = "R" if currency == "ZAR" else currency
    return f"{prefix} {amount:,.2f}"


class LimitExceededError(DomainError):
    """The send would take the day's or the month's running total over the
    sender's allowance (the tier's limits scaled by their risk rating).

    Names the limit that binds and what is left of it, so the sender knows
    what they can still send and when that changes. What is left is in rand,
    as the limits are; for a send from another currency, `estimate` is that
    figure in the send's own currency too, as (amount, currency).
    """

    def __init__(
        self,
        limit: str,
        remaining: Decimal,
        *,
        estimate: tuple[Decimal, str] | None = None,
    ) -> None:
        now, later = _PERIOD_WORDS[limit]
        if remaining > 0:
            left = _format_money(remaining, "ZAR")
            if estimate is not None:
                left += f" (about {_format_money(*estimate)})"
            detail = (
                f"This would exceed your {limit} limit. You can send up to "
                f"{left} {now}."
            )
        else:
            detail = f"You've reached your {limit} limit. You can send again {later}."
        super().__init__(detail)
        self.limit = limit
        self.remaining = remaining
        self.estimate = estimate
