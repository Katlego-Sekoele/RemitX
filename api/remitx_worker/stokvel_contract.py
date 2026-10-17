"""The worker's wrapper over the StokvelVault contract (doc section 1).

R2-12 (#234) adds `contribute` and the Treasury allowance it needs. R2-10
(#232) adds `createStokvel` and `startCycle` here, and R3-04 (#241)
`finalise`. Every send goes through `evm_service.submit_transaction`, so it
holds the Treasury send lock and can store its hash before the send.

The ABI is a copy of `contracts/abi/StokvelVault.json`
(`remitx_worker/abi/StokvelVault.json`): the worker image is built from
`api/` only, so it cannot read the contracts folder.
`tests/test_stokvel_contract.py` fails if the two copies differ.

IDs: stokvel and member IDs are database UUIDs packed into `bytes32`
(`evm_service.uuid_to_bytes32`, section 1). Log them in their UUID form.
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from remitx_api.config import Config
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractCustomError, ContractLogicError

from remitx_worker import evm_service

_ABI_PATH = Path(__file__).with_name("abi") / "StokvelVault.json"
VAULT_ABI: list[dict[str, Any]] = json.loads(_ABI_PATH.read_text())

# The token's own errors (OpenZeppelin `IERC20Errors`). UCTUSD raises them
# during `contribute`'s pull, so they are not in the vault's ABI (section 1,
# "Treasury allowance"): revert data is decoded against both.
_TOKEN_ERRORS = (
    "ERC20InsufficientBalance(address,uint256,uint256)",
    "ERC20InvalidSender(address)",
    "ERC20InvalidReceiver(address)",
    "ERC20InsufficientAllowance(address,uint256,uint256)",
    "ERC20InvalidApprover(address)",
    "ERC20InvalidSpender(address)",
)

# `approve(vault, type(uint256).max)`: the one-off approval section 1 agrees.
MAX_UINT256 = 2**256 - 1


def _signature(entry: dict[str, Any]) -> str:
    types = ",".join(item["type"] for item in entry["inputs"])
    return f"{entry['name']}({types})"


def _selector(signature: str) -> str:
    return Web3.keccak(text=signature)[:4].hex().removeprefix("0x")


_ERROR_NAMES: dict[str, str] = {
    _selector(signature): signature.split("(")[0] for signature in _TOKEN_ERRORS
} | {
    _selector(_signature(entry)): entry["name"]
    for entry in VAULT_ABI
    if entry["type"] == "error"
}


def error_name(data: Any) -> str | None:
    """The name of the custom error `data` encodes (its first four bytes), or
    None if it is not one the vault or the token defines."""
    if isinstance(data, bytes | bytearray):
        hex_data = bytes(data).hex()
    elif isinstance(data, str):
        hex_data = data.removeprefix("0x")
    else:
        return None
    return _ERROR_NAMES.get(hex_data[:8].lower())


class ContractRefused(RuntimeError):
    """The node's gas estimate says the call would revert, so it was never
    signed or sent. `error` is the decoded custom error's name (`NotMember`,
    `EnforcedPause`, `ERC20InsufficientBalance`, ...), or None for a revert
    without a known error."""

    def __init__(self, error: str | None, detail: str) -> None:
        super().__init__(f"contract call would revert: {error or detail}")
        self.error = error


def vault(w3: Web3) -> Contract:
    """The StokvelVault at `STOKVEL_CONTRACT_ADDRESS`."""
    address = Web3.to_checksum_address(Config().STOKVEL_CONTRACT_ADDRESS)
    return w3.eth.contract(address=address, abi=VAULT_ABI)


def _submit(tx: dict[str, Any], w3: Web3, on_signed) -> str:
    """`evm_service.submit_transaction`, with a revert at the gas estimate
    raised as `ContractRefused`. Nothing is signed or sent in that case."""
    try:
        return evm_service.submit_transaction(tx, w3=w3, on_signed=on_signed)
    except ContractCustomError as exc:
        raise ContractRefused(error_name(exc.data), str(exc)) from exc
    except ContractLogicError as exc:
        raise ContractRefused(error_name(exc.data), str(exc)) from exc


def ensure_allowance(amount: Decimal, w3: Web3 | None = None) -> str | None:
    """Make sure the vault may pull `amount` UCTUSD from the Treasury Wallet.

    Reads `allowance(treasury, vault)` and, when it is below `amount`,
    approves the vault for `MAX_UINT256` and waits for the approval to be
    mined (section 1: checked before every `contribute`, which also covers a
    redeploy to a new address). Returns the approval's hash, or None when the
    allowance was already enough. Approving again is harmless on UCTUSD, so a
    retry that repeats this is safe.
    """
    w3 = w3 or evm_service.get_web3()
    token = evm_service.token_contract(w3)
    spender = vault(w3).address
    owner = evm_service.treasury_address()
    needed = evm_service.to_base_units(amount)
    if token.functions.allowance(owner, spender).call() >= needed:
        return None
    tx = {
        "to": token.address,
        "data": token.encode_abi("approve", args=[spender, MAX_UINT256]),
    }
    tx_hash = _submit(tx, w3, None)
    evm_service.wait_for_receipt(tx_hash, w3=w3)
    return tx_hash


def contribute(
    stokvel_id: UUID,
    round_: int,
    member_id: UUID,
    *,
    on_signed=None,
    w3: Web3 | None = None,
) -> str:
    """Send `contribute(id, round, memberId)` from the Treasury Wallet and
    return its hash. Submits only: the caller waits on the hash with
    `evm_service.wait_for_receipt`.

    The contract pulls the stokvel's fixed contribution itself; there is no
    amount argument. `on_signed(tx_hash)` runs after signing and before the
    send (see `submit_transaction`). Raises `ContractRefused` when the gas
    estimate shows the call would revert, before anything is signed.
    """
    w3 = w3 or evm_service.get_web3()
    contract = vault(w3)
    data = contract.encode_abi(
        "contribute",
        args=[
            evm_service.uuid_to_bytes32(stokvel_id),
            round_,
            evm_service.uuid_to_bytes32(member_id),
        ],
    )
    return _submit({"to": contract.address, "data": data}, w3, on_signed)
