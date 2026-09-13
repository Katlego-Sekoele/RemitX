"""The limit has to hold while the bytes arrive, not after."""

from collections.abc import AsyncIterator

import pytest
from remitx_api.errors.kyc_documents import DocumentTooLargeError, EmptyUploadError
from remitx_api.services.upload_stream import read_upload

LIMIT = 1024


async def _stream(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


class CountingStream:
    """A body that records how much of itself was actually read."""

    def __init__(self, chunk: bytes, count: int) -> None:
        self.chunk = chunk
        self.count = count
        self.read = 0

    async def __aiter__(self):
        for _ in range(self.count):
            self.read += len(self.chunk)
            yield self.chunk


@pytest.mark.anyio
async def test_a_body_within_the_limit_comes_back_whole():
    assert await read_upload(_stream(b"abc", b"def"), limit=LIMIT) == b"abcdef"


@pytest.mark.anyio
async def test_a_declared_length_over_the_limit_is_refused_unread():
    """A browser sets Content-Length itself, so an honest oversized upload
    never gets to send a byte of body."""
    body = CountingStream(b"x" * 64, count=100)

    with pytest.raises(DocumentTooLargeError):
        await read_upload(
            body.__aiter__(),
            limit=LIMIT,
            content_length=str(LIMIT + 1),
        )

    assert body.read == 0


@pytest.mark.anyio
async def test_reading_stops_at_the_limit_rather_than_draining_the_body():
    """Content-Length is a claim, and chunked encoding sends none at all. An
    oversized upload costs the bytes already read and nothing more."""
    body = CountingStream(b"x" * 256, count=1000)

    with pytest.raises(DocumentTooLargeError):
        await read_upload(body.__aiter__(), limit=LIMIT)

    assert body.read <= LIMIT + 256


@pytest.mark.anyio
async def test_an_unparseable_declared_length_falls_through_to_the_real_check():
    """A header that cannot be read is not a limit; the running total is."""
    with pytest.raises(DocumentTooLargeError):
        await read_upload(
            _stream(b"x" * (LIMIT + 1)),
            limit=LIMIT,
            content_length="not-a-number",
        )


@pytest.mark.anyio
async def test_an_empty_body_is_not_a_413():
    with pytest.raises(EmptyUploadError):
        await read_upload(_stream(), limit=LIMIT)
