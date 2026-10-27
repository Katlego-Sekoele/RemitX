"""What a member's monthly limit holds back for their stokvel contributions
(D8).

A member who agrees to a stokvel's fixed contribution must be able to pay it
each round, so their remittances may not spend the month it needs. Each
unpaid round of an active cycle they are locked into is reserved in the SAST
month of its pay-by date (`deadline`), and an overdue one stays reserved until
it is paid. Weekly rounds reserve four or five contributions a month, rounds
every two weeks two or three, monthly rounds one: the dates decide, so the
stokvel needs no frequency of its own.

Nothing is stored. The reservation is worked out from the rounds and
contributions each time a standing is read, so paying a round, a payment
failing, the month turning, leaving the stokvel and the cycle closing all
change it with nothing to update.

Each contribution is valued as paying it would count (`contribution_cost_zar`:
the fixed UCTUSD amount and the member's fee share, in rand), but at the
newest stored rates rather than a live one: a standing is read inside
transactions that hold locks, where fetching a rate could commit and release
them. A contribution prices at the live rate, so it may differ from its
reservation by however far the rate moved.
"""

import logging
import uuid
from decimal import Decimal

from remitx_api.repositories.stokvel_contribution_repository import (
    StokvelContributionRepository,
    UnpaidRound,
)
from remitx_api.services.quote_service import (
    TokenRates,
    contribution_cost_zar,
    stored_token_rates,
)
from remitx_api.services.send_limits import LimitWindows

logger = logging.getLogger(__name__)


def reserved_zar(user_id: uuid.UUID, windows: LimitWindows) -> Decimal:
    """What the user's stokvel contributions due by the end of `windows`'
    month, overdue ones included, are worth in rand now."""
    due = [
        unpaid
        for unpaid in StokvelContributionRepository().unpaid_rounds(user_id)
        if unpaid.deadline < windows.month_end
    ]
    if not due:
        return Decimal("0.00")
    rates: dict[str, TokenRates] = {}
    total = Decimal("0.00")
    for unpaid in due:
        if unpaid.currency not in rates:
            rates[unpaid.currency] = stored_token_rates(unpaid.currency)
        total += _cost_zar(unpaid, rates[unpaid.currency])
    logger.debug(
        "reserved_zar: user %s has %s unpaid round(s) due this month",
        user_id,
        len(due),
    )
    return total


def _cost_zar(unpaid: UnpaidRound, rates: TokenRates) -> Decimal:
    return contribution_cost_zar(
        unpaid.contribution_amount,
        rates,
        member_count=unpaid.member_count,
        payout_currency=unpaid.payout_currency,
    )
