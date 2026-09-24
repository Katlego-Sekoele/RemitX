"""Identification numbers that pass the API's format validators.

`services/identity_validators.py` in the API decides what is acceptable; these
build numbers to that shape. Tests run every generator through the matching
validator, so a rule change there fails the seeder's tests rather than a seed
run halfway through QA.
"""

from __future__ import annotations

import random
import string
from datetime import date


def sa_id_check_digit(first_twelve: str) -> int:
    """The Department of Home Affairs check digit for 12 leading digits: the
    sum of the odd positions, plus the digit sum of twice the even-position
    concatenation, made up to a multiple of 10."""
    odds = sum(int(first_twelve[index]) for index in range(0, 12, 2))
    evens = int("".join(first_twelve[index] for index in range(1, 12, 2)))
    even_sum = sum(int(character) for character in str(evens * 2))
    return (10 - ((odds + even_sum) % 10)) % 10


def sa_id_number(
    rng: random.Random, date_of_birth: date, *, female: bool, citizen: bool = True
) -> str:
    """YYMMDD, four sequence digits (0000-4999 female, 5000-9999 male), the
    citizenship digit (0 citizen, 1 permanent resident), an 8, then the check
    digit."""
    sequence = rng.randint(0, 4999) if female else rng.randint(5000, 9999)
    first_twelve = f"{date_of_birth:%y%m%d}{sequence:04d}{0 if citizen else 1}8"
    return first_twelve + str(sa_id_check_digit(first_twelve))


def us_ssn(rng: random.Random) -> str:
    """Nine digits the SSA could have issued: area 001-665 or 667-899, group
    01-99, serial 0001-9999."""
    area = rng.choice([n for n in range(1, 900) if n != 666])
    return f"{area:03d}{rng.randint(1, 99):02d}{rng.randint(1, 9999):04d}"


def passport_number(rng: random.Random, pattern: str) -> str:
    """A number shaped by `pattern`: L is a letter, D a digit, anything else
    is literal (Namibia's leading P, for example)."""
    out = []
    for symbol in pattern:
        if symbol == "L":
            out.append(rng.choice(string.ascii_uppercase))
        elif symbol == "D":
            out.append(rng.choice(string.digits))
        else:
            out.append(symbol)
    return "".join(out)
