import uuid

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.kyc_controller import KycController
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR
from remitx_api.models.orm.kyc_lifecycle import KycStatus
from remitx_api.models.orm.user import User
from remitx_api.repositories.account_repository import AccountRepository
from tests.kyc_helpers import insert_application, make_user

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


def _approved_user_id(
    clerk_id: str,
    first_name: str,
    *,
    full_name: str,
    country: str,
    email: str | None = None,
    mobile_number: str | None = None,
) -> uuid.UUID:
    """A provisioned user whose KYC application a reviewer approved through
    `KycController.transition`, the path that copies the verified name and
    country onto `users`."""
    user_id = _provisioned_user_id(clerk_id, email, first_name)
    token = db.open_session()
    try:
        if mobile_number is not None:
            db.session.get(User, user_id).mobile_number = mobile_number
            db.session.commit()
        application = insert_application(
            user_id,
            KycStatus.UNDER_REVIEW,
            full_name=full_name,
            residential_country=country,
        )
        KycController().transition(
            application.application_id,
            KycStatus.APPROVED,
            expected_version=1,
            actor_user_id=make_user().id,
        )
    finally:
        db.close_session(token)
    return user_id


def _add(client, linked_id: uuid.UUID, payout_currency: str = "ZWL") -> dict:
    response = client.post(
        CREATE_ENDPOINT,
        json={
            "linked_user_id": str(linked_id),
            "payout_currency": payout_currency,
            "relationship": "sibling",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


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
    assert body["display_name"] == "Lookup"
    assert body["account_currency"] == "ZAR"


def test_lookup_shows_a_short_verified_name_country_and_currency_only(
    verified_client,
):
    client, _sender = verified_client
    linked_id = _approved_user_id(
        "user_lookup_verified",
        "Tendai",
        full_name="Tendai Moyo",
        country="ZW",
        email="tendai.moyo@gmail.com",
        mobile_number="+263771234523",
    )
    token = db.open_session()
    try:
        user = db.session.get(User, linked_id)
        zwl = AccountRepository().get_or_create_user_account(
            user.id, user.base_reference, "ZWL"
        )
        db.session.commit()
        zwl_reference = zwl.reference
    finally:
        db.close_session(token)

    # Case and surrounding space in what the sender typed don't matter.
    response = client.get(
        LOOKUP_ENDPOINT, params={"account_reference": f" {zwl_reference.upper()} "}
    )

    assert response.status_code == 200
    assert response.json() == {
        "linked_user_id": str(linked_id),
        "first_name": "Tendai",
        "display_name": "Tendai M.",
        "country": "ZW",
        "country_name": "Zimbabwe",
        "account_currency": "ZWL",
    }
    # A reference is guessable, so the lookup must not become a directory.
    assert "tendai.moyo" not in response.text
    assert "771234523" not in response.text


def test_lookup_by_fiat_account_reference_unknown_reference_is_404(verified_client):
    client, _sender = verified_client

    response = client.get(LOOKUP_ENDPOINT, params={"account_reference": "nobody-zar"})

    assert response.status_code == 404
    assert response.json() == {"detail": "No RemitX account has that reference."}


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
    assert response.json()["detail"].startswith("That's a settlement reference.")


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
    assert response.json() == {"detail": "That's your own account."}


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
    # Not KYC-approved, so the Clerk first name stands in for the verified
    # name, and there is no verified country yet.
    assert body["full_name"] == "Target"
    assert body["country"] is None
    assert body["country_name"] is None
    assert body["masked_email"] == "t•••@example.com"
    assert body["masked_mobile_number"] is None

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

    # Well formed, but the linked person's own profile refuses it: 409, not
    # the 422 the client reads as a malformed request.
    assert response.status_code == 409
    assert "no email or mobile" in response.json()["detail"]


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


def test_an_approved_beneficiary_lists_with_their_verified_name_and_country(
    verified_client,
):
    client, _sender = verified_client
    linked_id = _approved_user_id(
        "user_beneficiary_verified",
        "Tendai",
        full_name="Tendai Moyo",
        country="ZW",
        email="tendai@example.com",
    )
    _add(client, linked_id)

    [row] = client.get(LIST_ENDPOINT).json()

    assert row["full_name"] == "Tendai Moyo"
    assert row["country"] == "ZW"
    assert row["country_name"] == "Zimbabwe"


def test_the_list_never_returns_a_beneficiarys_full_contact_details(
    verified_client,
):
    client, _sender = verified_client
    linked_id = _approved_user_id(
        "user_beneficiary_contact",
        "Tendai",
        full_name="Tendai Moyo",
        country="ZW",
        email="tendai.moyo@gmail.com",
        mobile_number="+263771234523",
    )
    _add(client, linked_id)

    response = client.get(LIST_ENDPOINT)

    assert "tendai.moyo@gmail.com" not in response.text
    assert "+263771234523" not in response.text
    [row] = response.json()
    assert row["masked_email"] == "t•••@gmail.com"
    assert row["masked_mobile_number"] == "+2637••••••23"
    assert "email" not in row
    assert "mobile_number" not in row


def test_alphabetical_sort_uses_the_verified_name(verified_client):
    client, _sender = verified_client
    # Signed up as "Zola" but verified as "Amahle Dube": sorts under A.
    verified_id = _approved_user_id(
        "user_beneficiary_sort_verified",
        "Zola",
        full_name="Amahle Dube",
        country="ZW",
        email="amahle@example.com",
    )
    unverified_id = _provisioned_user_id(
        "user_beneficiary_sort_unverified", "busi@example.com", "busi"
    )
    _add(client, verified_id)
    _add(client, unverified_id)

    newest = client.get(LIST_ENDPOINT, params={"sort": "newest"}).json()
    alphabetical = client.get(LIST_ENDPOINT, params={"sort": "alphabetical"}).json()

    assert [row["full_name"] for row in newest] == ["busi", "Amahle Dube"]
    assert [row["full_name"] for row in alphabetical] == ["Amahle Dube", "busi"]


def test_adding_the_same_person_twice_is_a_409(verified_client):
    client, _sender = verified_client
    linked_id = _provisioned_user_id(
        "user_beneficiary_duplicate", "duplicate@example.com", "Duplicate"
    )
    _add(client, linked_id, payout_currency="USD")

    response = client.post(
        CREATE_ENDPOINT,
        json={
            "linked_user_id": str(linked_id),
            "payout_currency": "NAD",
            "relationship": "friend",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Already in your beneficiaries"}
    [only] = client.get(LIST_ENDPOINT).json()
    assert only["payout_currency"] == "USD"


def test_two_senders_may_each_add_the_same_person(verified_client):
    client, sender = verified_client
    linked_id = _provisioned_user_id(
        "user_beneficiary_shared", "shared@example.com", "Shared"
    )
    _add(client, linked_id)

    other_id = _provisioned_user_id(
        "user_beneficiary_second_sender", "second@example.com", "Second"
    )
    client.app.dependency_overrides[get_current_user] = lambda: User(id=other_id)
    try:
        response = client.post(
            CREATE_ENDPOINT,
            json={
                "linked_user_id": str(linked_id),
                "payout_currency": "USD",
                "relationship": "friend",
            },
        )
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: sender

    assert response.status_code == 200
