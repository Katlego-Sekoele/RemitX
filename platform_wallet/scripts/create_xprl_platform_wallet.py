"""
DECOMMISSIONED (#276): replaced by create_evm_platform_wallet.py; kept for
reference and rollback.

Create and fund the RemitX platform wallet on the XRPL testnet, and open its
UCTUSD trust line.

Adapted from the TA's (Marc's) onboard_customer.py example - the same
create/fund/trust-line pattern, applied to our platform's own wallet rather
than a customer's.

To Run:
    pip install -r platform_wallet/scripts/requirements.txt
    python platform_wallet/scripts/create_xprl_platform_wallet.py

Re-running reuses the wallet already recorded in .env instead of creating a
new one. Testnet only. The seed is encrypted before being written to .env,
plus a plaintext backup is kept locally at ~/platform_wallet_seed.local.txt
for recovery - never commit or share either.
"""

import json
import os
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv, set_key
from xrpl.clients import JsonRpcClient
from xrpl.models.amounts import IssuedCurrencyAmount
from xrpl.models.requests import AccountLines
from xrpl.models.requests.account_info import AccountInfo
from xrpl.models.transactions import TrustSet
from xrpl.transaction import submit_and_wait
from xrpl.wallet import Wallet, generate_faucet_wallet

_ROOT = Path(__file__).resolve().parent.parent.parent  # Root of the repo
_ENV_PATH = _ROOT / ".env"  # Path to the .env file
load_dotenv(
    _ENV_PATH
)  # Load env vars from .env so we can read/write them in this script


XRPL_TESTNET_URL = os.environ.get(
    "XRPL_TESTNET_URL", "https://s.altnet.rippletest.net:51234/"
)  # Testnet RPC URL
EXPLORER = "https://testnet.xrpl.org"  # XRPL Testnet Explorer URL

# Constants for the IOU token
CURRENCY_HEX = os.environ.get(
    "UCTUSD_CURRENCY_CODE_HEX", "5543545553440000000000000000000000000000"
)
ISSUER = os.environ.get("UCTUSD_ISSUER", "rELez4x4Zqv3KYqboYVfrYPF8521Ycbxa5")
TRUST_LIMIT = os.environ.get("UCTUSD_TRUST_LIMIT", "1000000")  # 1 million UCTUSD


# Helper functions for encryption and .env management
def _get_encryption_key() -> str:
    """XRPL_ENCRYPTION_KEY from .env, generating and persisting one if absent."""
    key = os.environ.get("XRPL_ENCRYPTION_KEY")
    if key:
        return key
    key = (
        Fernet.generate_key().decode()
    )  # if no key, generate one and persist it to .env
    set_key(str(_ENV_PATH), "XRPL_ENCRYPTION_KEY", key)
    print("No XRPL_ENCRYPTION_KEY found; generated a new one and saved it to .env.")
    return key


# Helper function to encrypt the XRPL seed before writing it to .env
def _encrypt_secret(plaintext: str, key: str) -> str:
    """
    Fernet-encrypt `plaintext`, returning a base64 token.
    Use to encrypt the XRPL seed before writing it to .env. The key is stored
    in .env too.
    """
    return Fernet(key.encode()).encrypt(plaintext.encode()).decode()


# Helper function to recover the XRPL seed stored in .env
def _decrypt_secret(token: str, key: str) -> str:
    """Fernet-decrypt `token`, the inverse of `_encrypt_secret`."""
    return Fernet(key.encode()).decrypt(token.encode()).decode()


_SEED_BACKUP_PATH = Path.home() / "platform_wallet_seed.local.txt"


def _write_seed_backup(wallet: Wallet) -> None:
    _SEED_BACKUP_PATH.write_text(f"address: {wallet.address}\nseed: {wallet.seed}\n")


# 1. Create a wallet using the Testnet faucet:
# https://xrpl.org/xrp-testnet-faucet.html
def _load_existing_wallet() -> Wallet | None:
    """Platform wallet from .env if one was already created, else None."""
    address = os.environ.get("PLATFORM_WALLET_ADDRESS")
    encrypted_seed = os.environ.get("PLATFORM_WALLET_SEED_ENCRYPTED")
    encryption_key = os.environ.get("XRPL_ENCRYPTION_KEY")
    if not (address and encrypted_seed and encryption_key):
        return None
    return Wallet.from_seed(_decrypt_secret(encrypted_seed, encryption_key))


def create_platform_wallet(client: JsonRpcClient) -> Wallet:
    """Return the existing platform wallet from .env, or create and fund a new one."""
    existing = _load_existing_wallet()
    if existing:
        print(
            f"Platform wallet already exists: {existing.address} - using stored seed."
        )
        return existing

    print("\nCreating a new platform wallet and funding it with Testnet XRP...")
    wallet = generate_faucet_wallet(client)  # funds the wallet with testnet XRP
    print(f"Created new wallet with address: {wallet.address}")
    print(f"Account Testnet Explorer URL: {EXPLORER}/accounts/{wallet.address}")

    _write_seed_backup(wallet)

    # Encrypt the seed at rest; only the address and the encrypted blob ever
    # touch disk or stdout.
    encryption_key = _get_encryption_key()
    encrypted_seed = _encrypt_secret(wallet.seed, encryption_key)
    set_key(str(_ENV_PATH), "PLATFORM_WALLET_ADDRESS", wallet.address)
    set_key(str(_ENV_PATH), "PLATFORM_WALLET_SEED_ENCRYPTED", encrypted_seed)
    print("Wrote PLATFORM_WALLET_ADDRESS and PLATFORM_WALLET_SEED_ENCRYPTED to .env.")

    return wallet


# 2. Look up info about the wallet's account
def get_account_info(client: JsonRpcClient, address: str) -> dict:
    """Get account info for the given address."""
    acct_info = AccountInfo(
        account=address,
        ledger_index="validated",
        strict=True,
    )
    response = client.request(acct_info)
    print("\nResponse Status: ", response.status)
    print(json.dumps(response.result, indent=4, sort_keys=True))
    print("\nAccount info retrieved successfully.")
    return response.result


# 3. Establish a trust line to an issuer
def create_trust_line(
    client: JsonRpcClient,
    wallet: Wallet,
    currency: str,
    issuer: str,
    limit: str,
) -> dict:
    """
    Submit a TrustSet transaction so this wallet can hold `currency`
    issued by `issuer`. Waits for validation before returning.
    Inputs:
        client: the XRPL client to use
        wallet: the wallet to authorize
        currency: the currency code (hex) to trust
        issuer: the address of the issuer of the currency
        limit: the maximum amount of the currency to trust
    Returns:
        The transaction result dictionary. Raises RuntimeError if the transaction fails.
    """
    trust_set_tx = TrustSet(
        account=wallet.address,
        #
        limit_amount=IssuedCurrencyAmount(
            currency=currency,
            issuer=issuer,
            value=limit,
        ),
    )
    response = submit_and_wait(trust_set_tx, client, wallet)
    result = response.result.get("meta", {}).get("TransactionResult")
    if result != "tesSUCCESS":
        raise RuntimeError(f"TrustSet failed: {result}")
    else:
        print(
            f"TrustSet result: {result} | validated: {response.result.get('validated')}"
        )
    return response.result["hash"]


def trust_line_exists(client: JsonRpcClient, address: str, issuer: str) -> bool:
    """Whether `address` already has a trust line to `issuer` for CURRENCY_HEX."""
    lines = client.request(
        AccountLines(account=address, peer=issuer, ledger_index="validated")
    ).result["lines"]
    return any(
        line["currency"] == CURRENCY_HEX for line in lines
    )  # return True if any trust line exists for the specified currency and issuer


def uctusd_balance(client: JsonRpcClient, address: str, issuer: str) -> str:
    """Current UCTUSD balance, or '0' if the trust line holds nothing."""
    lines = client.request(
        AccountLines(account=address, peer=issuer, ledger_index="validated")
    ).result["lines"]
    for line in lines:
        if line["currency"] == CURRENCY_HEX:
            return line["balance"]
    return "0"


def print_wallet_summary(
    wallet: Wallet, issuer: str, tx_hash: str, balance: str
) -> None:
    """Print what the API's config would need to use this platform wallet."""
    print("\n" + "=" * 62)
    print("  Platform wallet ready")
    print("=" * 62)
    print(f"  Address       : {wallet.address}")
    print("  Seed          : stored encrypted in .env (PLATFORM_WALLET_SEED_ENCRYPTED)")
    print(f"  Issuer        : {issuer}")
    print(f"  Currency      : {CURRENCY_HEX}")
    print(f"  Trust limit   : {TRUST_LIMIT}")
    print(f"  TrustSet tx   : {tx_hash}")
    print(f"  Balance       : {balance} UCTUSD")
    print(f"  Explorer      : {EXPLORER}/accounts/{wallet.address}")
    print("=" * 62)


def main() -> None:
    client = JsonRpcClient(XRPL_TESTNET_URL)  # get the testnet client
    issuer = ISSUER

    # 1. Create a wallet using the Testnet faucet
    wallet = create_platform_wallet(client)
    print(f"\n    Wallet address: {wallet.address}")

    # 2. Look up info about the wallet's account
    get_account_info(client, wallet.address)

    # 3. Establish a trust line to the issuer UCTUSD, unless one is already open
    if trust_line_exists(client, wallet.address, issuer):
        print("\nUCTUSD trust line already open; skipping TrustSet.")
        tx_hash = "(none - trust line already existed)"
    else:
        print(f"\nOpening UCTUSD trust line (limit {TRUST_LIMIT})...")
        tx_hash = create_trust_line(client, wallet, CURRENCY_HEX, issuer, TRUST_LIMIT)
        print(f"  ok  {tx_hash}")

    balance = uctusd_balance(client, wallet.address, issuer)

    print_wallet_summary(wallet, issuer, tx_hash, balance)


if __name__ == "__main__":
    main()
