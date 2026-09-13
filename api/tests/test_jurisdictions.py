"""Countries, the jurisdictions RemitX operates in, and scheme resolution — read
from rows, not from a list in code."""

from dataclasses import replace

import pytest
from remitx_api.errors.kyc import KycIdentitySchemesMisconfiguredError
from remitx_api.extensions import db
from remitx_api.models.orm.country import Country
from remitx_api.repositories.jurisdiction_repository import JurisdictionRepository
from sqlalchemy import update
from tests.kyc_helpers import seed_kyc_reference_data
from tests.rbac_helpers import make_user, rbac_client


def test_south_africa_and_the_united_states_are_the_operating_countries(
    app_context,
):
    seed_kyc_reference_data()

    catalogue = JurisdictionRepository().load()

    assert len(catalogue.countries) == 249
    assert {country.code for country in catalogue.operating_countries} == {
        "US",
        "ZA",
    }


@pytest.mark.parametrize(
    ("issuing_country", "id_type", "scheme"),
    [
        ("ZA", "national_id", "za_national_id"),
        ("US", "national_id", "us_national_id"),
        ("ZA", "passport", "za_passport"),
        ("US", "passport", "us_passport"),
        # Anyone else's passport falls back to the ICAO scheme...
        ("ZW", "passport", "passport"),
        # ...but there is no fallback national ID.
        ("ZW", "national_id", None),
        ("ZA", None, None),
    ],
)
def test_the_country_scheme_wins_and_only_passports_fall_back(
    app_context, issuing_country, id_type, scheme
):
    seed_kyc_reference_data()

    resolved = JurisdictionRepository().load().resolve_scheme(issuing_country, id_type)

    assert (None if resolved is None else resolved.scheme) == scheme


def test_opening_a_jurisdiction_is_an_update(app_context):
    seed_kyc_reference_data()
    db.session.execute(
        update(Country).where(Country.code == "NA").values(operates_in=True)
    )
    db.session.commit()

    catalogue = JurisdictionRepository().load()

    assert "NA" in {country.code for country in catalogue.operating_countries}


def test_a_scheme_naming_an_unknown_validator_is_refused(app_context):
    seed_kyc_reference_data()
    catalogue = JurisdictionRepository().load()
    broken = replace(catalogue.schemes[0], validator="no_such_validator")

    with pytest.raises(KycIdentitySchemesMisconfiguredError, match="no_such"):
        replace(catalogue, schemes=(broken, *catalogue.schemes[1:]))


def test_the_reference_endpoint_lists_countries_and_schemes():
    with rbac_client(make_user("reference")) as client:
        seed_kyc_reference_data()

        response = client.get("/kyc/reference")

    assert response.status_code == 200
    body = response.json()
    south_africa = next(c for c in body["countries"] if c["code"] == "ZA")
    assert south_africa == {
        "code": "ZA",
        "name": "South Africa",
        "operates_in": True,
    }
    ssn = next(s for s in body["identity_schemes"] if s["scheme"] == "us_national_id")
    assert ssn["label"] == "Social Security Number"
    assert ssn["requires_expiry"] is False
    assert "validator" not in ssn
