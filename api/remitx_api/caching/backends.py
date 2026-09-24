"""Cache backends whose ``clear`` does what invalidation needs.

fastapi-cache2's own two fall short of it:

- ``RedisBackend.clear(namespace=...)`` deletes through ``KEYS`` in a Lua
  script, which blocks Redis while it walks every key in the database — the
  same database the settlement queue lives in — and splices the namespace
  into the script's source unescaped.
- ``InMemoryBackend`` keeps one store for every instance (a class attribute),
  so apps built one after another in a process share entries; its namespace
  match has no separator, so "things" also clears "things-archive"; and
  clearing a key that is not there raises ``KeyError``.

Both here clear ``namespace`` as the keys beneath it (``<namespace>:*``), and
``key`` as that one key, whether or not it is there.
"""

import asyncio
import re

from fastapi_cache.backends.inmemory import InMemoryBackend, Value
from fastapi_cache.backends.redis import RedisBackend

from remitx_api.caching.keys import SEPARATOR

# Keys asked for per SCAN round trip, and deleted per UNLINK.
_SCAN_BATCH = 500

_GLOB_SPECIAL = re.compile(r"([\\*?\[\]])")


def escape_glob(text: str) -> str:
    """``text`` as a literal inside a Redis ``MATCH`` pattern."""
    return _GLOB_SPECIAL.sub(r"\\\1", text)


class RedisCacheBackend(RedisBackend):
    """Clears a namespace with ``SCAN`` + ``UNLINK``.

    ``SCAN`` walks the keyspace a batch at a time, so Redis keeps serving the
    queue in between, and ``UNLINK`` frees the memory off Redis's main thread.
    """

    async def clear(self, namespace: str | None = None, key: str | None = None) -> int:
        if namespace:
            return await self._unlink_matching(escape_glob(namespace) + SEPARATOR + "*")
        if key:
            return await self.redis.unlink(key)
        return 0

    async def _unlink_matching(self, pattern: str) -> int:
        removed = 0
        batch = []
        async for name in self.redis.scan_iter(match=pattern, count=_SCAN_BATCH):
            batch.append(name)
            if len(batch) == _SCAN_BATCH:
                removed += await self.redis.unlink(*batch)
                batch.clear()
        if batch:
            removed += await self.redis.unlink(*batch)
        return removed


class InMemoryCacheBackend(InMemoryBackend):
    """A store per instance. For tests: see ``Config.CACHE_BACKEND``."""

    def __init__(self) -> None:
        self._store: dict[str, Value] = {}
        # Per instance too: the base class's lock is shared, and an asyncio
        # lock belongs to the event loop that first waits on it.
        self._lock = asyncio.Lock()

    async def clear(self, namespace: str | None = None, key: str | None = None) -> int:
        async with self._lock:
            if namespace:
                beneath = namespace + SEPARATOR
                doomed = [name for name in self._store if name.startswith(beneath)]
            elif key:
                doomed = [key] if key in self._store else []
            else:
                doomed = []
            for name in doomed:
                del self._store[name]
            return len(doomed)
