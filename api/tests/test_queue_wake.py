"""WORKER_WAKE_URL gates the post-enqueue ping; failures never fail enqueue."""

from unittest.mock import MagicMock

from remitx_api.services import queue_service


def test_wake_skipped_when_url_unset(monkeypatch):
    monkeypatch.delenv("WORKER_WAKE_URL", raising=False)
    monkeypatch.setattr(queue_service.producer, "send_task", lambda *a, **k: None)
    opened = []
    monkeypatch.setattr(
        queue_service.urllib.request,
        "urlopen",
        lambda *a, **k: opened.append(a[0]),
    )

    queue_service.enqueue_integration_message("msg-1")

    assert opened == []


def test_wake_called_once_when_url_set(monkeypatch):
    monkeypatch.setenv("WORKER_WAKE_URL", "https://worker.example/health")
    monkeypatch.setattr(queue_service.producer, "send_task", lambda *a, **k: None)
    opened = []
    monkeypatch.setattr(
        queue_service.urllib.request,
        "urlopen",
        lambda url, timeout=5: opened.append((url, timeout)),
    )

    queue_service.enqueue_integration_message("msg-1")

    assert opened == [("https://worker.example/health", 5)]


def test_wake_error_does_not_fail_enqueue(monkeypatch):
    monkeypatch.setenv("WORKER_WAKE_URL", "https://worker.example/health")
    monkeypatch.setattr(queue_service.producer, "send_task", lambda *a, **k: None)
    monkeypatch.setattr(
        queue_service.urllib.request,
        "urlopen",
        MagicMock(side_effect=TimeoutError("cold start")),
    )

    queue_service.enqueue_integration_message("msg-1")
