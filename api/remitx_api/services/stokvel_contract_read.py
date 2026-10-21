"""Read-only calls to the stokvel vault from the API.

The worker signs transactions; the API only needs `paused()` to refuse
contributions before they are queued (R3-07, #244).
"""

import logging

from web3 import Web3

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
