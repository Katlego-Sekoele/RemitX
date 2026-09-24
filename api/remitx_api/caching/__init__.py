"""Response caching for read endpoints, on fastapi-cache2.

A read caches its response with ``@cache``. A write that changes what the
read would answer carries ``@invalidate_cache`` with the same ``namespace``
and key builder, so the entry it drops is the one the read stored::

    caller = key_from_args("user.id")

    @router.get("/beneficiaries", response_model=list[BeneficiaryRead])
    @cache(expire=300, namespace="beneficiaries", key_builder=caller)
    def list_beneficiaries(user: User = Depends(get_current_user)): ...

    @router.post("/beneficiaries", response_model=BeneficiaryRead)
    @invalidate_cache(namespace="beneficiaries", key_builder=caller)
    def create_beneficiary(payload: ..., user: User = Depends(get_current_user)):
        ...

The decorators go under the route decorator, so FastAPI registers the
wrapped handler. Only GET responses are cached, and dependencies still run on
a hit — authentication included — because ``@cache`` wraps the handler, not
the route.

Rules for a cached read:

- Key on the caller for anything that is theirs. ``key_from_args()`` with no
  names is one entry for everyone, so only for data that is the same for
  everyone.
- Every write that changes the response needs its ``@invalidate_cache``,
  including writes by someone else (an admin decision) and by the settlement
  worker, which never passes through a route. A read something outside the
  API changes should not be cached, or only for as long as it can be stale.
- Never cache a response whose *reading* must be recorded (a KYC document's
  signed URL is audited per read): a hit skips the handler.
"""

from fastapi_cache.decorator import cache

from remitx_api.caching.headers import CachedResponseHeadersMiddleware
from remitx_api.caching.invalidation import invalidate_cache
from remitx_api.caching.keys import cache_key, key_from_args
from remitx_api.caching.lifecycle import close_cache, init_cache

__all__ = [
    "CachedResponseHeadersMiddleware",
    "cache",
    "cache_key",
    "close_cache",
    "init_cache",
    "invalidate_cache",
    "key_from_args",
]
