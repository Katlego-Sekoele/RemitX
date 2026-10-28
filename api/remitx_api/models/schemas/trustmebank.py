from uuid import UUID

from remitx_api.models.schemas.base import Amount, Schema


class TrustMeBankStatusRead(Schema):
    enabled: bool


class TrustMeBankLinkRead(Schema):
    linked: bool
    customer_name: str | None = None


class TrustMeBankConnectRead(Schema):
    authorize_url: str


class TrustMeBankOAuthCompleteRequest(Schema):
    code: str
    state: str


class TrustMeBankOAuthCompleteRead(Schema):
    customer_id: str | None = None
    customer_name: str | None = None


class TrustMeBankAccountRead(Schema):
    id: str
    name: str
    account_number: str
    currency: str
    balance: str | None = None


class TrustMeBankDepositStartRequest(Schema):
    amount: Amount
    debtor_account_id: str


class TrustMeBankDepositStartRead(Schema):
    deposit_id: UUID
    payment_id: str
    authorisation_url: str


class TrustMeBankDepositSyncRead(Schema):
    payment_id: str
    status: str
