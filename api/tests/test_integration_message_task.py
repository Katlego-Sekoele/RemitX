"""The worker half of the integration slice.

Runs the task function directly against a scratch SQLite file — no broker
involved, so these are fast and need no Redis.
"""

import uuid

import pytest
from remitx_api.extensions import Base, build_engine
from remitx_api.models.orm.integration_message import (
    STATUS_PENDING,
    STATUS_PROCESSED,
    IntegrationMessage,
)
from remitx_worker import db as worker_db
from remitx_worker.tasks import process_integration_message
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def session_factory(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'worker.db'}")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    worker_db.configure(factory)
    yield factory
    worker_db.configure(None)


@pytest.fixture
def pending_message(session_factory):
    message_id = uuid.uuid4()
    with session_factory() as session:
        session.add(
            IntegrationMessage(id=message_id, body="hello", status=STATUS_PENDING)
        )
        session.commit()
    return message_id


def load(session_factory, message_id):
    with session_factory() as session:
        return session.get(IntegrationMessage, message_id)


def test_processes_a_pending_message(session_factory, pending_message):
    result = process_integration_message(str(pending_message))

    assert result == "processed"
    stored = load(session_factory, pending_message)
    assert stored.status == STATUS_PROCESSED
    assert stored.processed_at is not None


def test_running_twice_does_not_reprocess(session_factory, pending_message):
    process_integration_message(str(pending_message))
    first = load(session_factory, pending_message).processed_at

    result = process_integration_message(str(pending_message))

    assert result == "skipped"
    assert load(session_factory, pending_message).processed_at == first


def test_unknown_message_is_skipped_not_an_error(session_factory):
    assert process_integration_message(str(uuid.uuid4())) == "skipped"
