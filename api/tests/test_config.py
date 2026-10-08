from remitx_api.config import Config, TestConfig


def test_clerk_secret_key_defaults_to_empty(monkeypatch):
    monkeypatch.delenv("CLERK_SECRET_KEY", raising=False)
    assert Config().CLERK_SECRET_KEY == ""


def test_clerk_secret_key_reads_env(monkeypatch):
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_abc")
    assert Config().CLERK_SECRET_KEY == "sk_test_abc"


def test_test_config_supplies_a_fake_secret():
    assert TestConfig().CLERK_SECRET_KEY == "sk_test_fake"


EVM_DEFAULTS = {
    "EVM_RPC_URL": "https://rpc.testnet.xrplevm.org",
    "EVM_CHAIN_ID": 1449000,
    "EVM_EXPLORER_URL": "https://explorer.testnet.xrplevm.org",
    "UCTUSD_EVM_CONTRACT_ADDRESS": "0x7055071C7B79A859d9514e62833BFf041ce71074",
    "UCTUSD_EVM_DECIMALS": 18,
    "EVM_TREASURY_ADDRESS": "",
    "STOKVEL_CONTRACT_ADDRESS": "",
}


def test_evm_settings_default_to_the_xrpl_evm_testnet(monkeypatch):
    for name in EVM_DEFAULTS:
        monkeypatch.delenv(name, raising=False)

    config = Config()

    for name, default in EVM_DEFAULTS.items():
        assert getattr(config, name) == default


def test_evm_settings_read_env(monkeypatch):
    overrides = {
        "EVM_RPC_URL": "http://localhost:8545",
        "EVM_CHAIN_ID": "31337",
        "EVM_EXPLORER_URL": "http://localhost:4000",
        "UCTUSD_EVM_CONTRACT_ADDRESS": "0x" + "11" * 20,
        "UCTUSD_EVM_DECIMALS": "6",
        "EVM_TREASURY_ADDRESS": "0x" + "22" * 20,
        "STOKVEL_CONTRACT_ADDRESS": "0x" + "33" * 20,
    }
    for name, value in overrides.items():
        monkeypatch.setenv(name, value)

    config = Config()

    assert config.EVM_CHAIN_ID == 31337
    assert config.UCTUSD_EVM_DECIMALS == 6
    for name in (
        "EVM_RPC_URL",
        "EVM_EXPLORER_URL",
        "UCTUSD_EVM_CONTRACT_ADDRESS",
        "EVM_TREASURY_ADDRESS",
        "STOKVEL_CONTRACT_ADDRESS",
    ):
        assert getattr(config, name) == overrides[name]
