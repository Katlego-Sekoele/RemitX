"""Keep key material out of every log line the API and worker write.

Two shapes are replaced with ``[REDACTED]``:

- ``0x`` followed by 64 hex digits: an EVM private key as
  ``create_evm_platform_wallet.py`` writes it.
- Fernet tokens (``gAAAAA…``): the encrypted treasury key and the encrypted
  XRPL seed.

The hex pattern cannot tell a private key from any other 32-byte value, so it
**also redacts EVM transaction and block hashes**. Once #204 logs transaction
hashes they will read ``[REDACTED]``. #204 may switch to exact-value
redaction of the loaded key instead.

Redaction runs from a log-record factory, so it happens when a record is
created, not in a handler filter. uvicorn and Celery set up their own handlers
after this code is imported, and ``uvicorn.run(create_app(...))`` builds the
app before uvicorn configures logging, so a filter attached to handlers here
would miss theirs. A factory applies whatever handlers exist.
"""

import logging
import re
from collections.abc import Mapping

REDACTED = "[REDACTED]"

_PATTERNS = (
    re.compile(r"0x[0-9a-fA-F]{64}"),
    # A Fernet token's version byte 0x80 base64-encodes to a leading "gAAAAA".
    re.compile(r"gAAAAA[A-Za-z0-9_\-]{20,}={0,2}"),
)


def redact(text: str) -> str:
    """Return `text` with every key-shaped substring replaced."""
    for pattern in _PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def _redact_arg(value):
    """Redact one log-call argument, keeping its type unless it leaks.

    Non-strings are left as they are unless their string form contains a match,
    so ``%d`` and formatters that read args positionally keep working.
    """
    if isinstance(value, str):
        return redact(value)
    text = str(value)
    redacted = redact(text)
    return value if redacted == text else redacted


class RedactingFilter(logging.Filter):
    """Rewrite a record so its message, args and traceback carry no key material.

    The args are redacted in place rather than merged into the message:
    uvicorn's access formatter unpacks ``record.args`` itself, so they must
    keep their shape. A traceback is rendered into ``exc_text`` and redacted
    too, since an exception's message can carry a value just as a log call can.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_arg(record.msg)
        if isinstance(record.args, Mapping):
            record.args = {k: _redact_arg(v) for k, v in record.args.items()}
        elif isinstance(record.args, tuple):
            record.args = tuple(_redact_arg(arg) for arg in record.args)
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        return True


_filter = RedactingFilter()


def install_log_redaction() -> None:
    """Redact every log record this process creates from now on. Idempotent."""
    current = logging.getLogRecordFactory()
    if getattr(current, "_remitx_redacting", False):
        return

    def factory(*args, **kwargs) -> logging.LogRecord:
        record = current(*args, **kwargs)
        _filter.filter(record)
        return record

    factory._remitx_redacting = True
    logging.setLogRecordFactory(factory)
