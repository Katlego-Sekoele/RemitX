"""SQLAlchemy ORM models. Import models here so metadata is registered."""

from remitx_api.extensions import Base
from remitx_api.models.orm.integration_message import IntegrationMessage

__all__ = ["Base", "IntegrationMessage"]
