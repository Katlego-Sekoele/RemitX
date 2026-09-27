"""Sending limits as running totals (KYC-3, #25).

What a sender has used is read from their transfers, over the current day
and calendar month in South Africa (SAST, UTC+02:00), and a send is refused
when it would take either total over the standing allowance.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
import time_machine
from remitx_api.errors.remittances import KycNotApprovedError, LimitExceededError
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR
from remitx_api.models.orm.kyc_application import KycApplication
from remitx_api.models.orm.kyc_lifecycle import KYC_TIER_VERIFIED, KycStatus
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSING,
)
from remitx_api.repositories.kyc_application_repository import (
    KycApplicationRepository,
    KycStanding,
)
from remitx_api.services.send_limits import SAST, limit_windows, require_can_send
from sqlalchemy import select
from tests.kyc_helpers import insert_application, make_user
from tests.send_helpers import record_transfer

# --- The day and the month -------------------------------------------------


def sast(*parts) -> datetime:
    return datetime(*parts, tzinfo=SAST)


@pytest.mark.parametrize(
    ("now", "day_start", "month_start"),
    [
        # The last moment of 26 September in South Africa is still that day,
        # though it is already 21:59 UTC.
        (
            datetime(2026, 9, 26, 21, 59, 59, 999999, tzinfo=UTC),
            sast(2026, 9, 26),
            sast(2026, 9, 1),
        ),
        # 22:00 UTC is midnight SAST: a new day, two hours before UTC's.
        (datetime(2026, 9, 26, 22, 0, tzinfo=UTC), sast(2026, 9, 27), sast(2026, 9, 1)),
        # Midnight SAST on the 1st starts the month as well as the day.
        (
            datetime(2026, 9, 30, 22, 0, tzinfo=UTC),
            sast(2026, 10, 1),
            sast(2026, 10, 1),
        ),
        (sast(2026, 9, 30, 23, 59, 59), sast(2026, 9, 30), sast(2026, 9, 1)),
        (sast(2026, 12, 31, 23, 59), sast(2026, 12, 31), sast(2026, 12, 1)),
    ],
)
def test_the_day_and_month_are_south_african(now, day_start, month_start):
    windows = limit_windows(now)

    assert windows.day_start == day_start
    assert windows.month_start == month_start


def test_each_window_ends_where_the_next_begins():
    windows = limit_windows(sast(2026, 12, 31, 12))

    assert windows.day_end == sast(2027, 1, 1)
    assert windows.month_end == sast(2027, 1, 1)
    assert limit_windows(sast(2026, 2, 14)).month_end == sast(2026, 3, 1)


# --- Refusing a send -------------------------------------------------------


def standing(
    *,
    status: KycStatus = KycStatus.APPROVED,
    daily_used: str = "0",
    monthly_used: str = "0",
) -> KycStanding:
    """Tier 1 (R3,000 a day, R25,000 a month) with some of it used."""
    return KycStanding(
        status=status,
        tier=KYC_TIER_VERIFIED,
        application_id=None,
        daily_limit_zar=Decimal("3000.00"),
        monthly_limit_zar=Decimal("25000.00"),
        daily_used_zar=Decimal(daily_used),
        monthly_used_zar=Decimal(monthly_used),
    )


def check(
    standing: KycStanding,
    amount: str,
    currency: str = CURRENCY_ZAR,
    *,
    in_rand: str | None = None,
) -> None:
    """Can this standing send `amount` of `currency`, worth `in_rand` (the
    amount itself, for rand)?"""
    require_can_send(
        standing,
        Decimal(in_rand or amount),
        amount=Decimal(amount),
        currency=currency,
    )


def test_exactly_what_is_left_may_be_sent():
    check(standing(daily_used="1200", monthly_used="1200"), "1800.00")


def test_one_cent_over_the_day_is_refused_with_what_is_left():
    with pytest.raises(LimitExceededError) as refused:
        check(standing(daily_used="1200", monthly_used="1200"), "1800.01")

    assert refused.value.status_code == 400
    assert refused.value.detail == (
        "This would exceed your daily limit. You can send up to R 1,800.00 today."
    )


def test_the_month_is_named_when_it_leaves_less_than_the_day():
    with pytest.raises(LimitExceededError) as refused:
        check(standing(monthly_used="24500"), "500.01")

    assert refused.value.detail == (
        "This would exceed your monthly limit. You can send up to R 500.00 this month."
    )


def test_a_used_up_day_says_when_sending_can_resume():
    with pytest.raises(LimitExceededError) as refused:
        check(standing(daily_used="3000", monthly_used="3000"), "0.01")

    assert refused.value.detail == (
        "You've reached your daily limit. You can send again tomorrow."
    )


def test_a_used_up_month_outranks_the_day():
    """Tomorrow's fresh day wouldn't help, so the month is the one to name."""
    with pytest.raises(LimitExceededError) as refused:
        check(standing(daily_used="3000", monthly_used="25000"), "1")

    assert refused.value.detail == (
        "You've reached your monthly limit. You can send again next month."
    )


@pytest.mark.parametrize(
    "status", [KycStatus.NOT_STARTED, KycStatus.SUBMITTED, KycStatus.REJECTED]
)
def test_an_unverified_sender_is_refused_before_any_limit(status):
    with pytest.raises(KycNotApprovedError) as refused:
        check(standing(status=status), "1")

    assert refused.value.status_code == 403


def test_another_currency_is_checked_by_its_rand_value():
    """The limits stay in rand. USD 97.29 at R18.50 is R1,799.87, inside
    the R1,800.00 left."""
    check(
        standing(daily_used="1200", monthly_used="1200"),
        "97.29",
        "USD",
        in_rand="1799.87",
    )


def test_a_refusal_in_another_currency_estimates_what_is_left_in_it():
    """R1,800.00 is about USD 97.29 at the send's own rate (USD 100.00 for
    R1,850.00), rounded down so the estimate itself would fit."""
    with pytest.raises(LimitExceededError) as refused:
        check(
            standing(daily_used="1200", monthly_used="1200"),
            "100.00",
            "USD",
            in_rand="1850.00",
        )

    assert refused.value.detail == (
        "This would exceed your daily limit. You can send up to R 1,800.00 "
        "(about USD 97.29) today."
    )


def test_the_monthly_estimate_uses_the_same_rate():
    with pytest.raises(LimitExceededError) as refused:
        check(standing(monthly_used="24500"), "100.00", "USD", in_rand="1850.00")

    assert refused.value.detail == (
        "This would exceed your monthly limit. You can send up to R 500.00 "
        "(about USD 27.02) this month."
    )


# --- What has been used ----------------------------------------------------


@pytest.fixture
def sender(app_context):
    user = make_user("limits-sender")
    insert_application(user.id, KycStatus.APPROVED, tier_granted=KYC_TIER_VERIFIED)
    return user


@pytest.fixture
def recipient(app_context):
    return make_user("limits-recipient")


def send(sender, recipient, amount: str, at: datetime, status=STATUS_PENDING):
    record_transfer(
        sender, recipient, sender_amount=Decimal(amount), status=status, at=at
    )
    db.session.commit()


def standing_at(user, moment: datetime) -> KycStanding:
    with time_machine.travel(moment, tick=False):
        return KycApplicationRepository().get_standing(user.id)


def test_nothing_sent_leaves_the_whole_allowance(sender):
    now = standing_at(sender, sast(2025, 6, 15, 9))

    assert now.daily_used_zar == Decimal("0.00")
    assert now.monthly_used_zar == Decimal("0.00")
    assert now.daily_remaining_zar == Decimal("3000.00")
    assert now.monthly_remaining_zar == Decimal("25000.00")


def test_everything_but_a_failed_transfer_counts(sender, recipient):
    """Committed value uses the allowance, settled or not; a failed transfer
    gives its amount back."""
    moment = sast(2025, 6, 15, 8)
    send(sender, recipient, "100", moment, STATUS_PENDING)
    send(sender, recipient, "200", moment, STATUS_PROCESSING)
    send(sender, recipient, "400", moment, STATUS_CONFIRMED)
    send(sender, recipient, "800", moment, STATUS_FAILED)

    now = standing_at(sender, sast(2025, 6, 15, 9))

    assert now.daily_used_zar == Decimal("700.00")
    assert now.monthly_used_zar == Decimal("700.00")
    assert now.daily_remaining_zar == Decimal("2300.00")
    assert now.monthly_remaining_zar == Decimal("24300.00")


def test_the_day_turns_over_at_midnight_sast(sender, recipient):
    send(sender, recipient, "1000", sast(2025, 6, 14, 23, 59, 59))
    send(sender, recipient, "500", sast(2025, 6, 15, 0, 0))

    before = standing_at(sender, sast(2025, 6, 14, 23, 59, 59, 500000))
    after = standing_at(sender, sast(2025, 6, 15, 9))

    assert before.daily_used_zar == Decimal("1000.00")
    assert after.daily_used_zar == Decimal("500.00")
    assert after.monthly_used_zar == Decimal("1500.00")


def test_the_month_turns_over_at_midnight_sast_on_the_first(sender, recipient):
    send(sender, recipient, "2000", sast(2025, 6, 10, 12))
    send(sender, recipient, "1000", sast(2025, 6, 30, 23, 59, 59))
    send(sender, recipient, "500", sast(2025, 7, 1, 0, 0))

    june = standing_at(sender, sast(2025, 6, 30, 23, 59, 59, 500000))
    july = standing_at(sender, sast(2025, 7, 1, 9))

    assert june.monthly_used_zar == Decimal("3000.00")
    assert july.monthly_used_zar == Decimal("500.00")
    assert july.daily_used_zar == Decimal("500.00")


def test_only_what_the_user_sent_counts(sender, recipient):
    """Money they received, and anyone else's sends, use none of it."""
    moment = sast(2025, 6, 15, 8)
    send(recipient, sender, "900", moment)
    send(recipient, make_user("limits-other"), "700", moment)

    now = standing_at(sender, sast(2025, 6, 15, 9))

    assert now.daily_used_zar == Decimal("0.00")
    assert now.monthly_used_zar == Decimal("0.00")


def test_another_currency_counts_the_rand_value_its_quote_locked(sender, recipient):
    moment = sast(2025, 6, 15, 8)
    record_transfer(
        sender,
        recipient,
        sender_amount=Decimal("100"),
        sender_currency="USD",
        sender_amount_zar=Decimal("1850.00"),
        at=moment,
    )
    send(sender, recipient, "500", moment)

    now = standing_at(sender, sast(2025, 6, 15, 9))

    assert now.daily_used_zar == Decimal("2350.00")
    assert now.monthly_used_zar == Decimal("2350.00")


def test_a_quote_from_before_rand_values_counts_its_amount(sender, recipient):
    """Only a ZAR quote can have no rand value: the code that wrote one
    before the column existed could send nothing else."""
    record_transfer(
        sender,
        recipient,
        sender_amount=Decimal("700"),
        sender_amount_zar=None,
        at=sast(2025, 6, 15, 8),
    )
    db.session.commit()

    assert standing_at(sender, sast(2025, 6, 15, 9)).daily_used_zar == Decimal("700.00")


def test_what_is_left_never_goes_below_zero(sender, recipient):
    """A limit lowered after sending (a re-rating) leaves nothing, not a
    negative allowance."""
    send(sender, recipient, "2000", sast(2025, 6, 15, 8))
    application = db.session.scalars(
        select(KycApplication).where(KycApplication.user_id == sender.id)
    ).one()
    application.risk_rating = "high"  # 50% of tier 1: R1,500 a day
    db.session.commit()

    now = standing_at(sender, sast(2025, 6, 15, 9))

    assert now.daily_used_zar == Decimal("2000.00")
    assert now.daily_remaining_zar == Decimal("0.00")
    assert now.monthly_remaining_zar == Decimal("10500.00")
