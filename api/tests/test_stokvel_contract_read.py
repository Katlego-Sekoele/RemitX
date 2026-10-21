"""`stokvel_contract_read.is_paused` (R3-07, #244)."""

import pytest
from remitx_api.errors.stokvels import StokvelContractUnavailableError
from remitx_api.services import stokvel_contract_read


def test_is_paused_fails_closed_when_rpc_errors(monkeypatch):
    monkeypatch.setenv("STOKVEL_CONTRACT_ADDRESS", "0x" + "11" * 20)

    def broken_web3(*_args, **_kwargs):
        raise ConnectionError("rpc down")

    monkeypatch.setattr(stokvel_contract_read, "Web3", broken_web3)

    with pytest.raises(StokvelContractUnavailableError):
        stokvel_contract_read.is_paused()
