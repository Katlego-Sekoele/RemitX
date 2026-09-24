"""One real seed run against a migrated Postgres, then what it must have made.

This is the test that keeps the seeder honest while the backend changes: it
drives the real controllers, services and worker tasks, so a changed rule or
signature fails here, in the PR that changed it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from remitx_seeder.clerk import FakeClerkGateway
from remitx_seeder.engine import run_seed
from remitx_seeder.scenario import Scenario
from remitx_seeder.settlement import SYNTHETIC_HASH_PREFIX
from remitx_seeder.storage import MemoryStorage

EXISTING_CLERK_USERS = 70
CLERK_CAP = 80


@pytest.fixture(scope="module")
def run(database):
    clerk = FakeClerkGateway(existing_users=EXISTING_CLERK_USERS)
    storage = MemoryStorage()
    events: list[dict] = []
    scenario = Scenario(
        name="test",
        days=40,
        senders=14,
        recipients={"ZW": 5, "NA": 2, "ZA": 4, "US": 2},
        clerk_user_cap=CLERK_CAP,
    )
    summary = run_seed(
        scenario,
        clerk=clerk,
        clerk_enabled=True,
        storage=storage,
        emit=events.append,
    )
    return {
        "summary": summary,
        "clerk": clerk,
        "storage": storage,
        "events": events,
        "db": database,
    }


def query(run, statement):
    db = run["db"]
    token = db.open_session()
    try:
        return db.session.execute(statement).all()
    finally:
        db.close_session(token)


def test_the_backend_refused_nothing(run):
    assert run["summary"]["refusals"] == []


def test_every_business_rule_holds(run):
    report = run["summary"]["verify"]
    broken = [f for f in report["findings"] if f["severity"] == "error" and not f["ok"]]
    assert report["ok"], broken


def test_the_run_covers_the_whole_journey(run):
    counts = run["summary"]["counts"]
    for key in (
        "people.sender",
        "people.recipient",
        "people.staff",
        "kyc.submitted",
        "kyc.approved",
        "kyc.rejected",
        "kyc.more_info_requested",
        "kyc.documents",
        "money.beneficiaries",
        "deposits.matched",
        "send.quotes",
        "send.remittances",
        "settlement.settled",
    ):
        assert counts.get(key, 0) > 0, key


def test_edge_cases_are_guaranteed(run):
    from remitx_api.models.orm.kyc_application import KycApplication

    statuses = {row[0] for row in query(run, select(KycApplication.status))}
    assert {"approved", "rejected", "more_info_required", "in_progress"} <= statuses
    peps = query(
        run,
        select(KycApplication.pep_relationship, KycApplication.status).where(
            KycApplication.pep_relationship.is_not(None)
        ),
    )
    assert {relationship for relationship, _ in peps} >= {
        "self",
        "immediate_family_member",
    }
    tier_two = query(
        run, select(KycApplication.tier_granted).where(KycApplication.tier_granted == 2)
    )
    assert tier_two


def test_clerk_accounts_stop_at_the_cap(run):
    made = len(run["clerk"].users)
    assert made == CLERK_CAP - EXISTING_CLERK_USERS
    assert run["summary"]["counts"]["people.database_only"] > 0


def test_staff_decide_and_applicants_never_review_themselves(run):
    from remitx_api.models.orm.kyc_application import KycApplication
    from remitx_api.models.orm.kyc_decision import KycDecision

    rows = query(
        run,
        select(KycDecision.decided_by_user_id, KycApplication.user_id).join(
            KycApplication, KycApplication.application_id == KycDecision.application_id
        ),
    )
    assert rows
    assert all(decider != applicant for decider, applicant in rows)


def test_history_is_spread_over_the_window(run):
    from remitx_api.models.orm.user import User

    ((earliest, latest),) = query(
        run, select(func.min(User.created_at), func.max(User.created_at))
    )
    assert (latest - earliest).days >= 30


def test_documents_went_through_the_real_upload_path(run):
    from remitx_api.models.orm.kyc_document import KycDocument
    from remitx_api.services.file_signatures import sniff_content_type

    stored = query(run, select(KycDocument.storage_path, KycDocument.status))
    assert stored and all(status == "stored" for _, status in stored)
    objects = run["storage"].objects
    for path, _ in stored:
        body, content_type, _ = objects[path]
        assert sniff_content_type(body[:512]) == content_type


def test_settlement_used_only_synthetic_hashes_and_topped_up_the_treasury(run):
    from remitx_api.models.orm.transaction import (
        TYPE_TOKEN_BURN,
        TYPE_TREASURY_FUNDING,
        Transaction,
    )

    hashes = [
        row[0]
        for row in query(
            run,
            select(Transaction.xrpl_tx_hash).where(
                Transaction.type == TYPE_TOKEN_BURN,
                Transaction.xrpl_tx_hash.is_not(None),
            ),
        )
    ]
    assert hashes and all(h.startswith(SYNTHETIC_HASH_PREFIX) for h in hashes)
    burned = sum(
        (
            row[0]
            for row in query(
                run,
                select(Transaction.amount).where(
                    Transaction.type == TYPE_TOKEN_BURN,
                    Transaction.status == "confirmed",
                ),
            )
        ),
        Decimal("0"),
    )
    top_ups = [
        row[0]
        for row in query(
            run,
            select(Transaction.amount).where(Transaction.type == TYPE_TREASURY_FUNDING),
        )
    ]
    assert top_ups == [burned]
    assert Decimal(run["summary"]["simulated_burn_total"]) == burned


def test_progress_is_reported(run):
    assert any(event["type"] == "progress" for event in run["events"])


def test_verify_catches_a_broken_ledger(run):
    from remitx_api.models.orm.account import Account
    from sqlalchemy import update

    from remitx_seeder.verify import run_verify

    db = run["db"]
    token = db.open_session()
    try:
        account = db.session.scalars(
            select(Account).where(Account.account_balance > 0, Account.type == "USER")
        ).first()
        original = account.account_balance
        db.session.execute(
            update(Account)
            .where(Account.account_id == account.account_id)
            .values(account_balance=original + 1)
        )
        report = run_verify(db.session)
        db.session.rollback()
    finally:
        db.close_session(token)
    assert not report.ok
    assert [f.check for f in report.errors] == ["ledger.balances"]


def test_the_live_tail_signs_in_calls_the_api_and_respects_its_budget(run):
    import json
    import random
    from datetime import UTC, datetime

    import httpx
    from remitx_api.models.orm.beneficiary import Beneficiary
    from remitx_api.models.orm.user import User

    from remitx_seeder.clock import SimClock
    from remitx_seeder.context import RunContext, SeededPerson
    from remitx_seeder.generators.personas import build_sender
    from remitx_seeder.live_tail import make_live_tail

    senders = query(
        run,
        select(User, Beneficiary)
        .join(Beneficiary, Beneficiary.sender_user_id == User.id)
        .where(User.clerk_user_id.like("user_%")),
    )
    assert len({user.id for user, _ in senders}) >= 2
    scenario = Scenario(live_settlements=3, live_token_budget=25)
    ctx = RunContext(
        scenario=scenario,
        run_id="live-test",
        clock=SimClock(),
        clerk=run["clerk"],
        emit=lambda event: None,
        window_start=datetime.now(UTC),
        window_end=datetime.now(UTC),
    )
    seen: set = set()
    for user, beneficiary in senders:
        if user.id in seen:
            continue
        seen.add(user.id)
        person = SeededPerson(
            build_sender(
                random.Random(1),
                f"live{len(seen)}",
                datetime.now(UTC).date(),
                pep_rate=0,
                other_source_rate=0,
                high_volume_rate=0,
            ),
            user_id=user.id,
            clerk_user_id=user.clerk_user_id,
            email=user.email,
            base_reference=user.base_reference,
            verified=True,
        )
        person.beneficiaries.append(
            {
                "beneficiary_id": beneficiary.beneficiary_id,
                "user_id": beneficiary.linked_user_id,
                "currency": beneficiary.payout_currency,
            }
        )
        ctx.people[person.key] = person

    requests: list[httpx.Request] = []
    token_amounts = iter(["10.50", "20.00", "1.00"])

    def api(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST" and request.url.path == "/quotes":
            return httpx.Response(
                200, json={"quote_id": "q1", "token_amount": next(token_amounts)}
            )
        if request.method == "POST" and request.url.path == "/remittances":
            assert json.loads(request.content) == {"quote_id": "q1"}
            return httpx.Response(200, json={"remittance_id": "r1"})
        if request.url.path == "/remittances/r1":
            return httpx.Response(
                200, json={"status": "confirmed", "xrpl_tx_hash": "ABC123"}
            )
        return httpx.Response(404)

    live_tail = make_live_tail(
        "http://api.test",
        "http://origin.test",
        transport=httpx.MockTransport(api),
        poll_seconds=0,
    )
    result = live_tail(ctx)

    statuses = [send["status"] for send in result["sends"]]
    assert statuses == ["confirmed", "over_budget"]
    assert result["spent"] == "10.50"
    first = requests[0]
    assert first.headers["Authorization"].startswith("Bearer fake-token-for-user_")
    assert first.headers["Origin"] == "http://origin.test"
    assert [r.url.path for r in requests].count("/remittances") == 1
