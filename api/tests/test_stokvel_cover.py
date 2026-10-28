"""Cover photos on a stokvel (JPEG, PNG or WebP in object storage).

SQLite has no row-level security, so these tests prove the controller's own
checks. Who may write the row under Postgres is the test marked `postgres`.
"""

import uuid
from datetime import UTC, datetime

import pytest
from remitx_api.db.rls import bound_row_security_context
from remitx_api.extensions import db
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_cover import (
    MAX_COVER_BYTES,
    StokvelCover,
    cover_object_key,
)
from remitx_api.services import object_storage as object_storage_module
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, ProgrammingError
from tests.fake_object_storage import FakeObjectStorage
from tests.test_stokvels_route import (
    _in_session,
    _join,
    _provision_user,
    _sign_in_as,
)
from tests.test_stokvels_row_security import _customer, _member, _stokvel

STOKVELS = "/stokvels"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 64
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 32
GIF = b"GIF89a" + b"\x00" * 16
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>steal()</script></svg>'


@pytest.fixture
def storage():
    fake = FakeObjectStorage()
    object_storage_module.use_object_storage(fake)
    yield fake
    object_storage_module.use_object_storage(None)


def _create(client) -> str:
    response = client.post(
        STOKVELS,
        json={"name": "Family", "currency": "ZAR", "contribution_amount": "10"},
    )
    assert response.status_code == 201
    assert response.json()["cover_url"] is None
    return response.json()["stokvel_id"]


def _upload(client, stokvel_id: str, body: bytes, content_type: str):
    return client.post(
        f"{STOKVELS}/{stokvel_id}/cover",
        content=body,
        headers={"Content-Type": content_type},
    )


@pytest.mark.parametrize(
    ("content_type", "body"),
    [("image/jpeg", JPEG), ("image/png", PNG), ("image/webp", WEBP)],
)
def test_a_member_sets_a_cover_and_reads_it_back(
    verified_client, storage, content_type, body
):
    client, _user = verified_client
    stokvel_id = _create(client)

    uploaded = _upload(client, stokvel_id, body, content_type)

    assert uploaded.status_code == 200
    url = uploaded.json()["cover_url"]
    assert url.startswith(f"https://bucket.test/stokvel-covers/{stokvel_id}?")
    assert storage.objects[cover_object_key(uuid.UUID(stokvel_id))] == (
        body,
        content_type,
    )

    listed = client.get(STOKVELS).json()["stokvels"]
    assert listed[0]["cover_url"] == url
    detail = client.get(f"{STOKVELS}/{stokvel_id}").json()
    assert detail["cover_url"] == url


def test_a_fellow_member_replaces_the_cover(verified_client, storage):
    client, _organiser = verified_client
    stokvel_id = _create(client)
    assert _upload(client, stokvel_id, JPEG, "image/jpeg").status_code == 200

    member_id = _provision_user("cover_member")
    _join(uuid.UUID(stokvel_id), member_id)
    _sign_in_as(client, member_id)

    replaced = _upload(client, stokvel_id, PNG, "image/png")

    assert replaced.status_code == 200
    assert storage.objects[cover_object_key(uuid.UUID(stokvel_id))] == (
        PNG,
        "image/png",
    )


def test_someone_who_is_not_a_member_cannot_set_a_cover(verified_client, storage):
    client, _organiser = verified_client
    stokvel_id = _create(client)
    _sign_in_as(client, _provision_user("cover_outsider"))

    response = _upload(client, stokvel_id, JPEG, "image/jpeg")

    assert response.status_code == 404
    assert storage.objects == {}


def test_a_former_member_cannot_set_a_cover(verified_client, storage):
    client, _organiser = verified_client
    stokvel_id = _create(client)
    former_id = _provision_user("cover_former")
    _join(uuid.UUID(stokvel_id), former_id, left=True)
    _sign_in_as(client, former_id)

    response = _upload(client, stokvel_id, JPEG, "image/jpeg")

    assert response.status_code == 404
    assert storage.objects == {}


def test_a_deactivated_stokvel_refuses_a_cover(verified_client, storage):
    client, _user = verified_client
    stokvel_id = _create(client)

    def deactivate():
        stokvel = db.session.get(Stokvel, uuid.UUID(stokvel_id))
        stokvel.deactivated_at = datetime.now(UTC)
        db.session.commit()

    _in_session(deactivate)

    response = _upload(client, stokvel_id, JPEG, "image/jpeg")

    assert response.status_code == 409
    assert response.json()["code"] == "stokvel_deactivated"
    assert storage.objects == {}


def test_an_svg_is_refused_by_name(verified_client, storage):
    client, _user = verified_client
    stokvel_id = _create(client)

    response = _upload(client, stokvel_id, SVG, "image/svg+xml")

    assert response.status_code == 400
    assert "SVG" in response.json()["detail"]
    assert storage.objects == {}


def test_a_gif_is_refused(verified_client, storage):
    client, _user = verified_client
    stokvel_id = _create(client)

    response = _upload(client, stokvel_id, GIF, "image/gif")

    assert response.status_code == 400
    assert storage.objects == {}


def test_the_bytes_have_to_match_the_declared_type(verified_client, storage):
    client, _user = verified_client
    stokvel_id = _create(client)

    response = _upload(client, stokvel_id, PNG, "image/jpeg")

    assert response.status_code == 400
    assert "image/png" in response.json()["detail"]
    assert storage.objects == {}


def test_an_empty_body_is_refused(verified_client, storage):
    client, _user = verified_client
    stokvel_id = _create(client)

    response = _upload(client, stokvel_id, b"", "image/jpeg")

    assert response.status_code == 400
    assert storage.objects == {}


def test_a_cover_over_five_megabytes_is_refused(verified_client, storage):
    client, _user = verified_client
    stokvel_id = _create(client)
    oversized = b"\xff\xd8\xff" + b"\x00" * (MAX_COVER_BYTES - 2)

    response = _upload(client, stokvel_id, oversized, "image/jpeg")

    assert response.status_code == 413
    assert "5 MB" in response.json()["detail"]
    assert storage.objects == {}


def test_a_cover_pointing_at_another_object_is_not_signed(verified_client, storage):
    client, user = verified_client
    stokvel_id = _create(client)

    def plant():
        db.session.add(
            StokvelCover(
                stokvel_id=uuid.UUID(stokvel_id),
                object_key="kyc/someone-elses-document",
                content_type="image/jpeg",
                updated_by_user_id=user.id,
                updated_at=datetime.now(UTC),
            )
        )
        db.session.commit()

    _in_session(plant)

    detail = client.get(f"{STOKVELS}/{stokvel_id}").json()
    assert detail["cover_url"] is None
    assert storage.reads == []


@pytest.mark.postgres
def test_only_a_current_member_can_write_a_cover_under_row_security(postgres_app):
    token = db.open_session()
    try:
        organiser, member, former, outsider = (_customer() for _ in range(4))
        stokvel = _stokvel(organiser, "Family")
        _member(stokvel, member)
        _member(stokvel, former, left_at=datetime.now(UTC))
        db.session.commit()
        stokvel_id = stokvel.id

        def add_cover(user, key: str) -> None:
            db.session.add(
                StokvelCover(
                    stokvel_id=stokvel_id,
                    object_key=key,
                    content_type="image/jpeg",
                    updated_by_user_id=user.id,
                    updated_at=datetime.now(UTC),
                )
            )
            db.session.flush()

        with bound_row_security_context(member.id, is_admin_route=False):
            add_cover(member, cover_object_key(stokvel_id))
            db.session.commit()

        # Drop the identity map so the next read actually asks Postgres,
        # which is what applies the policy.
        db.session.expire_all()
        with bound_row_security_context(outsider.id, is_admin_route=False):
            visible = db.session.scalars(
                select(StokvelCover).where(StokvelCover.stokvel_id == stokvel_id)
            ).all()
            assert visible == []
        db.session.rollback()

        with bound_row_security_context(former.id, is_admin_route=False):
            with pytest.raises(ProgrammingError, match="row-level security"):
                add_cover(former, cover_object_key(stokvel_id))
        db.session.rollback()

        with bound_row_security_context(outsider.id, is_admin_route=False):
            with pytest.raises(ProgrammingError, match="row-level security"):
                add_cover(outsider, cover_object_key(stokvel_id))
        db.session.rollback()

        with bound_row_security_context(member.id, is_admin_route=False):
            with pytest.raises(IntegrityError, match="cover object key"):
                add_cover(member, "kyc/not-this-stokvel")
        db.session.rollback()
    finally:
        db.close_session(token)
