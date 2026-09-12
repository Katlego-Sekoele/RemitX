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


def serve_health(port: int | None = None) -> None:
    listen_port = port if port is not None else int(os.getenv("PORT", "4200"))
    server = ThreadingHTTPServer(("0.0.0.0", listen_port), HealthHandler)
    server.serve_forever()
