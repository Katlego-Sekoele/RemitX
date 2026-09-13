"""Identification number *format* checks, one per identity scheme — not identity
verification.

Each validator takes what the applicant typed and returns the number as it
should be stored, or raises `IdentityFormatError`. Passing means the characters
have the structure the issuer uses. It does not mean the number was issued, or
that it belongs to the applicant, and no message here may say otherwise.

A `kyc_identity_schemes` row names its validator by key in
`IDENTITY_VALIDATORS`; a new jurisdiction whose numbers look like an existing
scheme's reuses that key, and only a new format needs a function here.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date

from remitx_api.services.sa_id_number import (
    SaIdFormatError,
    matches_declared_date_of_birth,
    parse_sa_id_number,
)


class IdentityFormatError(ValueError):
    """The number does not have the structure its scheme requires."""


Validator = Callable[[str, date | None], str]

_SEPARATORS = re.compile(r"[\s-]")
_SSN = re.compile(r"^\d{9}$")
_LETTER_AND_EIGHT_DIGITS = re.compile(r"^[A-Z]\d{8}$")
_NINE_DIGITS = re.compile(r"^\d{9}$")
_ICAO_DOCUMENT_NUMBER = re.compile(r"^[A-Z0-9]{6,9}$")


def _compact(value: str) -> str:
    return _SEPARATORS.sub("", value).upper()


def validate_za_id(value: str, date_of_birth: date | None) -> str:
    """13 digits, a real embedded date, the DHA check digit — and, once a date
    of birth is declared, the embedded date must match it."""
    try:
        digits = parse_sa_id_number(value)
    except SaIdFormatError as exc:
        raise IdentityFormatError(str(exc)) from exc
    if date_of_birth is not None and not matches_declared_date_of_birth(
        digits, date_of_birth
    ):
        raise IdentityFormatError(
            "This ID number's format does not match the date of birth you "
            "entered. That is a consistency check on the digits, not a check "
            "that the number belongs to you."
        )
    return digits


def validate_us_ssn(value: str, _date_of_birth: date | None) -> str:
    """Nine digits in the SSA's area-group-serial structure. Area 000, 666 and
    900-999, group 00 and serial 0000 have never been issued (SSA, "Social
    Security Number Randomization")."""
    digits = _SEPARATORS.sub("", value)
    if not _SSN.fullmatch(digits):
        raise IdentityFormatError(
            "This Social Security Number's format is invalid. It must be 9 digits."
        )
    area, group, serial = digits[0:3], digits[3:5], digits[5:9]
    if area == "000" or area == "666" or area.startswith("9"):
        raise IdentityFormatError(
            "This Social Security Number's format is invalid. No number starts "
            f"with {area}."
        )
    if group == "00" or serial == "0000":
        raise IdentityFormatError(
            "This Social Security Number's format is invalid. The middle two or "
            "last four digits cannot all be zero."
        )
    return digits


def validate_us_passport(value: str, _date_of_birth: date | None) -> str:
    """9 digits (books before 2021), or one letter and 8 digits (Next
    Generation Passport, 2021 on — travel.state.gov, "Design and Security of
    our Documents")."""
    number = _compact(value)
    if not (
        _NINE_DIGITS.fullmatch(number) or _LETTER_AND_EIGHT_DIGITS.fullmatch(number)
    ):
        raise IdentityFormatError(
            "This passport number's format is invalid. A US passport number is "
            "9 digits, or one letter followed by 8 digits."
        )
    return number


def validate_za_passport(value: str, _date_of_birth: date | None) -> str:
    """One letter (A ordinary, M maxi, D diplomatic, T official) and 8 digits."""
    number = _compact(value)
    if not _LETTER_AND_EIGHT_DIGITS.fullmatch(number):
        raise IdentityFormatError(
            "This passport number's format is invalid. A South African passport "
            "number is one letter followed by 8 digits."
        )
    return number


def validate_icao_passport(value: str, _date_of_birth: date | None) -> str:
    """ICAO Doc 9303's document number field: at most 9 letters and digits.
    Issuers use 6 or more in practice."""
    number = _compact(value)
    if not _ICAO_DOCUMENT_NUMBER.fullmatch(number):
        raise IdentityFormatError(
            "This passport number's format is invalid. Enter the 6 to 9 letters "
            "and digits printed on the photo page."
        )
    return number


IDENTITY_VALIDATORS: dict[str, Validator] = {
    "za_id": validate_za_id,
    "us_ssn": validate_us_ssn,
    "us_passport": validate_us_passport,
    "za_passport": validate_za_passport,
    "icao_passport": validate_icao_passport,
}
