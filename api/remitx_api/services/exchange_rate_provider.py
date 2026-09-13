"""Live FX rate source for quote generation.

Kept behind a small interface so the live API can be swapped for a fake in
tests without monkeypatching httpx directly.
"""

from decimal import Decimal
from typing import Protocol

import httpx

from remitx_api.config import Config

_PAIR_URL = "https://v6.exchangerate-api.com/v6/{api_key}/pair/{base}/{quote}"


class RateFetchError(Exception):
    """The live rate API could not be reached, or returned something we
    can't use — caught by services/exchange_rate_service.py, which decides whether to
    fall back to a stored rate or refuse to quote."""


class RateProvider(Protocol):
    def get_rate(self, base_currency: str, quote_currency: str) -> Decimal: ...


class ExchangeRateApiProvider:
    """https://www.exchangerate-api.com/docs/pair-conversion-requests"""

    def __init__(self, config: Config | None = None) -> None:
        self._config = config or Config()

    def get_rate(self, base_currency: str, quote_currency: str) -> Decimal:
        api_key = self._config.EXCHANGE_RATE_API_KEY
        if not api_key:
            raise RateFetchError("EXCHANGE_RATE_API_KEY is not configured")

        # Build the API URL
        url = _PAIR_URL.format(
            api_key=api_key, base=base_currency, quote=quote_currency
        )
        # Try to fetch the rate from the external API 
        # (No retry logic here; if it fails, we fall back to a stored rate)
        try:
            response = httpx.get(url, timeout=5) 
            response.raise_for_status() # Raise an error for non-2xx responses # TODO: Consider if this is neeeded or nto
            payload = response.json() # Parse the JSON response
        except (httpx.HTTPError, ValueError) as exc:
            raise RateFetchError(f"rate fetch failed: {exc}") from exc

        if payload.get("result") != "success":
            raise RateFetchError(f"rate API returned {payload.get('result')!r}")

        # If the API response is successful, extract the conversion rate
        try:
            return Decimal(str(payload["conversion_rate"]))
        except (KeyError, ArithmeticError, TypeError, ValueError) as exc:
            raise RateFetchError(f"unexpected rate API response: {payload!r}") from exc
