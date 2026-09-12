"""Cloud worker entry: HTTP /health plus Celery in one process."""

import threading

from remitx_worker.celery_app import celery
from remitx_worker.http import serve_health


def main() -> None:
    threading.Thread(target=serve_health, daemon=True).start()
    celery.worker_main(["worker", "--loglevel=info"])


if __name__ == "__main__":
    main()
