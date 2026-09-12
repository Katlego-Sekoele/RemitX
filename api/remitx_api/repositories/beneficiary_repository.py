import uuid

from sqlalchemy import select

from remitx_api.extensions import db
from remitx_api.models.orm.beneficiary import Beneficiary
from remitx_api.models.orm.user import User
from remitx_api.repositories.repository import Repository


class BeneficiaryRepository(Repository[Beneficiary, uuid.UUID]):
    """
    Repository for Beneficiary ORM model.
    Used to encapsulate all database access for the Beneficiary model.
    """

    def __init__(self) -> None:
        super().__init__(Beneficiary)

    def get_sender_beneficiary_list_newest_order(
        self, sender_user_id: uuid.UUID
    ) -> list[tuple[Beneficiary, User]]:
        """A sender's own beneficiary contacts, newest first, each paired
        with its linked User — first_name/email live there, not on
        Beneficiary (see models/orm/beneficiary.py)."""
        return db.session.execute(
            select(Beneficiary, User)
            .join(User, Beneficiary.linked_user_id == User.id)
            .where(Beneficiary.sender_user_id == sender_user_id)
            .order_by(Beneficiary.created_at.desc())
        ).all()

    def get_sender_beneficiary_list_alphabetical_order(
        self, sender_user_id: uuid.UUID
    ) -> list[tuple[Beneficiary, User]]:
        """Same as get_sender_beneficiary_list_newest_order, sorted by the
        linked User's first name — Beneficiary itself has no name column to
        sort by."""
        return db.session.execute(
            select(Beneficiary, User)
            .join(User, Beneficiary.linked_user_id == User.id)
            .where(Beneficiary.sender_user_id == sender_user_id)
            .order_by(User.first_name)
        ).all()
