import uuid

from sqlalchemy import select, update

from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    TYPE_USER,
    Account,
    account_reference,
)
from remitx_api.repositories.repository import Repository


class AccountRepository(Repository[Account, uuid.UUID]):
    def __init__(self) -> None:
        super().__init__(Account)

    def get_platform_account(self, label: str) -> Account | None:
        """Look up a hand-seeded platform/external account by its label."""
        return db.session.scalars(select(Account).where(Account.label == label)).first()

    def get_by_reference(self, reference: str, currency: str) -> Account | None:
        """USER-account lookup by permanent reference, scoped to one currency.

        Always pass the statement's own currency here (ZAR for bank-statement
        reconciliation) — never search across every currency a user might
        hold. This is what stops a "sian1-tok" reference from ever resolving
        as a deposit target.
        """
        return db.session.scalars(
            select(Account).where(
                Account.reference == reference,
                Account.account_currency == currency,
                Account.type == TYPE_USER,
            )
        ).first()

    def get_user_account(self, user_id: uuid.UUID, currency: str) -> Account | None:
        """Strict lookup, no creation — every user has both accounts eagerly
        from signup, so this should always find one."""
        return db.session.scalars(
            select(Account).where(
                Account.user_id == user_id,
                Account.account_currency == currency,
                Account.type == TYPE_USER,
            )
        ).first()

    def create_user_accounts(
        self, user_id: uuid.UUID, base_reference: str
    ) -> tuple[Account, Account]:
        """Create a new user's ZAR and uctusd accounts together, at signup,
        both built from their `User.base_reference` (e.g. "sian1" ->
        "sian1-zar", "sian1-tok"). Flushes only — caller
        (UserController.ensure_provisioned) commits alongside the new User
        row, in the same transaction that assigned `base_reference`.
        """
        zar = self._build_account(user_id, base_reference, CURRENCY_ZAR)
        token = self._build_account(user_id, base_reference, CURRENCY_TOKEN)
        db.session.add_all([zar, token])
        db.session.flush()
        return zar, token

    def _build_account(
        self, user_id: uuid.UUID, base_reference: str, currency: str
    ) -> Account:
        reference = account_reference(base_reference, currency)
        return Account(
            user_id=user_id,
            type=TYPE_USER,
            account_currency=currency,
            reference=reference,
            label=f"{reference} ({currency})",
        )

    def increase_balance(self, account_id: uuid.UUID, amount) -> None:
        """Atomically add `amount` to an account's balance."""
        db.session.execute(
            update(Account)
            .where(Account.account_id == account_id)
            .values(account_balance=Account.account_balance + amount)
        )
