"""Get the freshly seeded database ready for Locust.

Runs once per load test, straight after the seeder and in the seeder's image,
because it drives the backend's own code the same way:

1. Stores exchange rates that never expire, for every pair a quote can ask
   for, so no quote needs the live rate API.
2. Tops every verified sender with a beneficiary up to TOP_UP_TO_ZAR through
   the real cash-in path: a bank-statement line, reconciled by the same job
   treasury runs. Seeded deposits follow paydays, so without this most senders
   would have too little to send for long.
3. Generates a throwaway RSA key pair. The API verifies session tokens with
   the public half (CLERK_JWT_KEY) and Locust signs its own with the private
   half, so nothing asks Clerk.
4. Writes the people Locust acts as: those senders, and staff holding the read
   permissions its admin tasks use.

Everything goes to the stack's run-data volume, deleted along with the stack.
"""

import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from remitx_api.config import Config
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.models.orm.user import User
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.beneficiary_repository import BeneficiaryRepository
from remitx_api.repositories.kyc_application_repository import (
    KycApplicationRepository,
)
from remitx_api.repositories.permission_repository import PermissionRepository
from remitx_api.services import deposit_service
from remitx_api.services.exchange_rate_service import SUPPORTED_CURRENCIES
from remitx_seeder.rates import HistoricalRateProvider
from sqlalchemy import select

RUN_DATA = Path(os.environ.get("LOADTEST_RUN_DATA", "/run-data"))
# Far more than a run can spend at the amounts locustfile.py sends.
TOP_UP_TO_ZAR = Decimal("50000")
# Longer than any run: a rate that expired mid-run would send the next quote
# to the rate API, which this stack cannot reach.
RATES_VALID_FOR = timedelta(days=3650)
# The permissions gating the admin endpoints locustfile.py's staff browse.
ADMIN_READ_PERMISSIONS = {
    "transaction:read_any",
    "kyc:application:read",
    "cashin:read",
}


def store_rates() -> int:
    """One never-expiring rate per ordered currency pair, identity pairs
    included (a ZAR -> ZAR send still prices a direct fiat rate). The seeder's
    rate provider supplies them, so they match the history it just seeded."""
    now = datetime.now(UTC)
    provider = HistoricalRateProvider(seed=0, start=now.date(), end=now.date())
    currencies = sorted(SUPPORTED_CURRENCIES)
    for base in currencies:
        for quote in currencies:
            db.session.add(
                ExchangeRate(
                    base_currency=base,
                    quote_currency=quote,
                    rate=provider.get_rate(base, quote),
                    fetched_at=now,
                    valid_until=now + RATES_VALID_FOR,
                )
            )
    db.session.commit()
    return len(currencies) ** 2


def sort_people() -> tuple[list, list[dict]]:
    """The seeded people Locust can act as: verified senders with a ZAR account
    and at least one beneficiary (as `(user, account, beneficiaries)`), and
    staff holding an admin read permission."""
    accounts = AccountRepository()
    beneficiaries = BeneficiaryRepository()
    kyc = KycApplicationRepository()
    permissions = PermissionRepository()

    senders: list = []
    staff: list[dict] = []
    seeded = db.session.scalars(
        select(User)
        .where(User.clerk_user_id.startswith("seed_", autoescape=True))
        .order_by(User.created_at)
    ).all()
    for user in seeded:
        granted = {
            code.value for code in permissions.get_effective_permissions(user.id)
        } & ADMIN_READ_PERMISSIONS
        if granted:
            staff.append({**_identity(user), "permissions": sorted(granted)})
            continue
        if not kyc.get_standing(user.id).is_verified:
            continue
        account = accounts.get_user_account(user.id, CURRENCY_ZAR)
        rows = beneficiaries.get_sender_beneficiary_list_newest_order(user.id)
        if account is not None and rows:
            senders.append((user, account, [row.beneficiary for row in rows]))
    return senders, staff


def fund(senders: list) -> int:
    """Bring each sender's available ZAR up to TOP_UP_TO_ZAR with one
    bank-statement line each, reconciled by deposit_service.process_deposits."""
    accounts = AccountRepository()
    today = datetime.now(UTC).isoformat()
    lines = []
    for _user, account, _beneficiaries in senders:
        shortfall = TOP_UP_TO_ZAR - accounts.get_available_balance(account.account_id)
        if shortfall > 0:
            lines.append(
                {
                    "date": today,
                    "reference": account.reference,
                    "amount": str(shortfall.quantize(Decimal("0.01"))),
                    "currency": CURRENCY_ZAR,
                }
            )
    if lines:
        deposit_service.process_deposits(lines)
    return len(lines)


def export_senders(senders: list) -> list[dict]:
    """The funded senders, as Locust needs them. One whose top-up did not land
    is left out rather than left to fail every send."""
    accounts = AccountRepository()
    exported = []
    for user, account, payees in senders:
        if accounts.get_available_balance(account.account_id) < TOP_UP_TO_ZAR:
            continue
        exported.append(
            {
                **_identity(user),
                "beneficiaries": [
                    {
                        "beneficiary_id": str(payee.beneficiary_id),
                        "payout_currency": payee.payout_currency,
                    }
                    for payee in payees
                ],
            }
        )
    return exported


def _identity(user: User) -> dict:
    return {
        "clerk_user_id": user.clerk_user_id,
        "email": user.email,
        "first_name": user.first_name,
    }


def write_signing_keys() -> None:
    """World-readable on purpose: Locust runs as your user id, not root, and
    the key only opens this throwaway stack."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (RUN_DATA / "jwt_private.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    (RUN_DATA / "jwt_public.pem").write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


def main() -> None:
    db.init(Config.DATABASE_URL)
    token = db.open_session()
    try:
        rates = store_rates()
        candidates, staff = sort_people()
        funded = fund(candidates)
        people = {"senders": export_senders(candidates), "staff": staff}
    finally:
        db.close_session(token)

    if not people["senders"]:
        raise SystemExit(
            "No seeded sender is verified, funded and has a beneficiary; see seed.log."
        )
    RUN_DATA.mkdir(parents=True, exist_ok=True)
    write_signing_keys()
    (RUN_DATA / "people.json").write_text(
        # The origin Locust's tokens must name as their authorized party.
        json.dumps({"origin": Config.CORS_ORIGINS[0], **people}, indent=2)
    )
    print(
        f"Prepared {len(people['senders'])} senders ({funded} topped up), "
        f"{len(people['staff'])} staff and {rates} exchange rates."
    )


if __name__ == "__main__":
    main()
