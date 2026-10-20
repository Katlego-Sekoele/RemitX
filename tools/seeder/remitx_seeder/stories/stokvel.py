"""The stokvel demo (R6-03, #268): the brief's three members, ready to start.

With `stokvel.enabled` in the scenario, three named members join early in the
window and walk the ordinary KYC path to approval (no chance rating override,
so it goes the same way every run). Once verified, each deposits enough for
three rounds of contributions and their fee shares, priced with the backend's
own `contribution_fee_share` at the replayed rate, with headroom for the live
rate on the day; the deposit is reconciled like any other and then kept.

A few hours before the window closes, through the stokvel controllers as the
routes call them:

- **The ready stokvel** (`READY_STOKVEL`): the Organiser creates it and
  invites the other two, who accept; each chooses a cross-border beneficiary
  from their corridor; the Organiser sets the payout order. Its cycle is left
  `forming`, for the demo to start with a schedule a few minutes apart (brief
  §7.5).
- **The lapse stokvel** (`LAPSE_STOKVEL`): the second member organises it with
  the third, both ready, and invites the Organiser of the first, who does not
  answer. Starting its cycle lapses that invitation. A second stokvel because
  the member cap (3) counts accepted members: a full stokvel cannot also hold
  a pending invitation.

The run summary's `stokvel_demo` names both stokvels and who to sign in as.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_UP, Decimal

from remitx_seeder.context import RunContext, SeededPerson
from remitx_seeder.data import load
from remitx_seeder.generators.personas import build_sender
from remitx_seeder.sim import Simulation
from remitx_seeder.stories.kyc import PATH_APPROVE
from remitx_seeder.stories.money import MoneyStory

# Room in the window for KYC review (which waits for office hours) and the
# deposit's next-working-morning reconciliation before the setup.
MIN_DEMO_DAYS = 14
STOKVEL_CURRENCY = "ZAR"
READY_STOKVEL = "Masakhane Savings Club"
LAPSE_STOKVEL = "Siyakhula Savings Club"
# The live rate on the day of the demo may be higher than the replayed one.
DEPOSIT_HEADROOM = Decimal("1.5")
MIN_DEPOSIT_ZAR = Decimal("500")
SETUP_BEFORE_END = timedelta(hours=3)


@dataclass(frozen=True)
class DemoMember:
    key: str
    label: str
    email_local: str
    # A corridor's name in data/corridors.json: who they are and who their
    # beneficiary is.
    corridor_name: str

    @property
    def corridor(self) -> dict:
        return next(
            corridor
            for corridor in load("corridors")["corridors"]
            if corridor["name"] == self.corridor_name
        )

    @property
    def recipient_country(self) -> str:
        return self.corridor["recipient_country"]


# The ready stokvel pays them in this order. Three corridors, so each payout
# crosses a different border.
DEMO_MEMBERS = (
    DemoMember(
        "stokvel-organiser",
        "Organiser",
        "stokvel.organiser",
        "Zimbabwean in SA supporting family at home",
    ),
    DemoMember(
        "stokvel-member-2",
        "second member",
        "stokvel.member2",
        "Namibian in SA supporting family at home",
    ),
    DemoMember(
        "stokvel-member-3",
        "third member",
        "stokvel.member3",
        "South African supporting someone in the US",
    ),
)
ROUNDS = len(DEMO_MEMBERS)


class DemoNotReady(RuntimeError):
    """A demo member is not verified or not funded when the setup starts."""


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
            persona, kyc_path=PATH_APPROVE, kyc_path_fixed=True, never_override=True
        )
        ctx.people[persona.key] = person
        members.append(person)
    return members


def is_demo_member(person: SeededPerson) -> bool:
    return "stokvel_demo" in person.persona.extra


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

    # --- before the setup --------------------------------------------------

    def signup_at(self, person: SeededPerson) -> datetime:
        """Early, a few hours apart, so there is time to verify and fund."""
        index = list(self.specs).index(person.key)
        return self.ctx.window_start + timedelta(hours=2 + 3 * index)

    def on_verified(self, person: SeededPerson) -> None:
        self.money.deposit_to_keep(person, self._deposit(person))
        self.ctx.count("stokvel_demo.funded")

    def _round_cost(self, person: SeededPerson) -> Decimal:
        """One round's contribution and fee share, in rand, at today's
        replayed rate, for the dearest payout currency of their corridor."""
        from remitx_api.controllers.stokvel_contribution_controller import (
            contribution_fee_share,
        )
        from remitx_api.services.quote_service import token_rates, token_to_fiat

        rates = token_rates(STOKVEL_CURRENCY)
        fiat = token_to_fiat(self.contribution, rates)
        fee = max(
            contribution_fee_share(
                fiat, rates, member_count=ROUNDS, payout_currency=currency
            )
            for currency in self.specs[person.key].corridor["payout_currencies"]
        )
        return fiat + fee

    def _deposit(self, person: SeededPerson) -> Decimal:
        needed = self._round_cost(person) * ROUNDS * DEPOSIT_HEADROOM
        rounded = (needed / 50).quantize(Decimal("1"), rounding=ROUND_UP) * 50
        return max(MIN_DEPOSIT_ZAR, rounded)

    # --- the setup -----------------------------------------------------------

    def schedule_setup(self) -> None:
        organiser, second, third = self.members
        steps = [
            ("stokvel.demo.check", self._check_ready),
            ("stokvel.demo.beneficiaries", self._add_beneficiaries),
            *self._stokvel_steps("ready", organiser, [second, third], pending=None),
            *self._stokvel_steps("lapse", second, [third], pending=organiser),
            ("stokvel.demo.summary", self._summarise),
        ]
        self._chain(self.ctx.window_end - SETUP_BEFORE_END, steps)

    def _chain(self, at: datetime, steps: list[tuple[str, Callable[[], None]]]):
        """Run `steps` as events a few minutes apart. A step the backend
        refuses is recorded and ends the chain: the demo is not ready."""
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
        for person in self.members:
            label = self.specs[person.key].label
            if not person.verified:
                raise DemoNotReady(
                    f"the {label} is not KYC-approved yet; try a longer window"
                )
            zar = accounts.get_user_account(person.user_id, CURRENCY_ZAR)
            available = accounts.get_available_balance(zar.account_id)
            needed = self._round_cost(person) * ROUNDS
            if available < needed:
                raise DemoNotReady(
                    f"the {label} has R{available} available but three rounds "
                    f"need R{needed}; their deposit has not been reconciled"
                )

    def _add_beneficiaries(self) -> None:
        used: set = set()
        for person in self.members:
            country = self.specs[person.key].recipient_country
            recipient = next(
                (
                    p
                    for p in self.ctx.people_with_role("recipient")
                    if p.persona.nationality == country
                    and p.user_id is not None
                    and p.user_id not in used
                ),
                None,
            )
            if recipient is None:
                raise DemoNotReady(f"no recipient in {country} has signed up")
            used.add(recipient.user_id)
            entry = self.money.add_beneficiary(person, recipient)
            self.beneficiary_ids[person.key] = entry["beneficiary_id"]

    def _stokvel_steps(
        self,
        which: str,
        organiser: SeededPerson,
        joiners: list[SeededPerson],
        *,
        pending: SeededPerson | None,
    ) -> list[tuple[str, Callable[[], None]]]:
        name = READY_STOKVEL if which == "ready" else LAPSE_STOKVEL
        members = [organiser, *joiners]
        steps = [
            (
                f"stokvel.demo.{which}.create",
                lambda: self._create(which, name, organiser),
            )
        ]
        for person in [*joiners, *([pending] if pending else [])]:
            steps.append(
                (
                    f"stokvel.demo.{which}.invite",
                    lambda person=person: self._invite(which, organiser, person),
                )
            )
        for person in joiners:
            steps.append(
                (
                    f"stokvel.demo.{which}.accept",
                    lambda person=person: self._accept(which, person),
                )
            )
        for person in members:
            steps.append(
                (
                    f"stokvel.demo.{which}.beneficiary",
                    lambda person=person: self._choose_beneficiary(which, person),
                )
            )
        steps.append(
            (
                f"stokvel.demo.{which}.payout_order",
                lambda: self._set_payout_order(which, organiser, members),
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
                "can_sign_in": bool(person.clerk_user_id)
                and person.clerk_user_id.startswith("user_"),
                "beneficiary_country": self.specs[person.key].recipient_country,
            }

        organiser, second, third = self.members
        ready, lapse = self.stokvels["ready"], self.stokvels["lapse"]
        self.summary = {
            "contribution_uctusd": str(self.contribution),
            "ready": {
                "stokvel_id": str(ready["stokvel_id"]),
                "name": ready["name"],
                "payout_order": [who(p) for p in self.members],
            },
            "lapse": {
                "stokvel_id": str(lapse["stokvel_id"]),
                "name": lapse["name"],
                "payout_order": [who(second), who(third)],
                "pending_invitation": who(organiser),
            },
        }
        self.ctx.log(
            f"Stokvel demo: '{ready['name']}' is ready to start, organised by "
            f"{organiser.email}, with {second.email} and {third.email}. "
            f"'{lapse['name']}' ({second.email}) has an invitation to "
            f"{organiser.email} still pending."
        )
        if not all(
            entry["can_sign_in"] for entry in self.summary["ready"]["payout_order"]
        ):
            self.ctx.log(
                "Some stokvel demo members are database-only and cannot sign in: "
                "set a Clerk key, or raise the Clerk user cap.",
                level="warning",
            )
