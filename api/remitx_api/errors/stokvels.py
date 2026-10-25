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
    """Only the Organiser invites, revokes an invitation (R2-16), or sets the
    payout order (R2-09). A fellow member can see the stokvel, so gets this
    rather than `StokvelNotFoundError`. `action` completes "Only the
    stokvel's organiser can ..."."""

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


# --- Starting a cycle (R2-10). Codes and wording are doc section 6's.


class CycleAlreadyStartedError(ConflictError):
    """The stokvel's open cycle has already started (contract error
    `CycleInProgress`). The next cycle starts only after this one closes."""

    code = "cycle_in_progress"

    def __init__(self) -> None:
        super().__init__("This stokvel's cycle has already started.")


class TooFewMembersError(ConflictError):
    """A cycle needs at least `minimum` current members (contract error
    `TooFewMembers`, `MIN_MEMBERS`). A 409: more members can join first."""

    code = "too_few_members"

    def __init__(self, minimum: int) -> None:
        super().__init__(f"A cycle needs at least {minimum} members.")
        self.minimum = minimum


class CycleNotReadyError(ConflictError):
    """The payout order or a beneficiary is missing, so the cycle cannot
    start: every current member needs a payout position and a beneficiary
    (CONTEXT.md, Payout beneficiary). `detail` says which."""

    code = "cycle_not_ready"

    @classmethod
    def order_missing(cls) -> CycleNotReadyError:
        return cls("Set the payout order for every current member first.")

    @classmethod
    def order_out_of_date(cls) -> CycleNotReadyError:
        return cls(
            "The members have changed since the payout order was set. Set it again."
        )

    @classmethod
    def beneficiary_missing(cls) -> CycleNotReadyError:
        return cls("Every member must choose a payout beneficiary first.")


class InvalidCycleScheduleError(DomainError):
    """The round schedule breaks a rule the contract enforces in
    `startCycle` (`ScheduleLengthMismatch`, `InvalidSchedule`). `detail` says
    which; rounds are numbered from 1 for the reader."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "invalid_schedule"

    @classmethod
    def wrong_length(cls, members: int) -> InvalidCycleScheduleError:
        return cls(
            f"Give one round for each of the {members} members, in payout order."
        )

    @classmethod
    def out_of_order(cls, round_: int) -> InvalidCycleScheduleError:
        return cls(
            f"Round {round_ + 1}: the start time, deadline and payout time must be "
            "in that order."
        )

    @classmethod
    def goes_backwards(cls, round_: int) -> InvalidCycleScheduleError:
        return cls(
            f"Round {round_ + 1} can't start or pay out before the round before it."
        )


class StokvelContractUnavailableError(DomainError):
    """The API could not read the vault's pause state from the chain."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    def __init__(self) -> None:
        super().__init__(
            "The stokvel contract cannot be reached right now. Try again shortly."
        )


class StokvelPausedError(DomainError):
    """The vault's emergency pause is active (OpenZeppelin `EnforcedPause`)."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "stokvel_paused"

    def __init__(self) -> None:
        super().__init__("Stokvels are temporarily paused.")


class StokvelContractAlreadyPausedError(ConflictError):
    """`pause()` was called while the vault is already paused."""

    code = "stokvel_paused"

    def __init__(self) -> None:
        super().__init__("Stokvels are already paused.")


class StokvelContractActionTimedOutError(DomainError):
    """The worker did not confirm the on-chain send before the API gave up
    waiting. The transaction may still land; the audit log records the attempt."""

    status_code = status.HTTP_504_GATEWAY_TIMEOUT

    def __init__(self) -> None:
        super().__init__(
            "The contract action is still being sent on-chain. Check the audit "
            "log and the vault's paused state."
        )


class RoundNotFinalisableError(ConflictError):
    """The contract would revert `NotYetFinalisable`: the round is not the
    next to release, it is not fully paid, or its payout time has not passed."""

    code = "round_not_finalisable"

    def __init__(self) -> None:
        super().__init__("This round can't be paid out yet.")


class RoundAlreadyFinalisedError(ConflictError):
    """The contract would revert `AlreadyFinalised`."""

    code = "round_already_finalised"

    def __init__(self) -> None:
        super().__init__("This round has already been paid out.")


class RoundReleaseNotPendingError(ConflictError):
    """The payout is `processing` or `failed`. `release_pool` only claims a
    `pending` row, so queueing again would record a send that never happens.
    Handing a `processing` claim back could pay the round twice."""

    code = "round_release_not_pending"

    def __init__(self) -> None:
        super().__init__(
            "This round's payout is already in progress or has failed, so it "
            "can't be queued again."
        )


class StokvelChainMismatchError(DomainError):
    """The database says this cycle is registered, but the vault has no open
    cycle for it, or does not know the stokvel. Retrying will not fix a
    redeployed vault or a wrong contract address."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "stokvel_chain_mismatch"

    def __init__(self) -> None:
        super().__init__(
            "This stokvel's records don't match the contract. An operator "
            "needs to check the vault before this round can be paid out."
        )


class StokvelContractNotPausedError(ConflictError):
    """`unpause()` was called while the vault is running."""

    def __init__(self) -> None:
        super().__init__("Stokvels aren't paused.")


class CycleStartingError(ConflictError):
    """The cycle has started but the worker has not yet registered it on the
    contract, which would refuse a contribution until it has
    (`CycleNotOpen`). Usually a matter of seconds."""

    code = "cycle_starting"

    def __init__(self) -> None:
        super().__init__(
            "This stokvel's cycle is still being set up. Try again in a minute."
        )
