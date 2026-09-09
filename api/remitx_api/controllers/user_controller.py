from collections.abc import Callable

from sqlalchemy.exc import IntegrityError

from remitx_api.extensions import db
from remitx_api.models.orm.user import User
from remitx_api.repositories.user_repository import UserRepository


class UserController:
    def __init__(self) -> None:
        self._users = UserRepository()

    def ensure_provisioned(
        self,
        clerk_user_id: str,
        resolve_email: Callable[[], str | None],
        resolve_first_name: Callable[[], str | None],
    ) -> User:
        """Return the local row for a Clerk identity, creating it on first sight.

        Clerk is the source of truth for who a user is; this row exists so
        domain records have a local foreign key to hang off.

        `resolve_email` and `resolve_first_name` are callables rather than
        values because resolving either costs a Clerk API call — neither is a
        session-token claim. Returning users short-circuit above, so each
        call happens once per user lifetime and never on the hot path.
        """
        existing = self._users.get_by_clerk_id(clerk_user_id)
        if existing is not None:
            return existing

        first_name = resolve_first_name()
        try:
            return self._users.save(
                User(
                    clerk_user_id=clerk_user_id,
                    email=resolve_email(),
                    first_name=first_name,
                    reference=self._users.next_reference(first_name),
                )
            )
        except IntegrityError:
            # A concurrent first request from the same caller won the insert.
            # The unique constraint on clerk_user_id is what arbitrates; roll
            # back the failed transaction and take the winner's row.
            db.session.rollback()
            winner = self._users.get_by_clerk_id(clerk_user_id)
            if winner is None:
                # Not a lost race — some other constraint failed. Surface it.
                raise
            return winner
