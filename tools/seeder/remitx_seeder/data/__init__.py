"""The JSON files that make seeded data look lived-in. Edit them, not code, to
change who the synthetic people are and how they behave."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent

FILES = (
    "names.json",
    "nationalities.json",
    "places.json",
    "occupations.json",
    "corridors.json",
    "templates.json",
    "banks.json",
)


@cache
def load(name: str) -> dict:
    """One data file, parsed. `name` without the `.json` suffix."""
    return json.loads((DATA_DIR / f"{name}.json").read_text())
