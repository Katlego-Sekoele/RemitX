"""Errors raised by the beneficiary domain.

Each ``detail`` is written for the sender to read as is: the add form shows
it inline, next to the field it belongs to.
"""

from __future__ import annotations

import uuid

from remitx_api.errors.base import ConflictError, DomainError, NotFoundError


class UnknownAccountReferenceError(NotFoundError):
    """The reference doesn't resolve to any customer account."""

    def __init__(self, reference: str) -> None:
        super().__init__("No RemitX account has that reference.")
        self.reference = reference


class SettlementReferenceError(DomainError):
    """The reference is someone's uctusd settlement account, which nobody is
    paid into directly."""

    def __init__(self, reference: str) -> None:
        super().__init__(
            "That's a settlement reference. Ask for the one ending in -zar, "
            "-usd, -zwl or -nad."
        )
        self.reference = reference


class OwnAccountReferenceError(DomainError):
    """The sender looked up one of their own references."""

    def __init__(self, reference: str) -> None:
        super().__init__("That's your own account.")
        self.reference = reference


class UnknownLinkedUserError(DomainError):
    """A beneficiary must already be a registered RemitX user."""

    def __init__(self, linked_user_id: uuid.UUID | str) -> None:
        super().__init__("linked_user_id does not exist")
        self.linked_user_id = str(linked_user_id)


class MissingContactInfoError(ConflictError):
    """The brief requires a beneficiary's mobile number or email address, and
    the linked user has neither on file. Theirs to fix, not the sender's."""

    def __init__(self, linked_user_id: uuid.UUID | str) -> None:
        super().__init__(
            "That person has no email or mobile number on file yet. Ask them "
            "to add one to their profile."
        )
        self.linked_user_id = str(linked_user_id)


class DuplicateBeneficiaryError(ConflictError):
    """One beneficiary per person per sender."""

    def __init__(self, linked_user_id: uuid.UUID | str) -> None:
        super().__init__("Already in your beneficiaries")
        self.linked_user_id = str(linked_user_id)


class PayoutAccountMissingError(DomainError):
    """The chosen payout currency is not a fiat account this person holds.

    Signup creates a ZAR account, so that is already a payout account. The
    token account is not."""

    def __init__(self, currency: str, held: tuple[str, ...]) -> None:
        if not held:
            detail = (
                "They don't have a payout account yet. Ask for a reference "
                "ending in -zar, -usd, -zwl or -nad."
            )
        else:
            detail = (
                f"They don't have a {currency} account. They can be paid in "
                f"{_or_list(held)}."
            )
        super().__init__(detail)
        self.currency = currency
        self.held = held


def _or_list(values: tuple[str, ...]) -> str:
    if len(values) == 1:
        return values[0]
    return f"{', '.join(values[:-1])} or {values[-1]}"


class UnknownBeneficiaryError(NotFoundError):
    """No beneficiary with that id belongs to the caller. Someone else's id
    reads the same as an unknown one, so ids can't be probed."""

    def __init__(self, beneficiary_id: uuid.UUID | str) -> None:
        super().__init__("Beneficiary not found")
        self.beneficiary_id = str(beneficiary_id)
