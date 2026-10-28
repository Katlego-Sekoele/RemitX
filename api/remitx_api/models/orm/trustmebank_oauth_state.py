import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


class TrustMeBankOAuthState(Base):
    __tablename__ = "trustmebank_oauth_states"

    state: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
