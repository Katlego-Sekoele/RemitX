"""When things happen: staff hours, paydays, and people's habits."""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, time, timedelta, timezone

# South Africa Standard Time. Staff work, and people get paid, in SAST; the
# database stores UTC.
SAST = timezone(timedelta(hours=2))
WORKDAY_START = time(8, 0)
WORKDAY_END = time(16, 45)


def business_time(rng: random.Random, moment: datetime) -> datetime:
    """`moment`, or the next weekday working minute in SAST after it. Staff do
    not claim applications at 3am on a Sunday."""
    local = moment.astimezone(SAST)
    while True:
        if local.weekday() >= 5:
            local = datetime.combine(
                local.date() + timedelta(days=1), WORKDAY_START, SAST
            )
            continue
        if local.time() < WORKDAY_START:
            local = datetime.combine(local.date(), WORKDAY_START, SAST)
            local += timedelta(minutes=rng.uniform(0, 90))
        if local.time() > WORKDAY_END:
            local = datetime.combine(
                local.date() + timedelta(days=1), WORKDAY_START, SAST
            )
            continue
        return local.astimezone(UTC)


def waking_time(rng: random.Random, day: date) -> datetime:
    """A moment on `day` when a customer might use the app: mostly evenings
    and lunchtimes, SAST."""
    hour = rng.choices(
        [7, 8, 12, 13, 17, 18, 19, 20, 21, 22],
        weights=[4, 4, 8, 8, 10, 14, 16, 14, 10, 5],
    )[0]
    return datetime.combine(day, time(hour, rng.randint(0, 59)), SAST).astimezone(UTC)


def last_working_day(year: int, month: int) -> date:
    first_next = date(year + (month == 12), month % 12 + 1, 1)
    day = first_next - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def paydays(kind: str, start: date, end: date) -> list[date]:
    """Paydays of one kind between `start` and `end` inclusive.

    `25th`: the 25th, or the Friday before when it falls on a weekend.
    `month_end`: the last weekday of the month. `weekly_friday`: every Friday.
    """
    days: list[date] = []
    if kind == "weekly_friday":
        day = start + timedelta(days=(4 - start.weekday()) % 7)
        while day <= end:
            days.append(day)
            day += timedelta(days=7)
        return days
    year, month = start.year, start.month
    while date(year, month, 1) <= end:
        if kind == "25th":
            day = date(year, month, 25)
            while day.weekday() >= 5:
                day -= timedelta(days=1)
        else:
            day = last_working_day(year, month)
        if start <= day <= end:
            days.append(day)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return days
