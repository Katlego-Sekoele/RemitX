"""Who the stokvel demo's members are and which stokvels they are in.

Plain data, with no backend import: `Scenario.validate` reads it, and a
scenario is validated in the UI's own process, which must never import
`remitx_api` (settings.py). The story that acts on it is stokvel.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from remitx_seeder.data import load

# Room in the window for KYC review (which waits for office hours) and the
# deposit's next-working-morning reconciliation before the setup.
MIN_DEMO_DAYS = 14
READY_STOKVEL = "Masakhane Savings Club"
LAPSE_STOKVEL = "Siyakhula Savings Club"


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


# Three corridors, so each payout crosses a different border.
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


@dataclass(frozen=True)
class DemoStokvel:
    which: str
    name: str
    # Indexes into DEMO_MEMBERS: the Organiser first, then the members who
    # join, in payout order.
    members: tuple[int, ...]
    # Invited and left unanswered, or None.
    pending: int | None


STOKVELS = (
    DemoStokvel("ready", READY_STOKVEL, members=(0, 1, 2), pending=None),
    # The member cap counts accepted members, so a full stokvel cannot also
    # hold a pending invitation: the lapse is shown on a second one.
    DemoStokvel("lapse", LAPSE_STOKVEL, members=(1, 2), pending=0),
)
