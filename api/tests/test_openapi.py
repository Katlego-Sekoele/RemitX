"""The OpenAPI spec is the frontend's contract: it has to be current, and
complete enough that the generated client reads well."""

import re
from collections import Counter

from remitx_api.app import create_app
from remitx_api.config import TestConfig
from remitx_api.openapi import SPEC_PATH, TAGS, render

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _operations():
    spec = create_app(TestConfig).openapi()
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method in HTTP_METHODS:
                yield f"{method.upper()} {path}", operation


def test_committed_spec_is_current():
    # The frontend client is generated from this file, so a stale one means
    # the client no longer matches the API. Regenerate it with:
    #   cd api && python scripts/export_openapi.py
    assert SPEC_PATH.read_text() == render(create_app(TestConfig))


def test_operation_ids_are_unique():
    # They become the client's function names; FastAPI only warns on a clash.
    counts = Counter(operation["operationId"] for _, operation in _operations())
    assert [name for name, count in counts.items() if count > 1] == []


def test_tags_are_dotted_identifiers():
    # The client nests operations by tag segment (``api.admin.users``), so
    # each segment has to be usable as a property name.
    for tag in TAGS:
        for segment in tag["name"].split("."):
            assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", segment), tag["name"]


def test_every_operation_has_one_declared_tag_and_a_summary():
    declared = {tag["name"] for tag in TAGS}
    for name, operation in _operations():
        assert len(operation.get("tags", [])) == 1, name
        assert operation["tags"][0] in declared, name
        assert operation.get("summary"), name


def test_authenticated_operations_declare_the_bearer_scheme():
    for name, operation in _operations():
        if name == "GET /health":
            assert "security" not in operation
        else:
            assert operation.get("security") == [{"ClerkSession": []}], name


def test_beneficiary_option_lists_are_named_enums():
    # The add and edit dialogs build their selects from these, so they have to
    # reach the generated client as values, not as free-form strings.
    schemas = create_app(TestConfig).openapi()["components"]["schemas"]
    assert schemas["PayoutCurrency"]["enum"] == ["USD", "ZWL", "NAD"]
    assert "sibling" in schemas["BeneficiaryRelationship"]["enum"]
