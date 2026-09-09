import uuid

import pytest
from remitx_api.extensions import db
from remitx_api.models.orm.user import User, reference_base
from sqlalchemy.exc import IntegrityError


def test_user_persists_with_generated_id(app_context):
    user = User(clerk_user_id="user_abc", email="a@example.com", reference="a1")
    db.session.add(user)
    db.session.commit()

    assert isinstance(user.id, uuid.UUID)
    assert user.created_at is not None
    assert user.updated_at is not None


def test_email_and_first_name_are_optional(app_context):
    user = User(clerk_user_id="user_no_email", reference="user1")
    db.session.add(user)
    db.session.commit()

    assert user.email is None
    assert user.first_name is None


def test_clerk_user_id_is_unique(app_context):
    db.session.add(User(clerk_user_id="user_dupe", reference="dupe1"))
    db.session.commit()

    db.session.add(User(clerk_user_id="user_dupe", reference="dupe2"))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_reference_is_unique(app_context):
    db.session.add(User(clerk_user_id="user_ref_a", reference="sian1"))
    db.session.commit()

    db.session.add(User(clerk_user_id="user_ref_b", reference="sian1"))
    with pytest.raises(IntegrityError):
        db.session.commit()


@pytest.mark.parametrize(
    ("first_name", "expected"),
    [
        ("Sian", "sian"),
        ("Alexandrina", "alexandr"),  # truncated to 8 chars
        ("O'Brien", "obrien"),  # non-alphanumeric characters stripped
        (None, "user"),  # no name available
        ("", "user"),
    ],
)
def test_reference_base(first_name, expected):
    assert reference_base(first_name) == expected
