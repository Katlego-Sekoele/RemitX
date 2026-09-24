"""The response cache's plumbing: keys, @invalidate_cache, backends, headers.

Routes here are test-only, mounted on a real app so the lifespan, middleware
and fastapi-cache's own ``@cache`` are the ones production runs. What a given
API route caches, and which writes invalidate it, is tested with that route.
"""

import asyncio
import os
import uuid
from dataclasses import dataclass
from enum import Enum

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from fastapi_cache import FastAPICache
from remitx_api.app import create_app
from remitx_api.caching import (
    cache,
    cache_key,
    close_cache,
    init_cache,
    invalidate_cache,
    key_from_args,
)
from remitx_api.caching.backends import (
    InMemoryCacheBackend,
    RedisCacheBackend,
    escape_glob,
)
from remitx_api.caching.keys import key_part
from remitx_api.caching.lifecycle import CACHE_PREFIX, DEFAULT_EXPIRE_SECONDS
from remitx_api.config import Config, TestConfig


class CachingTestConfig(TestConfig):
    CACHE_ENABLED = True


@dataclass(frozen=True)
class Caller:
    id: uuid.UUID


def get_caller(x_caller: str = Header()) -> Caller:
    return Caller(uuid.UUID(x_caller))


caller_key = key_from_args("user.id")
caller_and_sort_key = key_from_args("user.id", "sort")

ALICE = str(uuid.uuid4())
BOB = str(uuid.uuid4())


class Things:
    """A per-caller store, and how often the read handler really ran."""

    def __init__(self) -> None:
        self.by_caller: dict[uuid.UUID, list[str]] = {}
        self.reads = 0
        self.seen_during_write: list[bool] = []


def _mount(app: FastAPI, things: Things) -> None:
    @app.get("/things")
    @cache(namespace="things", key_builder=caller_and_sort_key)
    def list_things(user: Caller = Depends(get_caller), sort: str = "newest"):
        things.reads += 1
        items = list(things.by_caller.get(user.id, []))
        return {"items": sorted(items) if sort == "alphabetical" else items}

    @app.get("/things-archive")
    @cache(namespace="things-archive", key_builder=caller_key)
    async def list_archived_things(user: Caller = Depends(get_caller)):
        things.reads += 1
        return {"items": []}

    @app.get("/catalogue")
    @cache(expire=60, namespace="catalogue", key_builder=key_from_args())
    def get_catalogue():
        things.reads += 1
        return {"version": things.reads}

    @app.post("/things")
    @invalidate_cache(namespace="things", key_builder=caller_key)
    def add_thing(name: str, user: Caller = Depends(get_caller)):
        things.seen_during_write.append(_cached_count(user) > 0)
        things.by_caller.setdefault(user.id, []).append(name)
        return {"added": name}

    @app.post("/things/async")
    @invalidate_cache(namespace="things", key_builder=caller_key)
    async def add_thing_async(name: str, user: Caller = Depends(get_caller)):
        things.by_caller.setdefault(user.id, []).append(name)
        return {"added": name}

    @app.post("/things/refused")
    @invalidate_cache(namespace="things", key_builder=caller_key)
    def add_thing_refused(user: Caller = Depends(get_caller)):
        raise HTTPException(status_code=409, detail="refused")

    @app.delete("/things")
    @invalidate_cache(namespace="things")
    def clear_everyones_things():
        things.by_caller.clear()

    @app.post("/catalogue")
    @invalidate_cache(key="catalogue")
    def publish_catalogue():
        return None


def _cached_count(user: Caller) -> int:
    backend = FastAPICache.get_backend()
    beneath = f"{CACHE_PREFIX}:things:{user.id}:"
    return sum(1 for name in backend._store if name.startswith(beneath))


@pytest.fixture
def things():
    return Things()


@pytest.fixture
def cached(things):
    app = create_app(CachingTestConfig)
    _mount(app, things)
    with TestClient(app) as client:
        yield client


def _get(client, path, caller=ALICE, **params):
    return client.get(path, params=params, headers={"X-Caller": caller})


def _post(client, path, caller=ALICE, **params):
    return client.post(path, params=params, headers={"X-Caller": caller})


# --- @cache with deterministic keys ---------------------------------------


def test_a_repeated_read_is_served_from_the_cache(cached, things):
    first = _get(cached, "/things")
    second = _get(cached, "/things")

    assert first.headers["X-FastAPI-Cache"] == "MISS"
    assert second.headers["X-FastAPI-Cache"] == "HIT"
    assert second.json() == first.json()
    assert things.reads == 1


def test_each_caller_gets_their_own_entry(cached, things):
    things.by_caller[uuid.UUID(ALICE)] = ["alice's"]

    _get(cached, "/things", caller=ALICE)
    bob = _get(cached, "/things", caller=BOB)

    assert bob.headers["X-FastAPI-Cache"] == "MISS"
    assert bob.json() == {"items": []}


def test_the_key_names_the_resource_not_the_call(cached):
    _get(cached, "/things", sort="alphabetical")

    backend = FastAPICache.get_backend()
    assert f"{CACHE_PREFIX}:things:{ALICE}:alphabetical" in backend._store


def test_an_entry_without_its_own_expiry_still_expires(cached):
    _get(cached, "/things")

    ttl, _ = asyncio.run(
        FastAPICache.get_backend().get_with_ttl(f"{CACHE_PREFIX}:things:{ALICE}:newest")
    )
    assert 0 < ttl <= DEFAULT_EXPIRE_SECONDS


def test_a_cached_response_is_not_stored_by_the_browser(cached):
    miss = _get(cached, "/things")
    hit = _get(cached, "/things")

    assert miss.headers["Cache-Control"] == "no-store"
    assert hit.headers["Cache-Control"] == "no-store"


def test_an_uncached_response_keeps_its_headers(cached):
    response = cached.get("/health")

    assert "X-FastAPI-Cache" not in response.headers
    assert "Cache-Control" not in response.headers


# --- @invalidate_cache ----------------------------------------------------


def test_a_write_drops_every_variant_of_the_callers_entry(cached, things):
    _get(cached, "/things", sort="newest")
    _get(cached, "/things", sort="alphabetical")

    assert _post(cached, "/things", name="b").status_code == 200

    for sort in ("newest", "alphabetical"):
        response = _get(cached, "/things", sort=sort)
        assert response.headers["X-FastAPI-Cache"] == "MISS"
        assert response.json() == {"items": ["b"]}


def test_a_write_leaves_other_callers_entries_alone(cached):
    _get(cached, "/things", caller=BOB)

    _post(cached, "/things", caller=ALICE, name="a")

    assert _get(cached, "/things", caller=BOB).headers["X-FastAPI-Cache"] == "HIT"


def test_the_cache_is_dropped_only_after_the_write_ran(cached, things):
    _get(cached, "/things")

    _post(cached, "/things", name="a")

    assert things.seen_during_write == [True]
    assert _get(cached, "/things").headers["X-FastAPI-Cache"] == "MISS"


def test_a_refused_write_leaves_the_cache_as_it_was(cached):
    _get(cached, "/things")

    assert _post(cached, "/things/refused").status_code == 409

    assert _get(cached, "/things").headers["X-FastAPI-Cache"] == "HIT"


def test_an_async_write_invalidates_too(cached):
    _get(cached, "/things")

    _post(cached, "/things/async", name="a")

    assert _get(cached, "/things").json() == {"items": ["a"]}


def test_a_namespace_write_drops_everyones_entries_in_it_only(cached):
    _get(cached, "/things", caller=ALICE)
    _get(cached, "/things", caller=BOB)
    _get(cached, "/things-archive", caller=ALICE)

    cached.delete("/things")

    assert _get(cached, "/things", caller=ALICE).headers["X-FastAPI-Cache"] == "MISS"
    assert _get(cached, "/things", caller=BOB).headers["X-FastAPI-Cache"] == "MISS"
    archive = _get(cached, "/things-archive", caller=ALICE)
    assert archive.headers["X-FastAPI-Cache"] == "HIT"


def test_an_explicit_key_is_dropped(cached):
    first = cached.get("/catalogue").json()

    cached.post("/catalogue")

    assert cached.get("/catalogue").json() != first


def test_a_write_still_answers_when_the_cache_cannot_be_reached(
    cached, monkeypatch, caplog
):
    async def unreachable(*args, **kwargs):
        raise ConnectionError("cache is down")

    monkeypatch.setattr(FastAPICache.get_backend(), "clear", unreachable)

    response = _post(cached, "/things", name="a")

    assert response.status_code == 200
    assert "Could not invalidate cache key" in caplog.text


def test_invalidating_leaves_the_handlers_parameters_to_fastapi(cached):
    operation = cached.app.openapi()["paths"]["/things"]["post"]

    names = {parameter["name"] for parameter in operation["parameters"]}
    assert names == {"name", "x-caller"}


def test_naming_nothing_to_invalidate_is_refused():
    with pytest.raises(ValueError, match="namespace, key_builder or key"):
        invalidate_cache()


def test_keying_on_an_argument_the_write_does_not_take_fails_at_import():
    with pytest.raises(TypeError, match="has no argument 'user'"):

        @invalidate_cache(namespace="things", key_builder=caller_key)
        def write(owner: Caller):
            return None


# --- With the cache switched off ------------------------------------------


def test_switched_off_every_read_runs_the_handler(things):
    app = create_app(TestConfig)
    _mount(app, things)
    with TestClient(app) as client:
        _get(client, "/things")
        response = _get(client, "/things")
        assert _post(client, "/things", name="a").status_code == 200

    assert things.reads == 2
    assert "X-FastAPI-Cache" not in response.headers


def test_cache_enabled_reads_the_environment(monkeypatch):
    monkeypatch.setenv("CACHE_ENABLED", "false")
    assert Config().CACHE_ENABLED is False

    monkeypatch.delenv("CACHE_ENABLED", raising=False)
    assert Config().CACHE_ENABLED is True


# --- Keys -----------------------------------------------------------------


class Colour(Enum):
    RED = "red"


def test_key_parts_render_as_their_identity():
    user_id = uuid.UUID("0b0c4f2e-3a47-4f7b-9d1c-2f3e4a5b6c7d")

    assert cache_key("ns", user_id, Colour.RED, 7, True) == (
        "ns:0b0c4f2e-3a47-4f7b-9d1c-2f3e4a5b6c7d:red:7:true"
    )


def test_a_value_cannot_add_a_level_or_a_wildcard():
    assert key_part("a:b*c?[d]") == "a%3Ab%2Ac%3F%5Bd%5D"


def test_none_is_distinct_from_any_text():
    assert key_part(None) not in {key_part("None"), key_part("!"), key_part("")}


def test_keying_on_an_object_is_refused():
    with pytest.raises(TypeError, match="key on its id"):
        key_part(Caller(uuid.uuid4()))


def test_a_key_builder_needs_the_arguments_it_names():
    def handler():
        return None

    with pytest.raises(LookupError, match="'user'"):
        caller_key(handler, "ns", kwargs={})


def test_a_key_builder_refuses_a_name_that_is_not_an_argument():
    with pytest.raises(ValueError, match="not an argument name"):
        key_from_args("user.id()")


# --- Backends -------------------------------------------------------------


def test_in_memory_backends_do_not_share_a_store():
    first, second = InMemoryCacheBackend(), InMemoryCacheBackend()

    asyncio.run(first.set("k", b"v", 60))

    assert asyncio.run(second.get("k")) is None


def test_in_memory_clear_respects_the_separator_and_missing_keys():
    backend = InMemoryCacheBackend()
    for name in ("ns:a", "ns:a:b", "ns-other:a"):
        asyncio.run(backend.set(name, b"v", 60))

    assert asyncio.run(backend.clear(namespace="ns")) == 2
    assert asyncio.run(backend.clear(key="missing")) == 0
    assert asyncio.run(backend.get("ns-other:a")) == b"v"


def test_glob_characters_are_escaped():
    assert escape_glob("a*b?c[d]\\") == "a\\*b\\?c\\[d\\]\\\\"


redis_only = pytest.mark.skipif(
    os.getenv("SKIP_REDIS_TESTS", "1") == "1",
    reason="Redis not available",
)


class RedisCachingTestConfig(CachingTestConfig):
    CACHE_BACKEND = "redis"


@redis_only
def test_redis_clears_a_namespace_and_nothing_else():
    async def scenario():
        backend = init_cache(RedisCachingTestConfig())
        assert isinstance(backend, RedisCacheBackend)
        redis = backend.redis
        namespace = f"{CACHE_PREFIX}:test-{uuid.uuid4()}"
        others = [f"{namespace}-other:a", "celery-queue-lookalike"]
        try:
            for name in (f"{namespace}:a", f"{namespace}:a:b", *others):
                await redis.set(name, b"v", ex=60)

            assert await backend.clear(namespace=namespace) == 2
            assert await backend.clear(key=f"{namespace}:missing") == 0
            assert all([await redis.exists(name) for name in others])
        finally:
            await redis.delete(*others)
            await close_cache(backend)

    asyncio.run(scenario())
