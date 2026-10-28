from datetime import datetime

from sqlalchemy import DateTime, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


class TrustMeBankWebhookEvent(Base):
    __tablename__ = "trustmebank_webhook_events"

    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
