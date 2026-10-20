"""A scenario: how many of whom, over how long, behaving how.

Scenarios are JSON files in `tools/seeder/scenarios/`, edited in the UI or by
hand. Every knob has a default here, so a scenario file only needs to say what
it changes. Rates are probabilities between 0 and 1.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from remitx_seeder.settings import SCENARIOS_DIR


@dataclass
class KycBehaviour:
    # Signs up and never opens the verification wizard.
    never_start_rate: float = 0.06
    # Opens the wizard and stops partway (left `in_progress`).
    abandon_rate: float = 0.08
    # A reviewer asks for a clearer document before deciding.
    more_info_rate: float = 0.15
    # Of those, how many never come back with the document.
    more_info_no_reply_rate: float = 0.25
    reject_rate: float = 0.07
    # Rejected applicants who try again with a new application.
    reapply_rate: float = 0.4
    # An officer overrides the computed risk rating before deciding.
    override_rate: float = 0.08
    # Approved at tier 2 when a source of wealth was declared.
    tier_two_rate: float = 0.5
    pep_rate: float = 0.03
    other_source_rate: float = 0.05
    high_volume_rate: float = 0.05
    # Hours from submission until a reviewer picks it up.
    review_delay_hours: tuple[float, float] = (2, 72)


@dataclass
class MoneyBehaviour:
    # Verified senders who never deposit anything.
    dormant_rate: float = 0.1
    # Bank-statement lines whose reference the depositor mistyped.
    reference_typo_rate: float = 0.06
    # Of the unmatched lines, how many a treasury operator resolves.
    resolve_pending_rate: float = 0.6
    # Quotes looked at and left to expire.
    quote_abandon_rate: float = 0.15
    # Settlements whose (simulated) burn fails on-chain.
    settlement_failure_rate: float = 0.03
    # Deposits are topped up by this factor over what the month's sends need.
    deposit_headroom: float = 1.08
    # Verified customers who register an external bank account.
    bank_account_rate: float = 0.6
    # Of those accounts, the share a payout operator rejects.
    bank_reject_rate: float = 0.08
    # Of the rest, the share left in the verification queue.
    bank_leave_pending_rate: float = 0.12
    # Holders of a verified account who cash out some spare balance.
    withdraw_rate: float = 0.7


@dataclass
class StokvelDemo:
    # Seed the stokvel demo (R6-03, stories/stokvel.py): three named members,
    # KYC-approved and funded, in a stokvel ready for its Organiser to start,
    # plus a second stokvel with an invitation still pending.
    enabled: bool = False
    # The stokvel's fixed contribution per round, in uctusd. Every
    # contribution pulls this from the Treasury Wallet on-chain, which the
    # lecturer funds, so the default is small: 3 members x 3 rounds x 2 = 18.
    contribution_uctusd: float = 2.0


@dataclass
class Scenario:
    name: str = "default"
    description: str = ""
    seed: int = 20260924
    days: int = 90
    senders: int = 36
    # Recipients per country. Senders' beneficiaries are drawn from these.
    recipients: dict[str, int] = field(
        default_factory=lambda: {"ZW": 14, "NA": 5, "ZA": 10, "US": 3}
    )
    staff: dict[str, int] = field(
        default_factory=lambda: {
            "compliance_analyst": 2,
            "compliance_officer": 2,
            "treasury_operator": 1,
            "payout_operator": 1,
            "support_agent": 1,
        }
    )
    # Clerk development instances hold 100 users. The run makes at most this
    # many users in total exist (including ones already there) and makes the
    # rest database-only.
    clerk_user_cap: int = 80
    # Give the first senders one each of the rare paths (a PEP of each kind,
    # a rejection, a more-info round trip, one left unanswered, an abandoned
    # draft, a rating override, a tier 2 approval, a high declared volume),
    # so every run has at least one of each for testers to find.
    ensure_every_path: bool = True
    email_domain: str = "example.com"
    kyc: KycBehaviour = field(default_factory=KycBehaviour)
    money: MoneyBehaviour = field(default_factory=MoneyBehaviour)
    stokvel: StokvelDemo = field(default_factory=StokvelDemo)
    # Real settlements through the target's API, worker and EVM chain at the
    # end of the run. 0 keeps everything simulated.
    live_settlements: int = 0
    # The most uctusd the live tail may burn in one run.
    live_token_budget: float = 25.0

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> Scenario:
        known = {f.name for f in fields(cls)}
        unknown = set(raw) - known - {"_about"}
        if unknown:
            raise ValueError(f"Unknown scenario keys: {', '.join(sorted(unknown))}")
        values = {key: value for key, value in raw.items() if key in known}
        if "kyc" in values:
            values["kyc"] = _nested(KycBehaviour, values["kyc"], "kyc")
        if "money" in values:
            values["money"] = _nested(MoneyBehaviour, values["money"], "money")
        if "stokvel" in values:
            values["stokvel"] = _nested(StokvelDemo, values["stokvel"], "stokvel")
        scenario = cls(**values)
        scenario.validate()
        return scenario

    def validate(self) -> None:
        if not 1 <= self.days <= 365:
            raise ValueError("days must be between 1 and 365")
        if self.senders < 0 or any(n < 0 for n in self.recipients.values()):
            raise ValueError("people counts cannot be negative")
        if self.staff.get("compliance_officer", 0) < 1 and self.senders:
            raise ValueError("a scenario with senders needs a compliance_officer")
        if self.staff.get("treasury_operator", 0) < 1 and self.senders:
            raise ValueError("a scenario with senders needs a treasury_operator")
        for group in (self.kyc, self.money):
            for f in fields(group):
                value = getattr(group, f.name)
                if f.name.endswith("_rate") and not 0 <= value <= 1:
                    raise ValueError(f"{f.name} must be between 0 and 1")
        delay = self.kyc.review_delay_hours
        if len(delay) != 2:
            raise ValueError(
                "kyc.review_delay_hours must be [low, high] hours from submit "
                "to review, not a list of discrete values"
            )
        if delay[0] > delay[1]:
            raise ValueError("kyc.review_delay_hours low must be <= high")
        if self.stokvel.enabled:
            self._validate_stokvel_demo()

    def _validate_stokvel_demo(self) -> None:
        # Imported here: stories/stokvel.py imports this module.
        from remitx_seeder.stories.stokvel import DEMO_MEMBERS, MIN_DEMO_DAYS

        if not 0 < self.stokvel.contribution_uctusd <= 100:
            raise ValueError(
                "stokvel.contribution_uctusd must be above 0 and at most 100"
            )
        if self.days < MIN_DEMO_DAYS:
            raise ValueError(
                f"the stokvel demo needs at least {MIN_DEMO_DAYS} days of "
                "history, so its members are verified and funded before it is "
                "set up"
            )
        for role in ("compliance_officer", "treasury_operator"):
            if self.staff.get(role, 0) < 1:
                raise ValueError(f"the stokvel demo needs a {role}")
        for member in DEMO_MEMBERS:
            if self.recipients.get(member.recipient_country, 0) < 1:
                raise ValueError(
                    "the stokvel demo needs a recipient in "
                    f"{member.recipient_country} for the {member.label}'s "
                    "beneficiary"
                )


def _nested(kind, raw: dict, label: str):
    known = {f.name for f in fields(kind)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"Unknown {label} keys: {', '.join(sorted(unknown))}")
    values = dict(raw)
    if "review_delay_hours" in values:
        values["review_delay_hours"] = tuple(values["review_delay_hours"])
    return kind(**values)


def scenario_path(name: str) -> Path:
    return SCENARIOS_DIR / f"{name}.json"


def list_scenarios() -> list[str]:
    return sorted(path.stem for path in SCENARIOS_DIR.glob("*.json"))


def load_scenario(name_or_path: str) -> Scenario:
    path = Path(name_or_path)
    if not path.suffix:
        path = scenario_path(name_or_path)
    return Scenario.from_dict(json.loads(path.read_text()))


def save_scenario(scenario: Scenario) -> Path:
    scenario.validate()
    path = scenario_path(scenario.name)
    path.write_text(json.dumps(scenario.as_dict(), indent=2) + "\n")
    return path
