"""Signing people up, and making staff staff.

A synthetic person signs up the way a real one does: a Clerk account (or a
database-only id once the Clerk cap is reached), then the API's own
just-in-time provisioning, `UserController.ensure_provisioned`, which assigns
their base reference and opens their ZAR and uctusd accounts. Most then add a
contact mobile on their profile page, through `ProfileController`.

Staff are people too. Their roles are granted through `UserRoleController.grant`
by the administrator `seed_platform_accounts.py` provisioned, with a reason, the
way the IAM screen does it — so separation-of-duties checks apply.
"""

from __future__ import annotations

from datetime import timedelta

from remitx_seeder.clerk import database_only_id, test_email
from remitx_seeder.context import RunContext, SeededPerson
from remitx_seeder.data import load
from remitx_seeder.sim import Simulation

MOBILE_ON_PROFILE_RATE = 0.85


def unique_email(ctx: RunContext, person: SeededPerson) -> str:
    """`first.last+clerk_test@domain`, numbered when the address is taken in
    RemitX or in Clerk by someone the seeder did not make."""
    from remitx_api.extensions import db
    from remitx_api.models.orm.user import User
    from sqlalchemy import select

    base = person.persona.email_local
    domain = ctx.scenario.email_domain
    for attempt in range(1, 500):
        local = base if attempt == 1 else f"{base}{attempt}"
        email = test_email(local, domain)
        taken = db.session.scalar(select(User.id).where(User.email == email))
        if taken is None:
            return email
    raise RuntimeError(f"No free email address for {base}")


def sign_up(ctx: RunContext, person: SeededPerson) -> None:
    from remitx_api.controllers.profile_controller import ProfileController
    from remitx_api.controllers.user_controller import UserController
    from remitx_api.models.schemas.me import ProfileUpdate

    persona = person.persona
    email = unique_email(ctx, person)
    clerk_user_id = None
    # Read before stepping onto the real clock: Clerk records the replayed
    # sign-up moment, not today.
    signed_up_at = ctx.clock.now()
    if person.wants_clerk_account:
        with ctx.clock.real_time():
            existing = ctx.clerk.find_by_email(email)
            if existing is not None and existing[1]:
                # Left over from an earlier run whose database was reset
                # without Clerk; reuse it rather than fail on the address.
                clerk_user_id = existing[0]
            elif existing is None:
                clerk_user_id = ctx.clerk.create_user(
                    email=email,
                    first_name=persona.first_name,
                    last_name=persona.last_name,
                    created_at=signed_up_at,
                    run_id=ctx.run_id,
                )
        if clerk_user_id is not None:
            ctx.count("people.clerk_accounts")
    if clerk_user_id is None:
        clerk_user_id = database_only_id()
        ctx.count("people.database_only")

    user = UserController().ensure_provisioned(
        clerk_user_id,
        lambda: email,
        lambda: persona.first_name,
    )
    person.user_id = user.id
    person.clerk_user_id = clerk_user_id
    person.email = email
    person.base_reference = user.base_reference
    ctx.count(f"people.{persona.role}")

    if persona.role == "staff" or ctx.rng.random() < MOBILE_ON_PROFILE_RATE:
        ProfileController().update(user.id, ProfileUpdate(mobile_number=persona.mobile))


def grant_staff_role(ctx: RunContext, person: SeededPerson) -> None:
    from remitx_api.controllers.user_role_controller import UserRoleController
    from remitx_api.models.schemas.role import RoleGrantRequest

    role = person.persona.staff_role
    reason = load("templates")["role_grant_reasons"].get(
        role, f"Seeded {role} for QA testing."
    )
    UserRoleController().grant(
        person.user_id,
        RoleGrantRequest(role=role, reason=reason),
        ctx.admin_user_id,
    )
    ctx.count(f"staff.{role}")


def schedule_staff(ctx: RunContext, sim: Simulation, person: SeededPerson) -> None:
    joined = ctx.window_start - timedelta(days=ctx.rng.randint(20, 60))
    person.signup_at = joined

    def join() -> None:
        sign_up(ctx, person)
        sim.schedule(
            ctx.clock.now() + timedelta(hours=ctx.rng.uniform(1, 30)),
            "staff.grant",
            lambda: grant_staff_role(ctx, person),
        )

    sim.schedule(joined, "people.sign_up", join)
