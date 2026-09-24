"""A single integer a queue badge or overview card displays."""

from remitx_api.models.schemas.base import Schema


class CountRead(Schema):
    count: int
