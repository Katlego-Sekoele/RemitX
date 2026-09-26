from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer


class Schema(BaseModel):
    """Base for every request and response body.

    In a response, a field with a default is still always present, so the
    OpenAPI spec marks it required. Without this, ``processed_at: X | None =
    None`` reaches the generated client as optional *and* nullable. Request
    schemas are unaffected: FastAPI describes those in validation mode, where
    a default still makes a field optional.
    """

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


def _utc_isoformat(value: datetime) -> str:
    """Always emit an offset, whatever the backend stored.

    Postgres TIMESTAMPTZ round-trips as aware, but SQLite silently drops the
    offset, so the same row would serialize as "...T00:40:00" there and
    "...T00:40:00+00:00" in production. A JS client parses the offsetless form
    as *local* time, so the two differ by the viewer's UTC offset. Timestamps
    are written as UTC, so naive values are tagged as UTC here.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


# A type rather than a ``field_serializer`` so nullability stays on the field:
# ``UtcDateTime | None`` is described as a nullable string, ``UtcDateTime`` as
# a required one, instead of every field sharing one serializer's signature.
UtcDateTime = Annotated[datetime, PlainSerializer(_utc_isoformat, return_type=str)]


def _decimal_plain_str(value: Decimal) -> str:
    """Never emit scientific notation (e.g. ``0E-8`` from Numeric(20,8)).

    Pydantic's default ``Decimal`` JSON encoding uses ``str()``, which keeps
    Postgres/SQLAlchemy's exponent form and breaks the frontend's string money
    helpers.
    """
    return format(value, "f")


LedgerDecimal = Annotated[Decimal, PlainSerializer(_decimal_plain_str, return_type=str)]

# A money amount a client asks to move, bounded to what the ledger's
# Numeric(20,8) columns hold. Without the bound, an amount like 1e30
# overflows Decimal's 28-digit context when `round_amount` quantizes it to
# cents and surfaces as a 500 (InvalidOperation) instead of a refusal.
# Positive too, so zero and negative amounts never reach a service.
Amount = Annotated[Decimal, Field(gt=0, max_digits=20, decimal_places=8)]
