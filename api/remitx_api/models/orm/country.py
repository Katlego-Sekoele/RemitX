"""Every ISO 3166-1 country, and whether RemitX operates there.

Shared reference data rather than a KYC table: nationality, ID issuing country,
residence and PEP country point here today, and beneficiary country will.

`operates_in` is the jurisdiction gate. An applicant must live in a country
where it is true; nationality and a passport's issuing country may be anywhere.

Seeded from models/orm/country_seed.py.
"""

from sqlalchemy import Boolean, CheckConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


class Country(Base):
    __tablename__ = "countries"
    __table_args__ = (
        CheckConstraint(
            "length(code) = 2 AND code = upper(code)",
            name="countries_code_iso_alpha2",
        ),
    )

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    operates_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
