"""KYC document storage for seed runs.

The documents go through the API's real upload path
(`KycDocumentController.store_document`), which writes to whatever
`remitx_api.services.object_storage.object_storage()` returns. The seeder only
wraps that client so its calls run on the real clock (see clock.py): S3 signs
every request with the current time, and a request signed during a replayed
day is rejected as skewed.
"""

from __future__ import annotations

from datetime import datetime

from remitx_seeder.clock import SimClock


class RealTimeStorage:
    """Delegates every call to the target's bucket client, on the real clock."""

    def __init__(self, inner, clock: SimClock) -> None:
        self._inner = inner
        self._clock = clock

    def put_object(self, key: str, body: bytes, *, content_type: str) -> None:
        with self._clock.real_time():
            self._inner.put_object(key, body, content_type=content_type)

    def presign_get(
        self,
        key: str,
        *,
        content_type: str,
        expires_in: int,
        download_name: str | None = None,
    ) -> str:
        with self._clock.real_time():
            return self._inner.presign_get(
                key,
                content_type=content_type,
                expires_in=expires_in,
                download_name=download_name,
            )

    def stat(self, key: str):
        with self._clock.real_time():
            return self._inner.stat(key)

    def delete(self, key: str) -> None:
        with self._clock.real_time():
            self._inner.delete(key)


class MemoryStorage:
    """A bucket in memory, for tests."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str, datetime]] = {}

    def put_object(self, key: str, body: bytes, *, content_type: str) -> None:
        self.objects[key] = (body, content_type, datetime.now())

    def presign_get(
        self,
        key: str,
        *,
        content_type: str,
        expires_in: int,
        download_name: str | None = None,
    ) -> str:
        return f"memory://{key}?expires_in={expires_in}"

    def stat(self, key: str):
        from remitx_api.services.object_storage import StoredObject

        if key not in self.objects:
            return None
        body, content_type, _ = self.objects[key]
        return StoredObject(size_bytes=len(body), content_type=content_type)

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)
