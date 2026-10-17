"""A non-local target never borrows the developer's chain settings."""

import os

from remitx_seeder import settings


def test_public_chain_settings_match_the_api_defaults(monkeypatch):
    from remitx_api.config import Config

    for key in settings.PUBLIC_CHAIN_SETTINGS:
        monkeypatch.delenv(key, raising=False)
    config = Config()

    assert settings.PUBLIC_CHAIN_SETTINGS == {
        "EVM_RPC_URL": config.EVM_RPC_URL,
        "EVM_CHAIN_ID": str(config.EVM_CHAIN_ID),
        "UCTUSD_CONTRACT_ADDRESS": config.UCTUSD_CONTRACT_ADDRESS,
    }


def _load(monkeypatch, target, file_values, local):
    """`load_target_env` on a copy of the environment holding `local`."""
    environ = {**os.environ, **local}
    monkeypatch.setattr(settings.os, "environ", environ)
    monkeypatch.setattr(settings, "read_target_env", lambda _: dict(file_values))
    settings.load_target_env(target)
    return environ


_LOCAL_FORK = {
    "EVM_RPC_URL": "http://localhost:8545",
    "EVM_CHAIN_ID": "31337",
    "UCTUSD_CONTRACT_ADDRESS": "0x0000000000000000000000000000000000000001",
    "EVM_TREASURY_ADDRESS": "0x0000000000000000000000000000000000000002",
}


def test_a_qa_target_resets_chain_settings_to_the_public_testnet(monkeypatch):
    environ = _load(monkeypatch, "qa", {}, _LOCAL_FORK)

    for key, public in settings.PUBLIC_CHAIN_SETTINGS.items():
        assert environ[key] == public, key
    assert environ["EVM_TREASURY_ADDRESS"] == ""


def test_the_targets_own_file_still_wins(monkeypatch):
    own = {"EVM_RPC_URL": "https://qa-rpc.example", "EVM_TREASURY_ADDRESS": "0xqa"}
    environ = _load(monkeypatch, "qa", own, _LOCAL_FORK)

    assert environ["EVM_RPC_URL"] == "https://qa-rpc.example"
    assert environ["EVM_TREASURY_ADDRESS"] == "0xqa"


def test_the_local_target_keeps_your_settings(monkeypatch):
    environ = _load(monkeypatch, "local", {}, _LOCAL_FORK)

    for key, value in _LOCAL_FORK.items():
        assert environ[key] == value, key
