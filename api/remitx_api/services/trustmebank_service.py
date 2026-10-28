"""TrustMeBank OAuth, payment initiation, and deposit confirmation."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from remitx_api.config import Config
from remitx_api.db.transaction import db_transaction
from remitx_api.errors.trustmebank import (
    TrustMeBankDepositNotFoundError,
    TrustMeBankDisabledError,
    TrustMeBankKycRequiredError,
    TrustMeBankNotLinkedError,
    TrustMeBankOAuthStateError,
)
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR, TYPE_PLATFORM_FIAT
from remitx_api.models.orm.audit_log import AuditAction, AuditSubject
from remitx_api.models.orm.deposit import (
    CONFIRMED_BY_SYSTEM,
    PAYMENT_METHOD_TRUSTMEBANK,
    Deposit,
)
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_FAILED,
    STATUS_PENDING,
    TYPE_DEPOSIT,
    Transaction,
)
from remitx_api.models.orm.trustmebank_link import TrustMeBankLink
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.deposit_repository import DepositRepository
from remitx_api.repositories.kyc_application_repository import KycApplicationRepository
from remitx_api.repositories.transaction_repository import TransactionRepository
from remitx_api.repositories.trustmebank_repository import TrustMeBankRepository
from remitx_api.services.trustmebank_client import (
    TrustMeBankClient,
    TrustMeBankClientError,
)

logger = logging.getLogger(__name__)

_AMOUNT_QUANTUM = Decimal("0.01")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
_COMPLETED = "COMPLETED"
_REJECTED = "REJECTED"
_FAILED = "FAILED"
_FINAL_FAILURE = frozenset({_REJECTED, _FAILED})


def is_enabled(config: Config | None = None) -> bool:
    return (config or Config()).ENABLE_TRUSTMEBANK


def require_enabled(config: Config | None = None) -> None:
    if not is_enabled(config):
        raise TrustMeBankDisabledError()


def public_status(config: Config | None = None) -> dict[str, bool]:
    return {"enabled": is_enabled(config)}


def _require_verified(user_id: uuid.UUID) -> None:
    standing = KycApplicationRepository().get_standing(user_id)
    if not standing.is_verified:
        raise TrustMeBankKycRequiredError()


def _format_amount(amount: Decimal) -> str:
    quantized = amount.quantize(_AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)
    if quantized <= 0:
        raise ValueError("Amount must be positive")
    return format(quantized, "f")


class TrustMeBankService:
    def __init__(
        self,
        config: Config | None = None,
        client: TrustMeBankClient | None = None,
    ) -> None:
        self._config = config or Config()
        self._client = client or TrustMeBankClient(self._config)
        self._links = TrustMeBankRepository()
        self._deposits = DepositRepository()
        self._transactions = TransactionRepository()
        self._accounts = AccountRepository()

    def connect_authorize_url(self, user_id: uuid.UUID) -> str:
        require_enabled(self._config)
        state = secrets.token_urlsafe(24)
        self._links.create_oauth_state(user_id, state)
        db.session.commit()
        return self._client.authorize_url(
            state=state,
            redirect_uri=self._config.TRUSTMEBANK_OAUTH_REDIRECT_URI,
            scope=self._config.TRUSTMEBANK_SCOPES,
        )

    @db_transaction
    def complete_oauth(
        self, user_id: uuid.UUID, *, code: str, state: str
    ) -> dict[str, str | None]:
        require_enabled(self._config)
        owner = self._links.consume_oauth_state(state)
        if owner is None or owner != user_id:
            raise TrustMeBankOAuthStateError()
        tokens = self._client.exchange_code(
            code=code,
            redirect_uri=self._config.TRUSTMEBANK_OAUTH_REDIRECT_URI,
        )
        me = self._client.get_me(access_token=tokens.access_token)
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=tokens.expires_in)
        link = TrustMeBankLink(
            user_id=user_id,
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            consent_id=tokens.consent_id,
            scope=tokens.scope,
            customer_id=me.get("customer_id"),
            customer_name=me.get("full_name"),
            token_expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        self._links.save_link(link)
        return {
            "customer_id": link.customer_id,
            "customer_name": link.customer_name,
        }

    def link_status(self, user_id: uuid.UUID) -> dict[str, str | bool | None]:
        require_enabled(self._config)
        link = self._links.get_link(user_id)
        if link is None:
            return {"linked": False, "customer_name": None}
        return {
            "linked": True,
            "customer_name": link.customer_name,
        }

    def list_bank_accounts(self, user_id: uuid.UUID) -> list[dict[str, str]]:
        require_enabled(self._config)
        access_token = self._access_token_for(user_id)
        accounts = self._client.list_accounts(access_token=access_token)
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "account_number": row["account_number"],
                "currency": row["currency"],
                "balance": row.get("balance"),
            }
            for row in accounts
        ]

    @db_transaction
    def start_deposit(
        self,
        user_id: uuid.UUID,
        *,
        amount: Decimal,
        debtor_account_id: str,
    ) -> dict[str, str]:
        require_enabled(self._config)
        _require_verified(user_id)
        access_token = self._access_token_for(user_id)
        user_account = self._accounts.get_user_account(user_id, CURRENCY_ZAR)
        platform = self._accounts.get_platform_account(
            TYPE_PLATFORM_FIAT, CURRENCY_ZAR
        )
        if platform is None:
            raise TrustMeBankClientError("Platform ZAR account is not configured")

        amount_str = _format_amount(amount)
        reference = f"RX-{uuid.uuid4().hex[:10].upper()}"
        deposit_id = uuid.uuid4()
        payment = self._client.create_payment(
            access_token=access_token,
            idempotency_key=str(deposit_id),
            debtor_account_id=debtor_account_id,
            creditor_account_number=self._config.TRUSTMEBANK_SETTLEMENT_ACCOUNT,
            amount=amount_str,
            reference=reference,
            redirect_uri=self._config.TRUSTMEBANK_PAYMENT_REDIRECT_URI,
        )
        now = datetime.now(UTC)
        transaction = self._transactions.add(
            Transaction(
                type=TYPE_DEPOSIT,
                credit_account_id=platform.account_id,
                debit_account_id=user_account.account_id,
                amount=Decimal(amount_str),
                currency=CURRENCY_ZAR,
                status=STATUS_PENDING,
                created_at=now,
                processed_at=now,
            )
        )
        self._deposits.add(
            Deposit(
                deposit_id=deposit_id,
                tx_id=transaction.tx_id,
                user_id=user_id,
                user_account_reference=reference,
                payment_method=PAYMENT_METHOD_TRUSTMEBANK,
                statement_fingerprint=None,
                trustmebank_payment_id=payment.payment_id,
            )
        )
        return {
            "deposit_id": str(deposit_id),
            "payment_id": payment.payment_id,
            "authorisation_url": payment.authorisation_url,
        }

    @db_transaction
    def sync_deposit_for_user(
        self, user_id: uuid.UUID, payment_id: str
    ) -> dict[str, str]:
        require_enabled(self._config)
        deposit = self._deposits.get_by_trustmebank_payment_id(payment_id)
        if deposit is None or deposit.user_id != user_id:
            raise TrustMeBankDepositNotFoundError()
        access_token = self._access_token_for(user_id)
        payment = self._client.get_payment(
            access_token=access_token, payment_id=payment_id
        )
        status = self._apply_payment_status(deposit, payment["status"])
        return {"payment_id": payment_id, "status": status}

    @db_transaction
    def handle_webhook(self, body: bytes, signature_header: str) -> None:
        require_enabled(self._config)
        if not self._verify_signature(body, signature_header):
            raise ValueError("Invalid TrustMeBank webhook signature")
        import json

        event = json.loads(body.decode("utf-8"))
        event_id = event.get("id")
        if not event_id:
            raise ValueError("Webhook missing event id")
        if not self._links.record_webhook_event(event_id):
            return
        if event.get("event") != "payment.completed":
            return
        data = event.get("data") or {}
        payment_id = data.get("payment_id")
        if not payment_id:
            return
        deposit = self._deposits.get_by_trustmebank_payment_id(payment_id)
        if deposit is None:
            logger.warning(
                "TrustMeBank webhook for unknown payment_id=%s", payment_id
            )
            return
        self._apply_payment_status(deposit, data.get("status", _COMPLETED))

    def _apply_payment_status(self, deposit: Deposit, status: str) -> str:
        transaction = self._transactions.get_by_id(deposit.tx_id)
        if transaction.status == STATUS_CONFIRMED:
            return STATUS_CONFIRMED
        if transaction.status == STATUS_FAILED:
            return STATUS_FAILED
        normalized = (status or "").upper()
        if normalized == _COMPLETED:
            self._confirm_deposit(deposit, transaction)
            return STATUS_CONFIRMED
        if normalized in _FINAL_FAILURE:
            self._fail_deposit(transaction)
            return STATUS_FAILED
        return transaction.status

    def _confirm_deposit(
        self, deposit: Deposit, transaction: Transaction
    ) -> None:
        if transaction.status != STATUS_PENDING:
            return
        confirmed_at = datetime.now(UTC)
        if not self._transactions.confirm_pending_transaction(
            transaction.tx_id, confirmed_at
        ):
            return
        self._accounts.decrease_balance(
            transaction.credit_account_id, transaction.amount
        )
        assert transaction.debit_account_id is not None
        self._accounts.increase_balance(
            transaction.debit_account_id, transaction.amount
        )
        deposit.confirmed_by = CONFIRMED_BY_SYSTEM
        from remitx_api.services.audit_service import record_audit

        record_audit(
            actor_user_id=deposit.user_id,
            action=AuditAction.CASHIN_CONFIRMED,
            subject_type=AuditSubject.DEPOSIT,
            subject_id=deposit.deposit_id,
            after={
                "status": "confirmed",
                "auto_matched": True,
                "source": "trustmebank",
                "payment_id": deposit.trustmebank_payment_id,
            },
        )

    def _fail_deposit(self, transaction: Transaction) -> None:
        if transaction.status != STATUS_PENDING:
            return
        self._transactions.mark_failed(transaction.tx_id)

    def _access_token_for(self, user_id: uuid.UUID) -> str:
        link = self._links.get_link(user_id)
        if link is None:
            raise TrustMeBankNotLinkedError()
        if link.token_expires_at is not None and _as_utc(
            link.token_expires_at
        ) <= datetime.now(UTC) + timedelta(seconds=30):
            refreshed = self._client.refresh_tokens(refresh_token=link.refresh_token)
            now = datetime.now(UTC)
            link.access_token = refreshed.access_token
            link.refresh_token = refreshed.refresh_token
            link.scope = refreshed.scope
            link.consent_id = refreshed.consent_id
            link.token_expires_at = now + timedelta(seconds=refreshed.expires_in)
            link.updated_at = now
            db.session.flush()
        return link.access_token

    def _verify_signature(self, body: bytes, header: str) -> bool:
        secret = self._config.TRUSTMEBANK_WEBHOOK_SECRET
        if not secret:
            return False
        try:
            parts = dict(part.split("=", 1) for part in header.split(","))
            timestamp = int(parts["t"])
            supplied = parts["v1"]
        except (ValueError, KeyError):
            return False
        if abs(time.time() - timestamp) > 300:
            return False
        signed = hmac.new(
            secret.encode(),
            f"{timestamp}.".encode() + body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(signed, supplied)
