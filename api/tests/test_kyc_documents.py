"""Upload, verification and audited retrieval of KYC evidence (issue #59).

The upload goes through the API, so the interesting cases are about what the
API does with bytes it is holding: what it refuses, what never reaches the
bucket, and what it leaves behind when storing fails. The rest is about who is
allowed to look afterwards. A test that only walked the happy path would pass
against an implementation that trusts whatever the client says the file is.
"""

import hashlib
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from remitx_api.auth.dependencies import get_current_user
from remitx_api.extensions import db
from remitx_api.models.orm.audit_log import AuditAction, AuditLog, AuditSubject
from remitx_api.models.orm.kyc_application_history import KycApplicationHistory
from remitx_api.models.orm.kyc_document import (
    MAX_DOCUMENTS_PER_APPLICATION,
    MAX_SIZE_BYTES,
    KycDocument,
)
from remitx_api.models.orm.kyc_lifecycle import KycDocumentStatus, KycStatus
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.repositories.user_repository import UserRepository
from remitx_api.services import object_storage as object_storage_module
from sqlalchemy import select
from tests.fake_object_storage import FakeObjectStorage
from tests.kyc_helpers import ID_NUMBER, insert_application, make_user as make_kyc_user
from tests.rbac_helpers import grant_role, make_user, rbac_client

PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\ntrailer\n%%EOF\n"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 64
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>steal()</script></svg>'

DOCUMENTS = "/kyc/documents"
ADMIN_DOCUMENTS = "/admin/kyc/documents"


@pytest.fixture
def storage():
    """An in-memory bucket for the duration of one test."""
    fake = FakeObjectStorage()
    object_storage_module.use_object_storage(fake)
    yield fake
    object_storage_module.use_object_storage(None)


@pytest.fixture
def applicant_client(storage):
    """A signed-in customer with an application in progress.

    Yields the client, the caller, and their open application.
    """
    user = make_user("applicant")
    with rbac_client(user) as client:
        application = insert_application(user.id, with_pii=True)
        yield client, user, application


@contextmanager
def _acting_as(client, user):
    """Serve the next request as somebody else.

    A reviewer and an applicant have to share one app: each `rbac_client`
    builds its own in-memory database, so two of them cannot see each other's
    rows — and every interesting authorisation test here is about two people
    looking at the same document.
    """
    app = client.app
    previous = app.dependency_overrides[get_current_user]
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield
    finally:
        app.dependency_overrides[get_current_user] = previous


class _Caller:
    """The same client, acting as a different signed-in user."""

    def __init__(self, client, user):
        self._client = client
        self.user = user

    def get(self, *args, **kwargs):
        with _acting_as(self._client, self.user):
            return self._client.get(*args, **kwargs)


@pytest.fixture
def reviewer_client(applicant_client):
    """A compliance analyst — the seeded role that carries
    `kyc:document:read` — on the applicant's app and database."""
    client, _, _ = applicant_client
    reviewer = make_user("reviewer")
    UserRepository().save(reviewer)
    grant_role(reviewer.id, "compliance_analyst")
    return _Caller(client, reviewer)


def _upload(
    client,
    application_id,
    body=PDF,
    *,
    content_type="application/pdf",
    document_type="id_document",
):
    """POST one file, the way the browser does: the body *is* the document."""
    return client.post(
        DOCUMENTS,
        params={
            "application_id": str(application_id),
            "document_type": document_type,
        },
        content=body,
        headers={"Content-Type": content_type},
    )


def _rows(application_id) -> list[KycDocument]:
    db.session.expire_all()
    return list(
        db.session.scalars(
            select(KycDocument).where(KycDocument.application_id == application_id)
        ).all()
    )


def _audit_entries() -> list[AuditLog]:
    db.session.expire_all()
    return list(db.session.scalars(select(AuditLog)).all())


# ----------------------------------------------------------------------
# Uploading
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "content_type"),
    [(PDF, "application/pdf"), (JPEG, "image/jpeg"), (PNG, "image/png")],
)
def test_pdf_jpeg_and_png_are_accepted(applicant_client, storage, body, content_type):
    client, _, application = applicant_client

    response = _upload(
        client, application.application_id, body, content_type=content_type
    )

    assert response.status_code == 201
    stored = response.json()
    assert stored["status"] == KycDocumentStatus.STORED.value
    assert stored["sha256"] == hashlib.sha256(body).hexdigest()
    assert stored["size_bytes"] == len(body)
    assert stored["stored_at"] is not None

    document = _rows(application.application_id)[0]
    assert storage.objects[document.storage_path] == (body, content_type)


def test_the_object_key_carries_no_identifying_value(applicant_client):
    """Object keys turn up in storage access logs, in metrics and in any URL
    that gets pasted into a chat — channels no other control covers."""
    client, _, application = applicant_client
    _upload(client, application.application_id)

    document = _rows(application.application_id)[0]

    assert document.storage_path == (
        f"kyc/{application.application_id}/{document.document_id}"
    )
    # Checked with the generated ids blanked out: random hex contains short
    # digit runs like the postal code often enough to fail a run at random.
    key_shape = document.storage_path.replace(
        str(application.application_id), "<application>"
    ).replace(str(document.document_id), "<document>")
    for identifying in (
        ID_NUMBER,
        "Thandiwe",
        "Mokoena",
        "thandiwe.mokoena@example.com",
        "+27821234567",
        "8001",
        "id_document",
    ):
        assert identifying not in key_shape


def test_a_declared_type_outside_the_allowlist_is_refused(applicant_client, storage):
    client, _, application = applicant_client

    response = _upload(
        client, application.application_id, SVG, content_type="image/svg+xml"
    )

    assert response.status_code == 400
    assert "image/svg+xml" in response.json()["detail"]
    assert _rows(application.application_id) == []
    assert storage.objects == {}


def test_a_body_over_the_cap_is_refused(applicant_client, storage):
    """Refused while it arrives, not after — see services/upload_stream.py."""
    client, _, application = applicant_client

    response = _upload(
        client, application.application_id, PDF + b"\x00" * MAX_SIZE_BYTES
    )

    assert response.status_code == 413
    assert _rows(application.application_id) == []
    assert storage.objects == {}


def test_an_empty_body_is_refused(applicant_client):
    client, _, application = applicant_client

    response = _upload(client, application.application_id, b"")

    assert response.status_code == 400
    assert _rows(application.application_id) == []


def test_a_file_whose_real_type_differs_is_refused(applicant_client, storage):
    """`evil.pdf.exe` and a mislabelled Content-Type both pass a header check;
    neither passes this one."""
    client, _, application = applicant_client

    response = _upload(
        client, application.application_id, PDF, content_type="image/png"
    )

    assert response.status_code == 400
    assert "application/pdf" in response.json()["detail"]
    assert _rows(application.application_id) == []
    assert storage.objects == {}


def test_svg_is_refused_even_when_declared_as_png(applicant_client, storage):
    """An SVG is a scriptable document, and these files are rendered back to
    reviewers."""
    client, _, application = applicant_client

    response = _upload(
        client, application.application_id, SVG, content_type="image/png"
    )

    assert response.status_code == 400
    assert "SVG" in response.json()["detail"]
    assert storage.objects == {}


def test_unidentifiable_content_is_refused(applicant_client, storage):
    client, _, application = applicant_client

    response = _upload(
        client, application.application_id, b"MZ\x90\x00\x03" + b"\x00" * 40
    )

    assert response.status_code == 400
    assert storage.objects == {}


def test_the_same_file_twice_is_refused(applicant_client):
    """`sha256` is the dedup key, so a reviewer is never handed two rows to
    compare that hold the same scan."""
    client, _, application = applicant_client
    assert _upload(client, application.application_id).status_code == 201

    response = _upload(client, application.application_id)

    assert response.status_code == 409


def test_document_count_is_capped_per_application(applicant_client):
    client, _, application = applicant_client
    for index in range(MAX_DOCUMENTS_PER_APPLICATION):
        body = PDF + bytes([index])
        assert _upload(client, application.application_id, body).status_code == 201

    response = _upload(client, application.application_id, PDF + b"overflow")

    assert response.status_code == 409
    assert str(MAX_DOCUMENTS_PER_APPLICATION) in response.json()["detail"]


def test_documents_cannot_be_added_to_a_decided_application(applicant_client):
    client, user, _ = applicant_client
    decided = insert_application(make_kyc_user("decided").id, KycStatus.APPROVED)
    decided.user_id = user.id
    db.session.commit()

    response = _upload(client, decided.application_id)

    assert response.status_code == 409


def test_another_applicants_application_is_not_found(applicant_client, storage):
    client, _, _ = applicant_client
    theirs = insert_application(make_kyc_user("stranger").id)

    response = _upload(client, theirs.application_id)

    assert response.status_code == 404
    assert storage.objects == {}


# ----------------------------------------------------------------------
# When storage fails
# ----------------------------------------------------------------------


def test_a_failed_write_leaves_a_pending_row_and_nothing_to_see(
    applicant_client, reviewer_client, storage
):
    """The only way a pending row happens now: our own write to the bucket
    failed. It is a record of the attempt, not evidence."""
    client, _, application = applicant_client
    storage.fail_writes = True

    response = _upload(client, application.application_id)

    assert response.status_code == 502
    document = _rows(application.application_id)[0]
    assert document.status == KycDocumentStatus.PENDING.value
    assert document.sha256 is None

    assert client.get(f"{DOCUMENTS}/{document.document_id}/url").status_code == 409
    visible = reviewer_client.get(
        ADMIN_DOCUMENTS, params={"application_id": str(application.application_id)}
    )
    assert visible.json() == []


def test_the_same_file_can_be_retried_after_a_failed_write(applicant_client, storage):
    """A pending row carries no digest, so the unique index does not make the
    one file that failed to store the one file that can never be uploaded."""
    client, _, application = applicant_client
    storage.fail_writes = True
    assert _upload(client, application.application_id).status_code == 502

    storage.fail_writes = False
    response = _upload(client, application.application_id)

    assert response.status_code == 201
    assert response.json()["sha256"] == hashlib.sha256(PDF).hexdigest()


def test_a_truncated_write_is_not_marked_stored(applicant_client, storage):
    """`stored` means the object was seen in the bucket at the size we sent,
    not that the client library declined to raise."""
    client, _, application = applicant_client
    storage.truncate_writes_to = 4

    response = _upload(client, application.application_id)

    assert response.status_code == 409
    document = _rows(application.application_id)[0]
    assert document.status == KycDocumentStatus.PENDING.value
    assert document.storage_path in storage.deleted


def test_a_pending_row_does_not_spend_the_applicants_allowance(
    applicant_client, storage
):
    """An outage on our side must not cost somebody their document limit."""
    client, _, application = applicant_client
    storage.fail_writes = True
    for index in range(MAX_DOCUMENTS_PER_APPLICATION):
        _upload(client, application.application_id, PDF + bytes([index]))

    storage.fail_writes = False
    assert _upload(client, application.application_id).status_code == 201


# ----------------------------------------------------------------------
# Retrieval
# ----------------------------------------------------------------------


def test_an_applicant_can_retrieve_their_own_document(applicant_client):
    client, _, application = applicant_client
    document_id = _upload(client, application.application_id).json()["document_id"]

    response = client.get(f"{DOCUMENTS}/{document_id}/url")

    assert response.status_code == 200
    body = response.json()
    assert body["url"]
    assert body["content_type"] == "application/pdf"
    assert datetime.fromisoformat(body["expires_at"]) <= datetime.now(UTC) + timedelta(
        minutes=5
    )


def test_one_applicant_cannot_retrieve_anothers_document(applicant_client):
    """A valid session and a real document id, belonging to somebody else.

    404 rather than 403 on purpose: a 403 confirms the id is real, which is
    most of what enumerating ids is for.
    """
    client, _, _ = applicant_client
    stranger = make_kyc_user("other_applicant")
    theirs = insert_application(stranger.id)
    document = KycDocument(
        application_id=theirs.application_id,
        document_type="id_document",
        status=KycDocumentStatus.STORED.value,
        storage_path=f"kyc/{theirs.application_id}/{uuid.uuid4()}",
        content_type="application/pdf",
        size_bytes=len(PDF),
        sha256=hashlib.sha256(PDF).hexdigest(),
        uploaded_by_user_id=stranger.id,
        stored_at=datetime.now(UTC),
    )
    db.session.add(document)
    db.session.commit()

    response = client.get(f"{DOCUMENTS}/{document.document_id}/url")

    assert response.status_code == 404
    # And the refusal is not recorded as a look at somebody's identity
    # document, because no URL was issued.
    assert _audit_entries() == []


def test_reviewer_retrieval_requires_the_document_permission(storage):
    """`kyc:application:read` is not enough: looking at somebody's identity
    document is its own capability."""
    with rbac_client(
        make_user("nosy"), permissions=(PermissionCode.KYC_APPLICATION_READ,)
    ) as client:
        response = client.get(f"{ADMIN_DOCUMENTS}/{uuid.uuid4()}/url")

    assert response.status_code == 403


def test_reviewer_retrieval_is_short_lived_and_audited(
    applicant_client, reviewer_client, storage
):
    client, _, application = applicant_client
    document_id = _upload(client, application.application_id).json()["document_id"]

    response = reviewer_client.get(f"{ADMIN_DOCUMENTS}/{document_id}/url")

    assert response.status_code == 200
    body = response.json()
    assert datetime.fromisoformat(body["expires_at"]) <= datetime.now(UTC) + timedelta(
        minutes=5
    )
    assert storage.reads[-1].expires_in <= 5 * 60

    entries = db.session.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.KYC_DOCUMENT_VIEWED.value)
    ).all()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.subject_type == AuditSubject.KYC_DOCUMENT.value
    assert str(entry.subject_id) == document_id
    assert entry.after["application_id"] == str(application.application_id)
    assert entry.actor_user_id is not None


def test_the_audit_entry_names_the_actor_not_the_applicant(
    applicant_client, reviewer_client
):
    """ "Who looked at whose ID document" is the question the entry answers."""
    client, applicant, application = applicant_client
    document_id = _upload(client, application.application_id).json()["document_id"]

    reviewer_client.get(f"{ADMIN_DOCUMENTS}/{document_id}/url")

    entry = _audit_entries()[-1]
    assert entry.actor_user_id != applicant.id
    assert entry.after["as_reviewer"] is True


def test_audit_entries_carry_no_pii(applicant_client, reviewer_client):
    """An audit log that needs protecting as carefully as the thing it audits
    has defeated itself."""
    client, _, application = applicant_client
    document_id = _upload(client, application.application_id).json()["document_id"]
    reviewer_client.get(f"{ADMIN_DOCUMENTS}/{document_id}/url")

    serialised = str([entry.after for entry in _audit_entries()])

    for identifying in (ID_NUMBER, "Thandiwe", "Mokoena", "+27821234567"):
        assert identifying not in serialised


def test_a_reviewer_sees_verified_evidence_only(
    applicant_client, reviewer_client, storage
):
    client, _, application = applicant_client
    stored_id = _upload(client, application.application_id).json()["document_id"]
    storage.fail_writes = True
    _upload(client, application.application_id, PNG, content_type="image/png")

    listed = reviewer_client.get(
        ADMIN_DOCUMENTS, params={"application_id": str(application.application_id)}
    ).json()

    assert [item["document_id"] for item in listed] == [stored_id]


# ----------------------------------------------------------------------
# Removal
# ----------------------------------------------------------------------


def _mark_submitted(application, at: datetime) -> None:
    """Record that the application was put in front of a reviewer at `at`."""
    db.session.add(
        KycApplicationHistory(
            application_id=application.application_id,
            status=KycStatus.SUBMITTED.value,
            version_after=application.version + 1,
            changed_at=at,
        )
    )
    db.session.commit()


def test_an_unreviewed_upload_can_be_removed_and_is_audited(applicant_client, storage):
    client, user, application = applicant_client
    uploaded = _upload(client, application.application_id).json()

    listed = client.get(
        DOCUMENTS, params={"application_id": str(application.application_id)}
    ).json()
    response = client.delete(f"{DOCUMENTS}/{uploaded['document_id']}")

    assert listed[0]["removable"] is True
    assert response.status_code == 204
    assert _rows(application.application_id) == []
    assert storage.deleted
    (entry,) = [
        row
        for row in _audit_entries()
        if row.action == AuditAction.KYC_DOCUMENT_REMOVED.value
    ]
    assert entry.actor_user_id == user.id
    assert entry.subject_type == AuditSubject.KYC_DOCUMENT.value
    assert entry.before["document_type"] == "id_document"


def test_a_document_a_reviewer_was_given_cannot_be_removed(applicant_client, storage):
    client, _, application = applicant_client
    uploaded = _upload(client, application.application_id).json()
    # Sent to a reviewer, then returned for more information.
    _mark_submitted(application, datetime.now(UTC) + timedelta(seconds=1))
    application.status = KycStatus.MORE_INFO_REQUIRED.value
    db.session.commit()

    listed = client.get(
        DOCUMENTS, params={"application_id": str(application.application_id)}
    ).json()
    response = client.delete(f"{DOCUMENTS}/{uploaded['document_id']}")

    assert listed[0]["removable"] is False
    assert response.status_code == 409
    assert "replacement" in response.json()["detail"]
    assert len(_rows(application.application_id)) == 1
    assert storage.deleted == []


def test_a_replacement_uploaded_after_review_can_be_removed(applicant_client):
    client, _, application = applicant_client
    _mark_submitted(application, datetime.now(UTC) - timedelta(minutes=5))
    application.status = KycStatus.MORE_INFO_REQUIRED.value
    db.session.commit()
    replacement = _upload(client, application.application_id).json()

    response = client.delete(f"{DOCUMENTS}/{replacement['document_id']}")

    assert response.status_code == 204


def test_nothing_can_be_removed_while_the_application_is_with_a_reviewer(
    applicant_client,
):
    client, _, application = applicant_client
    uploaded = _upload(client, application.application_id).json()
    application.status = KycStatus.SUBMITTED.value
    db.session.commit()

    response = client.delete(f"{DOCUMENTS}/{uploaded['document_id']}")

    assert response.status_code == 409
    assert len(_rows(application.application_id)) == 1


def test_another_applicants_document_cannot_be_removed(applicant_client):
    client, _, _ = applicant_client
    stranger = make_kyc_user("remove_stranger")
    theirs = insert_application(stranger.id)
    document = KycDocument(
        application_id=theirs.application_id,
        document_type="id_document",
        status=KycDocumentStatus.STORED.value,
        storage_path=f"kyc/{theirs.application_id}/{uuid.uuid4()}",
        content_type="application/pdf",
        size_bytes=len(PDF),
        sha256=hashlib.sha256(PDF).hexdigest(),
        uploaded_by_user_id=stranger.id,
        stored_at=datetime.now(UTC),
    )
    db.session.add(document)
    db.session.commit()

    response = client.delete(f"{DOCUMENTS}/{document.document_id}")

    assert response.status_code == 404
    assert len(_rows(theirs.application_id)) == 1
