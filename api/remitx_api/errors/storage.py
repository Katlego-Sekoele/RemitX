"""Errors raised by the object storage layer."""

from __future__ import annotations

from fastapi import status

from remitx_api.errors.base import DomainError


class ObjectStorageNotConfiguredError(DomainError):
    """No bucket credentials in the environment.

    A 503 rather than a 500: nothing about the request is wrong, and the
    caller retrying once the deployment is fixed is the right behaviour.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    def __init__(self) -> None:
        super().__init__(
            "Document storage is not configured on this deployment; "
            "set OBJECT_STORAGE_ENDPOINT_URL and its credentials."
        )


class ObjectStorageError(DomainError):
    """The bucket refused or failed a request the API made on its own behalf."""

    status_code = status.HTTP_502_BAD_GATEWAY
