"""Worker liveness handler used when the worker is a free web service."""

from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread

from remitx_worker.http import HealthHandler


def test_health_returns_ok():
    server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = HTTPConnection(host, port, timeout=2)
        conn.request("GET", "/health")
        response = conn.getresponse()
        body = response.read()
        conn.close()
    finally:
        server.shutdown()

    assert response.status == 200
    assert body == b'{"status":"ok"}'
