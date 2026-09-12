import uuid

from sqlalchemy import func, select

from remitx_api.errors.users import UnknownUserError
from remitx_api.extensions import db
from remitx_api.models.orm.user import User, reference_base
from remitx_api.repositories.repository import Repository


class UserRepository(Repository[User, uuid.UUID]):
    def __init__(self) -> None:
        super().__init__(User)

    def require_by_id(self, user_id: uuid.UUID) -> User:
        """The user, or ``UnknownUserError``.

        Whether a user id exists is the user domain's question, so callers
        that only need the row get it answered here rather than each writing
        their own ``if is None: raise``.
        """
        user = self.get_by_id(user_id)
        if user is None:
            raise UnknownUserError(user_id)
        return user

    def get_by_clerk_id(self, clerk_user_id: str) -> User | None:
        return db.session.scalars(
            select(User).where(User.clerk_user_id == clerk_user_id)
        ).first()

    def search_by_email(self, query: str, limit: int = 10) -> list[User]:
        """Users whose email contains ``query``, for the grant panel's picker.

        Capped rather than paginated: the picker exists to find one colleague
        by address, not to browse the customer base, so a search that matches
        half the table should send the admin back to type more of it.
        """
        pattern = f"%{query.strip().lower()}%"
        return list(
            db.session.scalars(
                select(User)
                .where(func.lower(User.email).like(pattern))
                .order_by(User.email)
                .limit(limit)
            ).all()
        )

    def add(self, user: User) -> User:
        """Insert a user. Flushes only — caller commits."""
        db.session.add(user)
        db.session.flush()
        return user

    def next_base_reference(self, first_name: str | None) -> str:
        """The next free "<name><n>" base reference for a first name, e.g.
        the second "Sian" to sign up gets "sian2".

        Called once, by UserController.ensure_provisioned, when inserting a
        new user. Looks at every existing base reference sharing this name's
        base rather than just counting them, so a gap left by a deleted user
        can't make two live rows collide.
        """
        base = reference_base(first_name)
        existing = db.session.scalars(
            select(User.base_reference).where(User.base_reference.like(f"{base}%"))
        ).all()

        used_numbers = set()
        for value in existing:
            suffix = value[len(base) :]
            if suffix.isdigit():
                used_numbers.add(int(suffix))

        next_number = 1
        while next_number in used_numbers:
            next_number += 1
        return f"{base}{next_number}"
