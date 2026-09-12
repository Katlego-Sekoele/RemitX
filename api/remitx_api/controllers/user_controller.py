import uuid
from collections.abc import Callable

from sqlalchemy.exc import IntegrityError

from remitx_api.extensions import db
from remitx_api.models.orm.user import KYC_STATUSES, User
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.user_repository import UserRepository


class UnknownUserError(Exception):
    """Raised when an admin action targets a user id that doesn't exist."""


class UserController:
    def __init__(self) -> None:
        self._users = UserRepository()
        self._accounts = AccountRepository()

    def ensure_provisioned(
        self,
        clerk_user_id: str,
        resolve_email: Callable[[], str | None],
        resolve_first_name: Callable[[], str | None],
    ) -> User:
        """Return the local row for a Clerk identity, creating it on first sight.

        Clerk is the source of truth for who a user is; this row exists so
        domain records have a local foreign key to hang off. A new user also
        gets their base_reference assigned and their ZAR/uctusd accounts
        created eagerly here, in the same transaction — see
        UserRepository.next_base_reference and
        AccountRepository.create_user_accounts.

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
            user = self._users.add(
                User(
                    clerk_user_id=clerk_user_id,
                    email=resolve_email(),
                    first_name=first_name,
                    base_reference=self._users.next_base_reference(first_name),
                )
            )
            self._accounts.create_user_accounts(user.id, user.base_reference)
            db.session.commit()
            return user
        except IntegrityError:
            # A concurrent first request from the same caller won the insert,
            # OR a different same-named signup won the race for this user's
            # base_reference (a known, pre-existing gap — not retried). The
            # unique constraint on clerk_user_id is what arbitrates the
            # former; roll back and take the winner's row.
            db.session.rollback()
            winner = self._users.get_by_clerk_id(clerk_user_id)
            if winner is None:
                # Not a lost race on clerk_user_id — some other constraint
                # failed. Surface it.
                raise
            return winner

    def set_kyc_status(self, user_id: uuid.UUID, kyc_status: str) -> User:
        """Admin-only KYC toggle (Transaction_Flow_Context.md's flow assumes
        both parties are already KYC-approved; this is the minimal switch
        that makes that assumption satisfiable, not a real KYC module — no
        document intake or review queue exists here, deliberately).
        """
        if kyc_status not in KYC_STATUSES:
            raise ValueError(f"Unknown kyc_status: {kyc_status!r}")

        user = self._users.get_by_id(user_id)
        if user is None:
            raise UnknownUserError(str(user_id))

        user.kyc_status = kyc_status
        return self._users.save(user)
