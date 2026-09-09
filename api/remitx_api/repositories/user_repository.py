import uuid

from sqlalchemy import select

from remitx_api.extensions import db
from remitx_api.models.orm.user import User, reference_base
from remitx_api.repositories.repository import Repository


class UserRepository(Repository[User, uuid.UUID]):
    def __init__(self) -> None:
        super().__init__(User)

    def get_by_clerk_id(self, clerk_user_id: str) -> User | None:
        return db.session.scalars(
            select(User).where(User.clerk_user_id == clerk_user_id)
        ).first()

    def get_by_reference(self, reference: str) -> User | None:
        """Look up the sender who owns a permanent EFT reference.

        Called by deposit_service when attributing a bank statement line to
        a user — deposits are no longer pre-registered, so this reference is
        the only link between an incoming payment and an account.
        """
        return db.session.scalars(
            select(User).where(User.reference == reference)
        ).first()

    def next_reference(self, first_name: str | None) -> str:
        """The next free "<name><n>" reference for a first name, e.g. the
        second "Sian" to sign up gets "sian2".

        Called once, by UserController.ensure_provisioned, when inserting a
        new user. Looks at every existing reference sharing this name's base
        rather than just counting them, so a gap left by a deleted user can't
        make two live rows collide.
        """
        base = reference_base(first_name)
        existing = db.session.scalars(
            select(User.reference).where(User.reference.like(f"{base}%"))
        ).all()

        used_numbers = set()
        for reference in existing:
            suffix = reference[len(base) :]
            if suffix.isdigit():
                used_numbers.add(int(suffix))

        next_number = 1
        while next_number in used_numbers:
            next_number += 1
        return f"{base}{next_number}"
