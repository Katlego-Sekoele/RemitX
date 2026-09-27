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

        url = _PAIR_URL.format(
            api_key=api_key, base=base_currency, quote=quote_currency
        )
        # No retry logic here; if it fails, we fall back to a stored rate.
        try:
            response = httpx.get(url, timeout=5)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RateFetchError(f"rate fetch failed: {exc}") from exc

        if payload.get("result") != "success":
            raise RateFetchError(f"rate API returned {payload.get('result')!r}")

        try:
            return Decimal(str(payload["conversion_rate"]))
        except (KeyError, ArithmeticError, TypeError, ValueError) as exc:
            raise RateFetchError(f"unexpected rate API response: {payload!r}") from exc


# Set by `use_rate_provider`. None means "the live API", built fresh per call
# so its config is read when the rate is needed, not at import.
_override: RateProvider | None = None


def rate_provider() -> RateProvider:
    """The provider `exchange_rate_service` fetches live rates from."""
    return _override if _override is not None else ExchangeRateApiProvider()


def use_rate_provider(provider: RateProvider | None) -> None:
    """Install a different rate source, or ``None`` to go back to the live API.

    For code that runs the services outside a request and must not reach the
    live API: tests, and the QA seeder (tools/seeder), which replays past days
    and needs rates for those days rather than today's.
    """
    global _override
    _override = provider
