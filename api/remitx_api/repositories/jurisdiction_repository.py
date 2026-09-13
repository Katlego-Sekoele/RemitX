"""Read the countries RemitX knows, where it operates, and the identity schemes
each country supports.

Rows in, a frozen `JurisdictionCatalogue` out, so the onboarding service stays
a pure function of what it is handed — the same bridge
`KycOnboardingRepository` is for the wizard catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from remitx_api.errors.kyc import KycIdentitySchemesMisconfiguredError
from remitx_api.extensions import db
from remitx_api.models.orm.country import Country as CountryRecord
from remitx_api.models.orm.kyc_identity_scheme import KycIdentityScheme
from remitx_api.services.identity_validators import IDENTITY_VALIDATORS


@dataclass(frozen=True, slots=True)
class Country:
    code: str
    name: str
    operates_in: bool


@dataclass(frozen=True, slots=True)
class IdentityScheme:
    scheme: str
    country: str | None
    id_type: str
    label: str
    validator: str
    requires_expiry: bool
    input_mode: str
    number_hint: str
    document_hint: str


@dataclass(frozen=True, slots=True)
class JurisdictionCatalogue:
    countries: tuple[Country, ...]
    schemes: tuple[IdentityScheme, ...]

    def __post_init__(self) -> None:
        unknown = sorted(
            {scheme.validator for scheme in self.schemes} - set(IDENTITY_VALIDATORS)
        )
        if unknown:
            raise KycIdentitySchemesMisconfiguredError(
                "kyc_identity_schemes rows name validators that do not exist in "
                f"services/identity_validators.py: {', '.join(unknown)}"
            )

    def country(self, code: str | None) -> Country | None:
        if code is None:
            return None
        for country in self.countries:
            if country.code == code:
                return country
        return None

    @property
    def operating_countries(self) -> tuple[Country, ...]:
        return tuple(country for country in self.countries if country.operates_in)

    def resolve_scheme(
        self, issuing_country: str | None, id_type: str | None
    ) -> IdentityScheme | None:
        """The issuing country's own scheme for this type, else the
        any-country fallback, else None."""
        if id_type is None:
            return None
        fallback = None
        for scheme in self.schemes:
            if scheme.id_type != id_type:
                continue
            if scheme.country is not None and scheme.country == issuing_country:
                return scheme
            if scheme.country is None:
                fallback = scheme
        return fallback


class JurisdictionRepository:
    def load(self) -> JurisdictionCatalogue:
        countries = tuple(
            Country(code=row.code, name=row.name, operates_in=row.operates_in)
            for row in db.session.scalars(
                select(CountryRecord).order_by(CountryRecord.name)
            ).all()
        )
        if not countries:
            raise RuntimeError("countries is empty; seed the country reference data")
        schemes = tuple(
            IdentityScheme(
                scheme=row.scheme,
                country=row.country,
                id_type=row.id_type,
                label=row.label,
                validator=row.validator,
                requires_expiry=row.requires_expiry,
                input_mode=row.input_mode,
                number_hint=row.number_hint,
                document_hint=row.document_hint,
            )
            for row in db.session.scalars(
                select(KycIdentityScheme).order_by(KycIdentityScheme.scheme)
            ).all()
        )
        return JurisdictionCatalogue(countries=countries, schemes=schemes)
