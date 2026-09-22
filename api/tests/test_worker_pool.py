"""The worker sizes its pool from config, never from the host's core count.

Celery's default concurrency is ``os.cpu_count()``. On a Render free instance
that reports the underlying box's 8 cores while capping the container at
512 MB, and each pool process imports ``remitx_api`` (~100 MB), so the default
put the worker ~925 MB over budget: it was OOM-killed between "mingle" and
"ready" and consumed nothing. These tests fail if the explicit flag is ever
dropped again.
"""

import threading

import pytest
from remitx_api.config import Config
from remitx_worker import __main__ as worker_main, http


@pytest.fixture
def captured_argv(monkeypatch):
    """Run main() without starting a health server or a real worker."""
    argv = []
    monkeypatch.setattr(
        worker_main.celery, "worker_main", lambda args: argv.extend(args)
    )
    monkeypatch.setattr(
        threading, "Thread", lambda *a, **k: type("T", (), {"start": lambda s: None})()
    )
    worker_main.main()
    return argv


def test_worker_passes_an_explicit_concurrency(captured_argv):
    assert f"--concurrency={Config.CELERY_CONCURRENCY}" in captured_argv


def test_configured_concurrency_fits_a_free_instance():
    """Two processes measured ~330 MB; eight measured ~925 MB against 512 MB."""
    assert 1 <= Config.CELERY_CONCURRENCY <= 4


def test_forked_child_drops_the_inherited_health_socket(monkeypatch):
    """A child keeping the port bound answers Render's probe with a reset.

    Only the forking thread survives fork, so the child holds the descriptor
    with no server loop behind it. The handler must close the socket and must
    not call ``shutdown()``, which would block forever waiting on that absent
    loop.
    """
    closed = []
    fake_socket = type("S", (), {"close": lambda s: closed.append(True)})()
    fake_server = type("Srv", (), {"socket": fake_socket})()
    monkeypatch.setattr(http, "_server", fake_server)

    worker_main._close_health_socket_in_child()

    assert closed == [True]
    assert http._server is None


def test_closing_an_unowned_socket_is_a_no_op(monkeypatch):
    """The signal also fires in processes that never opened a server."""
    monkeypatch.setattr(http, "_server", None)

    http.close_inherited_socket()

    assert http._server is None
