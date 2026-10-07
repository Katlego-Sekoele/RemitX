"""The worker's EVM treasury key loader (#205): decrypts the key, checks it is
the configured address's, and never puts key material in an error."""

import pytest
from cryptography.fernet import Fernet
from eth_account import Account
from remitx_worker.evm_service import _load_treasury_account
from tests.evm_helpers import configure_fake_treasury


def _assert_no_key_material(error: BaseException, treasury) -> None:
    text = f"{error!s} {error!r} {error.__cause__!r} {error.__context__!r}"
    for secret in treasury.secrets:
        assert secret not in text


def test_loads_the_configured_account(monkeypatch):
    treasury = configure_fake_treasury(monkeypatch)

    account = _load_treasury_account()

    assert account.address == treasury.address
    assert "0x" + bytes(account.key).hex() == treasury.private_key


def test_accepts_an_address_in_any_case(monkeypatch):
    treasury = configure_fake_treasury(monkeypatch)
    monkeypatch.setenv("EVM_TREASURY_ADDRESS", treasury.address.lower())

    assert _load_treasury_account().address == treasury.address


def test_rejects_the_wrong_encryption_key(monkeypatch):
    treasury = configure_fake_treasury(monkeypatch)
    monkeypatch.setenv("EVM_ENCRYPTION_KEY", Fernet.generate_key().decode())

    with pytest.raises(RuntimeError, match="could not be decrypted") as caught:
        _load_treasury_account()

    _assert_no_key_material(caught.value, treasury)
    # Raised from None: the InvalidToken is not chained on.
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__


def test_rejects_an_encryption_key_that_is_not_a_fernet_key(monkeypatch):
    treasury = configure_fake_treasury(monkeypatch)
    monkeypatch.setenv("EVM_ENCRYPTION_KEY", "not-a-fernet-key")

    with pytest.raises(RuntimeError, match="could not be decrypted") as caught:
        _load_treasury_account()

    _assert_no_key_material(caught.value, treasury)


def test_rejects_a_mismatched_address(monkeypatch):
    treasury = configure_fake_treasury(monkeypatch)
    other = Account.create().address
    monkeypatch.setenv("EVM_TREASURY_ADDRESS", other)

    with pytest.raises(RuntimeError, match="derives") as caught:
        _load_treasury_account()

    # Both addresses are public and named; nothing secret is.
    assert treasury.address in str(caught.value)
    assert other in str(caught.value)
    _assert_no_key_material(caught.value, treasury)


def test_rejects_ciphertext_that_is_not_a_private_key(monkeypatch):
    treasury = configure_fake_treasury(monkeypatch)
    not_a_key = Fernet(treasury.encryption_key.encode()).encrypt(b"hello").decode()
    monkeypatch.setenv("EVM_TREASURY_PRIVATE_KEY_ENCRYPTED", not_a_key)

    with pytest.raises(RuntimeError, match="valid EVM private key") as caught:
        _load_treasury_account()

    assert "hello" not in str(caught.value)
    assert caught.value.__suppress_context__


@pytest.mark.parametrize(
    "missing",
    [
        "EVM_TREASURY_PRIVATE_KEY_ENCRYPTED",
        "EVM_ENCRYPTION_KEY",
        "EVM_TREASURY_ADDRESS",
    ],
)
def test_rejects_missing_settings(monkeypatch, missing):
    configure_fake_treasury(monkeypatch)
    monkeypatch.delenv(missing)

    with pytest.raises(RuntimeError, match="not configured"):
        _load_treasury_account()
