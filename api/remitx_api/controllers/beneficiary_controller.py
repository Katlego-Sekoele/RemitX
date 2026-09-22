"""
Controller for Beneficiary-related operations.
Used for business logic and orchestration of database
access for Beneficiary model.

"""

import uuid
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from remitx_api.errors.beneficiaries import (
    DuplicateBeneficiaryError,
    MissingContactInfoError,
    OwnAccountReferenceError,
    SettlementReferenceError,
    UnknownAccountReferenceError,
    UnknownLinkedUserError,
)
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_TOKEN
from remitx_api.models.orm.beneficiary import Beneficiary
from remitx_api.models.orm.country import Country
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


class InvalidSortOptionError(Exception):
    """Raised when a sort option isn't one of BENEFICIARY_SORT_OPTIONS"""


@dataclass(frozen=True)
class ReferenceLookup:
    """Who an account reference belongs to, and that account's currency."""

    user: User
    country: Country | None
    account_currency: str


class BeneficiaryController:
    def __init__(self) -> None:
        self._beneficiaries = BeneficiaryRepository()
        self._users = UserRepository()
        self._accounts = AccountRepository()

    def lookup_by_fiat_account_reference(
        self, sender_user_id: uuid.UUID, account_reference: str
    ) -> ReferenceLookup:
        """Resolve a beneficiary candidate from the fiat account reference
        (e.g. "sian1-zar") they shared with the sender off-platform — the
        preview step before `create`.

        Matches on the specific account, not just the person
        (`base_reference` alone), so the account's currency can pre-fill the
        payout currency.
        """
        reference = account_reference.strip().lower()
        account = self._accounts.get_user_account_by_reference(reference)
        if account is None:
            raise UnknownAccountReferenceError(reference)
        if account.account_currency == CURRENCY_TOKEN:
            raise SettlementReferenceError(reference)
        if account.user_id == sender_user_id:
            raise OwnAccountReferenceError(reference)
        user = self._users.require_by_id(account.user_id)
        country = (
            None if user.country is None else db.session.get(Country, user.country)
        )
        return ReferenceLookup(
            user=user, country=country, account_currency=account.account_currency
        )

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
            raise UnknownLinkedUserError(linked_user_id)

        if not linked_user.mobile_number and not linked_user.email:
            raise MissingContactInfoError(linked_user_id)

        if self._beneficiaries.exists_for_sender(sender_user_id, linked_user_id):
            raise DuplicateBeneficiaryError(linked_user_id)
        try:
            beneficiary = self._beneficiaries.save(
                Beneficiary(
                    sender_user_id=sender_user_id,
                    linked_user_id=linked_user_id,
                    payout_currency=payout_currency,
                    relationship=relationship,
                )
            )
        except IntegrityError as exc:
            # A concurrent add of the same person won the unique constraint.
            raise DuplicateBeneficiaryError(linked_user_id) from exc
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
