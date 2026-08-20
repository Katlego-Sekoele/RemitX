import uuid

import pytest
from remitx_api.extensions import db
from remitx_api.models.orm.user import User
from sqlalchemy.exc import IntegrityError


def test_user_persists_with_generated_id(app_context):
    user = User(clerk_user_id="user_abc", email="a@example.com")
    db.session.add(user)
    db.session.commit()

    assert isinstance(user.id, uuid.UUID)
    assert user.created_at is not None
    assert user.updated_at is not None


def test_email_is_optional(app_context):
    user = User(clerk_user_id="user_no_email")
    db.session.add(user)
    db.session.commit()

    assert user.email is None


def test_clerk_user_id_is_unique(app_context):
    db.session.add(User(clerk_user_id="user_dupe"))
    db.session.commit()

    db.session.add(User(clerk_user_id="user_dupe"))
    with pytest.raises(IntegrityError):
        db.session.commit()
