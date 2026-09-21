"""The one piece of real on-chain code in the worker: burning uctusd.

Burning an XRPL issued currency means sending it back to its issuer — the
issuer can freely reissue, so absorbing a balance back into it is the
standard way to destroy one. Used by
`remitx_worker.tasks.burn_treasury_tokens` to return the treasury's uctusd
to `UCTUSD Issuer (Exchange)` once a remittance's beneficiary pass-through
leg has landed it back in the treasury (Transaction_Flow_Context.md §1, §2
Phase C).

Mirrors `platform_wallet/scripts/create_xprl_platform_wallet.py`'s
submit/check/return-hash shape and its Fernet seed encryption — duplicated
rather than imported, same rationale `api/scripts/seed_platform_accounts.py`
already gives for its own duplicate of that script's balance-read logic:
keeps the standalone setup script and the app packages uncoupled.
"""

from decimal import Decimal

from cryptography.fernet import Fernet
from remitx_api.config import Config
from xrpl.clients import JsonRpcClient
from xrpl.models.amounts import IssuedCurrencyAmount
from xrpl.models.transactions import Payment
from xrpl.transaction import submit_and_wait
from xrpl.wallet import Wallet


def _load_treasury_wallet() -> Wallet:
    config = Config()
    encrypted_seed = config.PLATFORM_WALLET_SEED_ENCRYPTED
    encryption_key = config.XRPL_ENCRYPTION_KEY
    if not (encrypted_seed and encryption_key):
        raise RuntimeError(
            "PLATFORM_WALLET_SEED_ENCRYPTED / XRPL_ENCRYPTION_KEY not configured"
        )
    seed = Fernet(encryption_key.encode()).decrypt(encrypted_seed.encode()).decode()
    return Wallet.from_seed(seed)


def burn_tokens(amount: Decimal) -> str:
    """Send `amount` uctusd from the treasury wallet back to the issuer.

    Returns the validated transaction's hash. Raises `RuntimeError` if the
    ledger reports anything other than `tesSUCCESS`.
    """
    config = Config()
    client = JsonRpcClient(config.XRPL_TESTNET_URL)
    wallet = _load_treasury_wallet()

    payment = Payment(
        account=wallet.address,
        destination=config.UCTUSD_ISSUER,
        amount=IssuedCurrencyAmount(
            currency=config.UCTUSD_CURRENCY_CODE_HEX,
            issuer=config.UCTUSD_ISSUER,
            value=str(amount),
        ),
    )
    response = submit_and_wait(payment, client, wallet)
    result = response.result.get("meta", {}).get("TransactionResult")
    if result != "tesSUCCESS":
        raise RuntimeError(f"burn Payment failed: {result}")
    return response.result["hash"]
