"""An in-memory bucket, so the document flow can be tested without one.

The real implementation is thin — put, head, presign, delete — and every
interesting rule in this feature lives above it: what the bytes turn out to be,
who may ask for a URL, what happens when a write fails. Those are worth testing
against a bucket that cannot be slow, flaky or absent, and against one that can
be made to fail on demand.

`test_object_storage.py` covers the real client's own behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from remitx_api.errors.storage import ObjectStorageError
from remitx_api.services.object_storage import StoredObject


@dataclass(frozen=True)
class SignedRead:
    key: str
    content_type: str
    expires_in: int


@dataclass
class FakeObjectStorage:
    """Enough of ``ObjectStorage`` to drive the controller."""

    objects: dict[str, tuple[bytes, str]] = field(default_factory=dict)
    reads: list[SignedRead] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    #: Set to make the next and every later write fail, standing in for a
    #: bucket outage — the only way a `pending` row is ever left behind.
    fail_writes: bool = False
    #: Set to store fewer bytes than were handed over, standing in for a
    #: truncated write that the client library did not raise on.
    truncate_writes_to: int | None = None

    # -- the ObjectStorage surface ------------------------------------

    def put_object(self, key: str, body: bytes, *, content_type: str) -> None:
        if self.fail_writes:
            raise ObjectStorageError("Storage is unreachable: fake outage")
        if self.truncate_writes_to is not None:
            body = body[: self.truncate_writes_to]
        self.objects[key] = (body, content_type)

    def presign_get(
        self,
        key: str,
        *,
        content_type: str,
        expires_in: int,
        download_name: str | None = None,
    ) -> str:
        self.reads.append(SignedRead(key, content_type, expires_in))
        return f"https://bucket.test/{key}?read=1&expires={expires_in}"

    def stat(self, key: str) -> StoredObject | None:
        item = self.objects.get(key)
        if item is None:
            return None
        body, content_type = item
        return StoredObject(size_bytes=len(body), content_type=content_type)

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)
        self.deleted.append(key)
