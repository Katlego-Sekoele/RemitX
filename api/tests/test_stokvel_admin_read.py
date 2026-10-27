"""Rules for admin manual release readiness."""

import uuid
from datetime import UTC, datetime

from remitx_api.repositories.stokvel_contribution_repository import (
    StokvelContributionRepository,
)
from remitx_api.services.stokvel_admin_read import (
    admin_list_manual_release_allowed,
    round_manual_release_allowed,
)

_CYCLE = uuid.uuid4()
_MEMBERS = 3
_PAST = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
_FUTURE = datetime(2099, 6, 1, 12, 0, tzinfo=UTC)
_PAID = {uuid.uuid4(), uuid.uuid4(), uuid.uuid4()}


def test_manual_release_when_fully_paid_and_due(monkeypatch):
    monkeypatch.setattr(
        StokvelContributionRepository,
        "get_paid_member_ids",
        lambda self, cycle_id, round_: _PAID if round_ in (0, 1) else set(),
    )
    assert round_manual_release_allowed(
        cycle_id=_CYCLE,
        round_=0,
        total_rounds=_MEMBERS,
        payout_time=_PAST,
    )


def test_manual_release_before_payout_time(monkeypatch):
    monkeypatch.setattr(
        StokvelContributionRepository,
        "get_paid_member_ids",
        lambda self, cycle_id, round_: _PAID,
    )
    assert not round_manual_release_allowed(
        cycle_id=_CYCLE,
        round_=0,
        total_rounds=_MEMBERS,
        payout_time=_FUTURE,
    )


def test_manual_release_needs_next_round_unless_last(monkeypatch):
    monkeypatch.setattr(
        StokvelContributionRepository,
        "get_paid_member_ids",
        lambda self, cycle_id, round_: _PAID if round_ == 0 else set(),
    )
    assert not round_manual_release_allowed(
        cycle_id=_CYCLE,
        round_=0,
        total_rounds=_MEMBERS,
        payout_time=_PAST,
    )
    monkeypatch.setattr(
        StokvelContributionRepository,
        "get_paid_member_ids",
        lambda self, cycle_id, round_: _PAID if round_ == 2 else set(),
    )
    assert round_manual_release_allowed(
        cycle_id=_CYCLE,
        round_=2,
        total_rounds=_MEMBERS,
        payout_time=_PAST,
    )


def test_the_rounds_list_hides_release_while_not_pending(monkeypatch):
    monkeypatch.setattr(
        StokvelContributionRepository,
        "get_paid_member_ids",
        lambda self, cycle_id, round_: _PAID,
    )
    for status in ("processing", "failed", "released"):
        assert not admin_list_manual_release_allowed(
            cycle_id=_CYCLE,
            round_=0,
            total_rounds=_MEMBERS,
            payout_time=_PAST,
            release_status=status,
        )
    assert admin_list_manual_release_allowed(
        cycle_id=_CYCLE,
        round_=0,
        total_rounds=_MEMBERS,
        payout_time=_PAST,
        release_status="pending",
    )
