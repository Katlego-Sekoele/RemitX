"""The EVM treasury key stays in the worker (#205 acceptance).

(a) The API never loads the decryption path, and its Config cannot hand out
either secret. (b) With a known key configured, no API response, OpenAPI
schema or log line contains it.
"""

import logging
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from remitx_api.app import create_app
from remitx_api.auth.dependencies import get_current_user
from remitx_api.config import Config, TestConfig
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.user import User
from remitx_worker.evm_service import _load_treasury_account
from tests.evm_helpers import configure_fake_treasury

SECRET_SETTINGS = ("EVM_ENCRYPTION_KEY", "EVM_TREASURY_KEY_ENCRYPTED")


# --- (a) the API side never touches the key ---------------------------------


def test_importing_the_api_app_does_not_load_the_evm_key_loader():
    # A fresh interpreter: in this one, other tests have already imported
    # remitx_worker modules, so sys.modules here proves nothing.
    probe = (
        "import sys, remitx_api.app; "
        "loaded = sorted(m for m in sys.modules if m.startswith('remitx_worker')); "
        "assert 'remitx_worker.evm_service' not in loaded, loaded"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_config_has_no_setting_for_either_secret():
    names = {name.upper() for name in dir(Config)}
    for setting in SECRET_SETTINGS:
        assert setting not in names


def test_no_config_value_contains_the_key(monkeypatch):
    treasury = configure_fake_treasury(monkeypatch)
    config = Config()

    for name in dir(config):
        if name.startswith("_"):
            continue
        try:
            value = repr(getattr(config, name))
        except Exception:  # a setting that cannot build here is not a leak
            continue
        for secret in treasury.secrets:
            assert secret not in value, name


# --- (b) responses, schema and logs -----------------------------------------


@pytest.fixture
def treasury(monkeypatch):
    return configure_fake_treasury(monkeypatch)


@pytest.fixture
def lenient_client(treasury):
    """A client for a persisted user that turns server errors into 500s.

    Every GET route is called, and some of them fail in a bare test
    environment. A failure's body and log lines are exactly where a leak
    would show up, so they must be checked rather than raised.
    """
    app = create_app(TestConfig)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        token = db.open_session()
        try:
            persisted = UserController().ensure_provisioned(
                "user_evm_secrecy",
                lambda: "secrecy@example.com",
                lambda: "Secrecy",
            )
            user_id, base_reference = persisted.id, persisted.base_reference
        finally:
            db.close_session(token)
        user = User(id=user_id, base_reference=base_reference)
        app.dependency_overrides[get_current_user] = lambda: user
        yield test_client


def _parameterless_get_paths(app) -> list[str]:
    paths = app.openapi()["paths"]
    return [path for path, item in paths.items() if "get" in item and "{" not in path]


def _assert_absent(text: str, treasury, where: str) -> None:
    for secret in treasury.secrets:
        assert secret not in text, where


def test_no_response_or_schema_contains_the_key(lenient_client, treasury):
    paths = ["/health", "/openapi.json", *_parameterless_get_paths(lenient_client.app)]
    for path in paths:
        response = lenient_client.get(path)
        _assert_absent(response.text, treasury, path)
        _assert_absent(str(response.headers), treasury, f"{path} headers")


def test_no_log_line_contains_the_key(lenient_client, treasury, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)

    # Real flows: every GET route, and the loader failing.
    for path in _parameterless_get_paths(lenient_client.app):
        lenient_client.get(path)
    monkeypatch.setenv("EVM_TREASURY_ADDRESS", "0x" + "00" * 20)
    with pytest.raises(RuntimeError) as caught:
        _load_treasury_account()
    logging.getLogger("remitx_worker.evm_service").exception(
        "treasury load failed", exc_info=caught.value
    )

    # Mistakes: the key and its ciphertext logged outright, as a message, an
    # arg and inside a traceback.
    log = logging.getLogger("remitx_api.test_evm_key_secrecy")
    log.error("key %s", treasury.private_key)
    log.error(f"ciphertext {treasury.encrypted_key}")
    try:
        raise ValueError(f"bad key {treasury.private_key}")
    except ValueError:
        log.exception("decrypt failed")

    _assert_absent(caplog.text, treasury, "captured log text")
    for record in caplog.records:
        _assert_absent(record.getMessage(), treasury, record.name)
    # Positive control: the deliberate leaks were caught and rewritten, not
    # silently dropped.
    assert caplog.text.count("[REDACTED]") >= 3
