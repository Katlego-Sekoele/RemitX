"""Cloud worker entry: HTTP /health plus Celery in one process."""

import threading

from celery.signals import worker_process_init
from remitx_api.config import Config

from remitx_worker.celery_app import celery
from remitx_worker.http import close_inherited_socket, serve_health


@worker_process_init.connect
def _close_health_socket_in_child(**_kwargs) -> None:
    """Drop the listening socket a forked child inherited from the parent.

    Only the forking thread survives fork, so a child has the descriptor but
    no server loop behind it. Left open, a child that outlives an OOM-killed
    parent keeps the port bound and Render's health check gets a connection
    reset instead of a clean refusal, which reads as a sick instance rather
    than a dead one.
    """
    close_inherited_socket()


def main() -> None:
    threading.Thread(target=serve_health, daemon=True).start()
    # Concurrency is passed explicitly: Celery would otherwise size the pool
    # from os.cpu_count(), which on a free Render instance is the host's core
    # count and unrelated to the 512 MB the instance actually gets.
    celery.worker_main(
        [
            "worker",
            "--loglevel=info",
            f"--concurrency={Config.CELERY_CONCURRENCY}",
        ]
    )


if __name__ == "__main__":
    main()
