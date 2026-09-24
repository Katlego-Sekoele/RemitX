"""Generated values must pass the API's own validators: they are the judge."""

import random
import re
from datetime import date

import pytest
from remitx_api.services.file_signatures import sniff_content_type
from remitx_api.services.identity_validators import IDENTITY_VALIDATORS

from remitx_seeder import data
from remitx_seeder.generators.documents import identity_document, proof_of_address
from remitx_seeder.generators.identity import sa_id_number
from remitx_seeder.generators.personas import (
    build_recipient,
    build_sender,
    build_staff,
    declare_pep,
)
from remitx_seeder.generators.phones import mobile_number

E164 = re.compile(r"^\+[1-9]\d{7,14}$")
TODAY = date.today()


def validator_for(ident) -> str:
    return {
        ("national_id", "ZA"): "za_id",
        ("national_id", "US"): "us_ssn",
        ("passport", "ZA"): "za_passport",
        ("passport", "US"): "us_passport",
    }.get((ident.id_type, ident.issuing_country), "icao_passport")


def senders(n: int, seed: int = 1, **rates):
    rng = random.Random(seed)
    defaults = {"pep_rate": 0.05, "other_source_rate": 0.05, "high_volume_rate": 0.05}
    return [
        build_sender(rng, f"s{i}", TODAY, **{**defaults, **rates}) for i in range(n)
    ]


def test_every_generated_identification_passes_the_api_validator():
    people = senders(1500)
    rng = random.Random(2)
    for country in ("ZA", "US"):
        people += [build_recipient(rng, f"r{i}", TODAY, country) for i in range(300)]
    for person in people:
        ident = person.identification
        normalised = IDENTITY_VALIDATORS[validator_for(ident)](
            ident.number, person.date_of_birth
        )
        assert normalised == ident.number


def test_sa_id_numbers_carry_sex_and_citizenship():
    rng = random.Random(3)
    born = date(1991, 4, 17)
    female = sa_id_number(rng, born, female=True)
    male = sa_id_number(rng, born, female=False)
    resident = sa_id_number(rng, born, female=True, citizen=False)
    assert female.startswith("910417") and int(female[6:10]) < 5000
    assert int(male[6:10]) >= 5000
    assert female[10] == "0" and resident[10] == "1"


@pytest.mark.parametrize("country", ["ZA", "ZW", "NA", "US"])
def test_mobile_numbers_are_e164(country):
    rng = random.Random(4)
    for _ in range(200):
        assert E164.fullmatch(mobile_number(rng, country))


def test_us_numbers_stay_in_the_fictional_range():
    rng = random.Random(5)
    for _ in range(50):
        assert mobile_number(rng, "US")[5:10] == "55501"


def test_a_pep_always_declares_what_submission_requires():
    rng = random.Random(6)
    for person in senders(40):
        declare_pep(rng, person, "known_close_associate")
        assert person.pep["position"] and person.pep["country"]
        assert person.source_of_wealth
        assert person.pep["family_or_associate"]


def test_senders_live_in_sa_and_follow_their_corridor():
    for person in senders(300):
        assert person.residence == "ZA" and person.address.country == "ZA"
        assert person.nationality == person.corridor["sender_nationality"]
        if person.nationality != "ZA":
            assert person.identification.id_type == "passport"
            assert person.identification.expiry > TODAY


def test_names_come_from_the_nationality_s_cultures():
    cultures = data.load("nationalities")
    for person in senders(200):
        assert person.culture in cultures[person.nationality]["cultures"]


def test_recipients_abroad_have_no_address_and_cannot_verify():
    rng = random.Random(7)
    for country in ("ZW", "NA"):
        person = build_recipient(rng, "r", TODAY, country)
        assert person.residence is None and person.identification is None


def test_the_same_seed_builds_the_same_people():
    assert [p.full_name for p in senders(20, seed=9)] == [
        p.full_name for p in senders(20, seed=9)
    ]


def test_documents_are_accepted_uploads_and_unique():
    rng = random.Random(8)
    person = senders(1)[0]
    bodies = set()
    for _ in range(4):
        for document in (
            identity_document(rng, person),
            identity_document(rng, person, blurry=True),
            proof_of_address(rng, person, TODAY),
        ):
            assert sniff_content_type(document.body[:512]) == document.content_type
            assert len(document.body) < 10 * 1024 * 1024
            bodies.add(document.body)
    assert len(bodies) == 12


def test_staff_have_the_role_they_were_built_for():
    staff = build_staff(random.Random(1), "staff1", TODAY, "compliance_officer")
    assert staff.role == "staff" and staff.staff_role == "compliance_officer"
