"""Past exchange rates for a replayed timeline.

Installed with `remitx_api.services.exchange_rate_provider.use_rate_provider`
so quotes created "seven weeks ago" are priced at a rate for seven weeks ago,
and no seed run ever calls the live rate API.

USD/ZAR follows a small, seeded random walk around a plausible level. NAD and
LSL are pegged 1:1 to ZAR, as they are in reality (the Common Monetary
Area). ZWL, EUR, GBP, BWP, MWK and MZN each sit at a fixed level roughly
where exchangerate-api has reported them. Every other pair is a cross rate
through USD, so ZAR->NAD and USD->ZAR can never disagree with each other.
"""

from __future__ import annotations

import random
from datetime import UTC, date, datetime
from decimal import Decimal

USD_ZAR_ANCHOR = 18.10
USD_ZAR_DAILY_STEP = 0.06
USD_ZWL = Decimal("322.0")
USD_EUR = Decimal("0.92")
USD_GBP = Decimal("0.79")
USD_BWP = Decimal("13.5")
USD_MWK = Decimal("1740.0")
USD_MZN = Decimal("64.0")

_FIXED_RATES = {
    "ZWL": USD_ZWL,
    "EUR": USD_EUR,
    "GBP": USD_GBP,
    "BWP": USD_BWP,
    "MWK": USD_MWK,
    "MZN": USD_MZN,
}

_EIGHT_DP = Decimal("0.00000001")


class HistoricalRateProvider:
    """A `RateProvider` whose answer depends on the (travelled) current day."""

    def __init__(self, seed: int, start: date, end: date) -> None:
        self._start = start
        self._usd_zar: dict[date, Decimal] = {}
        rng = random.Random(seed)
        level = USD_ZAR_ANCHOR
        day = start
        while day <= end:
            level = min(19.6, max(16.8, level + rng.gauss(0, USD_ZAR_DAILY_STEP)))
            self._usd_zar[day] = Decimal(str(round(level, 4)))
            day = date.fromordinal(day.toordinal() + 1)

    def usd_per_unit(self, currency: str, day: date) -> Decimal:
        """How many of `currency` one US dollar buys, on `day`."""
        if currency == "USD":
            return Decimal("1")
        if currency in ("ZAR", "NAD", "LSL"):
            return self._usd_zar.get(day) or self._usd_zar[max(self._usd_zar)]
        if currency in _FIXED_RATES:
            return _FIXED_RATES[currency]
        raise KeyError(currency)

    def get_rate(self, base_currency: str, quote_currency: str) -> Decimal:
        day = datetime.now(UTC).date()
        if day < self._start:
            day = self._start
        rate = self.usd_per_unit(quote_currency, day) / self.usd_per_unit(
            base_currency, day
        )
        return rate.quantize(_EIGHT_DP)
