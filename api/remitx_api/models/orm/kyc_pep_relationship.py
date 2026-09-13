"""Catalogue of how an applicant can relate to a prominent person they declared.

Referenced by `kyc_applications.pep_relationship`. Seeded from
models/orm/kyc_seed.py in FICA's vocabulary (§21F-§21H), so the specification
can cite it.
"""

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


class KycPepRelationshipRecord(Base):
    __tablename__ = "kyc_pep_relationships"

    relationship: Mapped[str] = mapped_column(Text, primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
