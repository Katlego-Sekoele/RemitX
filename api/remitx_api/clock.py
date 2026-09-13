"""The one clock the API and worker read.

Timezone-aware UTC, always. Set in Python rather than by the database: SQLite's
CURRENT_TIMESTAMP has only second precision, which is too coarse to order rapid
inserts, and a naive `datetime.now()` is the bug every timestamp column here
exists to avoid.
"""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)
