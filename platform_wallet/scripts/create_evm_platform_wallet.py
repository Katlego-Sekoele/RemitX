"""
Create the RemitX treasury wallet on XRPL EVM Testnet: an EVM address whose
private key is Fernet-encrypted before it is written to .env.

This is separate from the XRPL platform wallet (create_xprl_platform_wallet.py),
which keeps serving normal remittances. UCTUSD on the EVM chain is a plain
ERC-20, so there are no trust lines and nothing to open - the script only reads
the wallet's native and UCTUSD balances. It never builds or signs a transaction.

To Run (on the host, not in Docker - the backup is written to your home folder):
    pip install -r platform_wallet/scripts/requirements.txt
    python platform_wallet/scripts/create_evm_platform_wallet.py

Re-running reuses the wallet already recorded in .env instead of creating a
new one. Testnet only. The key is encrypted before being written to .env, plus
a plaintext backup (0600, outside the repo) is kept at
~/evm_platform_wallet.local.txt for recovery - never commit or share either.
"""

import os
import sys
from decimal import Decimal
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv, set_key
from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3

_ROOT = Path(__file__).resolve().parent.parent.parent  # Root of the repo
_ENV_PATH = _ROOT / ".env"  # Path to the .env file
_BACKUP_PATH = Path.home() / "evm_platform_wallet.local.txt"

# Defaults for the XRPL EVM Testnet settings; each can be overridden in .env.
DEFAULT_RPC_URL = "https://rpc.testnet.xrplevm.org"
DEFAULT_CHAIN_ID = "1449000"
DEFAULT_EXPLORER_URL = "https://explorer.testnet.xrplevm.org"
DEFAULT_UCTUSD_CONTRACT = "0x7055071C7B79A859d9514e62833BFf041ce71074"
DEFAULT_UCTUSD_DECIMALS = "18"

# Faucet URL for testnet XRP (gas)
FAUCET_URL = "https://faucet.xrplevm.org"

# Just enough of ERC-20 to read a balance.
ERC20_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "decimals",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
    },
]


# Settings are read at call time (after main() has loaded .env), not at import.
def _setting(name: str, default: str) -> str:
    return os.environ.get(name) or default


# Helper functions for encryption and .env management
def _get_encryption_key() -> str:
    """EVM_ENCRYPTION_KEY from .env, generating and persisting one if absent."""
    key = os.environ.get("EVM_ENCRYPTION_KEY")
    if key:
        return key
    key = Fernet.generate_key().decode()
    set_key(str(_ENV_PATH), "EVM_ENCRYPTION_KEY", key)
    os.environ["EVM_ENCRYPTION_KEY"] = key
    print("No EVM_ENCRYPTION_KEY found; generated a new one and saved it to .env.")
    return key


def _encrypt_secret(plaintext: str, key: str) -> str:
    """Fernet-encrypt `plaintext`, returning a base64 token."""
    return Fernet(key.encode()).encrypt(plaintext.encode()).decode()


def _decrypt_secret(token: str, key: str) -> str:
    """Fernet-decrypt `token`, the inverse of `_encrypt_secret`."""
    return Fernet(key.encode()).decrypt(token.encode()).decode()


def _write_backup(account: LocalAccount) -> None:
    """
    Write the plaintext backup, 0600 from the moment it exists. O_EXCL makes it
    refuse to overwrite an existing backup, which may hold the only copy of a key.
    """
    if _ROOT in _BACKUP_PATH.resolve().parents:
        raise RuntimeError(f"Backup path {_BACKUP_PATH} is inside the repo.")
    fd = os.open(_BACKUP_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(
            f"address: {account.address}\nprivate_key: {Web3.to_hex(account.key)}\n"
        )


def _read_backup() -> LocalAccount | None:
    """Account from the backup file, or None if there is no backup."""
    if not _BACKUP_PATH.exists():
        return None
    fields = dict(
        line.split(": ", 1) for line in _BACKUP_PATH.read_text().splitlines() if line
    )
    return Account.from_key(fields["private_key"])


def _save_to_env(account: LocalAccount) -> None:
    """Encrypt the key and record the address and encrypted key in .env."""
    encrypted = _encrypt_secret(Web3.to_hex(account.key), _get_encryption_key())
    set_key(str(_ENV_PATH), "EVM_TREASURY_ADDRESS", account.address)
    set_key(str(_ENV_PATH), "EVM_TREASURY_KEY_ENCRYPTED", encrypted)
    print("Wrote EVM_TREASURY_ADDRESS and EVM_TREASURY_KEY_ENCRYPTED to .env.")


# 1. Load the treasury wallet from .env, or create one
def _load_existing_wallet() -> LocalAccount | None:
    """Treasury wallet from .env if one was already created, else None."""
    address = os.environ.get("EVM_TREASURY_ADDRESS")
    encrypted_key = os.environ.get("EVM_TREASURY_KEY_ENCRYPTED")
    encryption_key = os.environ.get("EVM_ENCRYPTION_KEY")
    if not (address and encrypted_key):
        return None
    if not encryption_key:
        raise SystemExit(
            "EVM_TREASURY_* is set in .env but EVM_ENCRYPTION_KEY is missing; "
            "restore the key rather than creating a new wallet."
        )
    try:
        account = Account.from_key(_decrypt_secret(encrypted_key, encryption_key))
    except InvalidToken:
        raise SystemExit(
            "EVM_TREASURY_KEY_ENCRYPTED cannot be decrypted with "
            "EVM_ENCRYPTION_KEY; wrong key?"
        ) from None
    # Catches a rotated key or a hand-edited address before anything relies on it.
    if account.address != Web3.to_checksum_address(address):
        raise SystemExit(
            f"EVM_TREASURY_ADDRESS ({address}) does not match the stored key "
            f"({account.address})."
        )
    return account


def create_treasury_wallet() -> LocalAccount:
    """Return the existing treasury wallet from .env, or create a new one."""
    existing = _load_existing_wallet()
    if existing:
        print(f"Treasury wallet already exists: {existing.address} - using stored key.")
        return existing

    # An interrupted earlier run: the backup was written but .env was not.
    restored = _read_backup()
    if restored:
        print(f"Restoring treasury wallet {restored.address} from {_BACKUP_PATH}.")
        _save_to_env(restored)
        return restored

    # Half a record in .env and no backup: a new key would orphan it.
    if os.environ.get("EVM_TREASURY_ADDRESS") or os.environ.get(
        "EVM_TREASURY_KEY_ENCRYPTED"
    ):
        raise SystemExit(
            "EVM_TREASURY_ADDRESS / EVM_TREASURY_KEY_ENCRYPTED are only "
            "partly set in .env and there is no backup; fix .env by hand."
        )

    print("\nCreating a new EVM treasury wallet...")
    account = Account.create()
    # Backup first: if .env fails to write, the key still exists somewhere.
    _write_backup(account)
    _save_to_env(account)
    print(f"Created new wallet with address: {account.address}")
    return account


# 2. Read-only chain checks
def connect() -> Web3:
    """Web3 client for EVM_RPC_URL; refuses any chain but EVM_CHAIN_ID."""
    w3 = Web3(Web3.HTTPProvider(_setting("EVM_RPC_URL", DEFAULT_RPC_URL)))
    expected = int(_setting("EVM_CHAIN_ID", DEFAULT_CHAIN_ID))
    actual = w3.eth.chain_id
    if actual != expected:
        raise SystemExit(f"RPC reports chain id {actual}, expected {expected}.")
    return w3


def read_balances(w3: Web3, address: str) -> tuple[str, str]:
    """(native balance in XRP, UCTUSD balance), both read-only."""
    native = w3.from_wei(w3.eth.get_balance(address), "ether")

    token_address = _setting("UCTUSD_CONTRACT_ADDRESS", DEFAULT_UCTUSD_CONTRACT)
    if not Web3.is_address(token_address):
        raise SystemExit("UCTUSD_CONTRACT_ADDRESS is not set to a valid address.")
    token_address = Web3.to_checksum_address(token_address)
    if not w3.eth.get_code(token_address):
        raise SystemExit(f"No contract deployed at {token_address} on this chain.")
    token = w3.eth.contract(address=token_address, abi=ERC20_ABI)

    decimals = token.functions.decimals().call()
    configured = int(_setting("UCTUSD_EVM_DECIMALS", DEFAULT_UCTUSD_DECIMALS))
    if decimals != configured:
        print(f"WARNING: token reports {decimals} decimals, configured {configured}.")
    raw = token.functions.balanceOf(address).call()
    return str(native), str(Decimal(raw) / Decimal(10) ** decimals)


def print_wallet_summary(
    address: str, native: str | None, uctusd: str | None, chain_id: str
) -> None:
    """Print what the treasury wallet looks like and what it still needs."""
    explorer = _setting("EVM_EXPLORER_URL", DEFAULT_EXPLORER_URL)
    unavailable = "unavailable (RPC check failed)"
    print("\n" + "=" * 62)
    print("  EVM treasury wallet ready")
    print("=" * 62)
    print(f"  Address       : {address}")
    print("  Private key   : stored encrypted in .env (never printed)")
    print(f"  Backup        : {_BACKUP_PATH}")
    print(f"  Chain id      : {chain_id}")
    print(f"  Native (XRP)  : {native if native is not None else unavailable}")
    print(f"  UCTUSD        : {uctusd if uctusd is not None else unavailable}")
    print(f"  Explorer      : {explorer}/address/{address}")
    print("=" * 62)
    print("The wallet needs testnet XRP for gas and UCTUSD from whoever mints it;")
    print(f"this script does neither. Faucet: {FAUCET_URL or '(see project brief)'}")


def main() -> None:
    load_dotenv(_ENV_PATH)

    # Create and persist first, so an RPC outage can't lose a new key.
    account = create_treasury_wallet()

    native = uctusd = None
    try:
        w3 = connect()
        native, uctusd = read_balances(w3, account.address)
    except SystemExit:
        raise  # wrong chain / bad token config: not an outage, stop loudly
    except Exception as e:  # noqa: BLE001 - RPC/network failures vary widely
        print(
            f"WARNING: could not read balances ({type(e).__name__}: {e}).",
            file=sys.stderr,
        )

    print_wallet_summary(
        account.address, native, uctusd, _setting("EVM_CHAIN_ID", DEFAULT_CHAIN_ID)
    )


if __name__ == "__main__":
    main()
