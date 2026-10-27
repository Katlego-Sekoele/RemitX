"""The three things the brief's demo must show going wrong safely (R6-05,
#270; brief §2): a round blocked because one member has not paid, a
duplicate contribution, and an early finalisation, each refused.

The contract's own tests cover each rule on-chain. These run them through
the API and the worker, on the same setup and fake vault as the three-round
test (test_stokvel_three_rounds.py), to show the platform refuses too, says
why, and moves no money. Each case also shows the way out: the blocked round
releases once the last member pays, and the early round once its payout time
has passed.
"""

# The shared fixtures are imported by name, which pytest needs and ruff
# reads as unused or redefined.
# ruff: noqa: F401, F811

import time
from decimal import Decimal

import pytest
from remitx_api.extensions import db
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.stokvel_contribution import StokvelContribution
from sqlalchemy import select
from tests.rbac_helpers import grant_permissions, seed_rbac_catalogue
from tests.test_stokvel_setup_route import _in_session, _person, _refused
from tests.test_stokvel_three_rounds import (
    OPENING_ZAR,
    PAID_OUT,
    _pay_round,
    _payouts,
    _set_up,
    _sync_and_settle,
    _zar_balance,
    broker,
    platform,
    rates,
    vault,
)


@pytest.fixture
def admin(platform):
    """A compliance officer who may release a round by hand (P5)."""
    person = _person("admin")

    def grant():
        seed_rbac_catalogue()
        grant_permissions(person.id, PermissionCode.STOKVEL_ROUND_FINALISE)

    _in_session(grant)
    return person


def _contributions(session_factory, member_id) -> list[StokvelContribution]:
    with session_factory() as session:
        rows = session.scalars(
            select(StokvelContribution).where(
                StokvelContribution.member_id == member_id
            )
        ).all()
        session.expunge_all()
        return rows


def _settled_to(platform, group, member, payout) -> None:
    """The payout reached `member`'s beneficiary, confirmed and burnt."""
    assert payout.member_id == group.member_ids[member]
    assert payout.remittance_status == "confirmed"
    assert _zar_balance(platform.session, group.recipients[member]) == PAID_OUT


# --- a blocked round -----------------------------------------------------------


def test_a_round_stays_blocked_until_the_last_member_pays(
    platform, vault, broker, admin
):
    """Round 0 is fully paid and due, but Lerato has not paid round 1, so
    Thandi's payout is held (D5, P2). Nothing releases it, the admin's
    button included. It is blocked, not lost: Lerato's payment releases it."""
    api = platform.api
    group = _set_up(platform, vault, broker)
    thandi, sipho, lerato = group.order
    _pay_round(platform, broker, group, 0)
    _pay_round(platform, broker, group, 1, members=(thandi, sipho))

    assert _sync_and_settle(broker) == []
    assert _payouts(platform.session) == {}
    _refused(api.finalise(admin, group.stokvel_id, 0), 409, "round_not_finalisable")
    assert broker.messages == []
    screen = api.stokvel(thandi, group.stokvel_id).json()
    assert screen["open_round"] == 1
    assert screen["cycle"]["rounds"][0]["release_status"] is None
    paid_round_1 = {c["member_id"] for c in screen["contributions"] if c["round"] == 1}
    assert paid_round_1 == {
        str(group.member_ids[thandi]),
        str(group.member_ids[sipho]),
    }

    _pay_round(platform, broker, group, 1, members=(lerato,))
    _sync_and_settle(broker)

    payouts = _payouts(platform.session)
    assert sorted(payouts) == [0]
    _settled_to(platform, group, thandi, payouts[0])


# --- a duplicate contribution ----------------------------------------------------


def test_a_second_contribution_to_the_same_round_is_refused(platform, vault, broker):
    """Thandi pays round 0, then presses Pay again: 409, and she is not
    debited twice. The contract never sees the second payment."""
    api = platform.api
    group = _set_up(platform, vault, broker)
    thandi = group.order[0]
    _pay_round(platform, broker, group, 0, members=(thandi,))
    balance = _zar_balance(platform.session, thandi)

    _refused(api.contribute(thandi, group.stokvel_id), 409, "contribution_already_paid")

    assert broker.messages == []
    assert _zar_balance(platform.session, thandi) == balance
    rows = _contributions(platform.session, group.member_ids[thandi])
    assert [(row.round, row.status) for row in rows] == [(0, "confirmed")]
    assert vault.contributes == [(0, group.member_ids[thandi])]


def test_a_contribution_message_delivered_twice_pays_once(platform, vault, broker):
    """The broker delivers Sipho's contribution twice, as a redelivery does:
    the contract is called once and he is debited once."""
    api = platform.api
    group = _set_up(platform, vault, broker)
    sipho = group.order[1]
    response = api.contribute(sipho, group.stokvel_id)
    assert response.status_code == 201, response.text
    body = response.json()
    debit = Decimal(body["amount_fiat"]) + Decimal(body["fee_amount"])
    broker.messages.append(broker.messages[0])

    broker.deliver()

    assert vault.contributes == [(0, group.member_ids[sipho])]
    rows = _contributions(platform.session, group.member_ids[sipho])
    assert [(row.round, row.status) for row in rows] == [(0, "confirmed")]
    # The member's ZAR moves when the contribution is confirmed, once
    assert _zar_balance(platform.session, sipho) == OPENING_ZAR - debit


# --- an early finalisation -------------------------------------------------------


def test_an_early_finalise_is_refused_until_the_payout_time(
    platform, vault, broker, admin
):
    """Rounds 0 and 1 are fully paid, but round 0's payout time is an hour
    away (D12). The admin's Release payout is refused and nothing is
    queued. Once the time has passed, the same button releases the round;
    pressing it again is refused as already released."""
    api = platform.api
    group = _set_up(platform, vault, broker, due=False)
    _pay_round(platform, broker, group, 0)
    _pay_round(platform, broker, group, 1)
    assert _sync_and_settle(broker) == []

    _refused(api.finalise(admin, group.stokvel_id, 0), 409, "round_not_finalisable")
    assert broker.messages == []
    assert _payouts(platform.session) == {}

    vault.now = lambda: time.time() + 2 * 60 * 60
    released = api.finalise(admin, group.stokvel_id, 0)
    assert released.status_code == 202, released.text
    assert [name for name, _ in broker.deliver()] == ["release_pool"]
    _sync_and_settle(broker)

    payouts = _payouts(platform.session)
    assert sorted(payouts) == [0]
    _settled_to(platform, group, group.order[0], payouts[0])
    _refused(api.finalise(admin, group.stokvel_id, 0), 409, "round_already_finalised")
