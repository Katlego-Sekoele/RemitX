"""Deterministic cache keys.

A key names the resource a response describes, not the call that produced it:
``remitx-cache:beneficiaries:<user id>``, never a hash of the handler's
arguments (fastapi-cache's default). That is what lets a write name the entry
a read stored, and drop it.

Keys are hierarchical. Each part after the namespace narrows the one before,
and invalidating a key drops the keys beneath it too. A read that varies by a
query parameter puts it after the resource's id (``<user id>:<sort>``), so a
write that names just the user clears every variant.
"""

from collections.abc import Callable, Mapping
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi_cache.types import KeyBuilder

SEPARATOR = ":"

# `quote(..., safe="")` percent-encodes "!", so no value renders as this.
_NONE = "!"


def key_part(value: object) -> str:
    """Render one value as a key segment.

    Only types whose text *is* their identity. Anything else — an ORM row, a
    Pydantic model — would render as its repr, which carries a memory address:
    every request would get its own key, nothing would ever hit, and no write
    could name the entry to drop. Key on its id instead (``"user.id"``).

    The text is percent-encoded, so a value can neither add a level to the
    key (":") nor act as a wildcard when a namespace is cleared ("*", "?").
    """
    if value is None:
        return _NONE
    if isinstance(value, Enum):
        return key_part(value.value)
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, date):  # datetime included
        text = value.isoformat()
    elif isinstance(value, str | int | Decimal | UUID):
        text = str(value)
    else:
        raise TypeError(
            f"{type(value).__name__} is not a cache key value; key on its id"
        )
    return quote(text, safe="")


def cache_key(namespace: str, *parts: object) -> str:
    """``namespace``, then each part rendered by `key_part`.

    ``namespace`` is the whole prefix fastapi-cache hands a key builder
    (``remitx-cache:beneficiaries``), used as is.
    """
    return SEPARATOR.join([namespace, *(key_part(part) for part in parts)])


def key_from_args(*names: str) -> KeyBuilder:
    """A key builder that keys on the named handler arguments, in order.

    A dotted name reads an attribute of the argument: ``"user.id"`` is the
    ``id`` of the handler's ``user`` parameter. FastAPI passes every handler
    argument by name, so a read and a write address the same entry by naming
    the same arguments — give those parameters the same names in both.

    With no names the key is the namespace itself: one entry shared by every
    caller, for data that is the same for everyone.
    """
    paths = [tuple(name.split(".")) for name in names]
    for name, path in zip(names, paths, strict=True):
        if not all(segment.isidentifier() for segment in path):
            raise ValueError(f"{name!r} is not an argument name or dotted path")

    def build(
        func: Callable[..., Any],
        namespace: str = "",
        *,
        request: Any = None,
        response: Any = None,
        args: tuple[Any, ...] = (),
        kwargs: Mapping[str, Any],
    ) -> str:
        return cache_key(namespace, *(_resolve(func, kwargs, path) for path in paths))

    build.argument_names = tuple(path[0] for path in paths)  # type: ignore[attr-defined]
    build.__qualname__ = f"key_from_args({', '.join(map(repr, names))})"
    return build


def _resolve(
    func: Callable[..., Any], kwargs: Mapping[str, Any], path: tuple[str, ...]
) -> object:
    name, *attributes = path
    if name not in kwargs:
        raise LookupError(
            f"cache key reads argument {name!r}, which "
            f"{func.__qualname__} was not called with"
        )
    value = kwargs[name]
    for attribute in attributes:
        value = getattr(value, attribute)
    return value
