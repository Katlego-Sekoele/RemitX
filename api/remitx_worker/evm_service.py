"""The worker's access to the EVM Treasury Wallet's signing key.

The stokvel Treasury Wallet is an address on the XRPL EVM Testnet. Its private
key sits in the environment Fernet-encrypted
(`EVM_TREASURY_KEY_ENCRYPTED`), and the key that decrypts it
(`EVM_ENCRYPTION_KEY`) is a separate setting, never stored with it. Both are
written by `platform_wallet/scripts/create_evm_platform_wallet.py`.

Only the worker decrypts the key, so this module lives in `remitx_worker`,
which the API never imports. The settings are read with `os.environ` rather
than through `remitx_api.config.Config`, so the API's config object has no way
to hand either secret out.

Models `xrpl_service._load_treasury_wallet`. Signing is built on top of this in
#204.
"""

import os

from cryptography.fernet import Fernet, InvalidToken
from eth_account import Account
from eth_account.signers.local import LocalAccount


def _load_treasury_account() -> LocalAccount:
    """Decrypt the treasury's EVM private key and return its account.

    Raises `RuntimeError` if a setting is missing, the key does not decrypt,
    or the derived address is not `EVM_TREASURY_ADDRESS`. No message carries
    the key or its ciphertext, and decryption errors are raised `from None` so
    no chained exception does either.
    """
    encrypted_key = os.environ.get("EVM_TREASURY_KEY_ENCRYPTED", "")
    encryption_key = os.environ.get("EVM_ENCRYPTION_KEY", "")
    address = os.environ.get("EVM_TREASURY_ADDRESS", "")
    if not (encrypted_key and encryption_key and address):
        raise RuntimeError(
            "EVM_TREASURY_KEY_ENCRYPTED / EVM_ENCRYPTION_KEY / "
            "EVM_TREASURY_ADDRESS not configured"
        )

    try:
        private_key = (
            Fernet(encryption_key.encode()).decrypt(encrypted_key.encode()).decode()
        )
    except (InvalidToken, ValueError):
        # ValueError: EVM_ENCRYPTION_KEY is not a valid Fernet key at all.
        raise RuntimeError(
            "EVM_TREASURY_KEY_ENCRYPTED could not be decrypted with EVM_ENCRYPTION_KEY"
        ) from None

    try:
        account = Account.from_key(private_key)
    except Exception:
        # Broad on purpose: bad hex is a ValueError, but a wrong-length key is
        # eth_keys' own ValidationError, and either may echo the input.
        raise RuntimeError(
            "EVM_TREASURY_KEY_ENCRYPTED does not decrypt to a valid EVM private key"
        ) from None

    # Addresses are public, so naming both is safe. Compared case-insensitively
    # because EIP-55 checksum casing is optional in the setting.
    if account.address.lower() != address.lower():
        raise RuntimeError(
            f"EVM treasury key derives {account.address}, but "
            f"EVM_TREASURY_ADDRESS is {address}"
        )
    return account
