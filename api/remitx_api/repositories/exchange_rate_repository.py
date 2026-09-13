import uuid
from datetime import datetime

from sqlalchemy import select

from remitx_api.extensions import db
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.repositories.repository import Repository


class ExchangeRateRepository(Repository[ExchangeRate, uuid.UUID]):
    def __init__(self) -> None:
        super().__init__(ExchangeRate)

    def get_current_rate(
        self, base_currency: str, quote_currency: str, now: datetime
    ) -> ExchangeRate | None:
        """Newest row for this currency pair still valid to quote from, if any."""
        return db.session.scalars(
            select(ExchangeRate)
            .where(
                ExchangeRate.base_currency == base_currency,
                ExchangeRate.quote_currency == quote_currency,
                ExchangeRate.valid_until > now,
            )
            .order_by(ExchangeRate.fetched_at.desc())
        ).first()

    def get_most_recent_rate(
        self, base_currency: str, quote_currency: str
    ) -> ExchangeRate | None:
        """Newest row for this currency pair regardless of validity.
        A staleness-fallback path when a live fetch fails (see
        services/exchange_rate_service.py)."""
        return db.session.scalars(
            select(ExchangeRate)
            .where(
                ExchangeRate.base_currency == base_currency,
                ExchangeRate.quote_currency == quote_currency,
            )
            .order_by(ExchangeRate.fetched_at.desc())
        ).first()
