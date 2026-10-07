"""Log redaction: key-shaped values never reach a log line (#205)."""

import logging

import pytest
from cryptography.fernet import Fernet
from remitx_api.log_redaction import (
    REDACTED,
    RedactingFilter,
    install_log_redaction,
    redact,
)

PRIVATE_KEY = "0x" + "ab12" * 16
FERNET_TOKEN = Fernet(Fernet.generate_key()).encrypt(PRIVATE_KEY.encode()).decode()


def _record(msg, args=(), exc_info=None) -> logging.LogRecord:
    return logging.LogRecord("t", logging.INFO, __file__, 1, msg, args, exc_info)


def _rendered(record: logging.LogRecord) -> str:
    RedactingFilter().filter(record)
    return logging.Formatter().format(record)


@pytest.mark.parametrize(
    "secret", [PRIVATE_KEY, "0x" + PRIVATE_KEY[2:].upper(), FERNET_TOKEN]
)
def test_redact_replaces_key_shapes(secret):
    assert redact(f"before {secret} after") == f"before {REDACTED} after"


def test_redact_replaces_every_occurrence():
    assert redact(f"{PRIVATE_KEY},{FERNET_TOKEN}") == f"{REDACTED},{REDACTED}"


@pytest.mark.parametrize(
    "harmless",
    [
        "0x" + "ab" * 20,  # an EVM address (20 bytes) is public
        "0xdeadbeef",
        "ab12" * 16,  # 64 hex without 0x is not this pattern
        "gAAAAA",  # too short to be a token
    ],
)
def test_redact_leaves_other_values(harmless):
    assert redact(harmless) == harmless


def test_filter_redacts_the_message():
    assert PRIVATE_KEY not in _rendered(_record(f"key {PRIVATE_KEY}"))


def test_filter_redacts_positional_args_and_keeps_their_shape():
    record = _record("%s %d", (PRIVATE_KEY, 7))

    assert _rendered(record) == f"{REDACTED} 7"
    assert isinstance(record.args, tuple)
    assert record.args[1] == 7


def test_filter_redacts_mapping_args():
    record = _record("%(key)s", ({"key": FERNET_TOKEN},))

    assert _rendered(record) == REDACTED


def test_filter_redacts_a_non_string_arg_whose_text_leaks():
    leaky = ValueError(PRIVATE_KEY)

    assert _rendered(_record("%s", (leaky,))) == REDACTED


def test_filter_redacts_tracebacks():
    try:
        raise RuntimeError(f"failed with {PRIVATE_KEY}")
    except RuntimeError:
        import sys

        record = _record("boom", exc_info=sys.exc_info())

    text = _rendered(record)
    assert PRIVATE_KEY not in text
    assert REDACTED in text


def test_install_is_idempotent_and_redacts_new_records(caplog):
    install_log_redaction()
    factory = logging.getLogRecordFactory()
    install_log_redaction()
    assert logging.getLogRecordFactory() is factory

    with caplog.at_level(logging.INFO):
        logging.getLogger("remitx_api.test_log_redaction").info("k=%s", PRIVATE_KEY)

    assert PRIVATE_KEY not in caplog.text
    assert REDACTED in caplog.text
