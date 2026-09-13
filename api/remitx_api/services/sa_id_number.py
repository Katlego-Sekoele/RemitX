"""South African national ID *format* checks — not identity verification.

A well-formed number has 13 digits, an embedded date of birth, and a Luhn-style
check digit. Passing this means the digits are structurally valid. It does not
mean Home Affairs issued the number, or that it belongs to the applicant.
"""

from __future__ import annotations

from datetime import date

_ID_LENGTH = 13


class SaIdFormatError(ValueError):
    """The digits are not a well-formed South African ID number."""


def parse_sa_id_number(value: str) -> str:
    """Return the 13-digit number, or raise `SaIdFormatError`.

    The error message talks about format only. Callers must not rewrite it into
    a claim that the person is who they say they are.
    """
    digits = value.strip()
    if not digits.isdigit() or len(digits) != _ID_LENGTH:
        raise SaIdFormatError(
            "This ID number's format is invalid. It must be 13 digits."
        )
    try:
        _embedded_date_of_birth(digits)
    except ValueError as exc:
        raise SaIdFormatError(
            "This ID number's format is invalid. The first six digits are not "
            "a real date."
        ) from exc
    if not _checksum_ok(digits):
        raise SaIdFormatError(
            "This ID number's format is invalid. The check digit does not match."
        )
    return digits


def matches_declared_date_of_birth(digits: str, declared: date) -> bool:
    return _embedded_date_of_birth(parse_sa_id_number(digits)) == declared


def _embedded_date_of_birth(digits: str) -> date:
    year, month, day = int(digits[0:2]), int(digits[2:4]), int(digits[4:6])
    # YY is century-ambiguous. Prefer the date that makes the holder 0–120
    # years old today; the check is "is this a date", not "how old are you".
    today = date.today()
    candidates = []
    for century in (1900, 2000):
        try:
            candidates.append(date(century + year, month, day))
        except ValueError:
            continue
    if not candidates:
        raise ValueError("not a date")
    in_range = [
        candidate
        for candidate in candidates
        if 0 <= (today.year - candidate.year) <= 120
    ]
    if not in_range:
        return candidates[-1]
    return max(in_range)


def _checksum_ok(digits: str) -> bool:
    # DHA algorithm: sum of odd positions (1-indexed), plus the digit-sum of
    # twice the even-position concatenation; check digit makes the total a
    # multiple of 10.
    odds = sum(int(digits[index]) for index in range(0, 12, 2))
    evens = int("".join(digits[index] for index in range(1, 12, 2)))
    even_sum = sum(int(character) for character in str(evens * 2))
    total = odds + even_sum
    check = (10 - (total % 10)) % 10
    return check == int(digits[12])
