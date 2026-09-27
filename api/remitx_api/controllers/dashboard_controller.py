"""Builds the customer dashboard from standing limits and transfer facts."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from remitx_api.models.orm.transaction import (
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSING,
)
from remitx_api.models.schemas.dashboard import (
    ActivityDayRead,
    BeneficiarySpendRead,
    DashboardRead,
    InFlightTransferRead,
    LimitHeadroomRead,
)
from remitx_api.repositories.kyc_application_repository import KycApplicationRepository
from remitx_api.repositories.overview_repository import OverviewRepository, TransferFact

WINDOW_DAYS = 30
TOP_BENEFICIARIES = 6
IN_FLIGHT_LIMIT = 5
AMOUNT_QUANTUM = Decimal("0.01")

DIRECTION_SENT = "sent"
DIRECTION_RECEIVED = "received"
_IN_FLIGHT = (STATUS_PENDING, STATUS_PROCESSING)


def _money(value: Decimal) -> Decimal:
    return value.quantize(AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)


def _midnight(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


class DashboardController:
    def __init__(self) -> None:
        self._overview = OverviewRepository()
        self._applications = KycApplicationRepository()

    def get_dashboard(self, user_id: uuid.UUID) -> DashboardRead:
        now = datetime.now(UTC)
        today = _midnight(now)
        window_start = today - timedelta(days=WINDOW_DAYS - 1)
        days = [
            window_start.date() + timedelta(days=offset)
            for offset in range(WINDOW_DAYS)
        ]

        # Limits and what was sent against them, as the limit check counts it.
        standing = self._applications.get_standing(user_id)
        facts = self._overview.transfers_for_user(user_id)

        sent_by_day: dict = defaultdict(lambda: Decimal("0"))
        received_by_day: dict = defaultdict(lambda: Decimal("0"))
        paid: dict[uuid.UUID, tuple[str, Decimal]] = {}
        in_flight: list[InFlightTransferRead] = []

        for fact in facts:
            sent = fact.sender_user_id == user_id
            counts = fact.status != STATUS_FAILED
            # Every currency's sends, at the rand value each quote locked.
            if sent and counts:
                if fact.created_at >= window_start:
                    sent_by_day[fact.created_at.date()] += fact.sender_amount_zar
                name = fact.beneficiary_name or "Unnamed"
                current = paid.get(fact.beneficiary_user_id)
                paid[fact.beneficiary_user_id] = (
                    name,
                    (current[1] if current else Decimal("0")) + fact.sender_amount_zar,
                )
            if not sent and counts and fact.created_at >= window_start:
                received_by_day[fact.created_at.date()] += fact.receiver_amount
            if fact.status in _IN_FLIGHT and len(in_flight) < IN_FLIGHT_LIMIT:
                in_flight.append(_in_flight(fact, user_id))

        beneficiaries = sorted(paid.values(), key=lambda item: (-item[1], item[0]))[
            :TOP_BENEFICIARIES
        ]

        return DashboardRead(
            limits=LimitHeadroomRead(
                daily_limit_zar=_money(standing.daily_limit_zar),
                daily_sent_zar=_money(standing.daily_used_zar),
                monthly_limit_zar=_money(standing.monthly_limit_zar),
                monthly_sent_zar=_money(standing.monthly_used_zar),
            ),
            activity=[
                ActivityDayRead(
                    day=day,
                    zar_sent=_money(sent_by_day[day]),
                    payout_received=_money(received_by_day[day]),
                )
                for day in days
            ],
            has_transfers=bool(facts),
            in_flight=in_flight,
            beneficiaries=[
                BeneficiarySpendRead(name=name, zar_sent=_money(amount))
                for name, amount in beneficiaries
            ],
        )


def _in_flight(fact: TransferFact, user_id: uuid.UUID) -> InFlightTransferRead:
    sent = fact.sender_user_id == user_id
    return InFlightTransferRead(
        remittance_id=fact.remittance_id,
        direction=DIRECTION_SENT if sent else DIRECTION_RECEIVED,
        counterparty_name=fact.beneficiary_name if sent else fact.sender_name,
        status=fact.status,
        amount=_money(fact.sender_amount if sent else fact.receiver_amount),
        currency=fact.sender_currency if sent else fact.receiver_currency,
        created_at=fact.created_at,
    )
