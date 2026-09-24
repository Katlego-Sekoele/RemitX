"""Keep cached responses out of the browser's cache.

fastapi-cache marks what it serves ``Cache-Control: max-age=<ttl>``, inviting
the browser to reuse the response for the entry's whole lifetime without
asking again. The browser never hears about ``@invalidate_cache``, so after a
write the page would go on showing what it stored, and the invalidation would
only reach other devices. These are a signed-in caller's own records, too,
which should not be left on disk.

So a cached response goes out ``no-store``: the cache is the server's alone.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# What fastapi-cache names the HIT / MISS header; passed to FastAPICache.init
# by lifecycle.py, so this is the one place it is spelled.
CACHE_STATUS_HEADER = "X-FastAPI-Cache"

_CACHE_STATUS = CACHE_STATUS_HEADER.lower().encode("latin-1")
_CACHE_CONTROL = b"cache-control"


class CachedResponseHeadersMiddleware:
    """Replace ``Cache-Control`` with ``no-store`` on every cached response.

    Pure ASGI for the reason given in ``remitx_api/middleware.py``: it only
    touches the response's start message and never buffers a body.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                if any(name.lower() == _CACHE_STATUS for name, _ in headers):
                    kept = [h for h in headers if h[0].lower() != _CACHE_CONTROL]
                    message = {
                        **message,
                        "headers": [*kept, (_CACHE_CONTROL, b"no-store")],
                    }
            await send(message)

        await self.app(scope, receive, send_no_store)
