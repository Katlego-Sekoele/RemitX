"""E.164 mobile numbers shaped like each country's real ones."""

from __future__ import annotations

import random

from remitx_seeder import data


def mobile_number(rng: random.Random, nationality_or_country: str) -> str:
    spec = data.load("nationalities")[nationality_or_country]["mobile"]
    prefix = rng.choice(spec["prefixes"])
    fictional = spec.get("fictional_exchange")
    if fictional:
        # North America: area code, the fictional 555 exchange, then 01XX.
        return f"{spec['country_code']}{prefix}{fictional}01{rng.randint(0, 99):02d}"
    digits = "".join(str(rng.randint(0, 9)) for _ in range(spec["subscriber_digits"]))
    return f"{spec['country_code']}{prefix}{digits}"
