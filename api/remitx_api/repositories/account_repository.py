import uuid
from decimal import Decimal

from sqlalchemy import func, select, update

from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    TYPE_USER,
    Account,
    create_account_reference,
)
from remitx_api.models.orm.transaction import (
    STATUS_PENDING,
    STATUS_PROCESSING,
    Transaction,
)
from remitx_api.repositories.repository import Repository


class AccountRepository(Repository[Account, uuid.UUID]):
    def __init__(self) -> None:
        super().__init__(Account)

    def get_platform_account_by_label(self, label: str) -> Account | None:
        """Look up a hand-seeded platform/external account by its label."""
        return db.session.scalars(select(Account).where(Account.label == label)).first()

    def get_platform_account(self, type_: str, currency: str) -> Account | None:
        """A hand-seeded platform account by `type` and currency — e.g. the
        `REMITX_REVENUE` account for whatever currency a leg is actually in,
        rather than a fixed label. `scripts/seed_platform_accounts.py` seeds
        exactly one per (type, currency) pair (Transaction_Flow_Context.md
        §1: "a fee earned on a ZAR transaction can no more land in a USD
        revenue account than a ZAR deposit could land in the USD bank
        account"), so this is always unique.
        """
        return db.session.scalars(
            select(Account).where(
                Account.type == type_,
                Account.account_currency == currency,
            )
        ).first()

    def get_user_account_by_reference(self, reference: str) -> Account | None:
        """USER-account lookup by permanent reference.

        `reference` is globally unique (see `Account.reference`) and already
        carries its own currency suffix (e.g. "sian1-zar" vs "sian1-tok"), so
        matching on it alone identifies exactly one account.
        """
        return db.session.scalars(
            select(Account).where(
                Account.reference == reference,
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

    def list_user_accounts(self, user_id: uuid.UUID) -> list[Account]:
        """Every currency account this person owns — always ZAR + uctusd
        today (both created eagerly at signup), but not assumed to stay
        exactly two."""
        return db.session.scalars(
            select(Account).where(
                Account.user_id == user_id,
                Account.type == TYPE_USER,
            )
        ).all()

    def get_or_create_user_account(
        self, user_id: uuid.UUID, base_reference: str, currency: str
    ) -> Account:
        """Like `get_user_account`, but provisions the account on the spot if
        this is the first time this person has ever needed one in this
        currency — e.g. a beneficiary receiving their first remittance in a
        payout currency nobody creates an account for at signup (only ZAR +
        uctusd are eager)."""
        account = self.get_user_account(user_id, currency)
        if account is not None:
            return account
        account = self._build_account(user_id, base_reference, currency)
        db.session.add(account)
        db.session.flush()
        return account

    def create_user_accounts(
        self, user_id: uuid.UUID, base_reference: str
    ) -> tuple[Account, Account]:
        """Create a new user's default ZAR account and their uctusd account,
        together, at signup — both built from their `User.base_reference`
        (e.g. "sian1" -> "sian1-zar", "sian1-tok"). Flushes only — caller
        (UserController.ensure_provisioned) commits alongside the new User
        row, in the same transaction that assigned `base_reference`.
        """
        zar = self._build_account(user_id, base_reference, CURRENCY_ZAR)
        token = self._build_account(user_id, base_reference, CURRENCY_TOKEN)
        db.session.add_all([zar, token])
        db.session.flush()
        return zar, token  # return Account objects

    def _build_account(
        self, user_id: uuid.UUID, base_reference: str, currency: str
    ) -> Account:
        reference = create_account_reference(base_reference, currency)
        return Account(
            user_id=user_id,
            type=TYPE_USER,
            account_currency=currency,
            reference=reference,
            label=f"({currency} Account)",
        )

    def increase_balance(self, account_id: uuid.UUID, amount) -> None:
        """Atomically add `amount` to an account's balance if it is
        on the debit_account_id (destination) side of a transaction."""
        db.session.execute(
            update(Account)
            .where(Account.account_id == account_id)
            .values(account_balance=Account.account_balance + amount)
        )

    def decrease_balance(self, account_id: uuid.UUID, amount) -> None:
        """Atomically subtract `amount` from an account's balance — the
        credit_account_id (source) side of a transaction."""
        db.session.execute(
            update(Account)
            .where(Account.account_id == account_id)
            .values(account_balance=Account.account_balance - amount)
        )

    def get_available_balance(self, account_id: uuid.UUID) -> Decimal:
        """Raw balance minus this account's own still-in-flight outgoing
        transactions. A quote is only valid if the user has sufficient
        available balance to cover the entire quote amount.

        Includes `processing` alongside `pending`: `burn_treasury_tokens`
        claims a quote's legs into `processing` before its XRPL call
        resolves, so excluding only `pending` would let that committed
        amount look spendable again during the burn/confirm window.
        """
        account = self.get_by_id(account_id)
        # credit_account_id is the source of a leg (money leaving this account).
        pending_outgoing = db.session.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.credit_account_id == account_id,
                Transaction.status.in_((STATUS_PENDING, STATUS_PROCESSING)),
            )
        )
        return account.account_balance - pending_outgoing

    def get_available_balance_locked(self, account_id: uuid.UUID) -> Decimal:
        """Like `get_available_balance`, but takes a `SELECT ... FOR UPDATE`
        row lock on the account first.

        Checking available balance and then inserting a new `pending` transaction
        is a check-then-act sequence: without a lock, two concurrent callers
        against the *same* account (two withdrawal requests, or a withdrawal
        racing a remittance confirm) can both read the balance before either
        has committed its own pending transaction, so both pass the check and
        together overdraw the account. Taking this lock first makes a second
        concurrent caller block until the first one's transaction commits or
        rolls back, so it re-reads a balance that already reflects the
        first caller's pending transaction.

        Only for call sites that are about to gate a spend on the result —
        `withdrawal_service.request_withdrawal`,
        `remittance_service.confirm_remittance`. 
        A read-only path (e.g.`GET /accounts`) use `get_available_balance` as
        a lock would add unnecessary contention with genuine spenders.
        """
        account = db.session.execute(
            select(Account).where(Account.account_id == account_id).with_for_update()
        ).scalar_one()
        pending_outgoing = db.session.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.credit_account_id == account_id,
                Transaction.status.in_((STATUS_PENDING, STATUS_PROCESSING)),
            )
        )
        return account.account_balance - pending_outgoing
