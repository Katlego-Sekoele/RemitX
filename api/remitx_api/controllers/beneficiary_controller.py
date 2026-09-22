"""
Controller for Beneficiary-related operations.
Used for business logic and orchestration of database
access for Beneficiary model.

"""

import uuid

from remitx_api.models.orm.account import CURRENCY_TOKEN
from remitx_api.models.orm.beneficiary import Beneficiary
from remitx_api.models.orm.user import User
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.beneficiary_repository import (
    BeneficiaryRepository,
    BeneficiaryRow,
)
from remitx_api.repositories.user_repository import UserRepository

SORT_NEWEST = "newest"
SORT_ALPHABETICAL = "alphabetical"
BENEFICIARY_SORT_OPTIONS = (SORT_NEWEST, SORT_ALPHABETICAL)


class UnknownLinkedUserError(Exception):
    """Raised when a beneficiary is created against a `linked_user_id` that
    doesn't exist — project requires the beneficiary already be a
    registered platform user."""


class InvalidSortOptionError(Exception):
    """Raised when a sort option isn't one of BENEFICIARY_SORT_OPTIONS"""


class LookupByReferenceError(Exception):
    """Raised when `lookup_by_fiat_account_reference` is given an account
    reference that doesn't resolve to any account."""


class NotAFiatAccountError(Exception):
    """Raised when the resolved account is the target's `uctusd` account
    instead of their fiat one.
    """


class CannotAddSelfError(Exception):
    """Raised when a sender looks up their own account reference — a single
    User account can't sensibly be its own beneficiary."""


class MissingContactInfoError(Exception):
    """Raised when the linked user has neither a mobile_number nor an email
    on file — brief: "mobile number or email address" required. Both now
    live on User (see models/orm/beneficiary.py), so this is purely a
    precondition on that user's own profile, not anything the sender
    provides — can't be a DB CHECK constraint since it's a single-field
    "at least one of" check on User, evaluated at Beneficiary-creation time."""


class BeneficiaryController:
    def __init__(self) -> None:
        self._beneficiaries = BeneficiaryRepository()
        self._users = UserRepository()
        self._accounts = AccountRepository()

    def lookup_by_fiat_account_reference(
        self, sender_user_id: uuid.UUID, account_reference: str
    ) -> User:
        """Resolve a beneficiary candidate from the fiat account reference
        (e.g. "sian1-zar") they shared with the sender off-platform — the
        preview step before `create`.

        Matches on the specific account, not just the person
        (`base_reference` alone), so this is already the right shape for a
        future where a user can hold more than one fiat account.
        """
        account = self._accounts.get_user_account_by_reference(account_reference)
        if account is None:
            raise LookupByReferenceError(account_reference)
        if account.account_currency == CURRENCY_TOKEN:
            raise NotAFiatAccountError(account_reference)
        if account.user_id == sender_user_id:
            raise CannotAddSelfError(account_reference)
        return self._users.get_by_id(account.user_id)

    def create(
        self,
        sender_user_id: uuid.UUID,
        linked_user_id: uuid.UUID,
        payout_currency: str,
        relationship: str,
    ) -> BeneficiaryRow:
        """Create a new Beneficiary record in the database.

        Returns the new row with its linked User, same shape as the list
        methods — name, contact and country all come from there, not this
        table.
        """
        # If the linked_user_id doesn't exist, raise an error.
        # This is a business rule for this project.
        linked_user = self._users.get_by_id(linked_user_id)
        if linked_user is None:
            raise UnknownLinkedUserError(str(linked_user_id))

        if not linked_user.mobile_number and not linked_user.email:
            raise MissingContactInfoError(str(linked_user_id))

        beneficiary = self._beneficiaries.save(
            Beneficiary(
                sender_user_id=sender_user_id,
                linked_user_id=linked_user_id,
                payout_currency=payout_currency,
                relationship=relationship,
            )
        )
        return self._beneficiaries.get_sender_beneficiary(
            sender_user_id, beneficiary.beneficiary_id
        )

    def list_beneficiaries(
        self, sender_user_id: uuid.UUID, sort: str = SORT_NEWEST
    ) -> list[BeneficiaryRow]:
        """Return a sender's beneficiaries, each with its linked User."""
        if sort not in BENEFICIARY_SORT_OPTIONS:
            raise InvalidSortOptionError(sort)
        if sort == SORT_ALPHABETICAL:  # Sort by display name, A-Z
            return self._beneficiaries.get_sender_beneficiary_list_alphabetical_order(
                sender_user_id
            )
        return self._beneficiaries.get_sender_beneficiary_list_newest_order(
            sender_user_id
        )
