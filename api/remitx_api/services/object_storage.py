"""S3-compatible object storage: Neon Object Storage in the cloud, MinIO locally.

Uploaded KYC documents are the only untrusted binary input this platform
accepts, and the one class of data the brief's data-protection criteria care
about most. Two properties are worth naming, because the rest of this module is
machinery in service of them:

**Writes go through the API; reads do not.** The API receives the upload,
validates it and puts the object here itself, so nothing reaches the bucket
that has not been checked. Reads are different: a document is rendered by the
reviewer's browser in an ``<img>`` or a sandboxed ``<iframe>``, and neither can
carry an ``Authorization`` header — serving those bytes through the API would
mean inventing a signed URL scheme of our own. So reads use the bucket's.

**Nothing long-lived is ever handed out.** Every URL this module mints carries
an expiry measured in minutes. There is no public bucket, no permanent link,
and no endpoint that streams document bytes through the API.

The signing endpoint and the endpoint the API itself calls are configured
separately because they genuinely differ in Docker Compose: the API reaches
MinIO at ``http://minio:9000`` while the browser reaches it at
``http://localhost:9000``, and the host is part of the SigV4 signature — a URL
signed for the wrong one fails with an opaque 403.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from remitx_api.config import Config
from remitx_api.errors.storage import (
    ObjectStorageError,
    ObjectStorageNotConfiguredError,
)


@dataclass(frozen=True)
class StoredObject:
    """What the bucket says about an object, as opposed to what a client
    claimed about it."""

    size_bytes: int
    content_type: str | None


@runtime_checkable
class ObjectStorage(Protocol):
    """The whole surface the KYC document flow needs.

    Narrow on purpose: the controller can be tested against an in-memory
    implementation of five methods, and swapping Neon for any other
    S3-compatible bucket is a configuration change.
    """

    def put_object(self, key: str, body: bytes, *, content_type: str) -> None:
        """Store one object the API has already validated."""

    def presign_get(
        self,
        key: str,
        *,
        content_type: str,
        expires_in: int,
        download_name: str | None = None,
    ) -> str:
        """A short-lived read URL for one object."""

    def stat(self, key: str) -> StoredObject | None:
        """The object's real size and type, or ``None`` if it is not there."""

    def delete(self, key: str) -> None:
        """Remove an object. Used when a write could not be completed, never
        on a stored document — retention is a lifecycle concern, not a
        route's."""


class S3ObjectStorage:
    """``ObjectStorage`` over any S3 API: Neon Object Storage, MinIO, S3."""

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str,
        public_endpoint_url: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
    ) -> None:
        if not (endpoint_url and bucket and access_key_id and secret_access_key):
            raise ObjectStorageNotConfiguredError()

        self._bucket = bucket
        self._client = self._build_client(
            endpoint_url, region, access_key_id, secret_access_key
        )
        # A second client only because presigning needs the browser-facing
        # host. It signs offline — it never opens a connection.
        self._signing_client = (
            self._client
            if public_endpoint_url == endpoint_url
            else self._build_client(
                public_endpoint_url, region, access_key_id, secret_access_key
            )
        )

    @staticmethod
    def _build_client(
        endpoint_url: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
    ):
        return boto3.session.Session().client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=BotoConfig(
                signature_version="s3v4",
                # Neon Object Storage addresses buckets by path only, and so
                # does MinIO out of the box. Virtual-host style would need DNS
                # for every bucket.
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    @classmethod
    def from_config(cls, config: Config) -> S3ObjectStorage:
        return cls(
            bucket=config.OBJECT_STORAGE_BUCKET,
            endpoint_url=config.OBJECT_STORAGE_ENDPOINT_URL,
            public_endpoint_url=config.OBJECT_STORAGE_PUBLIC_ENDPOINT_URL,
            region=config.OBJECT_STORAGE_REGION,
            access_key_id=config.OBJECT_STORAGE_ACCESS_KEY_ID,
            secret_access_key=config.OBJECT_STORAGE_SECRET_ACCESS_KEY,
        )

    def put_object(self, key: str, body: bytes, *, content_type: str) -> None:
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=body,
                # The type the API sniffed, not the one the client declared.
                # It is what a presigned read will serve the object back as.
                ContentType=content_type,
            )
        except ClientError as exc:
            raise ObjectStorageError(f"Storage rejected a write: {exc}") from exc
        except BotoCoreError as exc:
            raise ObjectStorageError(f"Storage is unreachable: {exc}") from exc

    def presign_get(
        self,
        key: str,
        *,
        content_type: str,
        expires_in: int,
        download_name: str | None = None,
    ) -> str:
        params = {
            "Bucket": self._bucket,
            "Key": key,
            # Serve the type we verified, not whatever the bucket recorded at
            # upload time: the reviewer's browser decides how to render this,
            # and that decision should follow from the sniffed type.
            "ResponseContentType": content_type,
        }
        if download_name:
            params["ResponseContentDisposition"] = f'inline; filename="{download_name}"'
        return self._signing_client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expires_in,
            HttpMethod="GET",
        )

    def stat(self, key: str) -> StoredObject | None:
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if _is_missing(exc):
                return None
            raise ObjectStorageError(f"Storage rejected a lookup: {exc}") from exc
        except BotoCoreError as exc:  # network, DNS, timeouts
            raise ObjectStorageError(f"Storage is unreachable: {exc}") from exc

        return StoredObject(
            size_bytes=int(response["ContentLength"]),
            content_type=response.get("ContentType"),
        )

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise ObjectStorageError(f"Storage rejected a delete: {exc}") from exc


def _is_missing(exc: ClientError) -> bool:
    """S3 answers a HEAD for a missing key with a bare 404 and no error code."""
    error = exc.response.get("Error", {})
    if error.get("Code") in ("404", "NoSuchKey", "NotFound"):
        return True
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return status == 404


_lock = threading.Lock()
_storage: ObjectStorage | None = None


def object_storage() -> ObjectStorage:
    """The process-wide bucket client, built on first use.

    Lazily rather than at import: the API must start and serve /health on a
    deployment with no bucket configured, and only the KYC document routes
    should fail there.
    """
    global _storage
    with _lock:
        if _storage is None:
            _storage = S3ObjectStorage.from_config(Config())
        return _storage


def use_object_storage(storage: ObjectStorage | None) -> None:
    """Install a different implementation. Tests use it; nothing else should."""
    global _storage
    with _lock:
        _storage = storage
