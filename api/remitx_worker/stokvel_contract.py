"""The worker's wrapper over the StokvelVault contract (doc section 1).

R2-12 (#234) adds `contribute` and the Treasury allowance it needs; R2-13
(#235) reads the events the sync applies (`fetch_logs`, `decode_log`); R2-10
(#232) `getStokvel`, `createStokvel` and `startCycle`; R3-04 (#241)
`finalise` and `round_finalised`; R3-07 (#244) `pause`, `unpause` and
`paused`. Treasury sends go through `evm_service.submit_transaction`; pause
and unpause use `submit_admin_transaction`. Every send goes through
`evm_service.submit_transaction`, so it holds the Treasury send lock and can
store its hash before the send.

The ABI is a copy of `contracts/abi/StokvelVault.json`
(`remitx_worker/abi/StokvelVault.json`): the worker image is built from
`api/` only, so it cannot read the contracts folder.
`tests/test_worker_stokvel_contribution.py` fails if the two copies differ.

IDs: stokvel and member IDs are database UUIDs packed into `bytes32`
(`evm_service.uuid_to_bytes32`, section 1). Log them in their UUID form.
"""

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from eth_utils import event_abi_to_log_topic
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
    None if it is not one the vault or the token defines.

    A node may hand the revert back as the hex string itself, or as the object
    Hardhat (and web3's dict branch) uses: ``{"message": "...", "data": "0x..."}``.
    The selector is in that inner ``data``.
    """
    if isinstance(data, dict):
        inner = data.get("data")
        if inner is None or inner is data:
            return None
        return error_name(inner)
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


def _submit_admin(tx: dict[str, Any], w3: Web3, on_signed) -> str:
    """`evm_service.submit_admin_transaction`, with the same revert handling
    as `_submit`."""
    try:
        return evm_service.submit_admin_transaction(tx, w3=w3, on_signed=on_signed)
    except ContractCustomError as exc:
        raise ContractRefused(error_name(exc.data), str(exc)) from exc
    except ContractLogicError as exc:
        raise ContractRefused(error_name(exc.data), str(exc)) from exc


def paused(w3: Web3 | None = None) -> bool:
    """OpenZeppelin `paused()` on the vault."""
    w3 = w3 or evm_service.get_web3()
    return bool(vault(w3).functions.paused().call())


def pause(*, on_signed=None, w3: Web3 | None = None) -> str:
    """Send `pause()` from the vault admin key and return its hash."""
    w3 = w3 or evm_service.get_web3()
    contract = vault(w3)
    data = contract.encode_abi("pause", args=[])
    return _submit_admin({"to": contract.address, "data": data}, w3, on_signed)


def unpause(*, on_signed=None, w3: Web3 | None = None) -> str:
    """Send `unpause()` from the vault admin key and return its hash."""
    w3 = w3 or evm_service.get_web3()
    contract = vault(w3)
    data = contract.encode_abi("unpause", args=[])
    return _submit_admin({"to": contract.address, "data": data}, w3, on_signed)


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


def finalise(
    stokvel_id: UUID,
    round_: int,
    *,
    on_signed=None,
    w3: Web3 | None = None,
) -> str:
    """Send `finalise(id, round)` from the Treasury Wallet and return its hash
    (R3-04). Submits only: the caller waits on the hash with
    `evm_service.wait_for_receipt`, then reads the release from the receipt
    with `round_finalised`.

    The contract releases the round's pool to the Treasury Wallet only if it
    is the next round to release, it and the next round are fully paid, and
    its payout time has passed. Otherwise the gas estimate reverts and this
    raises `ContractRefused` before anything is signed: `AlreadyFinalised`
    (a `contribute` released it first) or `NotYetFinalisable` (not due).
    """
    w3 = w3 or evm_service.get_web3()
    contract = vault(w3)
    data = contract.encode_abi(
        "finalise", args=[evm_service.uuid_to_bytes32(stokvel_id), round_]
    )
    return _submit({"to": contract.address, "data": data}, w3, on_signed)


# The events `stokvel.sync_events` applies (doc section 4, "Contract event →
# database update"). `StokvelCreated` and `CycleStarted` only confirm what the
# backend itself sent, so they are not read.
SYNCED_EVENTS = ("ContributionMade", "RoundFinalised", "CycleClosed")

# topic0 -> event name, built once with eth_utils (web3's own rule, which
# handles every argument type).
_TOPIC_EVENTS = {
    event_abi_to_log_topic(entry): entry["name"]
    for entry in VAULT_ABI
    if entry["type"] == "event" and entry["name"] in SYNCED_EVENTS
}


@dataclass(frozen=True)
class ContractEvent:
    """One decoded vault event, with where it happened on-chain."""

    name: str
    args: dict[str, Any]
    tx_hash: str
    block_number: int
    log_index: int


def fetch_logs(from_block: int, to_block: int, w3: Web3) -> list:
    """The vault's raw `SYNCED_EVENTS` logs in blocks `from_block`..`to_block`
    (inclusive), in chain order (block, then log index). The RPC call only:
    decode each with `decode_log`, so a log that will not decode is not
    mistaken for an RPC failure. One `eth_getLogs` call: the caller keeps the
    range within what the RPC allows."""
    logs = w3.eth.get_logs(
        {
            "address": vault(w3).address,
            "fromBlock": from_block,
            "toBlock": to_block,
            "topics": [list(_TOPIC_EVENTS)],
        }
    )
    return sorted(logs, key=lambda log: (log["blockNumber"], log["logIndex"]))


def decode_log(log, w3: Web3) -> ContractEvent:
    """Decode one raw vault log. Raises for a log that is not a synced event
    or does not match the ABI (a drifted ABI copy, a malformed log)."""
    name = _TOPIC_EVENTS.get(bytes(log["topics"][0]))
    if name is None:
        raise ValueError(f"not a synced vault event: topic {log['topics'][0]!r}")
    decoded = vault(w3).events[name]().process_log(log)
    return ContractEvent(
        name=name,
        args=dict(decoded["args"]),
        tx_hash=Web3.to_hex(decoded["transactionHash"]),
        block_number=decoded["blockNumber"],
        log_index=decoded["logIndex"],
    )


@dataclass(frozen=True)
class OnChainStokvel:
    """`getStokvel(id)`: the stokvel's fixed contribution in UCTUSD base
    units, its current (latest) cycle (0 before the first) and whether that
    cycle is open."""

    contribution: int
    current_cycle: int
    cycle_open: bool


def get_stokvel(stokvel_id: UUID, w3: Web3 | None = None) -> OnChainStokvel | None:
    """The stokvel as the contract holds it, or None if it is not registered
    (`getStokvel` reverts `UnknownStokvel`). A read: nothing is sent."""
    w3 = w3 or evm_service.get_web3()
    try:
        contribution, current_cycle, cycle_open = (
            vault(w3)
            .functions.getStokvel(evm_service.uuid_to_bytes32(stokvel_id))
            .call()
        )
    except (ContractCustomError, ContractLogicError) as exc:
        if error_name(exc.data) == "UnknownStokvel":
            return None
        raise
    return OnChainStokvel(int(contribution), int(current_cycle), bool(cycle_open))


def create_stokvel(
    stokvel_id: UUID,
    contribution: Decimal,
    *,
    on_signed=None,
    w3: Web3 | None = None,
) -> str:
    """Send `createStokvel(id, contribution)` from the Treasury Wallet and
    return its hash: register the stokvel and its fixed UCTUSD contribution
    for every cycle (D13). Submits only. Raises `ContractRefused` when the
    gas estimate shows it would revert (`StokvelExists` once it is
    registered), before anything is signed."""
    w3 = w3 or evm_service.get_web3()
    contract = vault(w3)
    data = contract.encode_abi(
        "createStokvel",
        args=[
            evm_service.uuid_to_bytes32(stokvel_id),
            evm_service.to_base_units(contribution),
        ],
    )
    return _submit({"to": contract.address, "data": data}, w3, on_signed)


def start_cycle(
    stokvel_id: UUID,
    member_ids: list[UUID],
    round_start_times: list[int],
    round_deadlines: list[int],
    payout_times: list[int],
    *,
    on_signed=None,
    w3: Web3 | None = None,
) -> str:
    """Send `startCycle(id, memberIds, roundStartTimes, roundDeadlines,
    payoutTimes)` from the Treasury Wallet and return its hash. Submits only.

    `member_ids` are in payout order (round i pays `member_ids[i]`); the
    times are Unix seconds, one per round. Raises `ContractRefused` when the
    gas estimate shows it would revert, before anything is signed.
    """
    w3 = w3 or evm_service.get_web3()
    contract = vault(w3)
    data = contract.encode_abi(
        "startCycle",
        args=[
            evm_service.uuid_to_bytes32(stokvel_id),
            [evm_service.uuid_to_bytes32(member_id) for member_id in member_ids],
            round_start_times,
            round_deadlines,
            payout_times,
        ],
    )
    return _submit({"to": contract.address, "data": data}, w3, on_signed)


def round_finalised(receipt, w3: Web3) -> list[ContractEvent]:
    """The vault's `RoundFinalised` events in a mined receipt, in log order.
    A `finalise` releases exactly one round; a `contribute` may release
    several. Logs from other contracts in the receipt are ignored."""
    address = vault(w3).address.lower()
    return [
        decode_log(log, w3)
        for log in receipt["logs"]
        if str(log["address"]).lower() == address
        and _TOPIC_EVENTS.get(bytes(log["topics"][0])) == "RoundFinalised"
    ]
