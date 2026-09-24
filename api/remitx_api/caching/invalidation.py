"""``@invalidate_cache``: drop cached reads once a write has succeeded.

The counterpart to fastapi-cache's ``@cache``. ``namespace`` and
``key_builder`` mean what they mean there, so a write names the entry a read
stored by repeating the read's arguments. What is dropped:

=========================  ===================================================
namespace only             every key in the namespace
namespace + key_builder    the key ``@cache`` stored under that namespace and
                           key builder for these arguments
namespace + key            ``<namespace>:<key>`` for each key given
key only                   ``<key>`` for each key given
=========================  ===================================================

Every key is dropped with the keys beneath it (``<key>:*``; see
``caching/keys.py``). A key builder here is called with the write's
arguments and no request, so it has to key on arguments alone —
``key_from_args`` does.

The handler runs first. Only once it returns are the keys dropped, so a
refused or failed write (any exception, ``HTTPException`` included) leaves the
cache as it was. Controllers commit before they return, so by then the next
read caches the new rows. A read that fetched the old rows before the commit
can still store them just after the drop; the entry's TTL is what bounds that.
"""

import inspect
import logging
from collections.abc import Awaitable, Callable, Sequence
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from fastapi.concurrency import run_in_threadpool
from fastapi_cache import FastAPICache
from fastapi_cache.types import KeyBuilder

from remitx_api.caching.keys import SEPARATOR

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def invalidate_cache(
    *,
    namespace: str = "",
    key_builder: KeyBuilder | None = None,
    key: str | Sequence[str] | None = None,
) -> Callable[[Callable[P, R] | Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Drop the cache entries a write makes stale, after the write succeeds.

    Stack one per namespace when a write changes more than one resource.
    """
    keys = [key] if isinstance(key, str) else list(key or ())
    if not (namespace or key_builder or keys):
        raise ValueError(
            "invalidate_cache needs a namespace, key_builder or key; "
            "with none it would drop every cached response"
        )

    def decorator(func):
        _check_arguments(func, key_builder)

        @wraps(func)
        async def inner(*args: P.args, **kwargs: P.kwargs) -> R:
            if inspect.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                # How FastAPI runs a plain `def` handler itself: on a worker
                # thread, so its blocking work stays off the event loop.
                result = await run_in_threadpool(func, *args, **kwargs)
            await _invalidate(func, args, kwargs, namespace, key_builder, keys)
            return result

        return inner

    return decorator


def _check_arguments(func: Callable[..., Any], key_builder: KeyBuilder | None) -> None:
    """Fail at import, not per request, when the key names a missing argument.

    A read with a bad key builder fails loudly on its first request. A write
    cannot: it has already committed by the time the key is built, so the
    error is only logged, and the stale entry lives out its TTL unnoticed.
    """
    names = getattr(key_builder, "argument_names", ())
    parameters = inspect.signature(func).parameters
    missing = [name for name in names if name not in parameters]
    if missing:
        raise TypeError(
            f"{func.__qualname__} has no argument {missing[0]!r} for "
            f"{key_builder.__qualname__} to key on"
        )


async def _invalidate(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    namespace: str,
    key_builder: KeyBuilder | None,
    keys: list[str],
) -> None:
    if not FastAPICache.get_enable():
        return  # nothing is cached, so nothing can be stale

    prefix = FastAPICache.get_prefix()
    scope = _join(prefix, namespace)
    try:
        targets = [_join(scope, k) for k in keys]
        if key_builder is not None:
            # Exactly what @cache hands its key builder, so the two agree.
            built = key_builder(
                func,
                f"{prefix}{SEPARATOR}{namespace}",
                request=None,
                response=None,
                args=args,
                kwargs=kwargs,
            )
            targets.append(await built if inspect.isawaitable(built) else built)
        if not targets:
            targets = [scope]
    except Exception:
        # The write has committed. Failing the request now would invite a
        # retry of something that already happened.
        logger.exception("Could not build the cache keys %s invalidates", func)
        return

    backend = FastAPICache.get_backend()
    for target in targets:
        try:
            await backend.clear(key=target)
            await backend.clear(namespace=target)
        except Exception:
            logger.warning("Could not invalidate cache key %r", target, exc_info=True)


def _join(scope: str, part: str) -> str:
    return f"{scope}{SEPARATOR}{part}" if part else scope
