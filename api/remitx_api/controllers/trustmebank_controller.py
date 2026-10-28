import uuid
from decimal import Decimal

from remitx_api.services import trustmebank_service


class TrustMeBankController:
    def status(self) -> dict[str, bool]:
        return trustmebank_service.public_status()

    def connect_url(self, user_id: uuid.UUID) -> str:
        return trustmebank_service.TrustMeBankService().connect_authorize_url(
            user_id
        )

    def complete_oauth(
        self, user_id: uuid.UUID, *, code: str, state: str
    ) -> dict[str, str | None]:
        return trustmebank_service.TrustMeBankService().complete_oauth(
            user_id, code=code, state=state
        )

    def link_status(self, user_id: uuid.UUID) -> dict[str, str | bool | None]:
        return trustmebank_service.TrustMeBankService().link_status(user_id)

    def list_accounts(self, user_id: uuid.UUID) -> list[dict[str, str]]:
        return trustmebank_service.TrustMeBankService().list_bank_accounts(user_id)

    def start_deposit(
        self, user_id: uuid.UUID, *, amount: Decimal, debtor_account_id: str
    ) -> dict[str, str]:
        return trustmebank_service.TrustMeBankService().start_deposit(
            user_id, amount=amount, debtor_account_id=debtor_account_id
        )

    def sync_deposit(
        self, user_id: uuid.UUID, payment_id: str
    ) -> dict[str, str]:
        return trustmebank_service.TrustMeBankService().sync_deposit_for_user(
            user_id, payment_id
        )

    def handle_webhook(self, body: bytes, signature: str) -> None:
        trustmebank_service.TrustMeBankService().handle_webhook(body, signature)
