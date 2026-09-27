import httpx
import pytest
from remitx_api.config import Config
from remitx_api.services.exchange_rate_provider import (
    ExchangeRateApiProvider,
    RateFetchError,
)


def test_failed_fetch_redacts_api_key_from_error_and_its_cause(monkeypatch):
    """The request URL embeds the API key. A failed request must not leak it —
    neither in the RateFetchError message nor in the chained httpx exception
    (exc_info=True logging of the RateFetchError also prints the cause)."""
    monkeypatch.setenv("EXCHANGE_RATE_API_KEY", "supersecretkey123")

    def _fake_get(url, timeout):
        assert "supersecretkey123" in url
        request = httpx.Request("GET", url)
        return httpx.Response(500, request=request, text="boom")

    monkeypatch.setattr(httpx, "get", _fake_get)

    provider = ExchangeRateApiProvider(Config())
    with pytest.raises(RateFetchError) as exc_info:
        provider.get_rate("USD", "ZAR")

    assert "supersecretkey123" not in str(exc_info.value)

    cause = exc_info.value.__cause__
    assert cause is not None
    assert "supersecretkey123" not in str(cause)
    assert "***" in str(cause)
