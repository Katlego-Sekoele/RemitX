from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_USD, CURRENCY_ZAR
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.services import exchange_rate_service
from remitx_api.services.exchange_rate_provider import RateFetchError


def _store_rate(fetched_at: datetime, valid_until: datetime) -> ExchangeRate:
    rate = ExchangeRate(
        base_currency=CURRENCY_USD,
        quote_currency=CURRENCY_ZAR,
        rate=Decimal("18.50"),
        fetched_at=fetched_at,
        valid_until=valid_until,
    )
    db.session.add(rate)
    db.session.commit()
    return rate


def test_valid_stored_rate_is_reused_without_a_live_fetch(app_context, monkeypatch):
    now = datetime.now(UTC)
    _store_rate(now, now + timedelta(hours=1))

    def _fail(*args, **kwargs):
        raise AssertionError("should not fetch live when a valid rate exists")

    monkeypatch.setattr(
        "remitx_api.services.exchange_rate_provider.ExchangeRateApiProvider.get_rate",
        _fail,
    )

    rate = exchange_rate_service.get_active_rate(
        base_currency=CURRENCY_USD, quote_currency=CURRENCY_ZAR, now=now
    )
    assert rate.rate == Decimal("18.50")


def test_expired_rate_triggers_a_live_fetch_and_store(app_context, monkeypatch):
    now = datetime.now(UTC)
    _store_rate(now - timedelta(hours=2), now - timedelta(hours=1))

    monkeypatch.setattr(
        "remitx_api.services.exchange_rate_provider.ExchangeRateApiProvider.get_rate",
        lambda self, base, quote: Decimal("19.00"),
    )

    rate = exchange_rate_service.get_active_rate(
        base_currency=CURRENCY_USD, quote_currency=CURRENCY_ZAR, now=now
    )
    assert rate.rate == Decimal("19.00")
    # SQLite drops the tz offset on the value re-read after commit.
    valid_until = rate.valid_until.replace(tzinfo=UTC)
    assert valid_until > now


def test_provider_failure_falls_back_to_a_recent_stored_rate(app_context, monkeypatch):
    now = datetime.now(UTC)
    # Expired for quoting, but recent enough to fall back to.
    _store_rate(now - timedelta(hours=2), now - timedelta(hours=1))

    def _fail(self, base, quote):
        raise RateFetchError("network unreachable")

    monkeypatch.setattr(
        "remitx_api.services.exchange_rate_provider.ExchangeRateApiProvider.get_rate",
        _fail,
    )

    rate = exchange_rate_service.get_active_rate(
        base_currency=CURRENCY_USD, quote_currency=CURRENCY_ZAR, now=now
    )
    assert rate.rate == Decimal("18.50")


def test_provider_failure_with_no_recent_rate_refuses_to_quote(
    app_context, monkeypatch
):
    now = datetime.now(UTC)
    # Too stale to fall back to (older than MAX_RATE_STALENESS_HOURS).
    _store_rate(now - timedelta(hours=40), now - timedelta(hours=39))

    def _fail(self, base, quote):
        raise RateFetchError("network unreachable")

    monkeypatch.setattr(
        "remitx_api.services.exchange_rate_provider.ExchangeRateApiProvider.get_rate",
        _fail,
    )

    with pytest.raises(exchange_rate_service.RateUnavailableError):
        exchange_rate_service.get_active_rate(
            base_currency=CURRENCY_USD, quote_currency=CURRENCY_ZAR, now=now
        )


def test_unsupported_currency_is_rejected_without_touching_repo_or_provider(
    app_context, monkeypatch
):
    def _fail(*args, **kwargs):
        raise AssertionError("should not fetch live for an unsupported currency")

    monkeypatch.setattr(
        "remitx_api.services.exchange_rate_provider.ExchangeRateApiProvider.get_rate",
        _fail,
    )

    with pytest.raises(exchange_rate_service.UnsupportedCurrencyError):
        exchange_rate_service.get_active_rate(
            base_currency="EUR", quote_currency=CURRENCY_ZAR
        )

    with pytest.raises(exchange_rate_service.UnsupportedCurrencyError):
        exchange_rate_service.get_active_rate(
            base_currency=CURRENCY_USD, quote_currency="EUR"
        )


class _FixedProvider:
    def __init__(self, rate: Decimal) -> None:
        self.rate = rate
        self.calls: list[tuple[str, str]] = []

    def get_rate(self, base_currency: str, quote_currency: str) -> Decimal:
        self.calls.append((base_currency, quote_currency))
        return self.rate


def test_an_installed_provider_replaces_the_live_api(app_context, monkeypatch):
    from remitx_api.services.exchange_rate_provider import use_rate_provider

    def _fail(*args, **kwargs):
        raise AssertionError("the live API must not be called")

    monkeypatch.setattr(
        "remitx_api.services.exchange_rate_provider.ExchangeRateApiProvider.get_rate",
        _fail,
    )
    provider = _FixedProvider(Decimal("17.25"))
    use_rate_provider(provider)
    try:
        rate = exchange_rate_service.get_active_rate(
            base_currency=CURRENCY_USD, quote_currency=CURRENCY_ZAR
        )
    finally:
        use_rate_provider(None)

    assert rate.rate == Decimal("17.25")
    assert provider.calls == [(CURRENCY_USD, CURRENCY_ZAR)]


def test_clearing_the_provider_goes_back_to_the_live_api(app_context, monkeypatch):
    from remitx_api.services.exchange_rate_provider import (
        ExchangeRateApiProvider,
        rate_provider,
        use_rate_provider,
    )

    use_rate_provider(_FixedProvider(Decimal("1")))
    use_rate_provider(None)

    assert isinstance(rate_provider(), ExchangeRateApiProvider)
