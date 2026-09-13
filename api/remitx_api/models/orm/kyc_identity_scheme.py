"""Which identification a country's applicants may use, and how its number is
checked.

`(country, id_type)` names a scheme; `country IS NULL` is the any-country
fallback, which exists for passports only — a national ID is accepted only
where a row says how to check its structure. The country-specific row wins
over the fallback, so a South African passport is held to its own format.

What a scheme's number *looks like* is code — a validator in
services/identity_validators.py, named by `validator`. Loading the catalogue
refuses a row naming a validator that does not exist. Everything an applicant
reads about the scheme (label, hints) is a column, so wording changes are an
UPDATE.

Seeded from models/orm/kyc_seed.py.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base
from remitx_api.models.orm.kyc_lifecycle import KycIdType, sql_value_list


class KycIdentityScheme(Base):
    __tablename__ = "kyc_identity_schemes"
    __table_args__ = (
        CheckConstraint(
            f"id_type IN ({sql_value_list(KycIdType)})",
            name="kyc_identity_schemes_id_type_valid",
        ),
        CheckConstraint(
            "input_mode IN ('numeric', 'text')",
            name="kyc_identity_schemes_input_mode_valid",
        ),
        UniqueConstraint(
            "country",
            "id_type",
            name="uq_kyc_identity_schemes_country_id_type",
        ),
        # A NULL country is distinct from every other NULL in a unique
        # constraint, so the "at most one fallback per type" rule needs its
        # own partial index.
        Index(
            "uq_kyc_identity_schemes_one_fallback_per_type",
            "id_type",
            unique=True,
            postgresql_where=text("country IS NULL"),
            sqlite_where=text("country IS NULL"),
        ),
    )

    scheme: Mapped[str] = mapped_column(Text, primary_key=True)
    country: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("countries.code", ondelete="RESTRICT"),
        nullable=True,
    )
    id_type: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    validator: Mapped[str] = mapped_column(Text, nullable=False)
    requires_expiry: Mapped[bool] = mapped_column(Boolean, nullable=False)
    input_mode: Mapped[str] = mapped_column(Text, nullable=False)
    number_hint: Mapped[str] = mapped_column(Text, nullable=False)
    document_hint: Mapped[str] = mapped_column(Text, nullable=False)
