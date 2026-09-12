"""PENDING rows are re-enqueued after a broker wipe; PROCESSED rows are not."""

import uuid

import pytest
from remitx_api.extensions import Base, build_engine
from remitx_api.models.orm.integration_message import (
    STATUS_PENDING,
    STATUS_PROCESSED,
    IntegrationMessage,
)
from remitx_worker import db as worker_db
from remitx_worker.reclaim import PROCESS_INTEGRATION_MESSAGE, reclaim_pending_messages
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def session_factory(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'reclaim.db'}")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    worker_db.configure(factory)
    yield factory
    worker_db.configure(None)


def test_reclaim_enqueues_pending_only(session_factory, monkeypatch):
    pending_id = uuid.uuid4()
    processed_id = uuid.uuid4()
    with session_factory() as session:
        session.add(
            IntegrationMessage(id=pending_id, body="wait", status=STATUS_PENDING)
        )
        session.add(
            IntegrationMessage(id=processed_id, body="done", status=STATUS_PROCESSED)
        )
        session.commit()

    sent = []
    monkeypatch.setattr(
        "remitx_worker.reclaim.celery.send_task",
        lambda name, args, queue: sent.append((name, args[0], queue)),
    )

    assert reclaim_pending_messages() == 1
    assert sent == [
        (PROCESS_INTEGRATION_MESSAGE, str(pending_id), "settlement"),
    ]


def test_reclaim_noop_when_empty(session_factory, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "remitx_worker.reclaim.celery.send_task",
        lambda *a, **k: sent.append(1),
    )

    assert reclaim_pending_messages() == 0
    assert sent == []
