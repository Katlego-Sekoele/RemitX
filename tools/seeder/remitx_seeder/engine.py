"""One seed run, start to finish.

1. **Preflight.** The platform accounts must exist — `alembic upgrade head`
   creates them — since every deposit and fee needs them. Staff roles are
   granted as the target's IAM admin if it has one, and with no granter
   otherwise.
2. **Plan.** Build the people from the scenario and the data files, decide
   who gets a Clerk account (staff first, then senders who can finish KYC,
   then other senders, then recipients, up to the cap), and put their
   sign-ups on the timeline.
3. **Replay.** Run the timeline over the last `days` days (sim.py). Stories
   schedule their own follow-ups.
4. **Top up the treasury** by what simulated burns took (direct.py).
5. **Verify** the whole database.
6. **Live tail**, when asked: a few real settlements through the API.

The caller (runner.py) loads the target's environment, checks the guards and
initialises the database before calling `run_seed`.
"""

from __future__ import annotations

import time
import uuid
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta

from remitx_seeder.clerk import ClerkGateway
from remitx_seeder.clock import SimClock
from remitx_seeder.context import Emit, RunContext, SeededPerson
from remitx_seeder.generators.personas import (
    STANDARD_MONTHLY_LIMIT_ZAR,
    build_recipient,
    build_sender,
    build_staff,
    declare_pep,
    declare_source_of_wealth,
)
from remitx_seeder.rates import HistoricalRateProvider
from remitx_seeder.scenario import Scenario
from remitx_seeder.settlement import SimulatedSettlement
from remitx_seeder.sim import Simulation
from remitx_seeder.storage import RealTimeStorage
from remitx_seeder.stories import people as people_story
from remitx_seeder.stories.kyc import (
    PATH_ABANDON,
    PATH_APPROVE,
    PATH_MORE_INFO,
    PATH_MORE_INFO_NO_REPLY,
    PATH_NEVER,
    PATH_REJECT,
    KycStory,
    plan_path,
)
from remitx_seeder.stories.money import MoneyStory

# Recipients who live where RemitX operates verify at this rate.
RECIPIENT_VERIFY_RATE = 0.5
# The replay stops a few minutes short of now, so nothing lands in the future.
WINDOW_END_MARGIN = timedelta(minutes=5)


class PreflightError(RuntimeError):
    """The target is not ready to be seeded."""


def preflight() -> uuid.UUID | None:
    """Who staff roles are granted as: the target's IAM admin, or None when it
    has none — a freshly migrated or Reset target — in which case the grants
    record no granter, as the migrations' own catalogue grants do. Raises when
    the platform accounts are missing."""
    from remitx_api.config import Config
    from remitx_api.extensions import db
    from remitx_api.models.orm.account import (
        PAYOUT_CURRENCIES,
        TYPE_PLATFORM_FIAT,
        TYPE_PLATFORM_REVENUE,
    )
    from remitx_api.models.orm.role import Role
    from remitx_api.models.orm.user_role import UserRole
    from remitx_api.repositories.account_repository import AccountRepository
    from remitx_api.services.remittance_service import REMITX_TREASURY_WALLET_LABEL
    from sqlalchemy import select

    accounts = AccountRepository()
    missing = [
        label
        for label in (REMITX_TREASURY_WALLET_LABEL, Config().UCTUSD_ISSUER_LABEL)
        if accounts.get_platform_account_by_label(label) is None
    ]
    for currency in PAYOUT_CURRENCIES:
        if accounts.get_platform_account(TYPE_PLATFORM_FIAT, currency) is None:
            missing.append(f"{currency} bank account")
    if accounts.get_platform_account(TYPE_PLATFORM_REVENUE, "ZAR") is None:
        missing.append("ZAR fee revenue account")
    admin = db.session.scalar(
        select(UserRole.user_id)
        .join(Role, Role.role_id == UserRole.role_id)
        .where(Role.name == "iam_admin", UserRole.revoked_at.is_(None))
        .limit(1)
    )
    if missing:
        raise PreflightError(
            "The target is missing: "
            + ", ".join(missing)
            + ". Run `alembic upgrade head`, or Reset."
        )
    return admin


def _plan_people(ctx: RunContext) -> None:
    scenario = ctx.scenario
    today = ctx.window_end.date()
    n = 0
    for role, count in scenario.staff.items():
        for _ in range(count):
            n += 1
            persona = build_staff(ctx.rng, f"staff{n}", today, role)
            person = SeededPerson(persona)
            ctx.people[persona.key] = person
            ctx.staff_by_role.setdefault(role, []).append(person)
    for country, count in scenario.recipients.items():
        for i in range(count):
            persona = build_recipient(
                ctx.rng, f"recipient-{country}-{i + 1}", today, country
            )
            ctx.people[persona.key] = SeededPerson(persona)
    for i in range(scenario.senders):
        persona = build_sender(
            ctx.rng,
            f"sender{i + 1}",
            today,
            pep_rate=scenario.kyc.pep_rate,
            other_source_rate=scenario.kyc.other_source_rate,
            high_volume_rate=scenario.kyc.high_volume_rate,
        )
        ctx.people[persona.key] = SeededPerson(persona)


def _guarantee_edge_cases(ctx: RunContext) -> None:
    """One sender down each rare path, so a run never lacks them by chance."""
    senders = [p for p in ctx.people.values() if p.persona.role == "sender"]
    rng = ctx.rng

    def pep(relationship: str):
        def apply(person: SeededPerson) -> None:
            declare_pep(rng, person.persona, relationship)

        return apply

    def path(name: str):
        def apply(person: SeededPerson) -> None:
            person.kyc_path = name
            person.kyc_path_fixed = True

        return apply

    def override(person: SeededPerson) -> None:
        person.force_override = True

    def tier_two(person: SeededPerson) -> None:
        declare_source_of_wealth(rng, person.persona)
        person.force_tier_two = True

    def high_volume(person: SeededPerson) -> None:
        person.persona.expected_monthly_volume_zar = STANDARD_MONTHLY_LIMIT_ZAR + 12000

    def awaiting_review(person: SeededPerson) -> None:
        # Signs up hours before the window closes: submitted, not yet claimed.
        person.persona.extra["late_signup"] = True
        path(PATH_APPROVE)(person)

    cases = [
        ("PEP (self)", pep("self")),
        ("PEP (family member)", pep("immediate_family_member")),
        ("rejected", path(PATH_REJECT)),
        ("more info, answered", path(PATH_MORE_INFO)),
        ("more info, unanswered", path(PATH_MORE_INFO_NO_REPLY)),
        ("abandoned draft", path(PATH_ABANDON)),
        ("risk rating override", override),
        ("tier 2 approval", tier_two),
        ("high declared volume", high_volume),
        ("awaiting review", awaiting_review),
    ]
    for (label, apply), person in zip(cases, senders, strict=False):
        apply(person)
        person.persona.extra["edge_case"] = label
    if len(senders) < len(cases):
        ctx.log(
            f"Only {len(senders)} senders: {len(cases) - len(senders)} edge cases "
            "not guaranteed this run.",
            level="warning",
        )


# Fixed KYC paths that never leave a verified sender — prefer not to spend
# scarce Clerk slots on them when the live tail (or a near-full cap) needs
# senders who can actually sign in and remit.
_CLERK_DEAD_END_PATHS = {
    PATH_NEVER,
    PATH_ABANDON,
    PATH_REJECT,
    PATH_MORE_INFO_NO_REPLY,
}


def _sender_can_finish_kyc(person: SeededPerson) -> bool:
    if person.persona.extra.get("late_signup"):
        return False
    return not (person.kyc_path_fixed and person.kyc_path in _CLERK_DEAD_END_PATHS)


def _allocate_clerk_accounts(ctx: RunContext, clerk_enabled: bool) -> None:
    if not clerk_enabled:
        ctx.log("No Clerk key for this target: everyone is database-only.")
        return
    with ctx.clock.real_time():
        existing = ctx.clerk.user_count()
    capacity = max(0, ctx.scenario.clerk_user_cap - existing)
    staff = [p for p in ctx.people.values() if p.persona.role == "staff"]
    senders = [p for p in ctx.people.values() if p.persona.role == "sender"]
    recipients = [p for p in ctx.people.values() if p.persona.role == "recipient"]
    preferred_senders = [p for p in senders if _sender_can_finish_kyc(p)]
    other_senders = [p for p in senders if not _sender_can_finish_kyc(p)]
    order = staff + preferred_senders + other_senders + recipients
    for person in order[:capacity]:
        person.wants_clerk_account = True
    ctx.log(
        f"Clerk has {existing} users; cap {ctx.scenario.clerk_user_cap} leaves room "
        f"for {capacity}. {min(capacity, len(order))} of {len(order)} people get "
        "Clerk accounts, the rest are database-only."
    )


def _schedule(ctx: RunContext, sim: Simulation, kyc: KycStory) -> None:
    rng = ctx.rng
    span = ctx.window_end - ctx.window_start
    for person in ctx.people.values():
        role = person.persona.role
        if role == "staff":
            people_story.schedule_staff(ctx, sim, person)
            continue
        if role == "recipient":
            signup = (
                ctx.window_start
                - timedelta(days=20)
                + (span * 0.55 + timedelta(days=20)) * rng.random()
            )
            verify = (
                person.persona.residence is not None
                and rng.random() < RECIPIENT_VERIFY_RATE
            )
            person.kyc_path = PATH_APPROVE if verify else "never_start"
        else:
            if person.persona.extra.get("late_signup"):
                signup = ctx.window_end - timedelta(hours=rng.uniform(1.5, 3))
            else:
                # Front-loaded: more people joined early in the window than late.
                signup = ctx.window_start + span * rng.betavariate(1.3, 2.4)
            if not person.kyc_path_fixed:
                person.kyc_path = plan_path(ctx, person)
        person.signup_at = signup

        def join(person: SeededPerson = person) -> None:
            people_story.sign_up(ctx, person)
            if person.kyc_path == "never_start" and person.persona.role == "recipient":
                return
            delay = (
                timedelta(minutes=rng.uniform(2, 50))
                if rng.random() < 0.6 or person.persona.extra.get("late_signup")
                else timedelta(days=rng.uniform(0.5, 6))
            )
            kyc.schedule(person, ctx.clock.now() + delay)

        sim.schedule(signup, "people.sign_up", join)


def run_seed(
    scenario: Scenario,
    *,
    clerk: ClerkGateway,
    clerk_enabled: bool,
    storage,
    emit: Emit,
    live_tail=None,
    check_chain: bool = False,
) -> dict:
    """Run a scenario against the initialised database. Returns the summary
    that becomes the run manifest."""
    from remitx_api.extensions import db
    from remitx_api.services.exchange_rate_provider import use_rate_provider
    from remitx_api.services.object_storage import use_object_storage

    from remitx_seeder import direct
    from remitx_seeder.verify import run_verify

    started = time.monotonic()
    token = db.open_session()
    try:
        admin_id = preflight()
    finally:
        db.close_session(token)

    window_end = datetime.now(UTC) - WINDOW_END_MARGIN
    window_start = window_end - timedelta(days=scenario.days)
    clock = SimClock()
    ctx = RunContext(
        scenario=scenario,
        run_id=f"run-{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}",
        clock=clock,
        clerk=clerk,
        emit=emit,
        window_start=window_start,
        window_end=window_end,
    )
    ctx.admin_user_id = admin_id
    ctx.log(
        f"Replaying {scenario.days} days, {window_start:%d %b} to "
        f"{window_end:%d %b %Y}, "
        f"seed {scenario.seed}."
    )
    _plan_people(ctx)
    if scenario.ensure_every_path:
        _guarantee_edge_cases(ctx)
    _allocate_clerk_accounts(ctx, clerk_enabled)

    sim = Simulation(ctx)
    money = MoneyStory(ctx, sim)
    kyc = KycStory(ctx, sim, on_verified=money.on_verified)
    _schedule(ctx, sim, kyc)

    top_up_id = None
    with ExitStack() as stack:
        use_rate_provider(
            HistoricalRateProvider(
                scenario.seed,
                (window_start - timedelta(days=90)).date(),
                window_end.date(),
            )
        )
        stack.callback(use_rate_provider, None)
        use_object_storage(RealTimeStorage(storage, clock))
        stack.callback(use_object_storage, None)
        SimulatedSettlement(ctx, sim).install(stack)
        stack.callback(clock.stop)

        sim.run()

        clock.move_to(window_start)
        token = db.open_session()
        try:
            top_up = direct.record_treasury_top_up(ctx.simulated_burn_total)
            top_up_id = str(top_up.tx_id) if top_up else None
        finally:
            db.close_session(token)
            clock.stop()

    ctx.log(
        f"Replay done: {sim.done} events, {sim.dropped} follow-ups fell past the "
        f"window and were left pending, {len(ctx.refusals)} refusals."
    )

    live = None
    if live_tail is not None and scenario.live_settlements > 0:
        live = live_tail(ctx)

    token = db.open_session()
    try:
        report = run_verify(db.session, check_chain=check_chain)
    finally:
        db.close_session(token)
    level = "info" if report.ok else "error"
    ctx.log(
        "verify: every rule holds"
        if report.ok
        else f"verify: {len(report.errors)} check(s) failed",
        level=level,
    )
    return {
        "run_id": ctx.run_id,
        "scenario": scenario.as_dict(),
        "window": {"start": window_start.isoformat(), "end": window_end.isoformat()},
        "counts": dict(sorted(ctx.counters.items())),
        "events": {"run": sim.done, "left_past_window": sim.dropped},
        "refusals": ctx.refusals,
        "simulated_burn_total": str(ctx.simulated_burn_total),
        "treasury_top_up_tx_id": top_up_id,
        "live_tail": live,
        "verify": report.as_dict(),
        "duration_seconds": round(time.monotonic() - started, 1),
    }
