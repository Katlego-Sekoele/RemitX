"""The signed-in customer's overview: limits, activity, and who they pay."""

import uuid
from datetime import date
from typing import Literal

from remitx_api.models.orm.transaction import TransactionStatus
from remitx_api.models.schemas.base import LedgerDecimal, Schema, UtcDateTime


class LimitHeadroomRead(Schema):
    """ZAR already sent against the caller's daily and monthly allowance.

    Sent includes queued and settling transfers and leaves out ones that
    failed. The allowance is the KYC standing's limit. Both come from the
    standing, so the day and month are the SAST ones the limit check counts.
    """

    daily_limit_zar: LedgerDecimal
    daily_sent_zar: LedgerDecimal
    monthly_limit_zar: LedgerDecimal
    monthly_sent_zar: LedgerDecimal


class ActivityDayRead(Schema):
    """One UTC day of the caller's own transfers."""

    day: date
    zar_sent: LedgerDecimal
    # Sum of `receiver_amount` on transfers received that day (each in its
    # quote's payout currency).
    payout_received: LedgerDecimal


class InFlightTransferRead(Schema):
    """A transfer still queued or settling."""

    remittance_id: uuid.UUID
    direction: Literal["sent", "received"]
    counterparty_name: str | None
    status: TransactionStatus
    amount: LedgerDecimal
    currency: str
    created_at: UtcDateTime


class BeneficiarySpendRead(Schema):
    """How much ZAR the caller has sent to one person, failures excluded."""

    name: str
    zar_sent: LedgerDecimal


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
