"""`stokvel_contract_read.is_paused` (R3-07, #244)."""

import pytest
from remitx_api.errors.stokvels import StokvelContractUnavailableError
from remitx_api.services import stokvel_contract_read
from web3.exceptions import ContractCustomError


def test_a_hardhat_revert_object_names_the_vault_error():
    selector = "27fef519"  # UnknownStokvel(bytes32)
    exc = ContractCustomError("execution reverted")
    exc.data = {
        "message": "reverted with an unrecognized custom error",
        "data": "0x" + selector + "00" * 32,
    }

    assert stokvel_contract_read._revert_name(exc) == "UnknownStokvel"


def test_is_paused_fails_closed_when_rpc_errors(monkeypatch):
    monkeypatch.setenv("STOKVEL_CONTRACT_ADDRESS", "0x" + "11" * 20)

    def broken_web3(*_args, **_kwargs):
        raise ConnectionError("rpc down")

    monkeypatch.setattr(stokvel_contract_read, "Web3", broken_web3)

    with pytest.raises(StokvelContractUnavailableError):
        stokvel_contract_read.is_paused()
