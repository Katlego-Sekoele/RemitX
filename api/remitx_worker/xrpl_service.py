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
rather than imported, same rationale `api/scripts/bootstrap.py`
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
    """Decrypt the treasury wallet's seed and return a `Wallet` object."""
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
    """Send `amount` of the platform token from the treasury wallet back to the issuer.

    Returns the validated transaction's hash. Raises `RuntimeError` if the
    ledger reports anything other than `tesSUCCESS`.
    """
    config = Config()
    # Initialize a JsonRpcClient with the XRPL testnet URL from the config
    client = JsonRpcClient(config.XRPL_TESTNET_URL)
    # Call the _load_treasury_wallet function to get the treasury wallet object
    wallet = _load_treasury_wallet()

    payment = Payment(
        account=wallet.address,
        # get the issuer address from the config
        destination=config.UCTUSD_ISSUER,
        amount=IssuedCurrencyAmount(
            currency=config.UCTUSD_CURRENCY_CODE_HEX,
            issuer=config.UCTUSD_ISSUER,
            value=str(amount),
        ),
        # Create a Payment transaction to send the specified amount of the
        # platform token from the treasury wallet to the issuer.
    )
    # Submit the payment transaction to the XRPL and wait for it to be validated.
    response = submit_and_wait(payment, client, wallet)
    result = response.result.get("meta", {}).get("TransactionResult")

    if result != "tesSUCCESS":
        raise RuntimeError(f"burn Payment failed: {result}")
    # Return the hash of the validated transaction.
    return response.result["hash"]
