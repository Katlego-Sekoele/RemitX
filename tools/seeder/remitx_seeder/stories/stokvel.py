"""The stokvel demo (R6-03, #268): the brief's three members, ready to start.

With `stokvel.enabled` in the scenario, three named members (stokvel_plan.py)
join early in the window and walk the ordinary KYC path to approval. They are
`scripted`: no edge case, no chance rating override, and no other story picks
them. Once verified, each deposits enough for every round of every stokvel
they will be in, with their fee shares, priced with the backend's own
`contribution_fee_share` at the replayed rate and with headroom for the live
rate on the day. The deposit is reconciled like any other, then kept.

A few hours before the window closes, through the stokvel controllers as the
routes call them, one step per event a few minutes apart:

- **The ready stokvel** (`READY_STOKVEL`): the Organiser creates it and
  invites the other two, who accept; each chooses a cross-border beneficiary
  from their corridor; the Organiser sets the payout order. Its cycle is left
  `forming`, for the demo to start with a schedule a few minutes apart (brief
  §7.5).
- **The lapse stokvel** (`LAPSE_STOKVEL`): the second member organises it with
  the third, both ready, and invites the first Organiser, who does not
  answer. Starting its cycle lapses that invitation.

If any step is refused, or falls past the window, `finish` records it as a
refusal, so the run cannot report a demo it did not set up. The run summary's
`stokvel_demo` names both stokvels and who to sign in as.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import ROUND_UP, Decimal

from remitx_seeder.clerk import can_sign_in, test_email
from remitx_seeder.context import RunContext, SeededPerson
from remitx_seeder.generators.personas import build_sender
from remitx_seeder.sim import Simulation
from remitx_seeder.stories.kyc import PATH_APPROVE
from remitx_seeder.stories.money import MoneyStory
from remitx_seeder.stories.stokvel_plan import (
    DEMO_MEMBERS,
    LAPSE_STOKVEL,
    READY_STOKVEL,
    STOKVELS,
    DemoStokvel,
)

__all__ = ["LAPSE_STOKVEL", "READY_STOKVEL"]

STOKVEL_CURRENCY = "ZAR"
# The live rate on the day of the demo may be higher than the replayed one.
DEPOSIT_HEADROOM = Decimal("1.5")
MIN_DEPOSIT_ZAR = Decimal("500")
SETUP_BEFORE_END = timedelta(hours=3)

Step = tuple[str, Callable[[], None]]


class DemoNotReady(RuntimeError):
    """The stokvel demo cannot be set up as asked."""


def plan_members(ctx: RunContext) -> list[SeededPerson]:
    """Add the demo's members to the run. Their own randomness, so the same
    seed gives the same three people whatever else the scenario says."""
    rng = random.Random(f"stokvel-demo-{ctx.scenario.seed}")
    today = ctx.window_end.date()
    members = []
    for spec in DEMO_MEMBERS:
        persona = build_sender(
            rng,
            spec.key,
            today,
            pep_rate=0,
            other_source_rate=0,
            high_volume_rate=0,
            corridor=spec.corridor,
        )
        persona.email_local = spec.email_local
        persona.extra["stokvel_demo"] = spec.label
        person = SeededPerson(
            persona, kyc_path=PATH_APPROVE, kyc_path_fixed=True, scripted=True
        )
        ctx.people[persona.key] = person
        members.append(person)
    return members


def refuse_if_already_seeded(ctx: RunContext, members: list[SeededPerson]) -> None:
    """Refuse before anything is written when a demo member's email is taken:
    a second demo on the same database would sign its members in under
    numbered emails (`stokvel.organiser2`), not the ones the demo uses."""
    from remitx_api.extensions import db
    from remitx_api.models.orm.user import User
    from sqlalchemy import select

    emails = [
        test_email(person.persona.email_local, ctx.scenario.email_domain)
        for person in members
    ]
    taken = db.session.scalars(select(User.email).where(User.email.in_(emails))).all()
    if taken:
        raise DemoNotReady(
            f"The stokvel demo's members already exist ({', '.join(sorted(taken))}): "
            "Reset the target, then seed the demo again."
        )


class StokvelDemoStory:
    def __init__(
        self,
        ctx: RunContext,
        sim: Simulation,
        money: MoneyStory,
        members: list[SeededPerson],
    ) -> None:
        self.ctx = ctx
        self.sim = sim
        self.money = money
        self.members = members
        self.specs = dict(zip((m.key for m in members), DEMO_MEMBERS, strict=True))
        self.contribution = Decimal(str(ctx.scenario.stokvel.contribution_uctusd))
        self.beneficiary_ids: dict[str, object] = {}
        self.stokvels: dict[str, dict] = {}
        self.summary: dict | None = None

    def owns(self, person: SeededPerson) -> bool:
        return person.key in self.specs

    def _member(self, index: int) -> SeededPerson:
        return self.members[index]

    # --- before the setup --------------------------------------------------

    def signup_at(self, person: SeededPerson) -> datetime:
        """Early, a few hours apart, so there is time to verify and fund."""
        index = list(self.specs).index(person.key)
        return self.ctx.window_start + timedelta(hours=2 + 3 * index)

    def on_verified(self, person: SeededPerson) -> None:
        needed = self._cost(person, self._rates()) * DEPOSIT_HEADROOM
        rounded = (needed / 50).quantize(Decimal("1"), rounding=ROUND_UP) * 50
        self.money.deposit_to_keep(person, max(MIN_DEPOSIT_ZAR, rounded))
        self.ctx.count("stokvel_demo.funded")

    def _rates(self):
        from remitx_api.services.quote_service import token_rates

        return token_rates(STOKVEL_CURRENCY)

    def _cost(self, person: SeededPerson, rates) -> Decimal:
        """Every round of every stokvel `person` will be in, with their fee
        share, in rand at `rates`: one round per member, the fee split
        between that stokvel's members, for the dearest payout currency of
        the person's corridor."""
        from remitx_api.controllers.stokvel_contribution_controller import (
            contribution_fee_share,
        )
        from remitx_api.services.quote_service import token_to_fiat

        fiat = token_to_fiat(self.contribution, rates)
        currencies = self.specs[person.key].corridor["payout_currencies"]
        total = Decimal("0")
        for stokvel in self._stokvels_of(person):
            size = len(stokvel.members)
            fee = max(
                contribution_fee_share(
                    fiat, rates, member_count=size, payout_currency=currency
                )
                for currency in currencies
            )
            total += (fiat + fee) * size
        return total

    def _stokvels_of(self, person: SeededPerson) -> list[DemoStokvel]:
        index = list(self.specs).index(person.key)
        return [stokvel for stokvel in STOKVELS if index in stokvel.members]

    # --- the setup -----------------------------------------------------------

    def schedule_setup(self) -> None:
        steps: list[Step] = [
            ("stokvel.demo.check", self._check_ready),
            ("stokvel.demo.beneficiaries", self._add_beneficiaries),
        ]
        for stokvel in STOKVELS:
            steps += self._stokvel_steps(stokvel)
        steps.append(("stokvel.demo.summary", self._summarise))
        self._chain(self.ctx.window_end - SETUP_BEFORE_END, steps)

    def _chain(self, at: datetime, steps: list[Step]) -> None:
        """Run `steps` as events a few minutes apart. A step the backend
        refuses is recorded and ends the chain; `finish` reports it."""
        if not steps:
            return
        (name, action), rest = steps[0], steps[1:]

        def run() -> None:
            action()
            gap = timedelta(minutes=self.ctx.rng.uniform(1, 6))
            self._chain(self.ctx.clock.now() + gap, rest)

        self.sim.schedule(at, name, run)

    def _check_ready(self) -> None:
        from remitx_api.models.orm.account import CURRENCY_ZAR
        from remitx_api.repositories.account_repository import AccountRepository

        accounts = AccountRepository()
        rates = self._rates()
        for person in self.members:
            label = self.specs[person.key].label
            if not person.verified:
                raise DemoNotReady(
                    f"the {label} is not KYC-approved yet; try a longer window"
                )
            zar = accounts.get_user_account(person.user_id, CURRENCY_ZAR)
            available = accounts.get_available_balance(zar.account_id)
            needed = self._cost(person, rates)
            if available < needed:
                raise DemoNotReady(
                    f"the {label} has R{available} available but their "
                    f"stokvels' rounds need R{needed}; their deposit has not "
                    "been reconciled"
                )

    def _add_beneficiaries(self) -> None:
        used: set = set()
        for person in self.members:
            pool = self.money.recipient_pool(person, exclude=used)
            if not pool:
                country = self.specs[person.key].recipient_country
                raise DemoNotReady(f"no recipient in {country} has signed up")
            entry = self.money.add_beneficiary(person, pool[0])
            used.add(pool[0].user_id)
            self.beneficiary_ids[person.key] = entry["beneficiary_id"]

    def _stokvel_steps(self, stokvel: DemoStokvel) -> list[Step]:
        which = stokvel.which
        organiser, *joiners = (self._member(i) for i in stokvel.members)
        invitees = [*joiners]
        if stokvel.pending is not None:
            invitees.append(self._member(stokvel.pending))
        steps: list[Step] = [
            (
                f"stokvel.demo.{which}.create",
                lambda: self._create(which, stokvel.name, organiser),
            )
        ]
        steps += [
            (
                f"stokvel.demo.{which}.invite",
                lambda person=person: self._invite(which, organiser, person),
            )
            for person in invitees
        ]
        steps += [
            (
                f"stokvel.demo.{which}.accept",
                lambda person=person: self._accept(which, person),
            )
            for person in joiners
        ]
        steps += [
            (
                f"stokvel.demo.{which}.beneficiary",
                lambda person=person: self._choose_beneficiary(which, person),
            )
            for person in (organiser, *joiners)
        ]
        steps.append(
            (
                f"stokvel.demo.{which}.payout_order",
                lambda: self._set_payout_order(which, organiser, [organiser, *joiners]),
            )
        )
        return steps

    def _create(self, which: str, name: str, organiser: SeededPerson) -> None:
        from remitx_api.controllers.stokvel_controller import StokvelController
        from remitx_api.models.schemas.stokvel import StokvelCreateRequest

        # Validated as the route validates its body.
        request = StokvelCreateRequest(
            name=name,
            currency=STOKVEL_CURRENCY,
            contribution_amount=self.contribution,
        )
        view = StokvelController().create_stokvel(
            organiser.user_id,
            name=request.name,
            currency=request.currency.value,
            contribution_amount=request.contribution_amount,
        )
        self.stokvels[which] = {
            "stokvel_id": view.stokvel_id,
            "name": view.name,
            "invitations": {},
        }
        self.ctx.count("stokvel_demo.stokvels")

    def _invite(self, which: str, organiser: SeededPerson, invitee: SeededPerson):
        from remitx_api.controllers.stokvel_invitation_controller import (
            StokvelInvitationController,
        )

        stokvel = self.stokvels[which]
        view = StokvelInvitationController().invite(
            organiser.user_id, stokvel["stokvel_id"], invitee.zar_reference
        )
        stokvel["invitations"][invitee.key] = view.invitation_id
        self.ctx.count("stokvel_demo.invitations")

    def _accept(self, which: str, person: SeededPerson) -> None:
        from remitx_api.controllers.stokvel_invitation_controller import (
            StokvelInvitationController,
        )

        invitation_id = self.stokvels[which]["invitations"][person.key]
        StokvelInvitationController().accept(person.user_id, invitation_id)
        self.ctx.count("stokvel_demo.accepted")

    def _choose_beneficiary(self, which: str, person: SeededPerson) -> None:
        from remitx_api.controllers.stokvel_setup_controller import (
            StokvelSetupController,
        )

        StokvelSetupController().set_beneficiary(
            person.user_id,
            self.stokvels[which]["stokvel_id"],
            self.beneficiary_ids[person.key],
        )

    def _set_payout_order(
        self, which: str, organiser: SeededPerson, members: list[SeededPerson]
    ) -> None:
        from remitx_api.controllers.stokvel_setup_controller import (
            StokvelSetupController,
        )
        from remitx_api.repositories.stokvel_member_repository import (
            StokvelMemberRepository,
        )

        stokvel_id = self.stokvels[which]["stokvel_id"]
        member_ids = {
            member.user_id: member.id
            for member in StokvelMemberRepository().list_active(stokvel_id)
        }
        StokvelSetupController().set_payout_order(
            organiser.user_id,
            stokvel_id,
            [member_ids[person.user_id] for person in members],
        )

    def _summarise(self) -> None:
        def who(person: SeededPerson) -> dict:
            return {
                "role": self.specs[person.key].label,
                "name": person.persona.full_name,
                "email": person.email,
                "can_sign_in": can_sign_in(person.clerk_user_id),
                "beneficiary_country": self.specs[person.key].recipient_country,
            }

        summary: dict = {"contribution_uctusd": str(self.contribution)}
        for stokvel in STOKVELS:
            created = self.stokvels[stokvel.which]
            entry = {
                "stokvel_id": str(created["stokvel_id"]),
                "name": created["name"],
                "payout_order": [who(self._member(i)) for i in stokvel.members],
            }
            if stokvel.pending is not None:
                entry["pending_invitation"] = who(self._member(stokvel.pending))
            summary[stokvel.which] = entry
        self.summary = summary

        organiser, second, third = self.members
        self.ctx.log(
            f"Stokvel demo: '{READY_STOKVEL}' is ready to start, organised by "
            f"{organiser.email}, with {second.email} and {third.email}. "
            f"'{LAPSE_STOKVEL}' ({second.email}) has an invitation to "
            f"{organiser.email} still pending."
        )
        if not all(can_sign_in(p.clerk_user_id) for p in self.members):
            self.ctx.log(
                "Some stokvel demo members are database-only and cannot sign "
                "in: set a Clerk key, or raise the Clerk user cap.",
                level="warning",
            )

    def finish(self) -> None:
        """After the replay: a setup that did not finish is a refusal, so the
        run never reports a demo it did not make. The step that was refused
        is already among the refusals; this names the outcome."""
        if self.summary is not None:
            return
        done = sorted(
            key for key in self.ctx.counters if key.startswith("events.stokvel.demo.")
        )
        message = (
            "The stokvel demo was not set up: a step was refused (see the "
            "refusals) or fell past the window. Completed: "
            + (", ".join(done) or "none")
        )
        self.ctx.refusals.append(
            {
                "event": "stokvel.demo",
                "at": self.ctx.window_end.isoformat(),
                "error": DemoNotReady.__name__,
                "message": message,
            }
        )
        self.ctx.count("refusals")
        self.ctx.log(message, level="error")
