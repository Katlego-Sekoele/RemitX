"""Errors raised by the stokvel domain.

Each ``detail`` is written for the customer to read as is.
"""

from __future__ import annotations

from decimal import Decimal

from remitx_api.errors.base import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
)


class KycNotApprovedToCreateStokvelError(ForbiddenError):
    """Creating a stokvel is for verified customers only: its members
    receive cross-border payouts, so the bar is the same as sending."""

    def __init__(self) -> None:
        super().__init__(
            "Only verified customers can create a stokvel. Finish verification "
            "to continue."
        )


class StokvelCurrencyAccountMissingError(DomainError):
    """The Organiser pays contributions from their own fiat account in the
    Stokvel currency (D7), and they don't hold one. Never opened on their
    behalf: they open it themselves first. A plain 400, as for the
    beneficiaries' `PayoutAccountMissingError`."""

    def __init__(self, currency: str) -> None:
        super().__init__(
            f"Open a {currency} account first. Your contributions are paid from it."
        )
        self.currency = currency


# --- Contributions (R2-11). Codes and wording are doc section 6's.


class StokvelNotFoundError(NotFoundError):
    """No stokvel with that id that the caller can see. One outcome for
    "unknown" and "not yours", so an id alone reveals nothing."""

    def __init__(self) -> None:
        super().__init__("Stokvel not found.")


class NotACycleMemberError(ForbiddenError):
    """The caller is a current member of the stokvel but not of its current
    cycle, so they have no round to pay into (contract error `NotMember`).
    Someone who is not a current member at all gets `StokvelNotFoundError`."""

    code = "not_a_member"

    def __init__(self) -> None:
        super().__init__("You're not a member of this stokvel's current cycle.")


class CycleNotOpenError(ConflictError):
    """The stokvel has no active cycle: none started yet, or the last one has
    closed (contract error `CycleNotOpen`)."""

    code = "cycle_not_open"

    def __init__(self) -> None:
        super().__init__("This stokvel has no active cycle right now.")


class NoOpenRoundError(ConflictError):
    """Every round of the cycle already has a contribution from every member,
    so there is no round left to pay into (contract error `WrongRound`)."""

    code = "wrong_round"

    def __init__(self) -> None:
        super().__init__("This round isn't open for contributions.")


class ContributionAlreadyPaidError(ConflictError):
    """The caller already has a contribution to the open round that has not
    failed (contract error `AlreadyPaid`)."""

    code = "contribution_already_paid"

    def __init__(self) -> None:
        super().__init__("You've already paid for this round.")


class ContributionInsufficientBalanceError(DomainError):
    """The member's available balance does not cover the contribution and its
    fee. A plain 400, as for a remittance's short balance."""

    def __init__(self, available: Decimal, needed: Decimal, currency: str) -> None:
        super().__init__(
            f"Your available {currency} balance is {available:,.2f}, and this "
            f"contribution needs {needed:,.2f}. Top up your {currency} account "
            "first."
        )
        self.available = available
        self.needed = needed
        self.currency = currency
