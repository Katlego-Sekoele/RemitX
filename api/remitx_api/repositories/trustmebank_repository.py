import uuid
from datetime import UTC, datetime, timedelta

from remitx_api.extensions import db
from remitx_api.models.orm.trustmebank_link import TrustMeBankLink
from remitx_api.models.orm.trustmebank_oauth_state import TrustMeBankOAuthState
from remitx_api.models.orm.trustmebank_webhook_event import TrustMeBankWebhookEvent

_OAUTH_STATE_TTL = timedelta(minutes=10)


class TrustMeBankRepository:
    def get_link(self, user_id: uuid.UUID) -> TrustMeBankLink | None:
        return db.session.get(TrustMeBankLink, user_id)

    def save_link(self, link: TrustMeBankLink) -> TrustMeBankLink:
        db.session.add(link)
        db.session.flush()
        return link

    def delete_link(self, user_id: uuid.UUID) -> None:
        row = db.session.get(TrustMeBankLink, user_id)
        if row is not None:
            db.session.delete(row)

    def create_oauth_state(self, user_id: uuid.UUID, state: str) -> None:
        now = datetime.now(UTC)
        db.session.add(
            TrustMeBankOAuthState(state=state, user_id=user_id, created_at=now)
        )
        db.session.flush()

    def consume_oauth_state(self, state: str) -> uuid.UUID | None:
        row = db.session.get(TrustMeBankOAuthState, state)
        if row is None:
            return None
        created_at = row.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if created_at < datetime.now(UTC) - _OAUTH_STATE_TTL:
            db.session.delete(row)
            return None
        user_id = row.user_id
        db.session.delete(row)
        return user_id

    def record_webhook_event(self, event_id: str) -> bool:
        """Insert the event id. Returns False if it was already recorded."""
        existing = db.session.get(TrustMeBankWebhookEvent, event_id)
        if existing is not None:
            return False
        db.session.add(
            TrustMeBankWebhookEvent(
                event_id=event_id, received_at=datetime.now(UTC)
            )
        )
        db.session.flush()
        return True
