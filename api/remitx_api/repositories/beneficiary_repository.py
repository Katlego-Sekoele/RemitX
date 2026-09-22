import uuid
from typing import NamedTuple

from sqlalchemy import Select, func, select

from remitx_api.extensions import db
from remitx_api.models.orm.beneficiary import Beneficiary
from remitx_api.models.orm.country import Country
from remitx_api.models.orm.user import User
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.repository import Repository


class BeneficiaryRow(NamedTuple):
    """A beneficiary with the linked person it resolves to. Name, contact and
    country live on `User` (and the country's name on `Country`), not on
    `Beneficiary` — see models/orm/beneficiary.py. `payout_currencies` is the
    payout accounts that person already holds."""

    beneficiary: Beneficiary
    user: User
    country: Country | None
    payout_currencies: tuple[str, ...]


# The name a beneficiary is listed and sorted by: the verified name once
# their KYC is approved, the Clerk first name until then.
display_name = func.coalesce(User.full_name, User.first_name)


class BeneficiaryRepository(Repository[Beneficiary, uuid.UUID]):
    """
    Repository for Beneficiary ORM model.
    Used to encapsulate all database access for the Beneficiary model.
    """

    def __init__(self) -> None:
        super().__init__(Beneficiary)

    def get_sender_beneficiary_list_newest_order(
        self, sender_user_id: uuid.UUID
    ) -> list[BeneficiaryRow]:
        """A sender's own beneficiary contacts, newest first."""
        return self._rows(
            self._for_sender(sender_user_id).order_by(Beneficiary.created_at.desc())
        )

    def get_sender_beneficiary_list_alphabetical_order(
        self, sender_user_id: uuid.UUID
    ) -> list[BeneficiaryRow]:
        """Same as get_sender_beneficiary_list_newest_order, A-Z by display
        name, ignoring case. Unnamed beneficiaries sort last."""
        return self._rows(
            self._for_sender(sender_user_id).order_by(
                func.lower(display_name).asc().nulls_last(),
                Beneficiary.created_at.desc(),
            )
        )

    def get_sender_beneficiary(
        self, sender_user_id: uuid.UUID, beneficiary_id: uuid.UUID
    ) -> BeneficiaryRow | None:
        """One of the sender's own beneficiaries. Someone else's id reads as
        absent, the same as an unknown one."""
        rows = self._rows(
            self._for_sender(sender_user_id).where(
                Beneficiary.beneficiary_id == beneficiary_id
            )
        )
        return rows[0] if rows else None

    def exists_for_sender(
        self, sender_user_id: uuid.UUID, linked_user_id: uuid.UUID
    ) -> bool:
        """Whether the sender already has this person as a beneficiary."""
        return (
            db.session.scalar(
                select(Beneficiary.beneficiary_id).where(
                    Beneficiary.sender_user_id == sender_user_id,
                    Beneficiary.linked_user_id == linked_user_id,
                )
            )
            is not None
        )

    @staticmethod
    def _for_sender(sender_user_id: uuid.UUID) -> Select:
        return (
            select(Beneficiary, User, Country)
            .join(User, Beneficiary.linked_user_id == User.id)
            .outerjoin(Country, User.country == Country.code)
            .where(Beneficiary.sender_user_id == sender_user_id)
        )

    @staticmethod
    def _rows(statement: Select) -> list[BeneficiaryRow]:
        raw = db.session.execute(statement).all()
        currencies = AccountRepository().payout_currencies_by_user(
            [user.id for _, user, _ in raw]
        )
        return [
            BeneficiaryRow(
                beneficiary,
                user,
                country,
                currencies.get(user.id, ()),
            )
            for beneficiary, user, country in raw
        ]
