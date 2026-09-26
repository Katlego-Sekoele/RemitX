"""Reads behind the customer dashboard and the staff operations overview.

Both surfaces need the same remittance facts — who sent, who received, the
frozen quote amounts, and the settlement leg's status — grouped in Python so
the day buckets stay in UTC on SQLite and Postgres alike.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import aliased

from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR
from remitx_api.models.orm.quote import Quote
from remitx_api.models.orm.remittance import Remittance
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_FAILED,
    TYPE_DEPOSIT,
    Transaction,
)
from remitx_api.models.orm.user import User, short_display_name


@dataclass(frozen=True)
class TransferFact:
    """One confirmed quote's settlement, from either party's side."""

    remittance_id: uuid.UUID
    created_at: datetime
    status: str
    confirmed_at: datetime | None
    sender_user_id: uuid.UUID
    beneficiary_user_id: uuid.UUID
    sender_amount: Decimal
    sender_currency: str
    receiver_amount: Decimal
    receiver_currency: str
    token_amount: Decimal
    token_name: str
    sender_name: str | None
    beneficiary_name: str | None


@dataclass(frozen=True)
class CashInFact:
    """A confirmed ZAR deposit, stamped when it was confirmed."""

    amount: Decimal
    at: datetime


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _person_name(
    full_name: str | None, first_name: str | None, last_name: str | None
) -> str | None:
    verified = (full_name or "").strip()
    if verified:
        return verified
    return short_display_name(first_name, last_name)


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


class OverviewRepository:
    def transfers_for_user(self, user_id: uuid.UUID) -> list[TransferFact]:
        """Every transfer the user sent or received, newest first."""
        sender = aliased(User)
        recipient = aliased(User)
        statement = (
            self._facts(sender, recipient)
            .where(
                or_(
                    Quote.sender_user_id == user_id,
                    Quote.beneficiary_user_id == user_id,
                )
            )
            .order_by(Remittance.created_at.desc(), Remittance.remittance_id)
        )
        return [_fact(row) for row in db.session.execute(statement)]

    def transfers_since(self, start: datetime) -> list[TransferFact]:
        """Transfers created or confirmed on or after `start` (UTC).

        A transfer created earlier and confirmed inside the window still
        belongs in that day's settled volume.
        """
        settlement = aliased(Transaction)
        sender = aliased(User)
        recipient = aliased(User)
        statement = self._facts(sender, recipient, settlement).where(
            or_(
                Remittance.created_at >= start,
                settlement.confirmed_at >= start,
            )
        )
        return [_fact(row) for row in db.session.execute(statement)]

    def failed_settlement_count(self) -> int:
        """Settlement legs currently failed, however old."""
        count = db.session.scalar(
            select(func.count(Remittance.remittance_id))
            .join(Transaction, Transaction.tx_id == Remittance.tx_id)
            .where(Transaction.status == STATUS_FAILED)
        )
        return int(count or 0)

    def confirmed_zar_cash_in_since(self, start: datetime) -> list[CashInFact]:
        """Confirmed ZAR deposits, the cash-in side of the volume chart."""
        rows = db.session.execute(
            select(
                Transaction.amount,
                Transaction.confirmed_at,
                Transaction.created_at,
            ).where(
                Transaction.type == TYPE_DEPOSIT,
                Transaction.currency == CURRENCY_ZAR,
                Transaction.status == STATUS_CONFIRMED,
                or_(
                    Transaction.confirmed_at >= start,
                    and_(
                        Transaction.confirmed_at.is_(None),
                        Transaction.created_at >= start,
                    ),
                ),
            )
        ).all()
        return [
            CashInFact(
                amount=_decimal(amount),
                at=_as_utc(confirmed_at or created_at),
            )
            for amount, confirmed_at, created_at in rows
        ]

    @staticmethod
    def _facts(sender: type[User], recipient: type[User], settlement=None):
        if settlement is None:
            settlement = aliased(Transaction)
        return (
            select(
                Remittance.remittance_id,
                Remittance.created_at,
                settlement.status,
                settlement.confirmed_at,
                Quote.sender_user_id,
                Quote.beneficiary_user_id,
                Quote.sender_amount,
                Quote.sender_currency,
                Quote.receiver_amount,
                Quote.receiver_currency,
                Quote.token_amount,
                Quote.token_name,
                sender.full_name,
                sender.first_name,
                sender.last_name,
                recipient.full_name,
                recipient.first_name,
                recipient.last_name,
            )
            .join(Quote, Quote.quote_id == Remittance.quote_id)
            .join(settlement, settlement.tx_id == Remittance.tx_id)
            .join(sender, sender.id == Quote.sender_user_id)
            .join(recipient, recipient.id == Quote.beneficiary_user_id)
        )


def _fact(row) -> TransferFact:
    (
        remittance_id,
        created_at,
        status,
        confirmed_at,
        sender_user_id,
        beneficiary_user_id,
        sender_amount,
        sender_currency,
        receiver_amount,
        receiver_currency,
        token_amount,
        token_name,
        sender_full_name,
        sender_first_name,
        sender_last_name,
        recipient_full_name,
        recipient_first_name,
        recipient_last_name,
    ) = row
    return TransferFact(
        remittance_id=remittance_id,
        created_at=_as_utc(created_at),
        status=status,
        confirmed_at=None if confirmed_at is None else _as_utc(confirmed_at),
        sender_user_id=sender_user_id,
        beneficiary_user_id=beneficiary_user_id,
        sender_amount=_decimal(sender_amount),
        sender_currency=sender_currency,
        receiver_amount=_decimal(receiver_amount),
        receiver_currency=receiver_currency,
        token_amount=_decimal(token_amount),
        token_name=token_name,
        sender_name=_person_name(sender_full_name, sender_first_name, sender_last_name),
        beneficiary_name=_person_name(
            recipient_full_name, recipient_first_name, recipient_last_name
        ),
    )
