"""Read-only calls to the stokvel vault from the API.

The worker signs transactions. The API reads `paused()` to refuse
contributions before they are queued (R3-07, #244), and `isFinalisable` plus
`getCycle` so a manual release can refuse before it is queued (R3-10, #247).
"""

import logging
import uuid
from enum import StrEnum

from web3 import Web3
from web3.exceptions import ContractCustomError, ContractLogicError

from remitx_api.config import Config
from remitx_api.errors.stokvels import StokvelContractUnavailableError

logger = logging.getLogger(__name__)

_PAUSED_ABI = [
    {
        "name": "paused",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "bool"}],
    }
]

# Views for one round. Errors are here so a revert names itself.
_FINALISE_ABI = [
    {
        "name": "getStokvel",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "id", "type": "bytes32"}],
        "outputs": [
            {"name": "contribution", "type": "uint256"},
            {"name": "currentCycle", "type": "uint32"},
            {"name": "cycleOpen", "type": "bool"},
        ],
    },
    {
        "name": "isFinalisable",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "id", "type": "bytes32"},
            {"name": "round", "type": "uint8"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "getCycle",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "id", "type": "bytes32"},
            {"name": "cycle", "type": "uint32"},
        ],
        "outputs": [
            {"name": "members", "type": "bytes32[]"},
            {"name": "roundStartTimes", "type": "uint64[]"},
            {"name": "roundDeadlines", "type": "uint64[]"},
            {"name": "payoutTimes", "type": "uint64[]"},
            {"name": "nextToFinalise", "type": "uint8"},
            {"name": "closed", "type": "bool"},
        ],
    },
    {
        "name": "UnknownStokvel",
        "type": "error",
        "inputs": [{"name": "id", "type": "bytes32"}],
    },
    {
        "name": "UnknownCycle",
        "type": "error",
        "inputs": [{"name": "cycle", "type": "uint32"}],
    },
]

_REVERT_NAMES = {
    Web3.keccak(text="UnknownStokvel(bytes32)")[:4].hex().removeprefix("0x"): (
        "UnknownStokvel"
    ),
    Web3.keccak(text="UnknownCycle(uint32)")[:4].hex().removeprefix("0x"): (
        "UnknownCycle"
    ),
}


def is_paused() -> bool:
    """Whether the vault's OpenZeppelin pause is active. False when the
    contract address is unset (local dev without a vault). Raises
    `StokvelContractUnavailableError` when the RPC call fails so callers
    fail closed rather than accepting contributions while state is unknown."""
    address = Config().STOKVEL_CONTRACT_ADDRESS
    if not address:
        return False
    config = Config()
    try:
        w3 = Web3(Web3.HTTPProvider(config.EVM_RPC_URL, request_kwargs={"timeout": 10}))
        if w3.eth.chain_id != config.EVM_CHAIN_ID:
            raise RuntimeError(
                f"chain id {w3.eth.chain_id} != EVM_CHAIN_ID {config.EVM_CHAIN_ID}"
            )
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(address), abi=_PAUSED_ABI
        )
        return bool(contract.functions.paused().call())
    except Exception as exc:
        logger.warning("event=stokvel.paused_read_failed: %s", exc)
        raise StokvelContractUnavailableError() from exc


class FinaliseReadiness(StrEnum):
    """What `finalise(id, round)` would do on the chain right now."""

    READY = "ready"
    NOT_YET = "not_yet"
    ALREADY = "already"
    NO_OPEN_CYCLE = "no_open_cycle"
    UNKNOWN_STOKVEL = "unknown_stokvel"


def classify_finalise(
    round_: int,
    *,
    current_cycle: int,
    cycle_open: bool,
    asked_cycle: int,
    is_finalisable: bool,
    next_to_finalise: int | None,
) -> FinaliseReadiness:
    """Turn one `getStokvel` / `isFinalisable` / `getCycle` read into a
    readiness. `isFinalisable` ignores pause and only looks at the chain's
    current cycle, so a true result counts only for that cycle.
    `next_to_finalise` is None when `getCycle` reverts `UnknownCycle`."""
    if is_finalisable and cycle_open and current_cycle == asked_cycle:
        return FinaliseReadiness.READY
    if current_cycle == 0 or asked_cycle > current_cycle or next_to_finalise is None:
        return FinaliseReadiness.NO_OPEN_CYCLE
    if round_ < next_to_finalise:
        return FinaliseReadiness.ALREADY
    return FinaliseReadiness.NOT_YET


def finalise_readiness(
    stokvel_id: uuid.UUID, cycle_number: int, round_: int
) -> FinaliseReadiness:
    """Whether `finalise` would release this round of this cycle. Raises
    `StokvelContractUnavailableError` when the vault cannot be read, including
    when its address is unset: a release must not be queued unseen."""
    address = Config().STOKVEL_CONTRACT_ADDRESS
    if not address:
        raise StokvelContractUnavailableError()
    config = Config()
    try:
        w3 = Web3(Web3.HTTPProvider(config.EVM_RPC_URL, request_kwargs={"timeout": 10}))
        if w3.eth.chain_id != config.EVM_CHAIN_ID:
            raise RuntimeError(
                f"chain id {w3.eth.chain_id} != EVM_CHAIN_ID {config.EVM_CHAIN_ID}"
            )
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(address), abi=_FINALISE_ABI
        )
        # Same left-aligned packing as remitx_worker.evm_service.uuid_to_bytes32.
        # The API does not import the worker.
        packed = stokvel_id.bytes + bytes(16)
        stokvel = _view(contract.functions.getStokvel(packed).call)
        if stokvel == "UnknownStokvel":
            return FinaliseReadiness.UNKNOWN_STOKVEL
        _contribution, current_cycle, cycle_open = stokvel
        current_cycle = int(current_cycle)
        is_finalisable = False
        if current_cycle == cycle_number and cycle_open:
            flag = _view(contract.functions.isFinalisable(packed, round_).call)
            if flag == "UnknownStokvel":
                return FinaliseReadiness.UNKNOWN_STOKVEL
            is_finalisable = bool(flag)
        next_to_finalise = None
        if not is_finalisable:
            cycle = _view(contract.functions.getCycle(packed, cycle_number).call)
            if cycle == "UnknownStokvel":
                return FinaliseReadiness.UNKNOWN_STOKVEL
            if cycle != "UnknownCycle":
                next_to_finalise = int(cycle[4])
        return classify_finalise(
            round_,
            current_cycle=current_cycle,
            cycle_open=bool(cycle_open),
            asked_cycle=cycle_number,
            is_finalisable=is_finalisable,
            next_to_finalise=next_to_finalise,
        )
    except StokvelContractUnavailableError:
        raise
    except Exception as exc:
        logger.warning("event=stokvel.finalise_read_failed: %s", exc)
        raise StokvelContractUnavailableError() from exc


def _view(call):
    """The call's return value, or the revert's name when it is one we know."""
    try:
        return call()
    except (ContractCustomError, ContractLogicError) as exc:
        name = _revert_name(exc)
        if name is None:
            raise
        return name


def _revert_name(exc: Exception) -> str | None:
    """The vault error name in `exc`, or None.

    web3 sets ``data`` to the hex string on the XRPL EVM testnet, and to
    ``{"message", "data"}`` when the node (Hardhat) returns an object.
    """
    data = getattr(exc, "data", None)
    if isinstance(data, dict):
        data = data.get("data")
    if isinstance(data, bytes | bytearray):
        hex_data = bytes(data).hex()
    elif isinstance(data, str):
        hex_data = data.removeprefix("0x")
    else:
        return None
    return _REVERT_NAMES.get(hex_data[:8].lower())
