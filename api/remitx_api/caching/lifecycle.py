"""Start and stop the response cache with the app (see ``app.py``'s lifespan)."""

from fastapi_cache import FastAPICache
from fastapi_cache.types import Backend
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

from remitx_api.caching.backends import InMemoryCacheBackend, RedisCacheBackend
from remitx_api.caching.headers import CACHE_STATUS_HEADER
from remitx_api.config import Config

# Every key starts with this. The Key Value is shared with the Celery broker,
# so it is what tells a cached response from a queued message.
CACHE_PREFIX = "remitx-cache"

# For an @cache that names no `expire`. The Key Value runs `noeviction` and
# holds the settlement queue: an entry that never expired would take memory
# the queue needs, and once it is full, enqueueing a transfer fails too.
DEFAULT_EXPIRE_SECONDS = 300

# A cache that is down should cost a request a moment, not the request. A
# refused connection fails at once; these bound a Key Value that hangs, to a
# second per cache call. The one immediate retry is for an idle connection
# the server has dropped: without it, that invalidation would be skipped and
# the stale entry served until it expired.
_TIMEOUT_SECONDS = 0.5
_RETRIES = 1


def init_cache(config: Config) -> Backend:
    """Point fastapi-cache at this app's backend, and return that backend.

    fastapi-cache keeps its settings on a class, one set per process, and its
    ``init`` does nothing the second time — so this resets it first, or a
    test's second app would go on using the first one's store.
    """
    backend = _backend(config)
    FastAPICache.reset()
    FastAPICache.init(
        backend,
        prefix=CACHE_PREFIX,
        expire=DEFAULT_EXPIRE_SECONDS,
        cache_status_header=CACHE_STATUS_HEADER,
        enable=config.CACHE_ENABLED,
    )
    return backend


async def close_cache(backend: Backend) -> None:
    """Close ``backend``'s connections.

    fastapi-cache's settings are left as they are: resetting them would also
    reset another app still running in this process (a test's second client)
    to "enabled, not initialised", and its cached routes would fail.
    """
    if isinstance(backend, RedisCacheBackend):
        await backend.redis.aclose()


def _backend(config: Config) -> Backend:
    # Off, nothing reads or writes the backend: no connection to open.
    if not config.CACHE_ENABLED or config.CACHE_BACKEND == "memory":
        return InMemoryCacheBackend()
    if config.CACHE_BACKEND == "redis":
        return RedisCacheBackend(
            Redis.from_url(
                config.REDIS_URL,
                socket_connect_timeout=_TIMEOUT_SECONDS,
                socket_timeout=_TIMEOUT_SECONDS,
                retry=Retry(NoBackoff(), _RETRIES),
            )
        )
    raise ValueError(f"Unknown CACHE_BACKEND {config.CACHE_BACKEND!r}")
