from remitx_api.config import Config, TestConfig


def test_clerk_secret_key_defaults_to_empty(monkeypatch):
    monkeypatch.delenv("CLERK_SECRET_KEY", raising=False)
    assert Config().CLERK_SECRET_KEY == ""


def test_clerk_secret_key_reads_env(monkeypatch):
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_abc")
    assert Config().CLERK_SECRET_KEY == "sk_test_abc"


def test_test_config_supplies_a_fake_secret():
    assert TestConfig().CLERK_SECRET_KEY == "sk_test_fake"
