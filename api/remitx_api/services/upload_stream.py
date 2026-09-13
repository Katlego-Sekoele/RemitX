"""Read an upload without letting the client decide how much we read.

The KYC document endpoint is the one place RemitX accepts a large body from a
stranger, so the size limit has to be something the server enforces while the
bytes arrive rather than something it discovers afterwards.

Two checks, in order of how little they cost:

1. **The declared length.** A browser sending a file sets ``Content-Length``
   itself, so an honest oversized upload is refused before a single byte of
   body is read.
2. **The running total.** ``Content-Length`` is a claim, and a client using
   chunked transfer encoding sends none at all, so the real limit is applied
   chunk by chunk: the moment the total crosses it, reading stops and the
   request is refused. An oversized upload costs the bytes already read and
   nothing more.

Multipart would have been the conventional shape and is deliberately not used:
the framework parses the whole body into a spooled temporary file *before* the
handler runs, which puts the decision of when to stop reading in the
framework's hands. Here the body is the file — ``fetch(url, {body: file})``
sets ``Content-Type`` and ``Content-Length`` from the ``File`` — and the
document's metadata travels in the query string.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from remitx_api.errors.kyc_documents import (
    DocumentTooLargeError,
    EmptyUploadError,
)

# Chunk size the ASGI server hands us is its own business; this only bounds how
# far past the limit the total can get before the check fires.
MAX_OVERSHOOT_HINT = 64 * 1024


def _too_large(limit: int) -> DocumentTooLargeError:
    return DocumentTooLargeError(
        f"Documents are limited to {limit // (1024 * 1024)} MB."
    )


async def read_upload(
    stream: AsyncIterator[bytes],
    *,
    limit: int,
    content_length: str | None = None,
) -> bytes:
    """Buffer an upload of at most ``limit`` bytes, or refuse.

    Returns the whole body: the caller has to hash it, sniff it and hand it to
    object storage, and at 10 MB holding it is cheaper than a temporary file
    the request has to clean up. The limit is what makes that affordable, which
    is why it is enforced here and not by whoever reads the result.
    """
    declared = _parse_length(content_length)
    if declared is not None and declared > limit:
        raise _too_large(limit)

    chunks: list[bytes] = []
    total = 0
    async for chunk in stream:
        total += len(chunk)
        if total > limit:
            # Stop reading. Draining the rest of the body to be polite about
            # the connection is exactly what an attacker sending 2 GB wants.
            raise _too_large(limit)
        chunks.append(chunk)

    if total == 0:
        raise EmptyUploadError("The request body is empty; send the file as the body.")

    return b"".join(chunks)


def _parse_length(value: str | None) -> int | None:
    """``None`` for absent or unparseable: an unusable header is not a limit,
    and the running total covers it either way."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
