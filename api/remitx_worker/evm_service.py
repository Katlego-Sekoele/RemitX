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
(#221, #222) replace the XRPL path: settlement burns UCTUSD through
`burn_tokens` (#278), and `xrpl_service` is kept only for reference. The
stokvel contract connection (#273) builds on the same helpers.

Fees: transactions use legacy `gasPrice`. The RPC does report EIP-1559 fields
(`eth_feeHistory` returned `baseFeePerGas` in October 2026), but no type-2
transaction has been tested on this chain, and a legacy price taken from
`eth_gasPrice` is accepted by any EVM node.

Nonces: `submit_transaction` takes the Treasury Wallet's *pending* nonce at the
moment it builds. Two sends from the wallet at once could read the same nonce,
so one would replace or be rejected in favour of the other. To stop that,
`submit_transaction` holds `remitx_worker.db.treasury_send_lock` from the
nonce read until the RPC reports the nonce used. Every send from the Treasury
Wallet must go through `submit_transaction`: the burn (#278), the
contribution tasks and the scheduled release task that calls `finalise`
(#273).

Logging: nothing scrubs log lines. Never log a transaction dict, a signed
transaction, an account object or a decrypted key, and log a stokvel or
member ID in its UUID form, not as `bytes32`. Persist a transaction hash in
the database so it can be found again.
"""

import logging
import os
import re
import time
import uuid
from collections.abc import Callable
from decimal import Decimal, localcontext
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from eth_account import Account
from eth_account.signers.local import LocalAccount
from remitx_api.config import Config
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import TransactionNotFound, Web3RPCError

from remitx_worker.db import treasury_send_lock

logger = logging.getLogger(__name__)

# Enough of ERC-20 for balances, supply, approvals, transfers and the burn.
# `burn` is OpenZeppelin ERC20Burnable's: it destroys the caller's own
# balance, so the Treasury needs no allowance (unlike `burnFrom`).
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
        "name": "totalSupply",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
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
    {
        "name": "burn",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "value", "type": "uint256"}],
        "outputs": [],
    },
]

# Enough digits for any uint256 (78) at full precision. Decimal's default of 28
# would silently round a balance of 10^10 tokens or more at 18 decimals.
_PRECISION = 80

# The only fields a caller may set; the rest are filled in here so that every
# send uses the treasury's nonce, this chain's id and a legacy gas price.
_CALLER_TX_FIELDS = frozenset({"to", "data", "value"})

# A UUID string once its hyphens are removed, as uuidToBytes32 checks it.
_UUID_HEX = re.compile(r"[0-9a-fA-F]{32}")

# After a send, how long `submit_transaction` keeps the send lock while it
# waits for the RPC's pending nonce to move past the one it used, so the next
# sender cannot read a stale nonce from a node that has not seen it yet.
_NONCE_ADVANCE_TIMEOUT = 10.0
_NONCE_ADVANCE_POLL = 0.5


def treasury_address() -> str:
    """The Treasury Wallet's address (`EVM_TREASURY_ADDRESS`), checksummed,
    for reads such as its allowance. Does not touch the key."""
    address = os.environ.get("EVM_TREASURY_ADDRESS", "")
    if not address:
        raise RuntimeError("EVM_TREASURY_ADDRESS not configured")
    return Web3.to_checksum_address(address)


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
    """The UCTUSD ERC-20 at `UCTUSD_CONTRACT_ADDRESS`."""
    address = Web3.to_checksum_address(Config().UCTUSD_CONTRACT_ADDRESS)
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


def uuid_to_bytes32(value: uuid.UUID | str) -> bytes:
    """A database UUID as a contract `bytes32` ID: its 16 bytes, then 16 zeros.

    Stokvel and member IDs are packed left-aligned. Must produce the same bytes
    as `uuidToBytes32` in contracts/test/helpers.ts, and accepts the same
    strings: hyphens are removed and exactly 32 hex digits (any case) must
    remain, so `{...}` and `urn:uuid:` forms are rejected. Raises `ValueError`
    for a string that is not a UUID and `TypeError` for anything else.
    """
    if isinstance(value, str):
        digits = value.replace("-", "")
        if not _UUID_HEX.fullmatch(digits):
            raise ValueError(f"not a UUID: {value!r}")
        return bytes.fromhex(digits) + bytes(16)
    if not isinstance(value, uuid.UUID):
        raise TypeError(f"value must be a UUID or str, not {type(value).__name__}")
    return value.bytes + bytes(16)


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


def submit_transaction(
    tx: dict[str, Any],
    w3: Web3 | None = None,
    *,
    on_signed: Callable[[str], None] | None = None,
) -> str:
    """Sign `tx` as the Treasury Wallet, send it, and return its hash.

    `tx` may only set `to`, `data` and `value`. The nonce (pending), chain id,
    legacy `gasPrice` and gas estimate are filled in here. Does not wait for
    the transaction to be mined: call `wait_for_receipt` on the hash, so a
    retry can wait on that hash instead of sending a second transaction.

    `on_signed(tx_hash)` runs after signing and before the send. A signed
    transaction's hash is final, so a caller can store it before anything
    reaches the chain: then no crash can leave a sent transaction without a
    record. If `on_signed` raises, nothing is sent.

    Raises `TransactionRejected` when the RPC answers the send with an error
    that means the node refused the transaction (`_REFUSED`), so it can never
    be mined. Any other failure of the send (a timeout, a dropped connection,
    an error answer not known to be a refusal) propagates as it is: it is
    unknown whether the transaction reached a node.

    Holds `treasury_send_lock` from the nonce read until the RPC's pending
    nonce has moved past the one used (see the module docstring on nonces).
    """
    extra = set(tx) - _CALLER_TX_FIELDS
    if extra:
        raise ValueError(f"unsupported transaction fields: {sorted(extra)}")
    w3 = w3 or get_web3()
    account = _load_treasury_account()

    with treasury_send_lock():
        nonce = w3.eth.get_transaction_count(account.address, "pending")
        full_tx: dict[str, Any] = {
            "value": 0,
            **tx,
            "from": account.address,
            "nonce": nonce,
            "chainId": Config().EVM_CHAIN_ID,
            "gasPrice": w3.eth.gas_price,
        }
        full_tx["gas"] = w3.eth.estimate_gas(full_tx)

        signed = account.sign_transaction(full_tx)
        tx_hash = Web3.to_hex(signed.hash)
        if on_signed is not None:
            on_signed(tx_hash)

        try:
            sent_hash = Web3.to_hex(w3.eth.send_raw_transaction(signed.raw_transaction))
        except Web3RPCError as exc:
            if _REFUSED.search(str(exc)):
                raise TransactionRejected(tx_hash, exc) from exc
            if not _ALREADY_KNOWN.search(str(exc)):
                raise
            # The node already holds this exact transaction: it was sent.
            sent_hash = tx_hash
        if sent_hash.lower() != tx_hash.lower():
            # Cannot happen for a well-behaved node: the hash is the keccak of
            # the signed bytes. Refuse to report a hash nobody stored.
            raise RuntimeError(
                f"EVM RPC accepted transaction {tx_hash} but reported {sent_hash}"
            )
        _wait_for_nonce_to_advance(w3, account.address, nonce)
    return tx_hash


def _wait_for_nonce_to_advance(w3: Web3, address: str, used_nonce: int) -> None:
    """Poll until the RPC's pending nonce for `address` passes `used_nonce`.

    Bounded by `_NONCE_ADVANCE_TIMEOUT`. On timeout it only logs: the send
    has already been accepted, so failing here would report a sent
    transaction as unsent.
    """
    deadline = time.monotonic() + _NONCE_ADVANCE_TIMEOUT
    while w3.eth.get_transaction_count(address, "pending") <= used_nonce:
        if time.monotonic() >= deadline:
            logger.warning(
                "event=evm.nonce_not_advanced address=%s nonce=%s timeout=%ss",
                address,
                used_nonce,
                _NONCE_ADVANCE_TIMEOUT,
            )
            return
        time.sleep(_NONCE_ADVANCE_POLL)


def burn_tokens(
    amount: Decimal,
    *,
    on_signed: Callable[[str], None] | None = None,
    w3: Web3 | None = None,
) -> str:
    """Burn exactly `amount` UCTUSD from the Treasury Wallet; return the tx hash.

    Calls the token's `burn(uint256)`, which destroys the caller's own
    balance and lowers `totalSupply`. Submits only: does not wait for the
    transaction to be mined. `on_signed` is passed to `submit_transaction`,
    so the caller can store the hash before the send, then wait on it with
    `wait_for_receipt`.

    Rejects a zero amount, and anything `to_base_units` rejects.
    """
    base_units = to_base_units(amount)
    if base_units == 0:
        raise ValueError("burn amount must be positive, got 0")
    w3 = w3 or get_web3()
    token = token_contract(w3)
    tx = {"to": token.address, "data": token.encode_abi("burn", args=[base_units])}
    return submit_transaction(tx, w3=w3, on_signed=on_signed)


class TransactionReverted(RuntimeError):
    """A mined transaction failed (receipt status 0): nothing it did happened."""


class TransactionRejected(RuntimeError):
    """The RPC answered the send with an error that means the node refused
    the transaction: it is in no mempool and can never be mined. Raised only
    for an error answer matching `_REFUSED`, never for a timeout, a dropped
    connection or any other error, where it may still have reached a node."""

    def __init__(self, tx_hash: str, error: Exception) -> None:
        super().__init__(f"EVM RPC refused transaction {tx_hash}: {error}")
        self.tx_hash = tx_hash


# Error answers that mean the node refused the transaction outright (geth's
# txpool messages, which Cosmos EVM reuses). An allowlist on purpose: some
# gateways answer their own timeout as a JSON-RPC error after the node has
# taken the transaction, and calling that a refusal could fail a burn that
# still lands. An unlisted error is treated as unknown, never as refused.
_REFUSED = re.compile(
    r"insufficient funds|nonce too low|underpriced|intrinsic gas too low"
    r"|exceeds block gas limit|invalid sender|fee cap less than block base fee",
    re.IGNORECASE,
)

# How nodes say they already hold a transaction (geth, and Cosmos EVM's
# mempool). Sending the same signed bytes again is not a refusal.
_ALREADY_KNOWN = re.compile(
    r"already known|known transaction|already in (the )?mempool", re.IGNORECASE
)

TX_PENDING = "pending"
TX_UNKNOWN = "unknown"


def transaction_status(tx_hash: str, w3: Web3 | None = None) -> str:
    """`TX_PENDING` if the RPC knows the transaction, `TX_UNKNOWN` if it has
    no record of it. Read-only, for telling a person what to check.

    `TX_UNKNOWN` is not proof the transaction can never be mined: another
    node may still hold it. Never send again on the strength of it.
    """
    w3 = w3 or get_web3()
    try:
        w3.eth.get_transaction(tx_hash)
    except TransactionNotFound:
        return TX_UNKNOWN
    return TX_PENDING


def wait_for_receipt(tx_hash: str, timeout: float = 120, w3: Web3 | None = None):
    """Wait for `tx_hash` to be mined and return its receipt.

    Raises `TransactionReverted` (a `RuntimeError`) if the transaction
    reverted (status 0). Any other error means only that no answer came, so
    the caller may wait on the same hash again. If it is not
    mined within `timeout` seconds, web3's `TimeExhausted` propagates and the
    caller may wait on the same hash again.
    """
    w3 = w3 or get_web3()
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
    if receipt["status"] == 0:
        raise TransactionReverted(f"EVM transaction {tx_hash} reverted")
    return receipt


def send_transaction(
    tx: dict[str, Any], timeout: float = 120, w3: Web3 | None = None
) -> tuple[str, int]:
    """Submit `tx` as the Treasury Wallet, wait for it, return (hash, block).

    `submit_transaction` followed by `wait_for_receipt` on one client. A revert
    raises `RuntimeError`. On web3's `TimeExhausted` the transaction may still
    be mined, but the caller never sees its hash, so it cannot wait on it
    again and a retry would send a second transaction. Retry-safe flows must
    call `submit_transaction`, store the hash, then call `wait_for_receipt`.
    """
    w3 = w3 or get_web3()
    tx_hash = submit_transaction(tx, w3=w3)
    receipt = wait_for_receipt(tx_hash, timeout=timeout, w3=w3)
    return tx_hash, receipt["blockNumber"]
