"""Applicant-facing onboarding: which step is next, and what submit needs.

The wizard's order, the fields each step needs, and which statuses the
applicant may still edit are rows — see repositories/kyc_onboarding_repository.py.
This module walks that catalogue. PATCH still validates format in code: a
regex is not a row.

Countries, the jurisdictions RemitX operates in, and which identification each
country supports are rows too — `JurisdictionCatalogue`, handed in by the
controller. What an identification number must look like is a validator in
services/identity_validators.py, chosen by the scheme row.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal
from typing import Protocol

from remitx_api.errors.kyc import (
    IncompleteKycDeclarationError,
    UnsupportedJurisdictionError,
)
from remitx_api.models.orm.kyc_lifecycle import KycIdType, KycSourceOfFunds
from remitx_api.repositories.jurisdiction_repository import JurisdictionCatalogue
from remitx_api.repositories.kyc_onboarding_repository import (
    OnboardingCatalogue,
    OnboardingRequirement,
)
from remitx_api.services.identity_validators import (
    IDENTITY_VALIDATORS,
    IdentityFormatError,
)
from remitx_api.services.kyc_risk_rules import missing_risk_declarations

_COUNTRY_FIELDS = ("nationality", "issuing_country", "pep_country")
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class _Draft(Protocol):
    status: str
    source_of_funds: str | None
    declares_pep: bool
    id_type: str | None
    issuing_country: str | None


def stored_types(documents: Iterable) -> frozenset[str]:
    return frozenset(
        document.document_type
        for document in documents
        if getattr(document, "is_stored", False)
    )


def next_step(
    application: _Draft | None,
    document_types: Iterable[str],
    catalogue: OnboardingCatalogue,
    jurisdictions: JurisdictionCatalogue,
) -> str:
    """The first incomplete step, or the outcome step once the draft is sent."""
    if application is None:
        return catalogue.entry_step
    if application.status not in catalogue.editable_statuses:
        return catalogue.outcome_step

    types = frozenset(document_types)
    for step in catalogue.steps:
        if step.role in {"entry", "outcome"}:
            continue
        if step.role == "review":
            return step.step
        if not _step_complete(
            application,
            types,
            catalogue.requirements_for(step.step),
            jurisdictions,
        ):
            return step.step
    return catalogue.outcome_step


def missing_for_submit(
    application: _Draft,
    document_types: Iterable[str],
    catalogue: OnboardingCatalogue,
    jurisdictions: JurisdictionCatalogue,
) -> list[str]:
    types = frozenset(document_types)
    missing: list[str] = []
    for step in catalogue.steps:
        if step.role != "collect":
            continue
        missing.extend(
            _missing_on_step(
                application,
                types,
                catalogue.requirements_for(step.step),
                jurisdictions,
            )
        )
    missing.extend(missing_risk_declarations(application))
    seen: set[str] = set()
    unique: list[str] = []
    for field in missing:
        if field not in seen:
            seen.add(field)
            unique.append(field)
    return unique


def require_complete_for_submit(
    application: _Draft,
    document_types: Iterable[str],
    catalogue: OnboardingCatalogue,
    jurisdictions: JurisdictionCatalogue,
) -> None:
    missing = missing_for_submit(application, document_types, catalogue, jurisdictions)
    if missing:
        raise IncompleteKycDeclarationError(missing)


def normalize_patch(
    fields: Mapping[str, object], jurisdictions: JurisdictionCatalogue
) -> dict:
    """Validate only the keys present. Empty strings become null, so a field
    can be cleared the same way it is filled.

    Raises `UnsupportedJurisdictionError` for a residence RemitX does not
    operate in, and `ValueError` for anything else malformed."""
    changes: dict = {}
    for name, value in fields.items():
        if name in _COUNTRY_FIELDS:
            changes[name] = _as_country(value, jurisdictions)
        elif name == "residential_country":
            changes[name] = normalize_residence(value, jurisdictions)
        else:
            changes[name] = _PATCH_HANDLERS[name](value)
    return changes


def normalize_residence(
    value: object, jurisdictions: JurisdictionCatalogue
) -> str | None:
    """A known country code, upper-cased, where RemitX operates — or None."""
    code = _as_country(value, jurisdictions)
    require_supported_residence(code, jurisdictions)
    return code


def require_supported_residence(
    code: str | None, jurisdictions: JurisdictionCatalogue
) -> None:
    country = jurisdictions.country(code)
    if country is None or country.operates_in:
        return
    raise UnsupportedJurisdictionError(
        country.name,
        [operating.name for operating in jurisdictions.operating_countries],
    )


def validate_identification(
    *,
    id_type: str | None,
    issuing_country: str | None,
    id_number: str | None,
    date_of_birth: date | None,
    id_expiry_date: date | None,
    jurisdictions: JurisdictionCatalogue,
) -> str | None:
    """Check the identification once type, issuing country and number are all
    known, and return the number as its scheme normalises it. Until then there
    is nothing to check against, and the number comes back as given.

    Raises `ValueError` with an applicant-facing message about format only.
    """
    if _is_blank(id_number) or id_type is None or issuing_country is None:
        return id_number
    scheme = jurisdictions.resolve_scheme(issuing_country, id_type)
    if scheme is None:
        country = jurisdictions.country(issuing_country)
        name = country.name if country is not None else issuing_country
        raise ValueError(
            f"We don't accept a national ID issued by {name}. Use your passport "
            "instead."
        )
    try:
        number = IDENTITY_VALIDATORS[scheme.validator](str(id_number), date_of_birth)
    except IdentityFormatError as exc:
        raise ValueError(str(exc)) from exc
    if (
        scheme.requires_expiry
        and id_expiry_date is not None
        and not _is_future(id_expiry_date)
    ):
        raise ValueError("This passport has expired. Use a passport that is valid.")
    return number


def scheme_requires_expiry(
    application: object, jurisdictions: JurisdictionCatalogue
) -> bool:
    scheme = jurisdictions.resolve_scheme(
        getattr(application, "issuing_country", None),
        getattr(application, "id_type", None),
    )
    return scheme is not None and scheme.requires_expiry


def _is_future(value: date) -> bool:
    return value > date.today()


def _step_complete(
    application: object,
    types: frozenset[str],
    requirements: tuple[OnboardingRequirement, ...],
    jurisdictions: JurisdictionCatalogue,
) -> bool:
    return not _missing_on_step(application, types, requirements, jurisdictions)


def _missing_on_step(
    application: object,
    types: frozenset[str],
    requirements: tuple[OnboardingRequirement, ...],
    jurisdictions: JurisdictionCatalogue,
) -> list[str]:
    missing: list[str] = []
    for requirement in requirements:
        if not _requirement_applies(requirement, application, jurisdictions):
            continue
        if requirement.kind == "document":
            if requirement.name not in types:
                missing.append(requirement.name)
            continue
        if _is_blank(getattr(application, requirement.name, None)):
            missing.append(requirement.name)
    return missing


def _requirement_applies(
    requirement: OnboardingRequirement,
    application: object,
    jurisdictions: JurisdictionCatalogue,
) -> bool:
    when = requirement.required_when
    if when == "always":
        return True
    if when == "never":
        return False
    if when == "declares_pep":
        return bool(getattr(application, "declares_pep", False))
    if when == "source_of_funds_other":
        return (
            getattr(application, "source_of_funds", None)
            == KycSourceOfFunds.OTHER.value
        )
    if when == "id_requires_expiry":
        return scheme_requires_expiry(application, jurisdictions)
    return True


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Expected text")
    stripped = value.strip()
    return stripped or None


def _as_name(value: object) -> str | None:
    text = _as_optional_str(value)
    if text is None:
        return None
    if len(text) < 2:
        raise ValueError("Full legal name must be at least two characters")
    return text


def _as_country(value: object, jurisdictions: JurisdictionCatalogue) -> str | None:
    text = _as_optional_str(value)
    if text is None:
        return None
    code = text.upper()
    if jurisdictions.country(code) is None:
        raise ValueError(
            f"{text} is not a country we recognise. Choose one from the list."
        )
    return code


def _as_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError("Date of birth must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Date of birth must be YYYY-MM-DD") from exc
    if parsed > date.today():
        raise ValueError("Date of birth cannot be in the future")
    return parsed


def _as_expiry(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Expiry date must be YYYY-MM-DD") from exc
    else:
        raise ValueError("Expiry date must be YYYY-MM-DD")
    if not _is_future(parsed):
        raise ValueError("This passport has expired. Use a passport that is valid.")
    return parsed


def _as_id_type(value: object) -> str | None:
    text = _as_optional_str(value)
    if text is None:
        return None
    try:
        return KycIdType(text).value
    except ValueError as exc:
        raise ValueError("ID type must be national_id or passport") from exc


def _as_mobile(value: object) -> str | None:
    text = _as_optional_str(value)
    if text is None:
        return None
    if not _E164.fullmatch(text):
        raise ValueError(
            "Mobile number must be international format, for example +27821234567"
        )
    return text


def _as_email(value: object) -> str | None:
    text = _as_optional_str(value)
    if text is None:
        return None
    if not _EMAIL.fullmatch(text):
        raise ValueError("Email address format is invalid")
    return text


def _as_source_of_funds(value: object) -> str | None:
    text = _as_optional_str(value)
    if text is None:
        return None
    try:
        return KycSourceOfFunds(text).value
    except ValueError as exc:
        raise ValueError("Source of funds is not a recognised value") from exc


def _as_volume(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value))
    except Exception as exc:
        raise ValueError("Expected monthly volume must be a number") from exc
    if amount < 0:
        raise ValueError("Expected monthly volume cannot be negative")
    return amount


def _as_bool(value: object) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    raise ValueError("Expected true or false")


_PATCH_HANDLERS = {
    "full_name": _as_name,
    "date_of_birth": _as_date,
    "id_type": _as_id_type,
    "id_number": _as_optional_str,
    "id_expiry_date": _as_expiry,
    "mobile_number": _as_mobile,
    "email": _as_email,
    "source_of_funds": _as_source_of_funds,
    "source_of_funds_detail": _as_optional_str,
    "residential_line1": _as_optional_str,
    "residential_line2": _as_optional_str,
    "residential_city": _as_optional_str,
    "residential_postal_code": _as_optional_str,
    "expected_monthly_volume_zar": _as_volume,
    "is_domestic_prominent_influential_person": _as_bool,
    "is_foreign_prominent_public_official": _as_bool,
    "is_pep_family_or_close_associate": _as_bool,
    "pep_relationship": _as_optional_str,
    "pep_position": _as_optional_str,
    "pep_details": _as_optional_str,
    "source_of_wealth": _as_optional_str,
}
