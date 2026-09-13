"""Exchange-rate access for quote generation (Transaction_Flow_Context.md §4).

Lazy fetch-on-demand rather than a scheduled job: a caller asking for the
active rate gets the stored one if it's still valid, otherwise a fresh fetch
is made and stored right then. If the live fetch itself fails, the most
recent stored rate is reused as long as it isn't older than
MAX_RATE_STALENESS_HOURS; past that, this refuses to quote rather than
fabricate a price.

This service only validates and fetches a *given* pair. Deciding which pair
a particular quote needs is the caller's job (see services/quote_service.py's
`_usd_rate`).
"""

import logging
from datetime import UTC, datetime, timedelta

from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_NAD,
    CURRENCY_USD,
    CURRENCY_ZAR,
    CURRENCY_ZWL,
)
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.repositories.exchange_rate_repository import ExchangeRateRepository
from remitx_api.services.exchange_rate_provider import (
    ExchangeRateApiProvider,
    RateFetchError,
)
from remitx_api.services.quote_config import (
    MAX_RATE_STALENESS_HOURS,
    RATE_FIXING_INTERVAL_HOURS,
)

logger = logging.getLogger(__name__)

# Currencies a rate may be fetched for.
SUPPORTED_CURRENCIES = {CURRENCY_USD, CURRENCY_ZAR, CURRENCY_ZWL, CURRENCY_NAD}


class RateUnavailableError(Exception):
    """No usable rate: the live fetch failed and no stored rate is recent
    enough to fall back to. Callers should refuse to quote (503), not guess."""


class UnsupportedCurrencyError(Exception):
    """Requested base or quote currency isn't in SUPPORTED_CURRENCIES —
    refuse rather than fetch/store an unknown or mistyped currency code."""


def get_active_rate(
    base_currency: str, quote_currency: str, now: datetime | None = None
) -> ExchangeRate:
    if base_currency not in SUPPORTED_CURRENCIES:
        raise UnsupportedCurrencyError(f"unsupported base currency {base_currency!r}")
    if quote_currency not in SUPPORTED_CURRENCIES:
        raise UnsupportedCurrencyError(f"unsupported quote currency {quote_currency!r}")

    now = now or datetime.now(UTC)  # Default to current time if not provided
    repo = ExchangeRateRepository()

    # Get the most recent valid rate for a pair, if any
    existing = repo.get_current_rate(base_currency, quote_currency, now)
    if existing is not None:
        return existing

    # If there is no valid rate, fetch a new one from the external API and store it
    try:
        rate_value = ExchangeRateApiProvider().get_rate(base_currency, quote_currency)
    except RateFetchError:
        logger.warning(
            "live rate fetch failed; falling back to stored rate", exc_info=True
        )
        fallback_rate = repo.get_most_recent_rate(base_currency, quote_currency)
        if fallback_rate is not None:
            fetched_at = fallback_rate.fetched_at
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=UTC)
            if now - fetched_at <= timedelta(hours=MAX_RATE_STALENESS_HOURS):
                return fallback_rate
        raise RateUnavailableError(
            "live rate fetch failed and no recent-enough stored rate exists"
        ) from None

    # If the live fetch succeeded, store the new rate and return it
    api_fetched_rate = ExchangeRate(
        base_currency=base_currency,
        quote_currency=quote_currency,
        rate=rate_value,
        fetched_at=now,
        valid_until=now + timedelta(hours=RATE_FIXING_INTERVAL_HOURS),
    )
    db.session.add(api_fetched_rate)
    db.session.commit()
    return api_fetched_rate
