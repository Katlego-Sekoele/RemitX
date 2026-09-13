"""ASGI middleware that runs before anything looks at a request.

Both of these are pure ASGI rather than Starlette's `BaseHTTPMiddleware`,
which buffers a request and its response to hand them over as objects. That is
exactly wrong in front of the KYC document upload, whose whole design is that
the route decides how much of the body is read
(`services/upload_stream.py`) — a buffering middleware would read all of it
first and the size limit would protect nothing.
"""

from __future__ import annotations

import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from remitx_api.models.orm.kyc_document import MAX_SIZE_BYTES
from remitx_api.request_context import reset_request_id, set_request_id

# The largest legitimate body RemitX accepts is one KYC document, plus room
# for the rest of the request around it. Derived from the document cap rather
# than written out, so the two cannot drift apart, and deliberately a little
# above it: an oversized *document* should be answered by the route, which can
# say what the document limit is, and this is the backstop for everything else.
BODY_SLACK_BYTES = 2 * 1024 * 1024
MAX_REQUEST_BODY_BYTES = MAX_SIZE_BYTES + BODY_SLACK_BYTES

REQUEST_ID_HEADER = b"x-request-id"


class _BodyTooLarge(Exception):
    """Raised out of the wrapped `receive` when a body outgrows the ceiling."""


class MaxBodySizeMiddleware:
    """Refuse a request body larger than `max_bytes`, on any route.

    Without this, the size limit is a property of one endpoint: a JSON body is
    read to completion by the framework before a handler sees it, so any
    route accepting one would happily buffer a gigabyte. Here the limit is a
    property of the deployment, and it applies to paths that do not exist —
    a request to a typo'd URL should not be able to cost us anything either.

    Two checks, as elsewhere: the declared `Content-Length` is refused before
    the body is read at all, and the running total covers a client that
    declared nothing (chunked transfer encoding) or lied.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int = MAX_REQUEST_BODY_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        if self._declared_over_limit(scope):
            return await self._refuse(send)

        remaining = self.max_bytes
        response_started = False

        async def guarded_receive() -> Message:
            nonlocal remaining
            message = await receive()
            if message["type"] == "http.request":
                remaining -= len(message.get("body", b""))
                if remaining < 0:
                    raise _BodyTooLarge
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, guarded_receive, guarded_send)
        except _BodyTooLarge:
            if response_started:
                # Too late to say anything useful; let the server tear the
                # response down rather than emit a second set of headers.
                raise
            await self._refuse(send)

    def _declared_over_limit(self, scope: Scope) -> bool:
        for name, value in scope.get("headers", ()):
            if name == b"content-length":
                try:
                    return int(value) > self.max_bytes
                except ValueError:
                    # An unparseable header is not a limit; the running total
                    # still covers this request.
                    return False
        return False

    async def _refuse(self, send: Send) -> None:
        # Hand-built rather than a JSONResponse: the body shape has to match
        # the one app.py's DomainError handler emits, and nothing else here
        # needs Starlette's response machinery.
        body = (
            b'{"detail":"Request body is too large for this API '
            b"(limit " + str(self.max_bytes).encode() + b' bytes)."}'
        )
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


class RequestIdMiddleware:
    """Tag every request, for `audit_log.request_id` and for log correlation.

    The id is generated here and never read from the request. An inbound
    `X-Request-Id` would let a caller choose the value that correlates their
    own entries in the audit log — including choosing one that collides with
    somebody else's — and nothing in front of this API is trusted enough to
    supply one.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        request_id = uuid.uuid4().hex
        token = set_request_id(request_id)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER, request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            reset_request_id(token)
