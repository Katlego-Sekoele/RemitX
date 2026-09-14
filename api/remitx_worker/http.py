"""Tiny liveness server so the worker can run as a Render free web service."""

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HEALTH_BODY = b'{"status":"ok"}'


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/health", "/"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(HEALTH_BODY)))
            self.end_headers()
            self.wfile.write(HEALTH_BODY)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


# Held so a forked Celery child can drop the descriptor it inherited; see
# close_inherited_socket.
_server: ThreadingHTTPServer | None = None


def serve_health(port: int | None = None) -> None:
    global _server
    listen_port = port if port is not None else int(os.getenv("PORT", "4200"))
    _server = ThreadingHTTPServer(("0.0.0.0", listen_port), HealthHandler)
    _server.serve_forever()


def close_inherited_socket() -> None:
    """Close the listening socket in a process that did not open it.

    Only the socket, never ``shutdown()``: that blocks until ``serve_forever``
    acknowledges, and the forked child has no such loop to answer.
    """
    global _server
    if _server is None:
        return
    _server.socket.close()
    _server = None
