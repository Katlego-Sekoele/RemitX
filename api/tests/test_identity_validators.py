"""Identification number format checks, one table per scheme validator.

Every rejection message is about format. None may claim the number is not the
applicant's, or was never issued — nothing here could know.
"""

from datetime import date

import pytest
from remitx_api.services.identity_validators import (
    IDENTITY_VALIDATORS,
    IdentityFormatError,
    validate_icao_passport,
    validate_us_passport,
    validate_us_ssn,
    validate_za_id,
    validate_za_passport,
)

# Check digit valid, embedded date 1990-01-01.
VALID_SA_ID = "9001015000085"

ACCEPTED = [
    # (validator, typed, stored)
    (validate_za_id, VALID_SA_ID, VALID_SA_ID),
    (validate_za_id, f" {VALID_SA_ID} ", VALID_SA_ID),
    (validate_us_ssn, "123-45-6789", "123456789"),
    (validate_us_ssn, "123 45 6789", "123456789"),
    (validate_us_ssn, "123456789", "123456789"),
    (validate_us_ssn, "899-99-9999", "899999999"),
    (validate_us_passport, "123456789", "123456789"),
    (validate_us_passport, "a12345678", "A12345678"),
    (validate_za_passport, "A01234567", "A01234567"),
    (validate_za_passport, "m 1234 5678", "M12345678"),
    (validate_icao_passport, "ab123456", "AB123456"),
    (validate_icao_passport, "123456", "123456"),
    (validate_icao_passport, "X1234 5678", "X12345678"),
]

REJECTED = [
    # (case, validator, typed)
    ("SA ID too short", validate_za_id, "900101500008"),
    ("SA ID bad check digit", validate_za_id, "9001015000086"),
    ("SA ID not a date", validate_za_id, "9013015000085"),
    ("SSN too short", validate_us_ssn, "12345678"),
    ("SSN with letters", validate_us_ssn, "12345678A"),
    ("SSN area 000", validate_us_ssn, "000-12-3456"),
    ("SSN area 666", validate_us_ssn, "666-12-3456"),
    ("SSN area 9xx", validate_us_ssn, "900-12-3456"),
    ("SSN group 00", validate_us_ssn, "123-00-4567"),
    ("SSN serial 0000", validate_us_ssn, "123-45-0000"),
    ("US passport 8 digits", validate_us_passport, "12345678"),
    ("US passport two letters", validate_us_passport, "AB1234567"),
    ("ZA passport all digits", validate_za_passport, "123456789"),
    ("ZA passport 7 digits", validate_za_passport, "A1234567"),
    ("ICAO passport too short", validate_icao_passport, "12345"),
    ("ICAO passport too long", validate_icao_passport, "1234567890"),
    ("ICAO passport punctuation", validate_icao_passport, "AB12#456"),
]


@pytest.mark.parametrize(("validator", "typed", "stored"), ACCEPTED)
def test_a_well_formed_number_is_stored_normalised(validator, typed, stored):
    assert validator(typed, None) == stored


@pytest.mark.parametrize(
    ("validator", "typed"),
    [case[1:] for case in REJECTED],
    ids=[case[0] for case in REJECTED],
)
def test_a_malformed_number_is_refused_in_terms_of_format(validator, typed):
    with pytest.raises(IdentityFormatError) as raised:
        validator(typed, None)

    message = str(raised.value).lower()
    assert "format" in message
    assert "identity" not in message
    assert "belong" not in message


def test_an_sa_id_must_agree_with_the_declared_date_of_birth():
    assert validate_za_id(VALID_SA_ID, date(1990, 1, 1)) == VALID_SA_ID

    with pytest.raises(IdentityFormatError, match="date of birth"):
        validate_za_id(VALID_SA_ID, date(1991, 1, 1))


def test_an_ssn_carries_no_date_of_birth_to_check():
    assert validate_us_ssn("123-45-6789", date(1991, 1, 1)) == "123456789"


def test_every_seeded_scheme_names_a_registered_validator():
    from remitx_api.models.orm.kyc_seed import IDENTITY_SCHEME_SEEDS

    assert {seed.validator for seed in IDENTITY_SCHEME_SEEDS} <= set(
        IDENTITY_VALIDATORS
    )
