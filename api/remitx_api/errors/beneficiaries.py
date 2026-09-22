"""Errors raised by the beneficiary domain.

Each ``detail`` is written for the sender to read as is: the add-beneficiary
dialog shows it inline, next to the reference they typed.
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
