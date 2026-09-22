import uuid

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR
from remitx_api.models.orm.user import User
from remitx_api.repositories.account_repository import AccountRepository

CREATE_ENDPOINT = "/beneficiaries/create-beneficiary"
LIST_ENDPOINT = "/beneficiaries/get-beneficiary-list"
LOOKUP_ENDPOINT = "/beneficiaries/lookup-by-reference"


def _provisioned_user(
    clerk_id: str, email: str | None, first_name: str
) -> tuple[uuid.UUID, str]:
    """Provision a user under its own DB session, outside of any request, and
    hand back (id, base_reference) — same pattern as test_deposits_route.py's
    `_seed_bank_account`. Must not call `create_app` again: that would
    re-init the shared `db` singleton's engine and orphan whatever
    `verified_client` already set up. Returning the ORM object itself would
    raise DetachedInstanceError on first attribute access once the session
    this function opened is closed.
    """
    token = db.open_session()
    try:
        user = UserController().ensure_provisioned(
            clerk_id, lambda: email, lambda: first_name
        )
        return user.id, user.base_reference
    finally:
        db.close_session(token)


def _provisioned_user_id(
    clerk_id: str, email: str | None, first_name: str
) -> uuid.UUID:
    return _provisioned_user(clerk_id, email, first_name)[0]


def test_anonymous_caller_is_rejected(anonymous_client):
    response = anonymous_client.get(LIST_ENDPOINT)

    assert response.status_code == 401


def test_list_rejects_an_invalid_sort_option(verified_client):
    client, _sender = verified_client

    response = client.get(LIST_ENDPOINT, params={"sort": "oldest"})

    assert response.status_code == 422


def test_lookup_by_fiat_account_reference_succeeds(verified_client):
    client, _sender = verified_client
    _linked_id, base_reference = _provisioned_user(
        "user_lookup_target", "lookup-target@example.com", "Lookup"
    )

    # The fiat (ZAR) reference — the same one they'd quote for an EFT
    # deposit — is what a sender is expected to have, not the tok reference.
    response = client.get(
        LOOKUP_ENDPOINT, params={"account_reference": f"{base_reference}-zar"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["first_name"] == "Lookup"


def test_lookup_by_fiat_account_reference_unknown_reference_is_404(verified_client):
    client, _sender = verified_client

    response = client.get(LOOKUP_ENDPOINT, params={"account_reference": "nobody-zar"})

    assert response.status_code == 404


def test_lookup_by_fiat_account_reference_rejects_the_token_account(verified_client):
    client, _sender = verified_client
    _linked_id, base_reference = _provisioned_user(
        "user_lookup_tok", "lookup-tok@example.com", "LookupTok"
    )

    # The uctusd account is real, but the lookup wants the fiat reference —
    # nobody would normally know to share this one.
    response = client.get(
        LOOKUP_ENDPOINT, params={"account_reference": f"{base_reference}-tok"}
    )

    assert response.status_code == 400


def test_lookup_by_fiat_account_reference_rejects_self(verified_client):
    client, sender = verified_client

    token = db.open_session()
    try:
        sender_zar_account = AccountRepository().get_user_account(
            sender.id, CURRENCY_ZAR
        )
        own_reference = sender_zar_account.reference
    finally:
        db.close_session(token)

    response = client.get(LOOKUP_ENDPOINT, params={"account_reference": own_reference})

    assert response.status_code == 400


def test_create_and_list_my_beneficiary(verified_client):
    client, _sender = verified_client
    linked_id = _provisioned_user_id(
        "user_beneficiary_target", "target@example.com", "Target"
    )

    response = client.post(
        CREATE_ENDPOINT,
        json={
            "linked_user_id": str(linked_id),
            "payout_currency": "ZWL",
            "relationship": "sibling",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["linked_user_id"] == str(linked_id)
    assert body["first_name"] == "Target"
    assert body["email"] == "target@example.com"
    # None of these are resolvable/settable on User yet (see
    # models/orm/user.py) — always None until a profile-editing flow exists.
    assert body["last_name"] is None
    assert body["mobile_number"] is None
    assert body["country"] is None

    listed = client.get(LIST_ENDPOINT)
    assert listed.status_code == 200
    [only] = listed.json()
    assert only["beneficiary_id"] == body["beneficiary_id"]


def test_create_requires_mobile_or_email(verified_client):
    client, _sender = verified_client
    # The linked user has no email on file, and mobile_number is never
    # resolvable yet (see models/orm/user.py) — neither is available.
    linked_id = _provisioned_user_id("user_beneficiary_no_contact", None, "NoContact")

    response = client.post(
        CREATE_ENDPOINT,
        json={
            "linked_user_id": str(linked_id),
            "payout_currency": "ZWL",
            "relationship": "friend",
        },
    )

    assert response.status_code == 422


def test_create_rejects_an_invalid_payout_currency(verified_client):
    client, _sender = verified_client
    linked_id = _provisioned_user_id(
        "user_beneficiary_bad_currency", "badcurrency@example.com", "Bad"
    )

    response = client.post(
        CREATE_ENDPOINT,
        json={
            "linked_user_id": str(linked_id),
            "payout_currency": "ZAR",  # sender-side currency, not a valid payout
            "relationship": "friend",
        },
    )

    assert response.status_code == 422


def test_create_rejects_an_invalid_relationship(verified_client):
    client, _sender = verified_client
    linked_id = _provisioned_user_id(
        "user_beneficiary_bad_relationship", "badrelationship@example.com", "Bad"
    )

    response = client.post(
        CREATE_ENDPOINT,
        json={
            "linked_user_id": str(linked_id),
            "payout_currency": "ZWL",
            "relationship": "acquaintance",  # not in RELATIONSHIPS
        },
    )

    assert response.status_code == 422


def test_create_rejects_unknown_linked_user(verified_client):
    client, _sender = verified_client

    response = client.post(
        CREATE_ENDPOINT,
        json={
            "linked_user_id": str(uuid.uuid4()),
            "payout_currency": "ZWL",
            "relationship": "friend",
        },
    )

    assert response.status_code == 400


def test_a_beneficiary_only_lists_for_its_owner(verified_client):
    client, sender = verified_client
    linked_id = _provisioned_user_id(
        "user_beneficiary_owned", "owned@example.com", "Owned"
    )
    client.post(
        CREATE_ENDPOINT,
        json={
            "linked_user_id": str(linked_id),
            "payout_currency": "NAD",
            "relationship": "parent",
        },
    )

    other_id = _provisioned_user_id(
        "user_beneficiary_other_owner", "otherowner@example.com", "Other"
    )
    other_sender = User(id=other_id)

    client.app.dependency_overrides[get_current_user] = lambda: other_sender
    try:
        response = client.get(LIST_ENDPOINT)
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: sender

    assert response.status_code == 200
    assert response.json() == []
