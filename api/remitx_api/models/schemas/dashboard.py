"""The signed-in customer's overview: limits, activity, and who they pay."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from remitx_api.models.orm.transaction import TransactionStatus
from remitx_api.models.schemas.base import Schema, UtcDateTime


class LimitHeadroomRead(Schema):
    """ZAR already sent against the caller's daily and monthly allowance.

    Sent includes queued and settling transfers and leaves out ones that
    failed. The allowance is the KYC standing's limit. Both come from the
    standing, so the day and month are the SAST ones the limit check counts.
    """

    daily_limit_zar: Decimal
    daily_sent_zar: Decimal
    monthly_limit_zar: Decimal
    monthly_sent_zar: Decimal


class ActivityDayRead(Schema):
    """One UTC day of the caller's own transfers."""

    day: date
    zar_sent: Decimal
    token_received: Decimal


class InFlightTransferRead(Schema):
    """A transfer still queued or settling."""

    remittance_id: uuid.UUID
    direction: Literal["sent", "received"]
    counterparty_name: str | None
    status: TransactionStatus
    amount: Decimal
    currency: str
    created_at: UtcDateTime


class BeneficiarySpendRead(Schema):
    """How much ZAR the caller has sent to one person, failures excluded."""

    name: str
    zar_sent: Decimal


class DashboardRead(Schema):
    """Everything the account overview draws besides balances."""

    limits: LimitHeadroomRead
    # Always the last 30 UTC days, oldest first, including quiet days.
    activity: list[ActivityDayRead]
    # True once the caller has any transfer, including ones older than the
    # activity window and ones that failed.
    has_transfers: bool
    in_flight: list[InFlightTransferRead]
    # Up to six people, most ZAR sent first.
    beneficiaries: list[BeneficiarySpendRead]
