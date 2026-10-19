"""Errors raised by the stokvel domain.

Each ``detail`` is written for the customer to read as is.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import status

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


# --- Invitations (R2-08). Codes and wording are doc section 6's.


class NotStokvelOrganiserError(ForbiddenError):
    """Only the Organiser invites, or sets the payout order (R2-09). A
    fellow member can see the stokvel, so gets this rather than
    `StokvelNotFoundError`. `action` completes "Only the stokvel's organiser
    can ..."."""

    code = "not_organiser"

    def __init__(self, action: str = "invite members") -> None:
        super().__init__(f"Only the stokvel's organiser can {action}.")


class StokvelDeactivatedError(ConflictError):
    """The stokvel has been decommissioned: nobody can be invited or join."""

    code = "stokvel_deactivated"

    def __init__(self) -> None:
        super().__init__("This stokvel is no longer active.")


class InviteeAccountNotFoundError(NotFoundError):
    """No customer account has that reference."""

    def __init__(self, reference: str) -> None:
        super().__init__(f"No account has the reference {reference!r}.")
        self.reference = reference


class CannotInviteYourselfError(DomainError):
    """The reference is one of the Organiser's own accounts: they are a
    member already (`stokvel_invitations_not_self`)."""

    def __init__(self) -> None:
        super().__init__("You can't invite yourself.")


class InviteeCurrencyMismatchError(DomainError):
    """The invitee pays contributions from the referenced account, so it
    must be in the Stokvel currency (D7)."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "invitee_currency_mismatch"

    def __init__(self, currency: str) -> None:
        super().__init__(
            f"The account's currency must match the stokvel's currency ({currency})."
        )
        self.currency = currency


class InviteeNotKycVerifiedError(ForbiddenError):
    """Members receive cross-border payouts, so an invitee must be verified,
    as anyone sending a remittance is."""

    code = "invitee_not_verified"

    def __init__(self) -> None:
        super().__init__("This person isn't verified yet, so they can't be invited.")


class AlreadyStokvelMemberError(ConflictError):
    """The invitee is a current member of the stokvel."""

    code = "already_a_member"

    def __init__(self) -> None:
        super().__init__("This person is already a member of the stokvel.")


class InvitationAlreadyPendingError(ConflictError):
    """The invitee already has a pending invitation to this stokvel
    (`uq_stokvel_invitations_pending`)."""

    code = "invitation_already_pending"

    def __init__(self) -> None:
        super().__init__("This person already has a pending invitation.")


class TooManyMembersError(DomainError):
    """The stokvel has `MAX_STOKVEL_MEMBERS` current members (contract error
    `MaxMembersExceeded`)."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "too_many_members"

    def __init__(self, max_members: int) -> None:
        super().__init__(f"A stokvel can have at most {max_members} members.")
        self.max_members = max_members


class InvitationNotFoundError(NotFoundError):
    """No invitation with that id that the caller can see."""

    def __init__(self) -> None:
        super().__init__("Invitation not found.")


class NotInviteeError(ForbiddenError):
    """Only the invitee answers their invitation. Fellow members can see it,
    so get this rather than `InvitationNotFoundError`."""

    code = "not_invitee"

    def __init__(self) -> None:
        super().__init__("Only the person invited can answer this invitation.")


class InvitationNotPendingError(ConflictError):
    """The invitation was already accepted, declined, revoked or lapsed."""

    code = "invitation_not_pending"

    def __init__(self) -> None:
        super().__init__("This invitation has already been answered or has expired.")


class KycNotApprovedToJoinStokvelError(ForbiddenError):
    """The invitee's verification has lapsed since they were invited."""

    def __init__(self) -> None:
        super().__init__(
            "Only verified customers can join a stokvel. Finish verification "
            "to continue."
        )


# --- Payout order and beneficiary (R2-09). Codes and wording are doc
# section 6's.


class PayoutSetupLockedError(ConflictError):
    """The stokvel's cycle has started: its payout order and beneficiaries
    are fixed until it closes."""

    code = "cycle_locked"

    def __init__(self) -> None:
        super().__init__(
            "The payout order and beneficiaries are locked while a cycle is running."
        )


class CycleNotFormingError(ConflictError):
    """The stokvel has no `forming` cycle to set up. Its last cycle has
    closed and the next has not been opened (#237), or, for a member who is
    not the Organiser, a stokvel from before cycles opened at creation has
    none yet: only the Organiser may open one."""

    code = "cycle_not_forming"

    def __init__(self) -> None:
        super().__init__("This stokvel's next cycle hasn't been opened yet.")


class InvalidPayoutOrderError(DomainError):
    """The payout order is not every current member exactly once. `detail`
    says which rule it breaks."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "invalid_payout_order"

    @classmethod
    def duplicate(cls) -> InvalidPayoutOrderError:
        return cls("Each member can appear only once in the payout order.")

    @classmethod
    def former_member(cls) -> InvalidPayoutOrderError:
        return cls("The payout order includes a member who has left the stokvel.")

    @classmethod
    def unknown_member(cls) -> InvalidPayoutOrderError:
        return cls(
            "The payout order includes someone who isn't a member of this stokvel."
        )

    @classmethod
    def missing_member(cls) -> InvalidPayoutOrderError:
        return cls("The payout order must include every current member.")
