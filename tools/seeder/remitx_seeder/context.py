"""What one seed run carries around: its scenario, randomness, clock, Clerk,
the people it has made so far, and how it reports progress."""

from __future__ import annotations

import random
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from remitx_seeder.clerk import ClerkGateway
from remitx_seeder.clock import SimClock
from remitx_seeder.generators.personas import Persona
from remitx_seeder.scenario import Scenario

Emit = Callable[[dict], None]


@dataclass
class SeededPerson:
    """A persona and what the run has made of it so far."""

    persona: Persona
    signup_at: datetime | None = None
    wants_clerk_account: bool = False
    user_id: uuid.UUID | None = None
    clerk_user_id: str | None = None
    email: str | None = None
    base_reference: str | None = None
    application_id: uuid.UUID | None = None
    verified: bool = False
    # KYC path decided up front, so the documents can match it (a blurry ID
    # for someone a reviewer will send back).
    kyc_path: str = "approve"
    # Set by the engine's edge-case guarantee rather than by chance.
    kyc_path_fixed: bool = False
    force_override: bool = False
    force_tier_two: bool = False
    beneficiaries: list[dict] = field(default_factory=list)
    # External bank accounts registered after verification, and whether this
    # person will cash out spare balance once one of them is verified.
    bank_accounts: list[dict] = field(default_factory=list)
    will_cash_out: bool = False
    cashed_out: bool = False

    @property
    def key(self) -> str:
        return self.persona.key

    @property
    def zar_reference(self) -> str | None:
        return f"{self.base_reference}-zar" if self.base_reference else None


@dataclass
class RunContext:
    scenario: Scenario
    run_id: str
    clock: SimClock
    clerk: ClerkGateway
    emit: Emit
    window_start: datetime
    window_end: datetime
    rng: random.Random = field(init=False)
    people: dict[str, SeededPerson] = field(default_factory=dict)
    staff_by_role: dict[str, list[SeededPerson]] = field(default_factory=dict)
    admin_user_id: uuid.UUID | None = None
    counters: Counter = field(default_factory=Counter)
    refusals: list[dict] = field(default_factory=list)
    simulated_burn_total: Decimal = Decimal("0")
    synthetic_hashes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.scenario.seed)

    def log(self, message: str, level: str = "info", **extra) -> None:
        self.emit({"type": "log", "level": level, "message": message, **extra})

    def count(self, key: str, amount: int = 1) -> None:
        self.counters[key] += amount

    def staff(self, role: str) -> SeededPerson:
        members = self.staff_by_role.get(role) or []
        if not members:
            raise RuntimeError(f"The scenario has no {role}")
        return self.rng.choice(members)

    def people_with_role(self, role: str) -> list[SeededPerson]:
        return [p for p in self.people.values() if p.persona.role == role]
