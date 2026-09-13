"""The bucket client's own behaviour.

boto3 signs offline, so the read-URL assertions run without a bucket, a
network or a credential that is worth anything. The write is checked against a
stub client: a wrong bucket, key or content type there is silent, and it is
the one call that puts an identity document somewhere.
"""

from urllib.parse import parse_qs, urlparse

import pytest
from remitx_api.errors.storage import ObjectStorageNotConfiguredError
from remitx_api.services.object_storage import S3ObjectStorage

BUCKET = "kyc-documents"
INTERNAL = "http://minio:9000"
PUBLIC = "http://localhost:9000"


def _storage(public: str = PUBLIC) -> S3ObjectStorage:
    return S3ObjectStorage(
        bucket=BUCKET,
        endpoint_url=INTERNAL,
        public_endpoint_url=public,
        region="auto",
        access_key_id="test-key-id",
        secret_access_key="test-secret",
    )


def _query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


class _StubClient:
    """Records the one call `put_object` makes, without a bucket to make it
    against."""

    def __init__(self):
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)
        return {}


def test_a_write_names_the_bucket_the_key_and_the_verified_type():
    storage = _storage()
    stub = _StubClient()
    storage._client = stub

    storage.put_object("kyc/app/doc", b"%PDF-1.7", content_type="application/pdf")

    assert stub.calls == [
        {
            "Bucket": BUCKET,
            "Key": "kyc/app/doc",
            "Body": b"%PDF-1.7",
            # The type the API sniffed, which is what a presigned read will
            # serve the object back as.
            "ContentType": "application/pdf",
        }
    ]


def test_read_url_is_signed_for_the_verified_type():
    """The reviewer's browser decides how to render the response, so the type
    it is told follows from what was sniffed, not from what the bucket
    recorded at upload time."""
    url = _storage().presign_get(
        "kyc/app/doc",
        content_type="application/pdf",
        expires_in=300,
        download_name="id_document-4a1b",
    )

    query = _query(url)
    assert query["response-content-type"] == "application/pdf"
    assert query["response-content-disposition"].startswith("inline;")
    assert int(query["X-Amz-Expires"]) <= 5 * 60


def test_urls_are_signed_for_the_host_the_browser_uses():
    """A read URL signed for `minio:9000` fails in a browser resolving
    `localhost:9000`, and fails with an opaque 403 rather than anything that
    names the cause."""
    url = _storage().presign_get(
        "kyc/app/doc",
        content_type="image/png",
        expires_in=60,
    )
    assert url.startswith(PUBLIC)


def test_bucket_is_addressed_by_path():
    """Neon Object Storage supports path-style addressing only; virtual-host
    style would need DNS for every bucket."""
    url = _storage().presign_get(
        "kyc/app/doc",
        content_type="image/png",
        expires_in=60,
    )
    assert urlparse(url).path == f"/{BUCKET}/kyc/app/doc"


def test_missing_configuration_is_a_503_not_a_crash():
    """The API has to boot and serve /health on a deployment with no bucket;
    only the document routes should fail there."""
    with pytest.raises(ObjectStorageNotConfiguredError):
        S3ObjectStorage(
            bucket=BUCKET,
            endpoint_url="",
            public_endpoint_url="",
            region="auto",
            access_key_id="",
            secret_access_key="",
        )
