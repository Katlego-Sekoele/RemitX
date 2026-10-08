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

Models `xrpl_service._load_treasury_wallet`. The web3.py helpers below it
(#204) sit alongside XRPL rather than replacing it: normal remittances still
settle on the XRP Ledger Testnet through `xrpl_service`. Nothing calls these
helpers yet; the burn (#206) and contributions and events (#201) build on them.

Fees: transactions use legacy `gasPrice`. The RPC does report EIP-1559 fields
(`eth_feeHistory` returned `baseFeePerGas` in October 2026), but no type-2
transaction has been tested on this chain, and a legacy price taken from
`eth_gasPrice` is accepted by any EVM node.

Nonces: `submit_transaction` takes the Treasury Wallet's *pending* nonce at the
moment it builds. Two tasks sending from the wallet at once can read the same
nonce, so one replaces or is rejected in favour of the other. #206 and #201
must serialise sends from the Treasury Wallet (one lock or one single-
concurrency queue).

Logging: `remitx_api.log_redaction` hides any `0x` + 64 hex digits, because
that is what a private key looks like. Transaction and block hashes have the
same shape, so they read `[REDACTED]` in logs too. Persist a hash in the
database rather than relying on a log line to find it again.
"""

import os
from decimal import Decimal, localcontext
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from eth_account import Account
from eth_account.signers.local import LocalAccount
from remitx_api.config import Config
from web3 import Web3
from web3.contract import Contract

# Enough of ERC-20 for balances, approvals and transfers.
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
    {
        "name": "allowance",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "approve",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "transfer",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
]

# Enough digits for any uint256 (78) at full precision. Decimal's default of 28
# would silently round a balance of 10^10 tokens or more at 18 decimals.
_PRECISION = 80

# The only fields a caller may set; the rest are filled in here so that every
# send uses the treasury's nonce, this chain's id and a legacy gas price.
_CALLER_TX_FIELDS = frozenset({"to", "data", "value"})


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


def get_web3() -> Web3:
    """A client for `EVM_RPC_URL` that refuses any chain but `EVM_CHAIN_ID`."""
    config = Config()
    w3 = Web3(Web3.HTTPProvider(config.EVM_RPC_URL, request_kwargs={"timeout": 30}))
    chain_id = w3.eth.chain_id
    if chain_id != config.EVM_CHAIN_ID:
        # The URL is left out: a hosted RPC URL can carry an API key.
        raise RuntimeError(
            f"EVM_RPC_URL reports chain id {chain_id}, expected "
            f"EVM_CHAIN_ID {config.EVM_CHAIN_ID}"
        )
    return w3


def token_contract(w3: Web3) -> Contract:
    """The UCTUSD ERC-20 at `UCTUSD_EVM_CONTRACT_ADDRESS`."""
    address = Web3.to_checksum_address(Config().UCTUSD_EVM_CONTRACT_ADDRESS)
    return w3.eth.contract(address=address, abi=ERC20_ABI)


def to_base_units(amount: Decimal) -> int:
    """UCTUSD as a Decimal -> integer base units, scaled by the token's decimals.

    The one place a token amount becomes an on-chain integer. Rejects floats
    (and anything else not a Decimal), non-finite and negative amounts, and any
    precision finer than one base unit, rather than rounding.
    """
    if not isinstance(amount, Decimal):
        raise TypeError(f"amount must be a Decimal, not {type(amount).__name__}")
    if not amount.is_finite():
        raise ValueError(f"amount must be finite, got {amount}")
    if amount < 0:
        raise ValueError(f"amount must not be negative, got {amount}")
    with localcontext() as context:
        context.prec = _PRECISION
        scaled = amount.scaleb(Config().UCTUSD_EVM_DECIMALS)
        if scaled != scaled.to_integral_value():
            raise ValueError(
                f"{amount} has more than {Config().UCTUSD_EVM_DECIMALS} decimal places"
            )
        return int(scaled)


def from_base_units(value: int) -> Decimal:
    """Integer base units -> UCTUSD as a Decimal. The inverse of `to_base_units`."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"value must be an int, not {type(value).__name__}")
    if value < 0:
        raise ValueError(f"value must not be negative, got {value}")
    with localcontext() as context:
        context.prec = _PRECISION
        return Decimal(value).scaleb(-Config().UCTUSD_EVM_DECIMALS)


def get_native_balance(address: str, w3: Web3 | None = None) -> Decimal:
    """The address's test XRP (gas) balance. The native coin has 18 decimals."""
    w3 = w3 or get_web3()
    wei = w3.eth.get_balance(Web3.to_checksum_address(address))
    return Web3.from_wei(wei, "ether")


def get_token_balance(address: str, w3: Web3 | None = None) -> Decimal:
    """The address's UCTUSD balance."""
    w3 = w3 or get_web3()
    raw = (
        token_contract(w3).functions.balanceOf(Web3.to_checksum_address(address)).call()
    )
    return from_base_units(raw)


def submit_transaction(tx: dict[str, Any], w3: Web3 | None = None) -> str:
    """Sign `tx` as the Treasury Wallet, send it, and return its hash.

    `tx` may only set `to`, `data` and `value`. The nonce (pending), chain id,
    legacy `gasPrice` and gas estimate are filled in here. Does not wait for
    the transaction to be mined: store the returned hash first, then call
    `wait_for_receipt`, so a retry can wait on that hash instead of sending a
    second transaction. See the module docstring on nonce collisions.
    """
    extra = set(tx) - _CALLER_TX_FIELDS
    if extra:
        raise ValueError(f"unsupported transaction fields: {sorted(extra)}")
    w3 = w3 or get_web3()
    account = _load_treasury_account()

    full_tx: dict[str, Any] = {
        "value": 0,
        **tx,
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address, "pending"),
        "chainId": Config().EVM_CHAIN_ID,
        "gasPrice": w3.eth.gas_price,
    }
    full_tx["gas"] = w3.eth.estimate_gas(full_tx)

    signed = account.sign_transaction(full_tx)
    return Web3.to_hex(w3.eth.send_raw_transaction(signed.raw_transaction))


def wait_for_receipt(tx_hash: str, timeout: float = 120, w3: Web3 | None = None):
    """Wait for `tx_hash` to be mined and return its receipt.

    Raises `RuntimeError` if the transaction reverted (status 0). If it is not
    mined within `timeout` seconds, web3's `TimeExhausted` propagates and the
    caller may wait on the same hash again.
    """
    w3 = w3 or get_web3()
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
    if receipt["status"] == 0:
        raise RuntimeError(f"EVM transaction {tx_hash} reverted")
    return receipt
