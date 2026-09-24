"""Who a synthetic person is: a coherent bundle of name, age, nationality,
home, work, money habits and identification.

Every field with a rule behind it (ID number, phone, dates) comes from the
rule-bound generators; everything else is drawn from the JSON data files. Two
people built from the same seed are the same two people.
"""

from __future__ import annotations

import random
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from remitx_seeder import data
from remitx_seeder.generators.identity import (
    passport_number,
    sa_id_number,
    us_ssn,
)
from remitx_seeder.generators.phones import mobile_number

ROLE_SENDER = "sender"
ROLE_RECIPIENT = "recipient"
ROLE_STAFF = "staff"

# The KYC tier 1 monthly limit in the migrations' seed (R25,000). A declared
# expected volume above it fires the `expected_volume_above_standard_limit`
# risk signal, which is what the generator uses it for.
STANDARD_MONTHLY_LIMIT_ZAR = Decimal("25000")


def weighted(rng: random.Random, weights: dict[str, float]) -> str:
    keys = list(weights)
    return rng.choices(keys, weights=[weights[key] for key in keys], k=1)[0]


def weighted_item(rng: random.Random, items: list[dict], key: str = "weight") -> dict:
    return rng.choices(items, weights=[item[key] for item in items], k=1)[0]


def fill(template: str, **values) -> str:
    return template.format(**values)


def email_local_part(first_name: str, last_name: str) -> str:
    raw = f"{first_name}.{last_name}".lower().replace(" ", "")
    ascii_only = (
        unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    )
    return "".join(ch for ch in ascii_only if ch.isalnum() or ch == ".")


@dataclass
class Address:
    line1: str
    line2: str | None
    city: str
    postal_code: str
    country: str
    suburb: str


@dataclass
class Identification:
    id_type: str  # national_id | passport
    issuing_country: str
    number: str
    expiry: date | None


@dataclass
class Persona:
    key: str
    role: str
    first_name: str
    last_name: str
    female: bool
    date_of_birth: date
    nationality: str
    culture: str
    mobile: str
    email_local: str
    residence: str | None = None
    address: Address | None = None
    occupation: str | None = None
    monthly_income_zar: int | None = None
    payday: str | None = None
    identification: Identification | None = None
    source_of_funds: str | None = None
    source_of_funds_detail: str | None = None
    expected_monthly_volume_zar: Decimal | None = None
    pep: dict | None = None
    source_of_wealth: str | None = None
    corridor: dict | None = None
    staff_role: str | None = None
    home_town: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def declares_pep(self) -> bool:
        return self.pep is not None


def _name(rng: random.Random, nationality: str) -> tuple[str, str, str, bool]:
    cultures = data.load("nationalities")[nationality]["cultures"]
    culture = weighted(rng, cultures)
    pool = data.load("names")["cultures"][culture]
    female = rng.random() < 0.5
    first = rng.choice(pool["female"] if female else pool["male"])
    last = rng.choice(pool["surnames"])
    return culture, first, last, female


def _birth_date(rng: random.Random, today: date, min_age: int, max_age: int) -> date:
    oldest = today - timedelta(days=365 * max_age)
    youngest = today - timedelta(days=365 * min_age)
    return oldest + timedelta(days=rng.randint(0, (youngest - oldest).days))


def _address(rng: random.Random, country: str) -> Address:
    spec = data.load("places")[country]
    city = weighted_item(rng, spec["cities"])
    suburb, postal_code = rng.choice(city["suburbs"])
    number = rng.randint(1, 480)
    line1 = f"{number} {rng.choice(spec['streets'])}"
    line2 = None
    if spec["unit_formats"] and rng.random() < 0.55:
        line2 = rng.choice(spec["unit_formats"]).format(
            n=rng.randint(1, 60),
            complex=rng.choice(spec["complexes"]) if spec["complexes"] else "",
            letter=rng.choice("ABCDEF"),
        )
    return Address(
        line1=line1,
        line2=f"{line2}, {suburb}" if line2 else suburb,
        city=city["city"],
        postal_code=postal_code,
        country=country,
        suburb=suburb,
    )


def _identification(
    rng: random.Random, nationality: str, persona_dob: date, female: bool, today: date
) -> Identification:
    if nationality == "ZA" and rng.random() < 0.9:
        return Identification(
            "national_id", "ZA", sa_id_number(rng, persona_dob, female=female), None
        )
    if nationality == "US" and rng.random() < 0.6:
        return Identification("national_id", "US", us_ssn(rng), None)
    pattern = data.load("nationalities")[nationality]["passport_pattern"]
    # Passports expire, so the expiry sits comfortably in the real future: a
    # seed run replays past days but the application is judged again today.
    expiry = today + timedelta(days=rng.randint(200, 3200))
    return Identification(
        "passport", nationality, passport_number(rng, pattern), expiry
    )


def _templates() -> dict:
    return data.load("templates")


def _home_town(rng: random.Random, nationality: str) -> str:
    return rng.choice(_templates()["home_towns"][nationality])


def build_sender(
    rng: random.Random,
    key: str,
    today: date,
    *,
    pep_rate: float,
    other_source_rate: float,
    high_volume_rate: float,
) -> Persona:
    corridor = weighted_item(rng, data.load("corridors")["corridors"])
    nationality = corridor["sender_nationality"]
    culture, first, last, female = _name(rng, nationality)
    dob = _birth_date(rng, today, 21, 58)
    occupation = weighted_item(rng, data.load("occupations")["occupations"])
    income = rng.randint(*occupation["income"])
    persona = Persona(
        key=key,
        role=ROLE_SENDER,
        first_name=first,
        last_name=last,
        female=female,
        date_of_birth=dob,
        nationality=nationality,
        culture=culture,
        mobile=mobile_number(rng, "ZA"),
        email_local=email_local_part(first, last),
        residence="ZA",
        address=_address(rng, "ZA"),
        occupation=occupation["title"],
        monthly_income_zar=income,
        payday=occupation["payday"],
        identification=_identification(rng, nationality, dob, female, today),
        source_of_funds=occupation["source_of_funds"],
        corridor=corridor,
        home_town=_home_town(rng, nationality),
    )
    low, high = corridor["monthly_send_zar"]
    volume = Decimal(rng.randint(low, high))
    if rng.random() < high_volume_rate:
        volume = STANDARD_MONTHLY_LIMIT_ZAR + Decimal(rng.randint(1000, 20000))
    persona.expected_monthly_volume_zar = volume.quantize(Decimal("1"))
    templates = _templates()
    if rng.random() < other_source_rate:
        persona.source_of_funds = "other"
        persona.source_of_funds_detail = fill(
            rng.choice(templates["source_of_funds_other"]),
            city=persona.address.city,
            suburb=persona.address.suburb,
        )
    if rng.random() < pep_rate:
        declare_pep(
            rng,
            persona,
            weighted(
                rng,
                {
                    "self": 20,
                    "immediate_family_member": 60,
                    "known_close_associate": 20,
                },
            ),
        )
    elif rng.random() < 0.15:
        declare_source_of_wealth(rng, persona)
    return persona


def declare_source_of_wealth(rng: random.Random, persona: Persona) -> None:
    persona.source_of_wealth = fill(
        rng.choice(_templates()["source_of_wealth"]),
        years=rng.randint(3, 20),
        occupation=(persona.occupation or "employee").lower(),
        home_town=persona.home_town,
    )


def declare_pep(rng: random.Random, persona: Persona, relationship: str) -> None:
    """Make `persona` declare a politically exposed connection. The position
    is a fictional office, never a real office holder."""
    templates = _templates()
    nationality = persona.nationality
    persona.pep = {
        "relationship": relationship,
        "position": fill(
            rng.choice(templates["pep_positions"][relationship]),
            city=persona.address.city if persona.address else "Johannesburg",
        ),
        "country": nationality,
        "details": fill(rng.choice(templates["pep_details"]), years=rng.randint(2, 9)),
        "domestic": relationship == "self" and nationality == "ZA",
        "foreign": relationship == "self" and nationality != "ZA",
        "family_or_associate": relationship != "self",
    }
    # Enhanced due diligence: a PEP must declare a source of wealth.
    declare_source_of_wealth(rng, persona)


def build_recipient(rng: random.Random, key: str, today: date, country: str) -> Persona:
    culture, first, last, female = _name(rng, country)
    dob = _birth_date(rng, today, 18, 78)
    persona = Persona(
        key=key,
        role=ROLE_RECIPIENT,
        first_name=first,
        last_name=last,
        female=female,
        date_of_birth=dob,
        nationality=country,
        culture=culture,
        mobile=mobile_number(rng, country),
        email_local=email_local_part(first, last),
        home_town=_home_town(rng, country),
    )
    if country in ("ZA", "US"):
        # Recipients who live where RemitX operates may verify too.
        persona.residence = country
        persona.address = _address(rng, country)
        persona.identification = _identification(rng, country, dob, female, today)
        persona.source_of_funds = rng.choice(["salary", "savings", "gift"])
        persona.expected_monthly_volume_zar = Decimal(rng.randint(0, 2000))
    return persona


def build_staff(rng: random.Random, key: str, today: date, role: str) -> Persona:
    culture, first, last, female = _name(rng, "ZA")
    return Persona(
        key=key,
        role=ROLE_STAFF,
        first_name=first,
        last_name=last,
        female=female,
        date_of_birth=_birth_date(rng, today, 24, 55),
        nationality="ZA",
        culture=culture,
        mobile=mobile_number(rng, "ZA"),
        email_local=email_local_part(first, last),
        staff_role=role,
    )
